"""Snippet generation for search results.

Given the raw body text of a matching document plus the user's query
tokens, produce a short (~60-80 character) excerpt of the body
centred on the first match, with the matching terms wrapped in
``[brackets]`` for visual emphasis.

References:
* Manning, Raghavan & Schutze, *Introduction to Information
  Retrieval*, Ch. 8.7 "Summarization and snippet generation". The
  "static" snippet strategy quotes a fixed window around the first
  match — what this module implements. Dynamic snippets (selecting
  sentences ranked by query-term density) are out of scope.

Design notes:

* Matching is done against the **raw body text** via case-insensitive
  word-boundary regex, not via the tokeniser. This preserves the
  user's original case in the highlight (``[Good]`` not ``[good]``)
  and avoids re-running tokenisation per snippet call. Trade-off:
  when the index was built with stemming enabled, a query token like
  ``run`` will not surface a snippet on a document whose body contains
  only ``running`` — see the project README for the explicit limitation.
* Window boundaries are snapped to whitespace so the snippet does not
  start or end mid-word. Whitespace inside the snippet is collapsed
  to single spaces so multi-line bodies still produce a one-line
  excerpt suitable for the CLI.
* ``[token]`` markup rather than ANSI colour codes — easier to assert
  against in tests, renders identically on every terminal, and copies
  cleanly into video screen recordings.
"""

from __future__ import annotations

import re

DEFAULT_WINDOW_CHARS = 70
# How far the window may grow past its nominal edges to align with a
# whitespace boundary. English words average ~5 chars; 20 covers
# unusually long words (~"institutionalisation") without letting a
# pathological no-whitespace run (e.g. base64 noise in a scraped page)
# eat the entire body. Hitting the slack cap simply falls back to a
# mid-word cut — the ellipsis prefix/suffix signals truncation either
# way, so the cosmetic loss is small.
WORD_SNAP_SLACK = 20
ELLIPSIS = "..."


def extract_snippet(
    body: str,
    query_tokens: list[str],
    *,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    phrase_mode: bool = False,
) -> str:
    """Return a short body excerpt with query matches highlighted.

    Args:
        body: The full body text of the matching document.
        query_tokens: Tokens from the user's query, already lowercased
            by the tokeniser. The tokens are matched against the raw
            body text case-insensitively, so any case in ``body`` is
            acceptable.
        window_chars: Total context characters around the anchor
            match (half before, half after). The matched token itself
            adds to the visible length; window boundary alignment to
            whitespace may add a few more characters per side.
        phrase_mode: If ``True``, search for and highlight the entire
            query as a consecutive phrase (e.g. ``[good friends]``)
            instead of each token independently (e.g. ``[good] ... [friends]``).
            Mirrors the find / find-phrase split on the search layer.

    Returns:
        The formatted snippet string. Returns an empty string when no
        query token appears in ``body`` — a defensive fallback for the
        rare case where the index says the document matches but the
        raw body cannot confirm (usually because stemming or other
        tokenisation rules transformed the index keys away from the
        original surface form).
    """
    if not body or not query_tokens:
        return ""

    half = max(window_chars // 2, 1)
    matches_pattern = _build_pattern(query_tokens, phrase_mode)

    anchor = matches_pattern.search(body)
    if anchor is None:
        return ""

    win_start, win_end = _expand_to_word_boundaries(
        body, anchor.start() - half, anchor.end() + half
    )

    excerpt = body[win_start:win_end]
    # Collapse internal whitespace (newlines, tabs, runs of spaces)
    # to single spaces so the snippet renders cleanly on one line.
    # ``str.split`` with no argument splits on any whitespace run.
    excerpt = " ".join(excerpt.split())
    excerpt = matches_pattern.sub(lambda m: f"[{m.group(0)}]", excerpt)

    # Mark mid-body truncation. We omit ellipses when the snippet
    # already starts at index 0 or ends at len(body) so the reader
    # is not misled into thinking content was cut where it wasn't.
    prefix = f"{ELLIPSIS} " if win_start > 0 else ""
    suffix = f" {ELLIPSIS}" if win_end < len(body) else ""

    return f"{prefix}{excerpt}{suffix}"


def _build_pattern(query_tokens: list[str], phrase_mode: bool) -> re.Pattern[str]:
    """Compile a case-insensitive regex for the configured match mode.

    Phrase mode joins tokens with ``\\s+`` so the phrase still matches
    when the body separates the tokens with arbitrary whitespace
    (multiple spaces, tabs, newlines) — common when the parser
    concatenates structural fields.

    Conjunctive mode produces ``\\b(t1|t2|...)\\b`` so a single regex
    scan finds the earliest match across all tokens; ``\\b`` prevents
    the classic "good matches goodness" false positive.
    """
    if phrase_mode:
        pattern = r"\b" + r"\s+".join(re.escape(t) for t in query_tokens) + r"\b"
        return re.compile(pattern, re.IGNORECASE)
    alternation = "|".join(re.escape(t) for t in query_tokens)
    return re.compile(r"\b(?:" + alternation + r")\b", re.IGNORECASE)


def _expand_to_word_boundaries(body: str, start: int, end: int) -> tuple[int, int]:
    """Push the (start, end) window outward to the nearest whitespace.

    Slicing ``body[start:end]`` directly can cut mid-word: e.g. window
    [10:80] of "...friendship is..." chops "friendship" into "endship".
    Expanding outward to whitespace keeps the anchored match visible
    and produces snippets that read as sentence fragments rather than
    truncated words.

    Expansion is capped at :data:`WORD_SNAP_SLACK` per side. If no
    whitespace exists within that slack (long base64 blob, no-space
    code fragment, …), we keep the original cut — the ellipsis
    prefix/suffix that ``extract_snippet`` adds still signals to the
    reader that content was truncated.
    """
    n = len(body)
    start = max(0, start)
    end = min(n, end)
    bound_left = max(0, start - WORD_SNAP_SLACK)
    bound_right = min(n, end + WORD_SNAP_SLACK)

    # Walk left within the slack window looking for whitespace; if we
    # hit the slack bound first, restore the original cut.
    new_start = start
    while new_start > bound_left and not body[new_start - 1].isspace():
        new_start -= 1
    if new_start > 0 and not body[new_start - 1].isspace():
        new_start = start

    new_end = end
    while new_end < bound_right and not body[new_end].isspace():
        new_end += 1
    if new_end < n and not body[new_end].isspace():
        new_end = end

    return new_start, new_end
