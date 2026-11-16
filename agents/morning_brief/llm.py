"""
The one way this agent talks to a model: ask for a tool call, get its JSON back.

Both the writer and the tone judge return structured answers by "calling" a
tool whose input_schema is the shape we want. Some models reject a forced
tool_choice, so we offer the tool, nudge once if the reply comes back as
prose, and fail loudly if the output was cut off at max_tokens (which
otherwise yields silently incomplete JSON, as the first live run showed).
"""

from __future__ import annotations

from typing import Any


def call_tool(client: Any, *, model: str, system: str, messages: list[dict],
              tool: dict, max_tokens: int) -> tuple[dict, dict[str, int]]:
    """Return (tool_input, usage). Usage sums every request made."""
    usage = {"input_tokens": 0, "output_tokens": 0}
    for _ in range(2):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "auto"},
            messages=messages,
        )
        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        call = next((b for b in response.content if b.type == "tool_use"), None)
        if call is not None:
            if response.stop_reason == "max_tokens":
                raise RuntimeError(f"{tool['name']} hit max_tokens ({max_tokens}); raise the limit.")
            return call.input, usage
        messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": f"Answer with the {tool['name']} tool, not as plain text."},
        ]
    raise RuntimeError(f"The model never called {tool['name']}.")


def default_client() -> Any:
    import anthropic   # imported lazily so tests and dry runs need no key
    return anthropic.Anthropic()
