"""
seed_data.py — Run this ONCE to pre-load all documents from resources/data/ into the system.
Usage:  python seed_data.py
"""
import sqlite3
import shutil
import os
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
RESOURCES   = BASE_DIR / "resources" / "data"
UPLOAD_DIR  = BASE_DIR / "static" / "uploads"
DB_PATH     = BASE_DIR / "roles_docs.db"

# ── Roles whose folders we'll seed ─────────────────────────────────────────────
ROLE_MAP = {
    "engineering": "Engineering",
    "finance":     "Finance",
    "general":     "General",
    "hr":          "HR",
    "marketing":   "Marketing",
}

def seed():
    conn = sqlite3.connect(str(DB_PATH))
    c    = conn.cursor()

    # Make sure roles exist
    for role_key in ROLE_MAP:
        c.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (role_key,))
    conn.commit()

    total = 0
    for role_key, upload_folder in ROLE_MAP.items():
        src_dir  = RESOURCES / role_key
        dest_dir = UPLOAD_DIR / upload_folder
        dest_dir.mkdir(parents=True, exist_ok=True)

        if not src_dir.exists():
            print(f"  [SKIP] No source folder: {src_dir}")
            continue

        files = list(src_dir.iterdir())
        if not files:
            print(f"  [SKIP] Empty folder: {src_dir}")
            continue

        for src_file in files:
            if src_file.suffix.lower() not in {".md", ".csv"}:
                continue

            dest_file = dest_dir / src_file.name
            shutil.copy2(src_file, dest_file)

            # Check if already in DB
            c.execute(
                "SELECT id FROM documents WHERE filepath = ?",
                (str(dest_file),)
            )
            if c.fetchone():
                print(f"  [SKIP] Already in DB: {dest_file.name}")
                continue

            # Compute headers_str for CSVs
            headers_str = None
            if src_file.suffix.lower() == ".csv":
                import pandas as pd
                try:
                    df = pd.read_csv(src_file)
                    headers_str = ",".join(df.columns.tolist())
                except Exception as e:
                    print(f"  [WARN] Could not read CSV headers for {src_file.name}: {e}")

            c.execute(
                "INSERT INTO documents (filename, role, filepath, headers_str, embedded) VALUES (?, ?, ?, ?, 0)",
                (src_file.name, role_key, str(dest_file), headers_str)
            )
            print(f"  [ADD] {role_key}/{src_file.name}")
            total += 1

    conn.commit()
    conn.close()
    print(f"\n✅ Seeded {total} new document(s) into the database.")

    # ── Now index them into the vectorstore ─────────────────────────────────────
    if total > 0:
        print("\n⏳ Running indexer (this may take a minute)...")
        sys.path.insert(0, str(BASE_DIR))
        os.chdir(BASE_DIR)          # chroma_db path is relative
        from app.rag_utils.rag_module import run_indexer
        run_indexer()
        print("✅ Indexing complete!")
    else:
        print("ℹ️  No new documents to index.")

    # ── Register CSVs in DuckDB ─────────────────────────────────────────────────
    seed_duckdb()

def seed_duckdb():
    """Load CSV files into DuckDB so SQL queries work."""
    import duckdb
    import pandas as pd

    DUCKDB_FILE = BASE_DIR / "static" / "data" / "structured_queries.duckdb"
    DUCKDB_FILE.parent.mkdir(parents=True, exist_ok=True)
    duck = duckdb.connect(str(DUCKDB_FILE))

    duck.execute("""
        CREATE TABLE IF NOT EXISTS tables_metadata (
            table_name TEXT,
            role TEXT
        )
    """)

    for role_key, upload_folder in ROLE_MAP.items():
        src_dir = RESOURCES / role_key
        if not src_dir.exists():
            continue
        for src_file in src_dir.iterdir():
            if src_file.suffix.lower() != ".csv":
                continue
            table_name = src_file.stem.replace("-", "_")
            try:
                df = pd.read_csv(src_file)
                duck.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df")
                # Avoid duplicate metadata
                existing = duck.execute(
                    "SELECT 1 FROM tables_metadata WHERE table_name = ?", [table_name]
                ).fetchone()
                if not existing:
                    duck.execute(
                        "INSERT INTO tables_metadata (table_name, role) VALUES (?, ?)",
                        [table_name, role_key]
                    )
                print(f"  [DuckDB] Loaded table: {table_name} ({role_key})")
            except Exception as e:
                print(f"  [DuckDB ERROR] {src_file.name}: {e}")

    duck.close()
    print("✅ DuckDB tables ready.")

if __name__ == "__main__":
    seed()
