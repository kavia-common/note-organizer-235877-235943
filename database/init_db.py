#!/usr/bin/env python3
"""Initialize SQLite database for the Notes app (database container).

This script creates the schema for:
- notes
- tags
- note_tags (many-to-many)

It also seeds sample data when the database is empty.

It additionally writes:
- db_connection.txt with the absolute db path and sqlite connection string
- db_visualizer/sqlite.env for the included Node DB viewer

Run:
  python3 init_db.py
"""

import os
import sqlite3
from typing import Optional

DB_NAME = "myapp.db"
DB_USER = "kaviasqlite"  # Not used for SQLite, kept for consistency with templates
DB_PASSWORD = "kaviadefaultpassword"  # Not used for SQLite, kept for consistency
DB_PORT = "5000"  # Not used for SQLite, kept for consistency


def _connect(db_name: str) -> sqlite3.Connection:
    """Create a SQLite connection with sensible defaults for this project."""
    conn = sqlite3.connect(db_name)
    # Return rows as dict-like objects when needed (not required, but handy).
    conn.row_factory = sqlite3.Row
    # Enforce FK constraints in SQLite.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return True if table exists."""
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? AND name NOT LIKE 'sqlite_%'",
        (table_name,),
    )
    return cur.fetchone() is not None


def _notes_count(conn: sqlite3.Connection) -> int:
    """Return count of notes if table exists, else 0."""
    if not _table_exists(conn, "notes"):
        return 0
    cur = conn.execute("SELECT COUNT(*) AS c FROM notes")
    row = cur.fetchone()
    return int(row["c"]) if row else 0


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the notes/tags schema, indexes, and triggers.

    Design notes:
    - notes.tags are modeled via note_tags join table (normalized).
    - tags.name is UNIQUE (case-insensitive handled at app layer; SQLite's NOCASE collation could be used,
      but we avoid implicit behavior across locales).
    - notes.updated_at is automatically bumped via a trigger.
    """
    cur = conn.cursor()

    # Basic app metadata table (kept from template, but repurposed).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            is_archived INTEGER NOT NULL DEFAULT 0, -- 0/1 boolean
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS note_tags (
            note_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (note_id, tag_id),
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
        """
    )

    # Helpful indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_updated_at ON notes(updated_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes(created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)")

    # Keep updated_at current without requiring app-side logic.
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_notes_updated_at
        AFTER UPDATE ON notes
        FOR EACH ROW
        BEGIN
            UPDATE notes SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END
        """
    )

    conn.commit()


def _seed_sample_data(conn: sqlite3.Connection) -> None:
    """Seed sample tags and notes.

    This runs only when the notes table exists and is empty.
    """
    if _notes_count(conn) > 0:
        print("Sample data seed skipped (notes table is not empty).")
        return

    cur = conn.cursor()

    # App info
    cur.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("project_name", "note-organizer"),
    )
    cur.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("version", "0.1.0"),
    )
    cur.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("description", "Notes app schema: notes/tags with many-to-many relation"),
    )

    # Tags (use INSERT OR IGNORE so re-running won't fail if partial data exists)
    tags = [
        "work",
        "personal",
        "ideas",
        "todo",
        "journal",
        "retro",
    ]
    for t in tags:
        cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (t,))

    # Notes
    notes = [
        (
            "Welcome to Note Organizer",
            "This is a sample note. You can create, edit, delete, and tag notes.\n\nTry searching for keywords like 'retro' or filtering by the 'todo' tag.",
        ),
        (
            "Retro Theme UI ideas",
            "- Use bold accent colors\n- Pixel-ish borders\n- Soft gradients\n- Chunky buttons\n\nKeep it readable and accessible.",
        ),
        (
            "Todo: Launch checklist",
            "1) Finalize schema\n2) Connect backend CRUD\n3) Hook up frontend\n4) Add search + tag filters\n5) Ship",
        ),
        (
            "Journal: Day 1",
            "Built the first draft of the notes app. Next step is tagging + search. Keep iterating.",
        ),
        (
            "Work meeting notes",
            "Discussed roadmap and milestones.\n- Database schema\n- API endpoints\n- UI polish",
        ),
    ]

    note_ids = []
    for title, content in notes:
        cur.execute("INSERT INTO notes (title, content) VALUES (?, ?)", (title, content))
        note_ids.append(int(cur.lastrowid))

    # Map tags to notes
    def tag_id(name: str) -> Optional[int]:
        r = cur.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        return int(r["id"]) if r else None

    mapping = {
        note_ids[0]: ["ideas", "retro"],
        note_ids[1]: ["ideas", "retro"],
        note_ids[2]: ["todo", "work"],
        note_ids[3]: ["journal", "personal"],
        note_ids[4]: ["work"],
    }

    for nid, tag_names in mapping.items():
        for name in tag_names:
            tid = tag_id(name)
            if tid is None:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (nid, tid),
            )

    conn.commit()
    print("Sample data seeded (notes, tags, note_tags).")


def _write_connection_info(db_name: str) -> None:
    """Write db_connection.txt and db_visualizer/sqlite.env based on current absolute DB path."""
    current_dir = os.getcwd()
    connection_string = f"sqlite:///{current_dir}/{db_name}"
    db_path = os.path.abspath(db_name)

    try:
        with open("db_connection.txt", "w", encoding="utf-8") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_name}')\n")
            f.write(f"# Connection string: {connection_string}\n")
            f.write(f"# File path: {current_dir}/{db_name}\n")
        print("Connection information saved to db_connection.txt")
    except Exception as e:
        print(f"Warning: Could not save connection info: {e}")

    if not os.path.exists("db_visualizer"):
        os.makedirs("db_visualizer", exist_ok=True)
        print("Created db_visualizer directory")

    try:
        with open("db_visualizer/sqlite.env", "w", encoding="utf-8") as f:
            f.write(f'export SQLITE_DB="{db_path}"\n')
        print("Environment variables saved to db_visualizer/sqlite.env")
    except Exception as e:
        print(f"Warning: Could not save environment variables: {e}")


def main() -> None:
    """Entrypoint for initializing the SQLite database file, schema, and sample data."""
    print("Starting SQLite setup...")

    db_exists = os.path.exists(DB_NAME)
    if db_exists:
        print(f"SQLite database already exists at {DB_NAME}")
        try:
            conn = _connect(DB_NAME)
            conn.execute("SELECT 1")
            conn.close()
            print("Database is accessible and working.")
        except Exception as e:
            print(f"Warning: Database exists but may be corrupted: {e}")
    else:
        print("Creating new SQLite database...")

    conn = _connect(DB_NAME)
    try:
        _create_schema(conn)
        _seed_sample_data(conn)

        # Stats
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_count = int(cur.fetchone()["c"])

        cur = conn.execute("SELECT COUNT(*) AS c FROM notes")
        notes_count = int(cur.fetchone()["c"])

        cur = conn.execute("SELECT COUNT(*) AS c FROM tags")
        tags_count = int(cur.fetchone()["c"])

    finally:
        conn.close()

    _write_connection_info(DB_NAME)

    print("\nSQLite setup complete!")
    print(f"Database: {DB_NAME}")
    print(f"Location: {os.getcwd()}/{DB_NAME}\n")

    print("Database statistics:")
    print(f"  Tables: {table_count}")
    print(f"  Notes: {notes_count}")
    print(f"  Tags: {tags_count}")

    # If sqlite3 CLI is available, show how to use it
    try:
        import subprocess

        result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
        if result.returncode == 0:
            print("\nSQLite CLI is available. You can also use:")
            print(f"  sqlite3 {DB_NAME}")
    except Exception:
        pass

    print("\nScript completed successfully.")


if __name__ == "__main__":
    main()
