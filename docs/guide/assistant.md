# The Assistant

**View → Show Assistant** opens a chat docked on the right, tabbed with the
Scripts panel and the Book. You describe what you want built; it writes a
Prism script.

## It writes scripts; you run them

The assistant **cannot touch the canvas**. Everything it produces arrives as
a script in a fenced block, and **Send Script to Editor** puts that script in
the Scripts panel, where you read it, edit it, and press Run — or don't.

That is the whole safety story, and it is why there are no approval dialogs
here. Nothing happens to your drawing that you did not read first, and what
arrives is the same kind of thing you write yourself: a script, in the same
language, which you can keep, change and replay.

```
you     how do I make a vanishing point?

claude  A vanishing point is just a point on the horizon with a pencil
        pinned through it. Label it first so the ids stay put.

        ```prism
        ; horizon, then a vanishing point with six rays
        (add horizon 1/3)
        (label (point L1 1/3) "V")
        (add-pencil V 6)
        ```
```

## It knows the language, and it knows your canvas

The command reference it works from is **read off the console** at the start
of every conversation, from `(help)` — so it cannot fall behind the commands
that actually exist. A form it doesn't find there, it won't write.

What is currently on the canvas goes with each question, from `(ls)`. So
"add a vanishing point to that horizon" means the horizon you drew, and the
ids it writes are the ids you have.

## Talking to it

| | |
|---|---|
| **Enter** | Send |
| **Shift+Enter** | A new line in the question |
| **Stop** | Give up on a reply being written; the turn is dropped rather than half-kept |
| **Send Script to Editor** | Append the last reply's script to the Scripts panel |
| **New Chat** | Forget the conversation. The canvas is untouched |

It is a conversation, so "now make it denser" follows on from what came
before. The line under the buttons shows what each turn cost in tokens.

## Reading it

Prose is set in a book serif and scripts in a monospace face, because the
panel holds two kinds of writing at once and one font cannot serve both —
prose wants to be read, a script wants its columns. The faces are the first
available of a short list at the top of `prism/agent_panel.py`, so changing
them is a one-line edit.

## Choosing a model

The **Model** box lists what you can actually use. It re-asks each time you
open it, so starting Ollama or pulling a model does not mean restarting
Prism.

### Ollama — no account, nothing leaves the machine

If [Ollama](https://ollama.com) is running, its models are listed first and
one is picked by default. There is nothing to set up beyond Ollama itself:

```bash
ollama serve
ollama pull llama3.2
```

Set `OLLAMA_HOST` if it listens somewhere other than `localhost:11434`.

Local models are small, and it shows — expect to correct them more than you
would Claude, and expect plain questions to go better than elaborate
constructions. That is survivable here precisely because the assistant
writes a script for you to read rather than driving the canvas itself.

### Claude — better at it, needs a key

Prism **never stores your API key**. It is read from the environment by
Anthropic's own library, so set it where Prism starts:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

An `ant auth login` profile works too, with no environment variable at all.
Each turn sends the command reference, which is long; it is marked for
[prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching),
so after the first turn most of it comes from cache at a fraction of the
price. The status line shows the token counts either way.

With neither available the assistant says so, and the rest of Prism is
unaffected — it is a panel, not a dependency.

## It checks its own work

Prism knows exactly which commands exist, so before a script is offered it
is **read against the real command table**. A line that names a form Prism
hasn't got, or that doesn't parse, is called out:

```
  — that script won't all run:
      line 1: there is no (add-horizon …)
```

It is said, not blocked — the script is still yours to keep, fix or throw
away. This is worth most with a local model, which will cheerfully invent
`(add-horizon …)` where Prism has `(add horizon …)`, and write a perfectly
confident paragraph explaining it.
