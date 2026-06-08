import re
import duckdb
import os,tabulate
from groq import Groq
import sqlite3
import os
from pathlib import Path

from .secret_key import groq_api_key, groq_model

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(BASE_DIR, "roles_docs.db")

# DuckDB setup
DUCKDB_FILE = "static/data/structured_queries.duckdb"
_duck_conn = None

def get_duck_conn():
    global _duck_conn
    if _duck_conn is None:
        _duck_conn = duckdb.connect(DUCKDB_FILE, read_only=False)
    return _duck_conn

# Groq setup
client = Groq(api_key=groq_api_key)

def get_allowed_tables_for_role(role: str) -> list[str]:
    conn = get_duck_conn()
    if role.lower() == "c-level":
        query = "SELECT table_name FROM tables_metadata"
        return [row[0] for row in conn.execute(query).fetchall()]
    elif role.lower() == "general":
        query = "SELECT table_name FROM tables_metadata WHERE lower(role) = 'general'"
        return [row[0] for row in conn.execute(query).fetchall()]
    else:
        query = """
        SELECT table_name FROM tables_metadata
        WHERE lower(role) = lower(?) OR lower(role) = 'general'
        """
        return [row[0] for row in conn.execute(query, [role]).fetchall()]

def extract_tables_from_sql(sql: str) -> list[str]:
    # Extract tables used in FROM and JOIN clauses
    return re.findall(r'FROM\s+(\w+)|JOIN\s+(\w+)', sql, flags=re.IGNORECASE)

def flatten_matches(matches: list[tuple]) -> list[str]:
    return [item for tup in matches for item in tup if item]

FORBIDDEN = ["insert", "update", "delete", "drop", "alter", "create"]

def is_safe_query(sql: str) -> bool:
    lowered = sql.strip().lower().rstrip(";")
    return lowered.startswith("select") and all(word not in lowered for word in FORBIDDEN)

def translate_nl_to_sql(question: str, allowed_tables: list[str]) -> str:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()

    # fetch headers from table
    cur.execute("""
        SELECT filename, headers_str FROM documents 
        WHERE embedded = 1 AND headers_str IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()

    schemas = []
    for filename, headers_str in rows:
        try:
            table_name = Path(filename).stem.replace("-", "_")
            cols = ", ".join(headers_str.split(","))
            schemas.append(f"Table: {table_name}\nColumns: {cols}")
        except Exception as e:
            print(f"[ERROR] Schema build failed for {filename}: {e}")

    schema_block = "\n\n".join(schemas)

    # Prompt for LLM
    prompt = f"""
    You are an assistant that converts natural language questions into safe SQL SELECT queries.

    Use only the following schemas:
    {schema_block}

    Constraints:
    - Use only the tables listed above.
    - Use the exact column names as-is (including hyphens, underscores, casing).
    - Return only a SELECT query (no INSERT/UPDATE/DELETE).
    - If asked about 'employee name', consider alternatives like 'full-name', 'last-name'.
    - If asked about 'position', consider synonyms like 'role', 'designation'.
    - Do not mix aggregate functions (like COUNT(*)) with *. Use either a grouped summary or return them separately.
    - Return ONLY the SQL query with no explanation, no markdown fences, no extra text.
    Natural Language Question: "{question}"

    SQL:
    """

    try:
        response = client.chat.completions.create(
            model=groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        response_text = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        response_text = re.sub(r"^```[\w]*\n?", "", response_text)
        response_text = re.sub(r"\n?```$", "", response_text).strip()
        print(f"[SQL] Generated: {response_text[:120]}")
        return response_text

    except Exception as e:
        print(f"[ERROR] SQL generation failed: {e}")
        return "Error generating SQL"

#async def ask_csv(question: str, role: str) -> dict:
async def ask_csv(question: str, role: str, username: str, return_sql: bool = False) -> dict:
    allowed_tables = get_allowed_tables_for_role(role)

    try:
        sql = translate_nl_to_sql(question, allowed_tables)
        print(f"[SQL GENERATED]:\n{sql}")

        if not is_safe_query(sql):
            return {"answer": "Only SELECT queries are allowed.", "error": True}

        raw_matches = extract_tables_from_sql(sql)
        referenced_tables = flatten_matches(raw_matches)

        for table in referenced_tables:
            if table not in allowed_tables:
                return {"answer": f"Access denied to table: {table}", "error": True}

        conn = get_duck_conn()
        result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]
        output = [list(row) for row in result]

        markdown_table = tabulate.tabulate(output, headers=columns, tablefmt="github")
        response = {
            "answer": markdown_table if output else "Query executed, but no results found."
        }

        if return_sql:
            response["sql"] = sql

        return response

    except Exception as e:
        return {"answer": f"[ERROR] {str(e)}", "error": True}
