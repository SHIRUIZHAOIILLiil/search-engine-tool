"""Search operations over an inverted index."""

from __future__ import annotations

from typing import Iterable

from src.indexer import FIELD_NAMES, Index
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


def parse_facets(
    args: list[str],
    valid_fields: tuple[str, ...] = FIELD_NAMES,
) -> tuple[dict[str, list[str]], str]:
    """Split CLI args into structural facet filters and free-text tokens.

    A facet has the shape ``field=value`` (e.g. ``author=einstein``).
    Args without an ``=`` are free-text tokens and join into the
    query body that ``find_pages`` / ``find_phrase`` consume — this
    is what preserves the brief's plain ``find good friends`` form:
    a query that contains zero ``=`` characters routes through
    exactly the same path it did before v1.5.0.

    Multiple values for the same field (e.g. ``tag=science tag=physics``)
    are *disjunctive* (OR) — matching the conventional facet UI
    behaviour where ticking two tags under one heading widens the
    result set. Across different fields, facets are conjunctive (AND);
    that combination is enforced by the caller, not this parser.

    Args:
        args: Tokens already produced by ``shlex.split`` of the CLI
            input. Quoted values like ``author="oscar wilde"`` arrive
            as a single argument here — shlex strips the quotes.
        valid_fields: Allowed left-hand sides of ``=``. Defaults to
            :data:`src.indexer.FIELD_NAMES`. Anything else raises so
            the user sees ``Unknown facet field: foo`` rather than
            having their typo silently match zero documents.

    Returns:
        ``({field: [value, ...]}, free_text)`` where ``free_text`` is
        the space-joined non-facet args (an empty string if every
        arg was a facet — facet-only queries are valid).

    Raises:
        ValueError: if a facet uses an unknown field, has an empty
            value (``author=``), or has an empty field (``=value``).
    """
    facets: dict[str, list[str]] = {}
    free_tokens: list[str] = []
    valid_set = set(valid_fields)

    for arg in args:
        if "=" not in arg:
            free_tokens.append(arg)
            continue

        field, _, value = arg.partition("=")
        # Normalise the field name to the canonical lowercase form
        # so that ``Author=Einstein`` works the same as ``author=einstein``.
        # Values are *not* normalised here; the retrieval layer
        # applies the tokeniser when comparing them against postings,
        # which handles case-folding consistently with the index.
        field = field.lower()

        if not field:
            raise ValueError(
                f"Empty facet field in '{arg}' — write field=value"
            )
        if field not in valid_set:
            raise ValueError(
                f"Unknown facet field: {field!r}. "
                f"Known fields: {', '.join(sorted(valid_set))}"
            )
        if not value:
            raise ValueError(
                f"Empty facet value for {field!r} in '{arg}'"
            )

        facets.setdefault(field, []).append(value)

    return facets, " ".join(free_tokens)


def find_pages_with_snippets(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
    facets: dict[str, list[str]] | None = None,
) -> list[tuple[str, str]]:
    """Find pages plus a highlighted context snippet for each result.

    Same retrieval contract as :func:`find_pages` (conjunctive match
    on ``query`` tokens, ranked by ``ranker`` defaulting to TF-IDF),
    but each entry pairs the URL with a short body excerpt produced
    by :func:`src.snippet.extract_snippet`. The snippet anchors on
    the earliest matching token in the body, with every query token
    occurrence wrapped in ``[brackets]`` for visual emphasis.

    ``facets`` (v1.5.0) layers a Lecture-12-"Fields and Extents"
    filter on top of the conjunctive match: each key is a structural
    field name (``author`` / ``tag`` / ``title`` / ``quote_text``) and
    each value is a list of accepted values. Values within one field
    are disjunctive (OR), values across fields are conjunctive (AND).
    When ``query`` is empty but facets are non-empty, every indexed
    document is a candidate and facets alone decide the result set;
    the snippet then falls back to a plain ~70-char preview without
    highlights since there are no free-text tokens to anchor on.

    A pre-v1.4.0 (INDEX_VERSION 4) index loaded into the current
    process would have an empty :attr:`Index.documents_text`; this
    function then returns an empty snippet string for that document,
    keeping the URL portion of the result intact. Rebuild via the
    ``build`` command to restore snippets.

    Returns:
        ``[(url, snippet), ...]`` ordered by relevance for free-text
        queries, or by doc_id ascending for facet-only queries.
    """
    facets = facets or {}
    tokens = tokenize(query, index.tokenizer_config)

    if tokens:
        # Free-text path: existing retrieval, then facet post-filter.
        if ranker is None:
            ranker = TFIDFRanker()
        scored = conjunctive_retrieval(index, tokens, ranker)
        candidate_doc_ids = [doc_id for doc_id, _ in scored]
        candidate_doc_ids = filter_by_facets(index, candidate_doc_ids, facets)
    elif facets:
        # Facet-only browse: no relevance signal, deterministic order.
        candidate_doc_ids = filter_by_facets(
            index, sorted(index.documents.keys()), facets
        )
    else:
        # Empty query, no facets — nothing to do.
        return []

    return _build_snippet_pairs(index, candidate_doc_ids, tokens, phrase_mode=False)


def find_phrase_with_snippets(
    index: Index,
    query: str,
    ranker: Ranker | None = None,
    facets: dict[str, list[str]] | None = None,
) -> list[tuple[str, str]]:
    """Phrase-mode counterpart of :func:`find_pages_with_snippets`.

    Retrieves pages where the query tokens occur as a consecutive
    phrase (same contract as :func:`find_phrase`) and produces a
    snippet for each, anchored on and highlighting the whole phrase
    as one bracketed unit (``[good friends]`` rather than
    ``[good] [friends]``).

    The optional ``facets`` parameter filters the result set in the
    same way as :func:`find_pages_with_snippets`. Phrase mode plus
    facets makes ``find "good friends" author=einstein`` work end
    to end — both filters must match.

    A pure-facet phrase query (empty phrase) is not meaningful —
    it returns ``[]`` rather than browsing the corpus. Use
    :func:`find_pages_with_snippets` for the facet-only browse case.
    """
    facets = facets or {}
    tokens = tokenize(query, index.tokenizer_config)
    if not tokens:
        return []

    if ranker is None:
        ranker = TFIDFRanker()

    scored = phrase_retrieval(index, tokens, ranker)
    candidate_doc_ids = [doc_id for doc_id, _ in scored]
    candidate_doc_ids = filter_by_facets(index, candidate_doc_ids, facets)

    return _build_snippet_pairs(index, candidate_doc_ids, tokens, phrase_mode=True)


def filter_by_facets(
    index: Index,
    doc_ids: list[int] | Iterable[int],
    facets: dict[str, list[str]],
) -> list[int]:
    """Return only the ``doc_ids`` that satisfy every facet predicate.

    Semantics (settled in the v1.5.0 step preamble):

    * **Within one field, multiple values are OR.** ``tag=science
      tag=physics`` keeps any document whose ``tag`` field contains
      ``science`` OR ``physics`` — matches the facet-UI convention.
    * **Across fields, the AND join is implicit.** ``author=einstein
      tag=science`` keeps documents that have both filters satisfied.
    * **Multi-token values are AND inside the value.** ``author="oscar
      wilde"`` requires both ``oscar`` AND ``wilde`` to appear inside
      the ``author`` field's posting — the conjunctive shape of
      multi-word names.

    Facet matching uses the per-field statistics already stored on
    every posting (``posting["fields"][field_name]["frequency"]``) so
    no extra index structure is needed — Lecture 12's "Fields and
    Extents" representation pays off here. Tokenisation of the value
    goes through the same ``index.tokenizer_config`` that built the
    index, so case-folding and (if configured) stemming match.

    An empty ``facets`` dict is a no-op; the input list is returned
    unchanged. This is the brief-compliance escape hatch: when the
    parser produces ``facets == {}`` (no ``=`` in the args), the
    filter pass is invisible.
    """
    if not facets:
        return list(doc_ids)

    surviving: list[int] = []
    for doc_id in doc_ids:
        if all(
            _doc_matches_field(index, doc_id, field, values)
            for field, values in facets.items()
        ):
            surviving.append(doc_id)
    return surviving


def _doc_matches_field(
    index: Index,
    doc_id: int,
    field: str,
    values: list[str],
) -> bool:
    """True if ``doc_id`` satisfies *any* of ``values`` on ``field``.

    Iterates the values disjunctively (OR). Each value is itself
    tokenised; a multi-token value requires *all* its tokens to
    appear in the field (e.g. ``author=oscar wilde`` requires both
    ``oscar`` and ``wilde`` in the author field of the same doc).
    """
    config = index.tokenizer_config
    for value in values:
        value_tokens = tokenize(value, config)
        if not value_tokens:
            continue
        if all(
            _doc_has_token_in_field(index, doc_id, field, tok)
            for tok in value_tokens
        ):
            return True
    return False


def _doc_has_token_in_field(
    index: Index,
    doc_id: int,
    field: str,
    token: str,
) -> bool:
    """True if ``doc_id`` has a non-zero ``token`` frequency in ``field``."""
    posting = index.postings.get(token, {}).get(doc_id)
    if not posting:
        return False
    fields_map = posting.get("fields")
    if not isinstance(fields_map, dict):
        return False
    field_stats = fields_map.get(field)
    if not isinstance(field_stats, dict):
        return False
    freq = field_stats.get("frequency", 0)
    return isinstance(freq, int) and freq > 0


def _build_snippet_pairs(
    index: Index,
    doc_ids: list[int],
    tokens: list[str],
    *,
    phrase_mode: bool,
) -> list[tuple[str, str]]:
    """Assemble ``(url, snippet)`` pairs for the final result list.

    Common back-end for :func:`find_pages_with_snippets` and
    :func:`find_phrase_with_snippets` so both paths share one
    snippet-generation code path.

    When ``tokens`` is empty (facet-only browse from
    :func:`find_pages_with_snippets`), the snippet falls back to a
    plain ~70-char head-of-body preview: there are no query tokens
    to highlight, but a preview is still much more informative than
    a bare URL when the user is browsing a tag or author.
    """
    pairs: list[tuple[str, str]] = []
    for doc_id in doc_ids:
        url = index.documents[doc_id]
        body = index.documents_text.get(doc_id, "")
        if not body:
            pairs.append((url, ""))
            continue
        if tokens:
            snippet = extract_snippet(body, tokens, phrase_mode=phrase_mode)
        else:
            snippet = _preview_head(body)
        pairs.append((url, snippet))
    return pairs


def _preview_head(body: str, max_chars: int = 70) -> str:
    """Return the first ``~max_chars`` of body as a plain preview.

    Used for facet-only queries where there are no query tokens to
    anchor a highlighted snippet on. The result is whitespace-
    collapsed and snapped to a word boundary so the preview reads
    as a sentence fragment rather than a truncated word, then
    ``...`` is appended if any content was cut.
    """
    collapsed = " ".join(body.split())
    if len(collapsed) <= max_chars:
        return collapsed
    cut = collapsed[:max_chars]
    # Back up to the last whitespace within the cut so we do not
    # truncate mid-word — at most a few characters lost.
    space = cut.rfind(" ")
    if space > max_chars // 2:
        cut = cut[:space]
    return cut + " ..."


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
