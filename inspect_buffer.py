from message_buffer import inspect_buffer

rows = inspect_buffer()
if not rows:
    print("No buffered messages.")
else:
    for row in rows:
        print("=" * 70)
        print(f"Sender   : {row['sender']}")
        print(f"Due at   : {row['due_at']}")
        print(f"Messages : {row['message_count']}")
        print(f"Content  : {row['messages']}")
