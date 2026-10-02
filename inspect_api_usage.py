import sys
from usage_store import usage_summary

if len(sys.argv) != 2:
    raise SystemExit("Usage: python inspect_api_usage.py <sender>")

u = usage_summary(sys.argv[1])
print(f"Sender             : {sys.argv[1]}")
print(f"API calls          : {u['api_calls']}")
print(f"Input tokens       : {u['input_tokens']:,}")
print(f"Cached input       : {u['cached_input_tokens']:,}")
print(f"Cache writes       : {u['cache_write_tokens']:,}")
print(f"Output tokens      : {u['output_tokens']:,}")
print(f"Estimated cost USD : ${u['estimated_cost_usd']:.6f}")
for row in u['by_type']:
    print(f"  - {row['call_type']}: {row['calls']} calls, in={row['input_tokens']:,}, out={row['output_tokens']:,}, ${row['estimated_cost_usd']:.6f}")
