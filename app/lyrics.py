import os
import re
import logging

log = logging.getLogger(__name__)

_genius = None
_genius_init_attempted = False


def _get_genius():
    global _genius, _genius_init_attempted
    if _genius is not None:
        return _genius
    if _genius_init_attempted:
        return None
    _genius_init_attempted = True

    token = os.environ.get("GENIUS_TOKEN")
    if not token:
        log.warning("GENIUS_TOKEN not set; lyrics fetching disabled")
        return None
    try:
        import lyricsgenius

        g = lyricsgenius.Genius(
            token,
            timeout=15,
            retries=2,
            remove_section_headers=True,
            skip_non_songs=True,
            verbose=False,
        )
        g.excluded_terms = ["(Remix)", "(Live)"]
        # Genius's public scraping endpoint (genius.com/api/...) blocks the
        # default python-requests User-Agent with a 403. A normal browser UA
        # gets through. The token-protected api.genius.com endpoint is fine
        # either way, but lyricsgenius 3.x uses the public one for search.
        browser_ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        try:
            g._session.headers.update({"User-Agent": browser_ua})
        except AttributeError:
            log.warning("Could not set custom User-Agent on Genius session")
        _genius = g
        return g
    except Exception as e:
        log.exception("Failed to init Genius client: %s", e)
        return None


def clean_lyrics(text: str) -> str:
    """Strip Genius page chrome that lyricsgenius leaves behind.

    Common prelude shape (all on one line, no newlines):
      "<N> ContributorsTranslations<lang>...<Song Title> Lyrics"
      then an optional description paragraph ending with "Read More"
      then the actual lyrics.

    Trailing junk: a "<N>Embed" tag glued to the last lyric line.
    Interstitials: "You might also like" block injected mid-page.
    """
    if not text:
        return text

    # 1) Discard everything up to and including the first "Lyrics" near the
    #    start (allow a generous 800 chars for the contributor/translations header).
    m = re.match(r".{0,800}?Lyrics(?=\W|$)", text, re.DOTALL)
    if m:
        text = text[m.end():]

    # 2) Discard an editorial description paragraph that ends with "Read More",
    #    but only if it appears near the top (within 2000 chars).
    m = re.match(r"\s*.{0,2000}?Read More\s*", text, re.DOTALL)
    if m:
        text = text[m.end():]

    # 3) Remove "You might also like" interstitials. Genius injects this between
    #    sections; cut from the phrase to the next blank line (or end of text).
    text = re.sub(
        r"You might also like.*?(?:\n\s*\n|\Z)",
        "\n\n",
        text,
        flags=re.DOTALL,
    )

    # 4) Concert/ticket ad block, e.g. "See A Flock of Seagulls LiveGet
    #    tickets as low as $40". The two phrases are usually glued together
    #    with no separator because they're adjacent HTML elements.
    text = re.sub(
        r"See [^\n]{1,80}?\s*Live\s*Get tickets[^\n]{0,80}?\$\d[\d.,]*",
        "",
        text,
    )

    # 5) Defensive sweep: stray "<N> Contributors" tokens that survived step 1
    #    (e.g. if "Lyrics" wasn't found in the first 800 chars).
    text = re.sub(r"\b\d+\s*Contributors?\b", "", text)

    # 6) Trailing "<N>Embed" tag — often glued onto the final lyric line.
    text = re.sub(r"\s*\d*\s*Embed\s*$", "", text)

    # 5) Old single-line cleanup: drop any leftover line that ends with "Lyrics"
    #    or "Embed" (rare but harmless).
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not cleaned_lines and stripped.endswith("Lyrics"):
            continue
        if stripped.endswith("Embed"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def fetch_lyrics(artist: str, title: str):
    """Return (lyrics_text_or_None, error_or_None)."""
    g = _get_genius()
    if g is None:
        return None, "Genius client unavailable (missing GENIUS_TOKEN?)"
    try:
        song = g.search_song(title=title, artist=artist)
    except Exception as e:
        return None, f"search error: {e}"
    if song is None or not getattr(song, "lyrics", None):
        return None, "not found"
    return clean_lyrics(song.lyrics), None
