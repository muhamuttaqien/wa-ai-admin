from conversation import _connect
with _connect() as conn:
    rows=conn.execute("SELECT * FROM leads ORDER BY updated_at DESC").fetchall()
if not rows:
    print("No leads stored.")
for row in rows:
    print("\n" + "="*60)
    for k,v in dict(row).items(): print(f"{k:24}: {v}")
