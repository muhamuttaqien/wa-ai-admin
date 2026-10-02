from followup_scheduler import inspect_followups

rows = inspect_followups()
if not rows:
    print("No scheduled follow-ups.")
else:
    for row in rows:
        print(row)
