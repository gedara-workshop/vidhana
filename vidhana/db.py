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
    con.commit()


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
    cols = list(rows[0])
    con.executemany(
        f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        [[r[c] for c in cols] for r in rows])


def index_fts(con: sqlite3.Connection, no: str, title: str, body: str) -> None:
    con.execute("DELETE FROM gazette_fts WHERE no=?", (no,))
    con.execute("INSERT INTO gazette_fts (no, title, body) VALUES (?,?,?)", (no, title, body))
