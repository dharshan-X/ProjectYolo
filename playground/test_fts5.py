import sqlite3
conn = sqlite3.connect(":memory:")
conn.execute("CREATE VIRTUAL TABLE fts USING fts5(user_id UNINDEXED, text)")
conn.execute("INSERT INTO fts (user_id, text) VALUES (?, ?)", (1, "Hello world"))
print(conn.execute("SELECT typeof(user_id) FROM fts").fetchall())
print(conn.execute("SELECT * FROM fts WHERE user_id = ?", (1,)).fetchall())
print(conn.execute("SELECT * FROM fts WHERE user_id = ?", ("1",)).fetchall())
