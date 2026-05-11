"""Search operations over an inverted index."""

from __future__ import annotations

from src.indexer import Index
from src.ranker import Ranker, TFIDFRanker
from src.retrieval import conjunctive_retrieval, phrase_retrieval
from src.snippet import extract_snippet
from src.suggest import suggest_corrections
from src.tokenizer import tokenize


def print_word(index: Index, word: str) -> dict[str, object]:
    """Return the posting list for one word, keyed by URL for display.

    Postings are stored against integer doc_ids internally; this view
    translates them back to URLs via :attr:`Index.documents` so the
    user sees the same shape they'd expect from the brief's example
    (``> print nonsense`` → URL → ``{frequency, positions}``).

    The query is tokenised under the index's stored
    :class:`~src.tokenizer.TokenizerConfig`, so if the index was built
    with stemming enabled the user can still print by the un-stemmed
    word (e.g. ``print running`` finds the stem ``run``).
    """
    tokens = tokenize(word, index.tokenizer_config)
    if not tokens:
        return {}
    raw = index.postings.get(tokens[0], {})
    return {index.documents[doc_id]: posting for doc_id, posting in raw.items()}


def find_pages(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[str]:
    """Find pages containing every query token, ordered by relevance.

    Two-stage retrieval (Lecture 13 conjunctive processing followed by
    Lecture 12 ranking), implemented by delegation:

    1. :func:`~src.retrieval.conjunctive_retrieval` walks the sorted
       posting lists in lock-step (Lecture 13's "Processing Conjunctive
       Queries, Simple Algorithm") to keep only documents that contain
       *every* query token. This honours the brief's "all pages
       containing the words 'good' and 'friends'" requirement.
    2. The same call scores the surviving candidates with ``ranker``
       (TF-IDF by default) and orders them by score descending. Ties
       on score break on doc_id ascending so the order is deterministic.

    The query is tokenised under ``index.tokenizer_config`` so the same
    stemming / stopword choices that produced the index also apply to
    the query — keeping the two sides consistent.

    Returns:
        URLs ordered by relevance. The doc_id → URL mapping comes
        from :attr:`Index.documents`.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = conjunctive_retrieval(index, tokens, ranker)
    return [index.documents[doc_id] for doc_id, _ in results]


def find_phrase(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[str]:
    """Find pages where the query tokens occur as a consecutive phrase.

    Stricter than :func:`find_pages`: every query token must appear
    *adjacent and in order* in the document, not merely co-present.
    Routed via :func:`~src.retrieval.phrase_retrieval` which uses the
    position-offset intersection trick described in Lecture 13's
    "advanced query processing" topic.

    Surfaced by the CLI as ``find "good friends"`` — the quoted form
    disambiguates phrase intent from the conjunctive form
    ``find good friends`` that the brief specifies for unquoted input.

    The query is tokenised under ``index.tokenizer_config`` so the
    phrase match operates on the same vocabulary as the index.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = phrase_retrieval(index, tokens, ranker)
    return [index.documents[doc_id] for doc_id, _ in results]


def find_pages_with_snippets(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[tuple[str, str]]:
    """Find pages plus a highlighted context snippet for each result.

    Same retrieval contract as :func:`find_pages` (conjunctive match
    on ``query`` tokens, ranked by ``ranker`` defaulting to TF-IDF),
    but each entry pairs the URL with a short body excerpt produced
    by :func:`src.snippet.extract_snippet`. The snippet anchors on
    the earliest matching token in the body, with every query token
    occurrence wrapped in ``[brackets]`` for visual emphasis.

    A pre-v1.4.0 (INDEX_VERSION 4) index loaded into the current
    process would have an empty :attr:`Index.documents_text`; this
    function then returns an empty snippet string for that document,
    keeping the URL portion of the result intact. Rebuild via the
    ``build`` command to restore snippets.

    Returns:
        ``[(url, snippet), ...]`` ordered by relevance. Order matches
        :func:`find_pages` exactly so existing relevance tests
        transfer.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = conjunctive_retrieval(index, tokens, ranker)
    pairs: list[tuple[str, str]] = []
    for doc_id, _ in results:
        url = index.documents[doc_id]
        body = index.documents_text.get(doc_id, "")
        snippet = extract_snippet(body, tokens) if body else ""
        pairs.append((url, snippet))
    return pairs


def find_phrase_with_snippets(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
) -> list[tuple[str, str]]:
    """Phrase-mode counterpart of :func:`find_pages_with_snippets`.

    Retrieves pages where the query tokens occur as a consecutive
    phrase (same contract as :func:`find_phrase`) and produces a
    snippet for each, anchored on and highlighting the whole phrase
    as one bracketed unit (``[good friends]`` rather than
    ``[good] [friends]``). This mirrors the user's intent — they
    asked for a phrase, the result presentation should respect it.
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    results = phrase_retrieval(index, tokens, ranker)
    pairs: list[tuple[str, str]] = []
    for doc_id, _ in results:
        url = index.documents[doc_id]
        body = index.documents_text.get(doc_id, "")
        snippet = (
            extract_snippet(body, tokens, phrase_mode=True) if body else ""
        )
        pairs.append((url, snippet))
    return pairs


def suggest_for_query(
    index: Index,
    query: str,
    *,
    max_distance: int = 2,
    max_suggestions: int = 3,
) -> dict[str, list[str]]:
    """Return spelling suggestions for unknown tokens in ``query``.

    Tokenises ``query`` under :attr:`Index.tokenizer_config` (so the
    same lowercasing / stopword / stemming that shaped the index also
    shapes the suggestion check) and looks up each token in the
    index's posting-list vocabulary. Tokens already in the vocabulary
    are omitted from the returned mapping — they are not typo
    candidates and surfacing synonyms would clutter the CLI.

    Returns:
        Mapping ``{unknown_token: [candidate_1, ...]}`` sorted by
        edit distance ascending. The mapping is empty when every
        query token is already in the vocabulary; an unknown token
        with no candidate within ``max_distance`` is included with
        an empty list (caller distinguishes "fine" from "no help").
    """
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return {}
    return suggest_corrections(
        tokens,
        index.postings.keys(),
        max_distance=max_distance,
        max_suggestions=max_suggestions,
    )


def format_did_you_mean(
    index: Index,
    query: str,
) -> str | None:
    """Return a CLI-ready ``"Did you mean: ...?"`` hint, or ``None``.

    Hints are query reformulations rather than per-token candidate
    lists — the user can copy-paste the suggested line directly into
    a new ``find`` invocation. Unknown tokens are replaced by their
    top candidate (lowest edit distance, alpha-sorted on ties);
    known tokens pass through verbatim so the reformulation reads
    naturally.

    Returns ``None`` — i.e. the CLI prints nothing — when:

    * the query is empty after tokenisation, or
    * every token is already in the vocabulary (the zero-result case
      is then a strict-AND fail, not a typo, and a "Did you mean"
      hint would mislead), or
    * at least one token is unknown but *no* unknown token has any
      candidate within the distance threshold (nothing useful to say).
    """
    suggestions = suggest_for_query(index, query)
    if not any(candidates for candidates in suggestions.values()):
        return None

    tokens = tokenize(query, index.tokenizer_config)
    reformulated: list[str] = []
    for tok in tokens:
        candidates = suggestions.get(tok)
        if candidates:
            reformulated.append(candidates[0])
        else:
            # Either a known token (passthrough) or an unknown one
            # with no candidate (keep the user's spelling so the
            # hint still surfaces every word they typed).
            reformulated.append(tok)
    return f"Did you mean: {' '.join(reformulated)}?"
