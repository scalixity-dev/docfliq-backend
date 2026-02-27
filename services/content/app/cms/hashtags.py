"""Hashtag extraction and normalization utilities."""

import re
from html import unescape

# Match #word patterns: must start with a letter after #, 2-50 chars tag name
HASHTAG_PATTERN = re.compile(r"#([A-Za-z][A-Za-z0-9_]{1,49})")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def extract_hashtags(body: str | None) -> list[str]:
    """Extract unique hashtags from post body (HTML or plain text).

    Returns lowercase tag names without '#' prefix, deduplicated,
    preserving first-occurrence order. Max 30 hashtags per post.
    """
    if not body:
        return []
    # Strip HTML tags for extraction from rich-text bodies
    plain = HTML_TAG_PATTERN.sub(" ", unescape(body))
    seen: set[str] = set()
    result: list[str] = []
    for match in HASHTAG_PATTERN.finditer(plain):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
        if len(result) >= 30:
            break
    return result
