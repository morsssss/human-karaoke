import os
import sqlite3
import threading
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "./karaoke.db")

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    lyrics TEXT,
    lyrics_status TEXT NOT NULL DEFAULT 'pending',
    lyrics_error TEXT,
    votes INTEGER NOT NULL DEFAULT 0,
    UNIQUE(artist, title)
);

CREATE INDEX IF NOT EXISTS idx_songs_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def get_conn():
    # sqlite3.Connection's own context manager commits but does NOT close,
    # which leaks FDs. We wrap it so `with get_conn() as conn:` always closes.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def reset_session():
    """Zero out votes and clear current song. Called once per process start
    so each restart begins a fresh singalong session."""
    with get_conn() as conn:
        conn.execute("UPDATE songs SET votes=0")
        conn.execute("DELETE FROM state WHERE key='current_song_id'")
        conn.commit()


def get_state(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_state(key, value):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO state(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
