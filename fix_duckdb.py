import duckdb
conn = duckdb.connect("static/data/structured_queries.duckdb")
rows = conn.execute("SELECT table_name, role FROM tables_metadata").fetchall()
print("Before:", rows)
for table_name, role in rows:
    conn.execute(
        "UPDATE tables_metadata SET role = ? WHERE table_name = ?",
        [role.lower(), table_name]
    )
rows = conn.execute("SELECT table_name, role FROM tables_metadata").fetchall()
print("After:", rows)
conn.close()
print("Done.")
