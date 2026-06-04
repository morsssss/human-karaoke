(function () {
  const params = new URLSearchParams(window.location.search);
  const isCaptain = params.has("captain");
  if (isCaptain) {
    document.body.classList.add("is-captain");
    const header = document.querySelector(".app-header");
    if (header) {
      const badge = document.createElement("span");
      badge.className = "captain-badge";
      badge.textContent = "CAPTAIN";
      header.appendChild(badge);
    }
  }

  // Phosphor "piano-keys" (duotone), tweaked: currentColor + 22px.
  const PROMOTE_ICON = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="currentColor" viewBox="0 0 256 256" aria-hidden="true"><path d="M184,40V144H144V40ZM72,144h40V40H72Z" opacity="0.2"></path><path d="M208,32H48A16,16,0,0,0,32,48V208a16,16,0,0,0,16,16H208a16,16,0,0,0,16-16V48A16,16,0,0,0,208,32ZM80,48h24v88H80Zm32,104a8,8,0,0,0,8-8V48h16v96a8,8,0,0,0,8,8h8v56H104V152Zm40-16V48h24v88ZM48,48H64v96a8,8,0,0,0,8,8H88v56H48ZM208,208H168V152h16a8,8,0,0,0,8-8V48h16V208Z"></path></svg>`;

  // ---- State ----
  let songs = [];               // [{id,artist,title,votes,lyrics_status}]
  let songIndex = new Map();    // id -> song
  let current = { id: null, song: null };
  let searchTerm = "";
  let activeTab = "songs";

  // Per-device record of which songs *this* phone has voted on, so we can
  // give tactile feedback (tint + ✅) without the server having to know.
  const VOTED_KEY = "hr91.votedIds";
  function loadVotedIds() {
    try {
      const raw = localStorage.getItem(VOTED_KEY);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch (e) {
      return new Set();
    }
  }
  function saveVotedIds() {
    try {
      localStorage.setItem(VOTED_KEY, JSON.stringify([...votedIds]));
    } catch (e) {
      /* localStorage full or disabled — feedback degrades to in-memory only */
    }
  }
  let votedIds = loadVotedIds();

  // ---- DOM ----
  const $search = document.getElementById("search");
  const $songList = document.getElementById("song-list");
  const $songsEmpty = document.getElementById("songs-empty");
  const $voteList = document.getElementById("vote-list");
  const $votesEmpty = document.getElementById("votes-empty");
  const $lyricsMeta = document.getElementById("lyrics-meta");
  const $lyricsBody = document.getElementById("lyrics-body");
  const $lyricsEmpty = document.getElementById("lyrics-empty");

  // ---- Tabs ----
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  function switchTab(name) {
    activeTab = name;
    document.querySelectorAll(".tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    document.querySelectorAll(".pane").forEach((p) => {
      p.classList.toggle("active", p.id === "pane-" + name);
    });
  }

  // ---- Rendering ----
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    }[c]));
  }

  function matches(song, term) {
    if (!term) return true;
    const t = term.toLowerCase();
    return (
      song.artist.toLowerCase().includes(t) ||
      song.title.toLowerCase().includes(t)
    );
  }

  function renderSongList() {
    const filtered = songs.filter((s) => matches(s, searchTerm));
    $songsEmpty.hidden = songs.length !== 0;
    if (songs.length === 0) {
      $songList.innerHTML = "";
      return;
    }
    $songList.innerHTML = filtered
      .map(
        (s) =>
          `<li data-id="${s.id}"${votedIds.has(s.id) ? ' class="voted"' : ""}>` +
          `<span class="check"></span>` +
          `<span class="artist">${escapeHtml(s.artist)}</span>` +
          `<span class="title">${escapeHtml(s.title)}</span>` +
          `</li>`
      )
      .join("");
  }

  function renderVoteList() {
    const voted = songs
      .filter((s) => s.votes > 0)
      .sort((a, b) => b.votes - a.votes || a.artist.localeCompare(b.artist));
    $votesEmpty.hidden = voted.length > 0;
    $voteList.innerHTML = voted
      .map(
        (s) =>
          `<li data-id="${s.id}">` +
          `<span class="count">${s.votes}</span>` +
          `<span class="artist">${escapeHtml(s.artist)}</span>` +
          `<span class="title">${escapeHtml(s.title)}</span>` +
          (isCaptain
            ? `<button class="promote" data-promote="${s.id}" aria-label="Make this the current song">${PROMOTE_ICON}</button>`
            : "") +
          `</li>`
      )
      .join("");
  }

  function renderLyrics() {
    if (!current.song) {
      $lyricsEmpty.hidden = false;
      $lyricsMeta.textContent = "";
      $lyricsBody.textContent = "";
      return;
    }
    $lyricsEmpty.hidden = true;
    const { artist, title, lyrics, lyrics_status, lyrics_error } = current.song;
    $lyricsMeta.innerHTML =
      `<span class="artist">${escapeHtml(artist)}</span>` +
      `<span class="title">${escapeHtml(title)}</span>`;
    if (lyrics) {
      $lyricsBody.textContent = lyrics;
    } else if (lyrics_status === "pending") {
      $lyricsBody.textContent = "Fetching lyrics…";
    } else if (lyrics_status === "not_found") {
      $lyricsBody.textContent = "Oh noes! We couldn't find the lyrics. But surely you have this memorized.";
    } else if (lyrics_status === "error") {
      $lyricsBody.textContent = "Could not fetch lyrics" + (lyrics_error ? `: ${lyrics_error}` : "");
    } else {
      $lyricsBody.textContent = "";
    }
  }

  function flashRow(list, id) {
    const li = list.querySelector(`li[data-id="${id}"]`);
    if (li) {
      li.classList.remove("flash");
      // re-trigger animation
      void li.offsetWidth;
      li.classList.add("flash");
    }
  }

  // ---- Events ----
  $search.addEventListener("input", (e) => {
    searchTerm = e.target.value;
    renderSongList();
  });

  $songList.addEventListener("click", async (e) => {
    const li = e.target.closest("li[data-id]");
    if (!li) return;
    const id = Number(li.dataset.id);
    if (votedIds.has(id)) return; // already voted from this device

    // Optimistic UI: flip to the "voted" state immediately so the row
    // doesn't flash back to its original color while the POST is in flight
    // on slower connections. Roll back if the server rejects.
    li.classList.add("voted");
    votedIds.add(id);
    saveVotedIds();
    try {
      const r = await fetch(`/api/songs/${id}/vote`, { method: "POST" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      // Server will also broadcast 'vote' for the count update.
    } catch (err) {
      console.error(err);
      li.classList.remove("voted");
      votedIds.delete(id);
      saveVotedIds();
    }
  });

  $voteList.addEventListener("click", async (e) => {
    if (!isCaptain) return;
    const btn = e.target.closest("button[data-promote]");
    if (!btn) return;
    const id = Number(btn.dataset.promote);
    try {
      const r = await fetch(`/api/admin/current`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ song_id: id }),
      });
      if (r.ok) switchTab("lyrics");
    } catch (err) {
      console.error(err);
    }
  });

  // ---- Data loading ----
  async function loadSongs() {
    const r = await fetch("/api/songs");
    songs = await r.json();
    songIndex = new Map(songs.map((s) => [s.id, s]));
    renderSongList();
    renderVoteList();
  }
  async function loadCurrent() {
    const r = await fetch("/api/state/current");
    const data = await r.json();
    current = { id: data.current_song_id, song: data.song };
    renderLyrics();
  }

  // ---- Socket.IO ----
  const socket = io({ transports: ["websocket", "polling"] });
  socket.on("vote", ({ id, votes }) => {
    const s = songIndex.get(id);
    if (!s) return;
    s.votes = votes;
    renderVoteList();
    if (activeTab === "votes") flashRow($voteList, id);
  });
  socket.on("current_changed", (payload) => {
    current = { id: payload.current_song_id, song: payload.song };
    if (current.song) {
      const s = songIndex.get(current.song.id);
      if (s) s.votes = 0;
    }
    renderVoteList();
    renderLyrics();
  });
  socket.on("songs_changed", () => {
    // Song IDs may no longer mean what they used to (CSV reupload, wipe).
    // Drop the per-device voted record so checkmarks don't lie.
    votedIds = new Set();
    saveVotedIds();
    loadSongs();
    loadCurrent();
  });

  loadSongs();
  loadCurrent();
})();
