"""Where the assistant's replies come from.

One backend today, Claude. The seam is the **turn** rather than the message,
so a second one — a local model, say — slots in by implementing
:meth:`ClaudeBackend.stream_turn` and nothing else has to know.
"""

import os
from typing import Callable

#: The model used unless one is chosen in Settings.
DEFAULT_MODEL = "claude-opus-5-5"

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
