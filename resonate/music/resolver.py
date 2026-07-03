"""Turn user input (URL or free text) into a Track."""

import logging
import re

from . import extractor, ytmusic
from .track import Track

log = logging.getLogger(__name__)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(query: str) -> bool:
    return bool(_URL_RE.match(query.strip()))


async def resolve_track(query: str) -> Track:
    """Resolve a URL or free-text query to a single Track.

    Free text is searched on YouTube Music first, falling back to a plain
    YouTube search for anything YouTube Music doesn't index.

    Raises extractor.ExtractionError when nothing could be found.
    """
    query = query.strip()
    if is_url(query):
        return await extractor.resolve(query)
    try:
        results = await ytmusic.search_songs(query, limit=1)
    except Exception:
        log.warning("YouTube Music search failed for %r, falling back to yt-dlp", query)
        results = []
    if results:
        return results[0]
    return await extractor.resolve(f"ytsearch1:{query}")
