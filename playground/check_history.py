import sqlite3, json, os
conn = sqlite3.connect(os.path.expanduser("~/.yolo/yolo_v2.db"))
cursor = conn.cursor()
cursor.execute("SELECT history FROM sessions ORDER BY last_active DESC LIMIT 1")
row = cursor.fetchone()
if row:
    history = json.loads(row[0])
    for msg in history[-3:]:
        role = msg.get('role')
        content = msg.get('content')
        print(f"ROLE: {role}")
        print(f"CONTENT:\n{content}\n" + "-"*40)
