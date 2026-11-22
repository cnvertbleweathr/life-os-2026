"""
The one way this agent talks to a model: ask for a tool call, get its JSON back.

Both the writer and the tone judge return structured answers by "calling" a
tool whose input_schema is the shape we want. Claude 5.5 models reject a forced
tool_choice, so we offer the tool, nudge once if the reply comes back as
prose, and fail loudly if the output was cut off at max_tokens (which
otherwise yields silently incomplete JSON, as the first live run showed).

Every call is logged to data/ai/generations.jsonl in the OpenClaw shape
(openclaw/audit.py) with its cost, and shares OpenClaw's monthly budget
(openclaw/config.py): a call is refused once this month's logged spend reaches it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.store import JsonlLog, now_local

GENERATIONS_LOG = JsonlLog("ai", "generations.jsonl")
MONTHLY_BUDGET_USD = 5.00   # shared with OpenClaw and the film scripts (openclaw/config.py)

# $ per million tokens (Claude API list prices, Nov 2026). Thinking tokens bill as output.
PRICE_PER_MTOK = {
    "claude-haiku-5-5":  {"input": 0.10, "output": 0.50},   # prompts up to 100K tokens
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5":   {"input": 4.00, "output": 20.00},
}


class BudgetExceeded(RuntimeError):
    pass


def cost_usd(model: str, usage: dict[str, int]) -> float:
    price = PRICE_PER_MTOK.get(model)
    if price is None:
        return 0.0
    return round(usage.get("input_tokens", 0) / 1e6 * price["input"]
                 + usage.get("output_tokens", 0) / 1e6 * price["output"], 6)


def month_spend(now: datetime | None = None) -> float:
    month = (now or now_local()).strftime("%Y-%m")
    return round(sum(float(r.get("cost_usd") or 0) for r in GENERATIONS_LOG.rows()
                     if str(r.get("timestamp", "")).startswith(month)), 6)


def log_generation(*, analyzer: str, model: str, usage: dict[str, int], status: str = "success",
                   error: str | None = None, tables_read: list[str] | None = None) -> dict[str, Any]:
    return GENERATIONS_LOG.append({
        "timestamp": now_local().isoformat(),
        "analyzer_name": analyzer,
        "capability_used": "generate_text",
        "model": model,
        "tables_read": tables_read or [],
        "tables_written": [],
        "tokens_input": usage.get("input_tokens", 0),
        "tokens_output": usage.get("output_tokens", 0),
        "cost_usd": cost_usd(model, usage),
        "policy_enforced": True,
        "status": status,
        "error_message": error,
    })


def call_tool(client: Any, *, model: str, system: str, messages: list[dict],
              tool: dict, max_tokens: int, effort: str | None = None,
              analyzer: str | None = None, tables_read: list[str] | None = None,
              ) -> tuple[dict, dict[str, int]]:
    """Return (tool_input, usage). Usage sums every request made.

    With `analyzer` set, the call is budget-checked first and logged after
    (success or failure) to generations.jsonl.
    """
    if analyzer:
        spent = month_spend()
        if spent >= MONTHLY_BUDGET_USD:
            raise BudgetExceeded(f"AI budget spent this month (${spent:.2f} of ${MONTHLY_BUDGET_USD:.2f}).")

    usage = {"input_tokens": 0, "output_tokens": 0}
    extra: dict[str, Any] = {"output_config": {"effort": effort}} if effort else {}
    try:
        for _ in range(2):
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=[tool],
                tool_choice={"type": "auto"},
                messages=messages,
                **extra,
            )
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            if response.stop_reason == "refusal":
                raise RuntimeError(f"{tool['name']}: the model declined ({getattr(response, 'stop_details', None)}).")
            call = next((b for b in response.content if b.type == "tool_use"), None)
            if call is not None:
                if response.stop_reason == "max_tokens":
                    raise RuntimeError(f"{tool['name']} hit max_tokens ({max_tokens}); raise the limit.")
                if analyzer:
                    log_generation(analyzer=analyzer, model=model, usage=usage, tables_read=tables_read)
                return call.input, usage
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": f"Answer with the {tool['name']} tool, not as plain text."},
            ]
        raise RuntimeError(f"The model never called {tool['name']}.")
    except Exception as e:
        if analyzer and not isinstance(e, BudgetExceeded):
            log_generation(analyzer=analyzer, model=model, usage=usage, status="failed",
                           error=f"{type(e).__name__}: {e}", tables_read=tables_read)
        raise


def default_client() -> Any:
    import anthropic   # imported lazily so tests and dry runs need no key
    return anthropic.Anthropic()
