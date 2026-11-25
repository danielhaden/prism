"""Where the assistant's replies come from.

Two backends: **Ollama**, which runs a model on this machine and needs no
account, and **Claude**, which is better at it and needs an API key. The
seam is the *turn* — ``stream_turn(system, messages, …)`` — so neither the
panel nor the prompt knows which is answering.

Mode A asks for no tools, which is what makes a small local model usable at
all: it has to write text in a fenced block, not drive an agent loop.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Callable

#: The Claude model used unless another is chosen.
DEFAULT_MODEL = "claude-opus-5-5"

#: Claude models worth offering in the picker.
CLAUDE_MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")

#: Where Ollama listens unless ``OLLAMA_HOST`` says otherwise.
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

#: Enough for a long explanation and a script; the request streams, so a
#: generous ceiling costs nothing but room.
MAX_TOKENS = 16000


class AgentError(Exception):
    """Something went wrong talking to the model, phrased for the panel."""


class ClaudeBackend:
    """Claude, through the official SDK.

    The API key is **not** stored by Prism. It is read from the environment
    by the SDK itself, which also picks up an ``ant auth login`` profile —
    so there is nothing of yours in Prism's settings file to leak.
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Args:
            model: The model id to send to.
        """
        self.model = model or DEFAULT_MODEL
        self._client = None

    @staticmethod
    def looks_configured() -> bool:
        """Whether a key is in the environment.

        False does not mean it won't work — an ``ant auth login`` profile is
        picked up without one — so this only decides whether to show a hint,
        never whether to let someone try.

        Returns:
            Whether an API key or auth token is set.
        """
        return bool(
            os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        )

    def client(self) -> object:
        """The SDK client, made on first use.

        Returns:
            The client.

        Raises:
            AgentError: If the SDK isn't installed.
        """
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AgentError(
                    "The anthropic package isn't installed. "
                    "pip install -r requirements.txt"
                ) from exc
            self._client = anthropic.Anthropic()
        return self._client

    def request_kwargs(self, system: str, messages: list) -> dict:
        """The request, as a dict, so it can be read without being sent.

        Args:
            system: The standing instructions.
            messages: The conversation so far.

        Returns:
            Keyword arguments for ``messages.stream``.
        """
        return {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            # One block with a cache breakpoint: the instructions and the
            # command reference don't change between turns, and the canvas
            # state that does is sent in the turn instead.
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": list(messages),
            # Summarised rather than hidden: without it a long think is a
            # silent pause in a chat window, which reads as a hang.
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "medium"},
        }

    def stream_turn(
        self,
        system: str,
        messages: list,
        on_text: Callable,
        on_thinking: Callable,
        cancelled: Callable,
    ) -> dict:
        """Take one turn, handing text back as it arrives.

        Args:
            system: The standing instructions.
            messages: The conversation so far, ending with the person's turn.
            on_text: Called with each chunk of the reply.
            on_thinking: Called with each chunk of the reasoning summary.
            cancelled: Called between chunks; stop when it returns True.

        Returns:
            ``{"text": …, "usage": {…}}`` — what was said, and what it cost.

        Raises:
            AgentError: With a message worth showing, for any failure.
        """
        import anthropic

        spoken: list[str] = []
        usage: dict = {}
        try:
            with self.client().messages.stream(
                **self.request_kwargs(system, messages)
            ) as stream:
                for event in stream:
                    if cancelled():
                        stream.close()
                        break
                    if event.type != "content_block_delta":
                        continue
                    delta = event.delta
                    if delta.type == "text_delta":
                        spoken.append(delta.text)
                        on_text(delta.text)
                    elif delta.type == "thinking_delta":
                        on_thinking(delta.thinking)
                if not cancelled():
                    final = stream.get_final_message()
                    usage = _usage_of(final)
                    if final.stop_reason == "refusal":
                        raise AgentError(
                            "Claude declined to answer that one."
                        )
        except AgentError:
            raise
        except anthropic.AuthenticationError as exc:
            raise AgentError(
                "Claude didn't accept the credentials. Set ANTHROPIC_API_KEY "
                "in the environment Prism starts in, or run `ant auth login`."
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AgentError("Rate limited — give it a moment.") from exc
        except anthropic.APIStatusError as exc:
            raise AgentError(f"Claude returned {exc.status_code}.") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentError("Couldn't reach Claude — check the network.") from exc
        return {"text": "".join(spoken), "usage": usage}


def _usage_of(message: object) -> dict:
    """Token counts from a finished message, as plain numbers.

    Args:
        message: The final message.

    Returns:
        Input, output and cached token counts.
    """
    counts = getattr(message, "usage", None)
    if counts is None:
        return {}
    return {
        "input": getattr(counts, "input_tokens", 0) or 0,
        "output": getattr(counts, "output_tokens", 0) or 0,
        "cached": getattr(counts, "cache_read_input_tokens", 0) or 0,
    }


def ollama_host() -> str:
    """Where to find Ollama.

    Returns:
        ``OLLAMA_HOST`` if set — the same variable Ollama's own tools read —
            otherwise the default port on this machine.
    """
    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return DEFAULT_OLLAMA_HOST
    if not host.startswith("http"):
        host = "http://" + host
    return host.rstrip("/")


def ollama_models(host: str = "", timeout: float = 1.5) -> list:
    """What Ollama has pulled on this machine.

    Asked rather than guessed: which models are here is the user's business,
    and a picker offering one they haven't pulled is worse than an empty one.

    Args:
        host: Where Ollama listens; the default when empty.
        timeout: How long to wait before deciding it isn't running.

    Returns:
        Model names, sorted. Empty when Ollama isn't reachable — which is
            not an error, just an answer.
    """
    url = (host or ollama_host()) + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return []
    names = [
        str(entry.get("name"))
        for entry in payload.get("models", [])
        if isinstance(entry, dict) and entry.get("name")
    ]
    return sorted(names)


class OllamaBackend:
    """A model running on this machine, through Ollama's chat endpoint.

    No account, no key, no bill, and nothing leaves the machine. The models
    are small, so expect to correct it more than you would Claude — which
    is exactly why the assistant writes scripts for you to read rather than
    driving the canvas itself.
    """

    #: Asked for explicitly: Ollama's own default context is small, and the
    #: command reference alone would be cut off in it — leaving the model
    #: guessing at a language it was never shown.
    CONTEXT_TOKENS = 8192

    #: Low, because the job is writing a script in a fixed language rather
    #: than being interesting.
    TEMPERATURE = 0.3

    def __init__(self, model: str, host: str = ""):
        """
        Args:
            model: The Ollama model name, e.g. ``llama3.2:latest``.
            host: Where Ollama listens; the default when empty.
        """
        self.model = model
        self.host = (host or ollama_host()).rstrip("/")

    def looks_configured(self) -> bool:
        """Whether Ollama is answering and has this model."""
        return self.model in ollama_models(self.host)

    def request_body(self, system: str, messages: list) -> dict:
        """The request, as a dict, so it can be read without being sent.

        Ollama takes the standing instructions as the first **message**
        rather than as a field of its own.

        Args:
            system: The standing instructions.
            messages: The conversation so far.

        Returns:
            The JSON body.
        """
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + list(messages),
            "stream": True,
            "options": {
                "num_ctx": self.CONTEXT_TOKENS,
                "temperature": self.TEMPERATURE,
            },
        }

    def stream_turn(
        self,
        system: str,
        messages: list,
        on_text: Callable,
        on_thinking: Callable,
        cancelled: Callable,
    ) -> dict:
        """Take one turn against the local model.

        Args:
            system: The standing instructions.
            messages: The conversation so far.
            on_text: Called with each chunk of the reply.
            on_thinking: Unused; local models report no reasoning here.
            cancelled: Called between chunks; stop when it returns True.

        Returns:
            ``{"text": …, "usage": {…}}``.

        Raises:
            AgentError: With a message worth showing, for any failure.
        """
        body = json.dumps(self.request_body(system, messages)).encode("utf-8")
        request = urllib.request.Request(
            self.host + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        spoken: list[str] = []
        usage: dict = {}
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                for line in response:
                    if cancelled():
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except ValueError:
                        continue  # a half-written line; the next one follows
                    if chunk.get("error"):
                        raise AgentError(str(chunk["error"]))
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        spoken.append(piece)
                        on_text(piece)
                    if chunk.get("done"):
                        usage = {
                            "input": chunk.get("prompt_eval_count", 0) or 0,
                            "output": chunk.get("eval_count", 0) or 0,
                            "cached": 0,
                        }
        except AgentError:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise AgentError(
                    f"Ollama hasn't got {self.model}. Pull it first: "
                    f"ollama pull {self.model}"
                ) from exc
            raise AgentError(f"Ollama returned {exc.code}.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise AgentError(
                f"Couldn't reach Ollama at {self.host}. Is it running? "
                "Start it with `ollama serve`."
            ) from exc
        return {"text": "".join(spoken), "usage": usage}
