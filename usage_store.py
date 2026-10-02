"""OpenAI token/cost telemetry per WhatsApp lead (Milestone 6A)."""
from datetime import datetime, timezone
from conversation import _connect, _lock

# USD per 1M text tokens. GPT-5.6 Sol promotional Standard pricing,
# verified 2026-10-03. Long-context pricing applies above 272K input tokens.
GPT56_SOL_SHORT = {"input": 4.00, "cached": 0.40, "cache_write": 5.00, "output": 20.00}
GPT56_SOL_LONG = {"input": 8.00, "cached": 0.80, "cache_write": 10.00, "output": 30.00}
GPT56_LUNA_SHORT = {"input": 0.20, "cached": 0.02, "cache_write": 0.25, "output": 1.20}
GPT56_LUNA_LONG = {"input": 0.40, "cached": 0.04, "cache_write": 0.50, "output": 1.80}


def init_usage_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    call_type TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_usage_sender_id ON api_usage(sender, id)")


def _value(obj, name, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _token_usage(response):
    usage = getattr(response, "usage", None)
    input_tokens = int(_value(usage, "input_tokens", 0) or 0)
    output_tokens = int(_value(usage, "output_tokens", 0) or 0)
    details = _value(usage, "input_tokens_details", None)
    cached = int(_value(details, "cached_tokens", 0) or 0)
    cache_write = int(_value(details, "cache_write_tokens", 0) or 0)
    # Defensive: token subcategories must never exceed total input.
    cached = min(max(cached, 0), input_tokens)
    cache_write = min(max(cache_write, 0), max(0, input_tokens - cached))
    return input_tokens, cached, cache_write, output_tokens


def estimate_cost(model, input_tokens, cached_tokens, cache_write_tokens, output_tokens):
    # Model-aware pricing. Unknown models are recorded with $0 rather than
    # silently applying an incorrect rate.
    if model in {"gpt-5.6", "gpt-5.6-sol"}:
        rates = GPT56_SOL_LONG if input_tokens > 272_000 else GPT56_SOL_SHORT
    elif model == "gpt-5.6-luna":
        rates = GPT56_LUNA_LONG if input_tokens > 272_000 else GPT56_LUNA_SHORT
    else:
        return 0.0
    uncached = max(0, input_tokens - cached_tokens - cache_write_tokens)
    return (
        uncached * rates["input"]
        + cached_tokens * rates["cached"]
        + cache_write_tokens * rates["cache_write"]
        + output_tokens * rates["output"]
    ) / 1_000_000


def record_openai_usage(sender, call_type, model, response):
    if not sender:
        return None
    input_tokens, cached, cache_write, output_tokens = _token_usage(response)
    cost = estimate_cost(model, input_tokens, cached, cache_write, output_tokens)
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _connect() as conn:
            cur = conn.execute("""
                INSERT INTO api_usage(
                    sender, call_type, model, input_tokens, cached_input_tokens,
                    cache_write_tokens, output_tokens, estimated_cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sender, call_type, model, input_tokens, cached, cache_write, output_tokens, cost, now))
    print(
        f"API USAGE [{call_type}] : in={input_tokens} cached={cached} "
        f"write={cache_write} out={output_tokens} cost=${cost:.6f}"
    )
    return cost


def usage_summary(sender):
    init_usage_db()
    with _lock:
        with _connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS api_calls,
                       COALESCE(SUM(input_tokens),0) AS input_tokens,
                       COALESCE(SUM(cached_input_tokens),0) AS cached_input_tokens,
                       COALESCE(SUM(cache_write_tokens),0) AS cache_write_tokens,
                       COALESCE(SUM(output_tokens),0) AS output_tokens,
                       COALESCE(SUM(estimated_cost_usd),0) AS estimated_cost_usd
                FROM api_usage WHERE sender=?
            """, (sender,)).fetchone()
            by_type = conn.execute("""
                SELECT call_type, COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens),0) AS input_tokens,
                       COALESCE(SUM(output_tokens),0) AS output_tokens,
                       COALESCE(SUM(estimated_cost_usd),0) AS estimated_cost_usd
                FROM api_usage WHERE sender=? GROUP BY call_type ORDER BY call_type
            """, (sender,)).fetchall()
    result = dict(row)
    result["by_type"] = [dict(x) for x in by_type]
    return result


init_usage_db()
