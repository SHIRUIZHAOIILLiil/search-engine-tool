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
from typing import Protocol, runtime_checkable

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
            tf = int(posting.get("frequency", 0))
            df = len(postings)
            if df == 0:
                continue
            idf = math.log(n_docs / df)
            total += tf * idf
        return total
