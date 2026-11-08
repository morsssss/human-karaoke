# Human Karaoke

Human Karaoke is a web app for running an audience-powered karaoke session. Guests open the app on their phones, browse a prepared song list, and vote for the songs they want to hear. The host uses the captain view to choose the next song; the app then displays its lyrics for the room.

The name comes from the original format: the host played the songs on piano while everyone sang. You can also use the app with karaoke tracks or another way of performing the songs.

## How to use it

1. Start the app and prepare a setlist in the admin screen at `/admin`.
2. Share the main app URL with participants. They can search the list, tap songs to vote, and see the live vote totals.
3. Open the main app URL with `?captain` appended (for example, `https://your-app.example/?captain`). The captain view adds controls to the vote list so the host can select a song as the current song.
4. Open the Lyrics tab to show the selected song's lyrics. The display updates for everyone connected to the app.

Participants can vote for multiple songs. A checkmark on a phone indicates that the song has been voted for from that browser; it is a convenience for participants, not an account-based voting restriction.

## Set up the song list and lyrics

The admin screen accepts a CSV file with artist and song-title columns. It recognizes these column names:

- Artist: `artist`, `artists`, or `performer`
- Song title: `song`, `title`, `song title`, `track`, or `song_title`

Rows without both values are ignored, and duplicate artist/title pairs are removed. Uploading a CSV replaces the current list. Matching songs keep their cached lyrics; new songs are added and queued for lyric lookup. Votes and the current-song selection are reset on import.

The repository includes [`songs-5-31-26.csv`](./songs-5-31-26.csv) as an example setlist. Song lists can be assembled from any source. A Billboard-derived list can also be prepared as a spreadsheet and exported to CSV before uploading.

Lyrics are looked up using Genius through the `lyricsgenius` package. Set a Genius API access token as `GENIUS_TOKEN` for lyric fetching. Without it, the song list and voting still work, but lyrics cannot be fetched. Lookups run in the background, and the admin screen shows progress and the status of each song. You can retry missing or failed lyrics there.

## Run locally

The project targets Python 3.11. From the repository root:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set the environment variables for the server process. `GENIUS_TOKEN` is optional if you do not need automatic lyrics fetching.

```sh
export GENIUS_TOKEN="your-genius-api-token"
export DB_PATH="./karaoke.db"
export PORT=5000
python -m app.server
```

Open [http://localhost:5000](http://localhost:5000) for the participant and captain app, or [http://localhost:5000/admin](http://localhost:5000/admin) for administration. The `.env.example` file lists the available variables, but the app does not load a `.env` file automatically; export the variables in your shell or configure them in your hosting environment.

## Admin screen

The admin screen at `/admin` can:

- Upload a CSV and start importing songs and fetching lyrics.
- View import progress, lyric-fetch status, and per-song errors.
- Retry missing or failed lyrics, including a single song.
- Reset vote counts without changing the song list or cached lyrics.
- Wipe the database. This deletes all songs, lyrics, votes, and the current-song selection, and cannot be undone.

The admin screen and captain controls do not require authentication. Do not expose this app to an untrusted audience without adding access controls or otherwise restricting access.

## How it works

- **Web app:** Flask serves the mobile-friendly participant and admin pages, along with a JSON API.
- **Live updates:** Flask-SocketIO broadcasts vote, current-song, and import-progress updates to connected browsers.
- **Storage:** SQLite stores songs, lyrics, lyric-fetch status, vote counts, and the current-song selection. Set `DB_PATH` to choose the database file.
- **Imports and lyrics:** The CSV importer matches existing songs by artist and title, preserving their cached lyrics. New songs are looked up asynchronously through Genius; lyrics and lookup status are saved in SQLite.
- **Session state:** On process startup, the app resets votes and clears the current song while retaining the song list and cached lyrics. CSV imports also reset votes and clear the current song.

The captain query parameter only changes the browser interface; it is not authentication. Likewise, vote markers are kept in each browser's local storage, while vote totals are stored by the server.

## Deployment

The repository includes a `Procfile` and Railway configuration. The configured start command runs Gunicorn with one worker and eight threads. Keep one worker: the app's Socket.IO broadcasts and background import/lyrics job use in-process state.

Configure `GENIUS_TOKEN` and `PORT` in the hosting environment. For deployments where the filesystem is not persistent, attach persistent storage and set `DB_PATH` to a location on that storage; otherwise the database, song list, and cached lyrics may be lost when the service restarts or is redeployed. Votes and current-song selection are reset on every process start in either case.

## License

This project is distributed under the MIT License; see [`LICENSE`](./LICENSE).
