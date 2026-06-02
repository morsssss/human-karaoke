import os
import logging
from flask import Flask, jsonify, request, send_from_directory, abort
from flask_socketio import SocketIO

from . import db
from . import csv_import

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB CSV limit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

db.init_db()
db.reset_session()


def emit(event: str, payload: dict):
    socketio.emit(event, payload)


# ---------- Static routing ----------

@app.route("/")
def karaoke_root():
    return send_from_directory(os.path.join(STATIC_DIR, "karaoke"), "index.html")


@app.route("/karaoke/<path:filename>")
def karaoke_static(filename):
    return send_from_directory(os.path.join(STATIC_DIR, "karaoke"), filename)


@app.route("/admin")
def admin_root():
    return send_from_directory(os.path.join(STATIC_DIR, "admin"), "index.html")


@app.route("/admin/<path:filename>")
def admin_static(filename):
    return send_from_directory(os.path.join(STATIC_DIR, "admin"), filename)


# ---------- API: songs ----------

def _serialize_song(row, include_lyrics=False):
    out = {
        "id": row["id"],
        "artist": row["artist"],
        "title": row["title"],
        "votes": row["votes"],
        "lyrics_status": row["lyrics_status"],
    }
    if include_lyrics:
        out["lyrics"] = row["lyrics"]
        out["lyrics_error"] = row["lyrics_error"]
    return out


@app.route("/api/songs")
def list_songs():
    include_lyrics = request.args.get("with_lyrics") == "1"
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM songs ORDER BY artist COLLATE NOCASE, title COLLATE NOCASE"
        ).fetchall()
    return jsonify([_serialize_song(r, include_lyrics) for r in rows])


@app.route("/api/songs/<int:song_id>")
def get_song(song_id):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (song_id,)).fetchone()
    if not row:
        abort(404)
    return jsonify(_serialize_song(row, include_lyrics=True))


@app.route("/api/songs/<int:song_id>/vote", methods=["POST"])
def vote(song_id):
    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE songs SET votes = votes + 1 WHERE id=?", (song_id,)
        )
        if cur.rowcount == 0:
            abort(404)
        conn.commit()
        row = conn.execute(
            "SELECT id, votes FROM songs WHERE id=?", (song_id,)
        ).fetchone()
    payload = {"id": row["id"], "votes": row["votes"]}
    emit("vote", payload)
    return jsonify(payload)


@app.route("/api/state/current")
def get_current():
    sid = db.get_state("current_song_id")
    if not sid:
        return jsonify({"current_song_id": None, "song": None})
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (int(sid),)).fetchone()
    if not row:
        return jsonify({"current_song_id": None, "song": None})
    return jsonify(
        {"current_song_id": int(sid), "song": _serialize_song(row, include_lyrics=True)}
    )


@app.route("/api/admin/current", methods=["POST"])
def set_current():
    data = request.get_json(silent=True) or {}
    sid = data.get("song_id")
    if sid is None:
        abort(400, "song_id required")
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM songs WHERE id=?", (int(sid),)).fetchone()
        if not row:
            abort(404)
        conn.execute("UPDATE songs SET votes=0 WHERE id=?", (int(sid),))
        conn.commit()
    db.set_state("current_song_id", str(int(sid)))
    payload = {
        "current_song_id": int(sid),
        "song": _serialize_song(row, include_lyrics=True),
    }
    # The above row was read before vote-reset; patch for the emitted payload
    payload["song"]["votes"] = 0
    emit("current_changed", payload)
    emit("vote", {"id": int(sid), "votes": 0})
    return jsonify(payload)


@app.route("/api/admin/current", methods=["DELETE"])
def clear_current():
    with db.get_conn() as conn:
        conn.execute("DELETE FROM state WHERE key='current_song_id'")
        conn.commit()
    emit("current_changed", {"current_song_id": None, "song": None})
    return jsonify({"ok": True})


# ---------- API: admin upload ----------

@app.route("/api/admin/upload", methods=["POST"])
def upload_csv():
    f = request.files.get("file")
    if not f:
        abort(400, "file required")
    data = f.read()
    try:
        pairs = csv_import.parse_csv(data)
    except Exception as e:
        return jsonify({"error": f"failed to parse CSV: {e}"}), 400
    if not pairs:
        return jsonify({"error": "no valid (artist, song) rows found"}), 400
    started = csv_import.kick_off_refresh(pairs, emit)
    return jsonify({"started": started, "rows": len(pairs)})


@app.route("/api/admin/refresh-lyrics", methods=["POST"])
def refresh_lyrics():
    """Retry pending/errored lyrics without changing the song list."""
    with db.get_conn() as conn:
        pairs = [
            (r["artist"], r["title"])
            for r in conn.execute(
                "SELECT artist, title FROM songs"
            ).fetchall()
        ]
    started = csv_import.kick_off_refresh(pairs, emit)
    return jsonify({"started": started})


@app.route("/api/admin/songs/<int:song_id>/refetch", methods=["POST"])
def refetch_one(song_id):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM songs WHERE id=?", (song_id,)
        ).fetchone()
        if not row:
            abort(404)
        conn.execute(
            "UPDATE songs SET lyrics_status='pending', lyrics_error=NULL WHERE id=?",
            (song_id,),
        )
        conn.commit()
    emit("songs_changed", {})
    with db.get_conn() as conn:
        pairs = [
            (r["artist"], r["title"])
            for r in conn.execute("SELECT artist, title FROM songs").fetchall()
        ]
    started = csv_import.kick_off_refresh(pairs, emit)
    return jsonify({"started": started})


@app.route("/api/admin/status")
def admin_status():
    s = csv_import.status()
    with db.get_conn() as conn:
        counts = conn.execute(
            "SELECT lyrics_status, COUNT(*) AS n FROM songs GROUP BY lyrics_status"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM songs").fetchone()["n"]
    s["counts"] = {r["lyrics_status"]: r["n"] for r in counts}
    s["total"] = total
    s["genius_token_set"] = bool(os.environ.get("GENIUS_TOKEN"))
    return jsonify(s)


@app.route("/api/admin/songs")
def admin_list_songs():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, artist, title, lyrics_status, lyrics_error, "
            "       CASE WHEN lyrics IS NULL THEN 0 ELSE LENGTH(lyrics) END AS lyrics_len "
            "FROM songs ORDER BY artist COLLATE NOCASE, title COLLATE NOCASE"
        ).fetchall()
    return jsonify(
        [
            {
                "id": r["id"],
                "artist": r["artist"],
                "title": r["title"],
                "lyrics_status": r["lyrics_status"],
                "lyrics_error": r["lyrics_error"],
                "lyrics_len": r["lyrics_len"],
            }
            for r in rows
        ]
    )


@app.route("/healthz")
def healthz():
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
