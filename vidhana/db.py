"""SQLite storage. One file, no service — the corpus is 137 documents."""
from __future__ import annotations

import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data", "vidhana.db")
SCHEMA = os.path.join(ROOT, "schema.sql")


def connect(path: str = DEFAULT_DB) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def init(con: sqlite3.Connection) -> None:
    with open(SCHEMA) as f:
        con.executescript(f.read())
    migrate(con)
    migrate_fts(con)
    con.commit()


def migrate(con: sqlite3.Connection) -> list[str]:
    """Add columns that schema.sql declares but an existing database lacks.

    `CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists, so a
    new column in schema.sql would otherwise only appear in databases built from
    scratch. Rebuilding is not free here — it means re-downloading 137 PDFs and
    paying for the LLM pass again — so missing columns are added in place.

    Only additive changes are handled. A type change or a dropped column still
    needs a real migration; this is deliberately the boring 90% case.
    """
    import re
    wanted: dict[str, list[tuple[str, str]]] = {}
    sql = open(SCHEMA).read()
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", sql, re.S):
        table, body = m.group(1), m.group(2)
        cols = []
        for line in body.splitlines():
            line = re.sub(r"--.*$", "", line).strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
                continue
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].isidentifier():
                cols.append((parts[0], parts[1]))
        wanted[table] = cols

    added = []
    for table, cols in wanted.items():
        have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if not have:
            continue                      # table did not exist; executescript made it
        for name, decl in cols:
            if name in have:
                continue
            # SQLite cannot ALTER in a NOT NULL column without a default, and it
            # cannot add a PRIMARY KEY at all — skip those rather than fail.
            d = decl.upper()
            if "PRIMARY KEY" in d or ("NOT NULL" in d and "DEFAULT" not in d):
                continue
            decl = re.sub(r"REFERENCES\s+\w+\s*\([^)]*\)", "", decl).strip()
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(f"{table}.{name}")
    if added:
        con.commit()
    return added


def upsert_gazette(con: sqlite3.Connection, row: dict) -> None:
    """Insert or update by gazette number, touching only the columns supplied.

    Deliberately not `INSERT ... ON CONFLICT DO UPDATE`: SQLite validates the
    INSERT's NOT NULL columns before it resolves the conflict, so a partial
    enrichment update (which carries no `year` or `title`) would fail on a row
    that already exists.
    """
    no = row["no"]
    cols = [k for k in row if k != "no"]
    if con.execute("SELECT 1 FROM gazette WHERE no=?", (no,)).fetchone():
        if cols:
            con.execute(f"UPDATE gazette SET {', '.join(f'{c}=?' for c in cols)} WHERE no=?",
                        [row[c] for c in cols] + [no])
    else:
        con.execute(
            f"INSERT INTO gazette ({', '.join(['no'] + cols)}) "
            f"VALUES ({', '.join('?' * (len(cols) + 1))})",
            [no] + [row[c] for c in cols])


def replace_children(con: sqlite3.Connection, table: str, no: str, rows: list[dict]) -> None:
    """Child rows are derived from the PDF, so re-deriving replaces them wholesale."""
    con.execute(f"DELETE FROM {table} WHERE no=?" if table != "gazette_reference"
                else "DELETE FROM gazette_reference WHERE src_no=?", (no,))
    if not rows:
        return
    # Union of keys, not the first row's. Rows are not uniformly shaped: only
    # pages that were OCR'd carry `ocr_chars`, so taking the first row's keys
    # silently dropped that column for every document whose page 1 needed no OCR.
    cols = list(dict.fromkeys(k for r in rows for k in r))
    con.executemany(
        f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        [[r.get(c) for c in cols] for r in rows])


def index_fts(con: sqlite3.Connection, no: str, title: str, body: str,
              summary: str | None = None) -> None:
    con.execute("DELETE FROM gazette_fts WHERE no=?", (no,))
    con.execute("INSERT INTO gazette_fts (no, title, summary, body) VALUES (?,?,?,?)",
                (no, title, summary, body))


def migrate_fts(con: sqlite3.Connection) -> bool:
    """Rebuild gazette_fts if schema.sql declares columns it does not have.

    fts5 has no ALTER TABLE ... ADD COLUMN, so unlike `migrate` this cannot be
    additive: the table is dropped and recreated empty. That is safe only
    because the index is derived — the text it indexes is on disk and the
    summaries are in gazette_summary — but it does leave search returning
    nothing until `vidhana reindex` runs, so callers are told it happened.
    """
    import re
    m = re.search(r"CREATE VIRTUAL TABLE IF NOT EXISTS gazette_fts USING fts5\((.*?)\);",
                  open(SCHEMA).read(), re.S)
    if not m:
        return False
    wanted = [c.split()[0] for c in m.group(1).split(",")
              if c.strip() and not c.strip().startswith("tokenize")]
    have = [r[1] for r in con.execute("PRAGMA table_info(gazette_fts)")]
    if not have or have == wanted:
        return False
    con.execute("DROP TABLE gazette_fts")
    con.executescript(m.group(0))
    con.commit()
    return True
