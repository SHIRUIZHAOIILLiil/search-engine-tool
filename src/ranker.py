"""Relevance ranking for search results (Lecture 12: ranking function).

Lecture 12 frames the ranking task as a sum of feature contributions::

    R(Q, D) = Σ g_i(Q) · f_i(D)

where ``g_i`` is a query-side feature and ``f_i`` is a document-side
feature. This module turns that abstraction into code: the
:class:`Ranker` protocol fixes the score interface, and concrete
classes plug in particular ``g_i`` / ``f_i`` choices. :class:`TFIDFRanker`
is the textbook vector-space instantiation; later commits will add
:class:`BM25Ranker` (Croft et al., chapter 5) without disturbing this
layer.
"""

from __future__ import annotations

import math
from typing import Protocol, cast, runtime_checkable

from src.indexer import Index


@runtime_checkable
class Ranker(Protocol):
    """A per-document relevance scorer for a tokenised query."""

    def score(
        self,
        index: Index,
        query_tokens: list[str],
        doc_id: int,
    ) -> float:
        """Return a non-negative relevance score for ``doc_id`` under ``query_tokens``."""
        ...


class BM25Ranker:
    """Okapi BM25 scorer (Croft, Metzler & Strohman, ch. 5).

    BM25 is the de-facto standard ranking function in modern IR systems
    (Lucene, Elasticsearch, Solr all default to it). It improves on
    plain TF-IDF in three ways:

    * **TF saturation** — additional occurrences of a term contribute
      diminishing returns via the ``tf * (k1 + 1) / (tf + k1 * ...)``
      shape, instead of TF-IDF's linear ``tf`` factor.
    * **Length normalisation** — longer documents are penalised through
      the ``b * dl / avgdl`` term, since long documents are more likely
      to mention any given word by chance.
    * **Smoothed IDF** — the Robertson IDF ``log((N - df + 0.5) / (df + 0.5) + 1)``
      stays non-negative even when a term appears in every document,
      avoiding the degenerate ``log(N/N) = 0`` of the plain formula.

    Per-term score::

        score(t, d) = idf(t) * tf * (k1 + 1)
                      ────────────────────────
                      tf + k1 * (1 - b + b * dl/avgdl)

    Multi-term query: scores are summed across query tokens.

    Default parameters (``k1=1.5``, ``b=0.75``) sit at the textbook
    midpoint and match Croft's chapter 5 examples; both are
    constructor-configurable for tuning.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def score(
        self,
        index: Index,
        query_tokens: list[str],
        doc_id: int,
    ) -> float:
        n_docs = len(index.documents)
        if n_docs == 0 or doc_id not in index.documents:
            return 0.0

        # Average document length over the corpus. ``len(documents)``
        # rather than ``len(doc_lengths)`` keeps the divisor stable if
        # a length entry is somehow missing.
        avgdl = sum(index.doc_lengths.values()) / n_docs
        if avgdl == 0:
            avgdl = 1.0
        dl = index.doc_lengths.get(doc_id, 0)

        total = 0.0
        for token in query_tokens:
            postings = index.postings.get(token)
            if not postings:
                continue
            posting = postings.get(doc_id)
            if not posting:
                continue
            # ``Posting`` is ``dict[str, object]`` to accommodate
            # int frequencies and list positions in one mapping;
            # cast preserves the int invariant for mypy without a
            # TypedDict refactor (queued for v1.7.0 docs suite).
            tf = cast(int, posting.get("frequency", 0))
            if tf == 0:
                continue
            df = len(postings)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * dl / avgdl)
            if denominator == 0:
                continue
            total += idf * (tf * (self.k1 + 1)) / denominator
        return total


class TFIDFRanker:
    """Vector-space TF-IDF scorer.

    Implements the textbook formula::

        score(t, d) = tf(t, d) * idf(t)
                    = posting["frequency"] * log(N / df(t))
        score(q, d) = Σ_{t ∈ q} score(t, d)

    where ``N`` is the total number of documents in the index and
    ``df(t)`` is the number of documents that contain term ``t``.

    Edge cases handled:

    * ``df(t) == N`` (term appears in every document): ``idf = log(1) = 0``,
      so the term contributes nothing and tied documents fall back to
      doc_id ordering at the call site.
    * ``df(t) == 0`` (term not in the index): the term is skipped.
    * Empty index (``N == 0``): every score is 0.
    """

    def score(
        self,
        index: Index,
        query_tokens: list[str],
        doc_id: int,
    ) -> float:
        n_docs = len(index.documents)
        if n_docs == 0:
            return 0.0

        total = 0.0
        for token in query_tokens:
            postings = index.postings.get(token)
            if not postings:
                continue
            posting = postings.get(doc_id)
            if not posting:
                continue
            # See indexer.py / TFIDFRanker.score for the cast rationale.
            tf = cast(int, posting.get("frequency", 0))
            df = len(postings)
            if df == 0:
                continue
            idf = math.log(n_docs / df)
            total += tf * idf
        return total
