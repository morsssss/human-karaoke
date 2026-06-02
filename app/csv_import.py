import csv
import io
import threading
import logging
from typing import Callable, Optional

from .db import get_conn
from .lyrics import fetch_lyrics

log = logging.getLogger(__name__)


ARTIST_KEYS = ("artist", "artists", "performer")
TITLE_KEYS = ("song", "title", "song title", "track", "song_title")


def _norm(s: str) -> str:
    return (s or "").strip()


def _pick(row: dict, candidates) -> Optional[str]:
    lower = {k.lower().strip(): v for k, v in row.items() if k is not None}
    for c in candidates:
        if c in lower:
            return lower[c]
    return None


def parse_csv(data: bytes) -> list[tuple[str, str]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in reader:
        artist = _norm(_pick(row, ARTIST_KEYS) or "")
        title = _norm(_pick(row, TITLE_KEYS) or "")
        if not artist or not title:
            continue
        key = (artist.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((artist, title))
    return out


def apply_import(
    pairs: list[tuple[str, str]],
    progress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Incremental import: keep cached lyrics for (artist,title) matches,
    insert new rows, delete rows not in CSV. Reset votes on every import."""
    progress = progress or (lambda _e: None)

    with get_conn() as conn:
        existing = {
            (r["artist"].lower(), r["title"].lower()): dict(r)
            for r in conn.execute(
                "SELECT id, artist, title, lyrics, lyrics_status FROM songs"
            ).fetchall()
        }

        incoming_keys = {(a.lower(), t.lower()) for a, t in pairs}
        to_delete = [v["id"] for k, v in existing.items() if k not in incoming_keys]

        to_insert: list[tuple[str, str]] = []
        for artist, title in pairs:
            if (artist.lower(), title.lower()) not in existing:
                to_insert.append((artist, title))

        # Reset votes on every import (fresh session)
        conn.execute("UPDATE songs SET votes=0")
        # Clear current song
        conn.execute("DELETE FROM state WHERE key='current_song_id'")

        if to_delete:
            conn.executemany(
                "DELETE FROM songs WHERE id=?", [(i,) for i in to_delete]
            )

        for artist, title in to_insert:
            conn.execute(
                "INSERT OR IGNORE INTO songs(artist,title,lyrics_status) VALUES(?,?,?)",
                (artist, title, "pending"),
            )
        conn.commit()

    summary = {
        "total": len(pairs),
        "inserted": len(to_insert),
        "deleted": len(to_delete),
        "kept": len(pairs) - len(to_insert),
    }
    progress({"event": "import_done", **summary})
    return summary


def fetch_pending_lyrics(progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Iterate pending songs and fill in lyrics one by one."""
    progress = progress or (lambda _e: None)
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT id, artist, title FROM songs "
            "WHERE lyrics_status='pending' OR lyrics_status='error' "
            "ORDER BY id"
        ).fetchall()
    total = len(pending)
    progress({"event": "lyrics_start", "total": total})

    found = 0
    not_found = 0
    errored = 0
    with get_conn() as conn:
        for idx, row in enumerate(pending, 1):
            artist, title, sid = row["artist"], row["title"], row["id"]
            text, err = fetch_lyrics(artist, title)
            if text:
                status = "found"
                found += 1
            elif err and err != "not found":
                status = "error"
                errored += 1
            else:
                status = "not_found"
                not_found += 1
            conn.execute(
                "UPDATE songs SET lyrics=?, lyrics_status=?, lyrics_error=? WHERE id=?",
                (text, status, err if status != "found" else None, sid),
            )
            conn.commit()
            progress(
                {
                    "event": "lyrics_progress",
                    "done": idx,
                    "total": total,
                    "artist": artist,
                    "title": title,
                    "status": status,
                }
            )

    progress(
        {
            "event": "lyrics_done",
            "found": found,
            "not_found": not_found,
            "errored": errored,
        }
    )
    return {"found": found, "not_found": not_found, "errored": errored}


_refresh_thread: Optional[threading.Thread] = None
_refresh_lock = threading.Lock()
_refresh_status: dict = {"running": False, "last": None}


def status() -> dict:
    return dict(_refresh_status)


def kick_off_refresh(
    pairs: list[tuple[str, str]], emit: Callable[[str, dict], None]
) -> bool:
    """Start a background thread to import + fetch lyrics. Returns False if
    one is already running."""
    global _refresh_thread
    with _refresh_lock:
        if _refresh_status["running"]:
            return False
        _refresh_status["running"] = True
        _refresh_status["last"] = None

    def progress(ev: dict):
        try:
            emit("refresh_progress", ev)
        except Exception:
            log.exception("emit failed")

    def run():
        try:
            summary = apply_import(pairs, progress)
            emit("songs_changed", {})
            lyric_summary = fetch_pending_lyrics(progress)
            with _refresh_lock:
                _refresh_status["last"] = {**summary, **lyric_summary}
            emit("songs_changed", {})
        except Exception as e:
            log.exception("refresh failed")
            progress({"event": "error", "message": str(e)})
        finally:
            with _refresh_lock:
                _refresh_status["running"] = False
            emit("refresh_done", _refresh_status["last"] or {})

    _refresh_thread = threading.Thread(target=run, daemon=True)
    _refresh_thread.start()
    return True
