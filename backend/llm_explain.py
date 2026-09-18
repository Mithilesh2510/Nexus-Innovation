"""
LLM explanation layer with multi-provider support (OpenAI, Anthropic, Groq, OpenRouter).

Deliberate design boundary: the LLM NEVER computes a risk score or a recommended order
quantity -- it only narrates numbers that risk_scoring.py / procurement_optimizer.py already
produced deterministically. This keeps the system auditable (a hospital procurement officer
can trace every number back to a formula) and is a stronger hackathon story than "the LLM
decides everything," which is both less defensible and, for a healthcare context, riskier.

Supports:
- OpenAI (keys starting with `sk-` or OPENAI_API_KEY)
- Anthropic (keys starting with `sk-ant-` or ANTHROPIC_API_KEY)
- Groq (keys starting with `gsk_` or GROQ_API_KEY)
- OpenRouter (keys starting with `sk-or-` or OPENROUTER_API_KEY)
- Fallback deterministic template if keys are missing, invalid, or API calls time out.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


def _fallback_explanation(facts: dict) -> str:
    name = facts.get("name", "This item")
    tier = facts.get("risk_tier", "elevated")
    stockout = facts.get("stockout_probability_pct", 0)
    cover = facts.get("days_of_cover_p50", 0)
    lead = facts.get("supplier_lead_time_mean", 0)
    order = facts.get("recommended_order_units")
    overdue = facts.get("overdue_orders_units", 0)

    parts = [
        f"{name} is at {tier.upper()} risk: {stockout:.0f}% modeled stockout probability "
        f"with only {cover:.1f} days of cover against a {lead:.0f}-day supplier lead time."
    ]
    if overdue:
        parts.append(f"Note: {int(overdue)} units are sitting in overdue pending orders and should not be relied on.")
    if order:
        parts.append(f"Recommend ordering {int(order)} units now.")
    return " ".join(parts)


def _detect_provider(api_key: str) -> str:
    """Detect LLM provider from key format."""
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("gsk_"):
        return "groq"
    if api_key.startswith("sk-or-"):
        return "openrouter"
    # Standard sk- keys default to OpenAI
    return "openai"


def explain_risk(facts: dict, api_key: str | None = None, timeout: int = 10) -> dict:
    """
    facts: a flat dict of the numbers already computed for one SKU.
    Returns {"explanation": str, "source": "llm"|"fallback", "provider": str, "error"?: str}.
    """
    key = (
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("LLM_API_KEY")
    )
    if not key:
        return {"explanation": _fallback_explanation(facts), "source": "fallback", "provider": "none"}

    provider = _detect_provider(key)

    prompt = (
        "You are writing a one-to-two sentence plain-English clinical supply chain justification "
        "for a hospital procurement officer, based ONLY on the structured facts below. Do not invent any "
        "numbers not present in the facts. Be direct, authoritative, and specific. Facts:\n\n"
        f"{json.dumps(facts, indent=2)}\n\n"
        "Write only the justification text, no preamble."
    )

    try:
        if provider == "anthropic":
            resp = requests.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()

        elif provider == "groq":
            resp = requests.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "max_tokens": 200,
                    "messages": [
                        {"role": "system", "content": "You are a clinical hospital procurement intelligence assistant."},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()

        else:  # openai or openai-compatible
            resp = requests.post(
                OPENAI_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 200,
                    "messages": [
                        {"role": "system", "content": "You are a clinical hospital procurement intelligence assistant."},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()

        if not text:
            raise ValueError("Empty LLM response received")

        return {"explanation": text, "source": "llm", "provider": provider}

    except Exception as e:
        fallback = _fallback_explanation(facts)
        # Extract meaningful error message if it was an HTTP error
        err_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_json = e.response.json()
                err_msg = err_json.get("error", {}).get("message", e.response.text)
            except Exception:
                err_msg = e.response.text or str(e)

        return {
            "explanation": fallback,
            "source": "fallback",
            "provider": provider,
            "error": err_msg[:200],
        }
