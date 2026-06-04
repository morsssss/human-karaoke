(function () {
  const $form = document.getElementById("upload-form");
  const $file = document.getElementById("file");
  const $uploadBtn = document.getElementById("upload-btn");
  const $uploadMsg = document.getElementById("upload-msg");
  const $statusSummary = document.getElementById("status-summary");
  const $progress = document.getElementById("progress");
  const $progressFill = document.getElementById("progress-fill");
  const $progressLabel = document.getElementById("progress-label");
  const $refreshBtn = document.getElementById("refresh-btn");
  const $reloadBtn = document.getElementById("reload-btn");
  const $songsBody = document.getElementById("songs-body");
  const $filter = document.getElementById("filter");

  let songs = [];
  let filterTerm = "";

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    }[c]));
  }

  async function loadSongs() {
    const r = await fetch("/api/admin/songs");
    songs = await r.json();
    renderSongs();
  }

  function renderSongs() {
    const term = filterTerm.toLowerCase();
    const rows = songs
      .filter((s) =>
        !term ||
        s.artist.toLowerCase().includes(term) ||
        s.title.toLowerCase().includes(term)
      )
      .map(
        (s) =>
          `<tr data-id="${s.id}">` +
          `<td>${escapeHtml(s.artist)}</td>` +
          `<td>${escapeHtml(s.title)}</td>` +
          `<td><span class="status-tag ${s.lyrics_status}">${s.lyrics_status}</span>` +
          (s.lyrics_error
            ? `<div class="muted">${escapeHtml(s.lyrics_error)}</div>`
            : "") +
          `</td>` +
          `<td>${s.lyrics_len ? s.lyrics_len + " chars" : "—"}</td>` +
          `<td><button class="mini secondary" data-refetch="${s.id}">Re-fetch</button></td>` +
          `</tr>`
      )
      .join("");
    $songsBody.innerHTML = rows || `<tr><td colspan="5" class="muted">No songs yet.</td></tr>`;
  }

  async function loadStatus() {
    const r = await fetch("/api/admin/status");
    const s = await r.json();
    const c = s.counts || {};
    const pill = (k, n) => `<span class="pill ${k}">${k}: ${n}</span>`;
    const parts = [
      `<span class="pill">total: ${s.total}</span>`,
      pill("found", c.found || 0),
      pill("pending", c.pending || 0),
      pill("not_found", c.not_found || 0),
      pill("error", c.error || 0),
    ];
    if (!s.genius_token_set) {
      parts.push(`<span class="pill error">GENIUS_TOKEN not set</span>`);
    }
    $statusSummary.innerHTML = parts.join("");
    $refreshBtn.disabled = s.running;
    $uploadBtn.disabled = s.running;
    if (!s.running) {
      $progress.hidden = true;
    }
  }

  $filter.addEventListener("input", (e) => {
    filterTerm = e.target.value;
    renderSongs();
  });

  $form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!$file.files[0]) return;
    const fd = new FormData();
    fd.append("file", $file.files[0]);
    $uploadMsg.textContent = "Uploading…";
    $uploadBtn.disabled = true;
    try {
      const r = await fetch("/api/admin/upload", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok) {
        $uploadMsg.textContent = data.error || "Upload failed";
      } else {
        $uploadMsg.textContent = `Queued refresh of ${data.rows} rows.`;
        $progress.hidden = false;
        $progressFill.style.width = "0%";
        $progressLabel.textContent = "Starting…";
      }
    } catch (err) {
      $uploadMsg.textContent = "Network error: " + err.message;
    } finally {
      loadStatus();
    }
  });

  $refreshBtn.addEventListener("click", async () => {
    $refreshBtn.disabled = true;
    await fetch("/api/admin/refresh-lyrics", { method: "POST" });
    $progress.hidden = false;
    $progressFill.style.width = "0%";
    $progressLabel.textContent = "Starting…";
    loadStatus();
  });

  $reloadBtn.addEventListener("click", () => {
    loadStatus();
    loadSongs();
  });

  const $resetVotesBtn = document.getElementById("reset-votes-btn");
  const $resetVotesMsg = document.getElementById("reset-votes-msg");
  $resetVotesBtn.addEventListener("click", async () => {
    if (!confirm("Reset every song's vote count to 0? Connected phones will lose their ✅ checkmarks.")) return;
    $resetVotesBtn.disabled = true;
    $resetVotesMsg.textContent = "Resetting…";
    try {
      const r = await fetch("/api/admin/reset-votes", { method: "POST" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      $resetVotesMsg.textContent = "Votes reset.";
    } catch (err) {
      $resetVotesMsg.textContent = "Failed: " + err.message;
    } finally {
      $resetVotesBtn.disabled = false;
    }
  });

  const $wipeBtn = document.getElementById("wipe-btn");
  const $wipeMsg = document.getElementById("wipe-msg");
  $wipeBtn.addEventListener("click", async () => {
    if (!confirm("Delete every song, lyric, and vote? This cannot be undone.")) return;
    $wipeBtn.disabled = true;
    $wipeMsg.textContent = "Wiping…";
    try {
      const r = await fetch("/api/admin/wipe", { method: "POST" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      $wipeMsg.textContent = "Wiped.";
      loadStatus();
      loadSongs();
    } catch (err) {
      $wipeMsg.textContent = "Failed: " + err.message;
    } finally {
      $wipeBtn.disabled = false;
    }
  });

  $songsBody.addEventListener("click", async (e) => {
    const id = e.target.dataset.refetch;
    if (!id) return;
    e.target.disabled = true;
    await fetch(`/api/admin/songs/${id}/refetch`, { method: "POST" });
    loadStatus();
  });

  // Socket updates
  const socket = io({ transports: ["websocket", "polling"] });
  socket.on("refresh_progress", (ev) => {
    $progress.hidden = false;
    if (ev.event === "lyrics_start") {
      $progressFill.style.width = "0%";
      $progressLabel.textContent = `Fetching ${ev.total} lyrics…`;
    } else if (ev.event === "lyrics_progress") {
      const pct = ev.total ? Math.round((ev.done / ev.total) * 100) : 0;
      $progressFill.style.width = pct + "%";
      $progressLabel.textContent = `${ev.done}/${ev.total} — ${ev.artist} — ${ev.title} (${ev.status})`;
    } else if (ev.event === "import_done") {
      $progressLabel.textContent = `Imported: ${ev.inserted} new, ${ev.kept} kept, ${ev.deleted} removed`;
      loadSongs();
    } else if (ev.event === "lyrics_done") {
      $progressFill.style.width = "100%";
      $progressLabel.textContent = `Done — found: ${ev.found}, not found: ${ev.not_found}, errors: ${ev.errored}`;
    }
  });
  socket.on("refresh_done", () => {
    loadStatus();
    loadSongs();
  });
  socket.on("songs_changed", () => {
    loadSongs();
    loadStatus();
  });

  loadStatus();
  loadSongs();
})();
