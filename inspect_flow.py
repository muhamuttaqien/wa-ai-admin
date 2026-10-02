from conversation import _connect
with _connect() as conn:
    rows=conn.execute("SELECT * FROM program_flow_state ORDER BY updated_at DESC").fetchall()
for row in rows:
    print(dict(row))
