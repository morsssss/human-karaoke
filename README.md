# Human Karaoke

Human Karaoke is a web app to run an audience-powered karaoke party, where everyone can vote for the songs the group sings!

## How to use it

Everyone opens the app on their devices. They see three tabs:
* **Songs**: a list of songs - artist and title. They can scroll around or search for a song by artist or title. Tapping on a song votes for that song.
* **Votes**: a list of songs people have voted for, each with a vote count
* **Lyrics**: lyrics for the song the group is currently singing

The **host** sees a special interface, which they access by adding `?captain` to the app URL. The host sees a special button next to each song in the "Votes" tab. Tapping that button makes that song the current song. The host can choose the song with the most votes, but they don't have to.

## Why did I make this?

Because my brain is weird, I know a ton of pop songs and can play them on the piano (or the guitar if it's just a matter of playing chords). So at parties I sometimes lead a singalong. But how do we decide what songs to sing?

So I put together a list of some of the songs I knew that other folks were likely to also know, by scraping song titles from historical US Billboard Hot 100 charts, then adding in some indie tunes and musicals. The lyrics were scraped, with mixed success, from genius.com. Problem solved!

## Running locally

You'll need Python and a browser. I tested it with Python 3.11, but I'm sure you can get it to work with other versions as well.

Clone the repository. Go to the folder where you cloned it. If you use `uv` to install dependencies, do this:

```sh
 uv venv --python 3.11
 source .venv/bin/activate
 uv pip install -r requirements.txt
```

Otherwise, you can, as they might say in one of the songs in your list, kick it old-school:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set the environment variables for the server process. You only need `GENIUS_TOKEN` if you're fetching lyrics. `DB_PATH` defaults to `./karaoke.db` and `PORT` defaults to `5000`, so you only need to set those if you want something different.

```sh
export GENIUS_TOKEN="your-genius-api-token"
export DB_PATH="./karaoke.db"
export PORT=5000
```

Then, kick off the server! One server serves both the API and the web app.

```sh
python -m app.server
```

Open [http://localhost:5000](http://localhost:5000) for the participant and captain app, or [http://localhost:5000/admin](http://localhost:5000/admin) for administration. The `.env.example` file lists the available variables, but the app does not load a `.env` file automatically. Instead, export the variables in your shell or configure them in your hosting environment.

## Admin functions

Use the admin screen at `/admin` to:

- Upload a CSV and start importing songs and fetching lyrics.
- View import progress, lyric-fetch status, and per-song errors.
- Retry missing or failed lyrics, including a single song.
- Reset vote counts without changing the song list or cached lyrics.
- Wipe the database. This deletes all songs, lyrics, votes, and the current-song selection, and cannot be undone.

The admin screen and captain controls don't require authentication. We trust people.

## Changing the songs

On the admin screen, you can upload a CSV file with artist and song-title columns. It recognizes these column names:

- Artist: `artist`, `artists`, or `performer`
- Song title: `song`, `title`, `song title`, `track`, or `song_title`

Rows without both values are ignored, and duplicate artist/title pairs are removed. Uploading a CSV replaces the current list. Matching songs keep their cached lyrics; new songs are added and queued for lyric lookup. Votes and the current-song selection are reset on import.

The repository includes [`songs-5-31-26.csv`](./songs-5-31-26.csv) as an example setlist. If you want to grab more songs from Billboard charts, check out `utils/fetch-billboard.py`. That's what I used. It needs a couple of extra packages, and it writes an Excel file, not a CSV:

```sh
pip install billboard.py openpyxl
python utils/fetch-billboard.py
```

This creates `billboard_songs.xlsx`. Edit it however you like, then export it as CSV before uploading. Its `Artist` and `Song Title` columns already match what the importer expects.

The app uses [`lyricsgenius`](https://lyricsgenius.readthedocs.io/en/master/) to scrape lyrics from genius.com. Lookups run in the background, and the admin screen shows progress and the status of each song. You can retry missing or failed lyrics there.

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

This project uses the MIT License; see [`LICENSE`](./LICENSE).
