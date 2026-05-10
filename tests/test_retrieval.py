import unittest

from src.indexer import Index
from src.ranker import BM25Ranker, TFIDFRanker
from src.retrieval import (
    conjunctive_match,
    conjunctive_retrieval,
    document_at_a_time,
    phrase_match,
    phrase_retrieval,
    term_at_a_time,
)


def _posting(frequency: int, positions: list[int]) -> dict:
    return {"frequency": frequency, "positions": positions, "fields": {}}


class FixedScoreRanker:
    """Test stub: hands back a per-doc_id score from a precomputed map.

    Lets retrieval tests exercise sorting / top-k logic without coupling
    them to the TF-IDF or BM25 formulas.
    """

    def __init__(self, scores: dict[int, float]) -> None:
        self.scores = scores

    def score(self, index, query_tokens, doc_id):
        return self.scores.get(doc_id, 0.0)


class DocumentAtATimeTests(unittest.TestCase):
    def _index_with_term(self, term: str, doc_ids: list[int]) -> Index:
        return Index(
            documents={did: f"page-{did}" for did in doc_ids},
            postings={term: {did: _posting(1, [0]) for did in doc_ids}},
            doc_lengths={did: 10 for did in doc_ids},
        )

    def test_returns_results_sorted_by_score_descending(self):
        index = self._index_with_term("good", [0, 1, 2])
        ranker = FixedScoreRanker({0: 1.0, 1: 3.0, 2: 2.0})

        results = document_at_a_time(index, ["good"], ranker)

        self.assertEqual(results, [(1, 3.0), (2, 2.0), (0, 1.0)])

    def test_breaks_ties_by_doc_id_ascending(self):
        index = self._index_with_term("good", [5, 2, 8])
        ranker = FixedScoreRanker({5: 1.0, 2: 1.0, 8: 1.0})

        results = document_at_a_time(index, ["good"], ranker)

        self.assertEqual([doc_id for doc_id, _ in results], [2, 5, 8])

    def test_top_k_limits_returned_results(self):
        index = self._index_with_term("good", [0, 1, 2, 3, 4])
        ranker = FixedScoreRanker({0: 1.0, 1: 3.0, 2: 2.0, 3: 5.0, 4: 4.0})

        results = document_at_a_time(index, ["good"], ranker, top_k=3)

        self.assertEqual(results, [(3, 5.0), (4, 4.0), (1, 3.0)])

    def test_top_k_keeps_smaller_doc_ids_when_scores_tie(self):
        # All five candidates share the same score; with top_k=2 the
        # result must contain the two *smallest* doc_ids, never doc_ids
        # 3 or 4. This pins down the ``-doc_id`` tiebreak inside the
        # min-heap — a naive ``(score, doc_id)`` heap would evict the
        # smallest doc_ids and silently produce the wrong answer.
        index = self._index_with_term("good", [0, 1, 2, 3, 4])
        ranker = FixedScoreRanker({0: 5.0, 1: 5.0, 2: 5.0, 3: 5.0, 4: 5.0})

        results = document_at_a_time(index, ["good"], ranker, top_k=2)

        self.assertEqual([doc_id for doc_id, _ in results], [0, 1])

    def test_returns_empty_when_no_query_term_in_index(self):
        index = self._index_with_term("good", [0, 1])

        results = document_at_a_time(index, ["missing"], FixedScoreRanker({}))

        self.assertEqual(results, [])

    def test_returns_empty_for_empty_query(self):
        index = self._index_with_term("good", [0, 1])

        results = document_at_a_time(index, [], FixedScoreRanker({}))

        self.assertEqual(results, [])

    def test_works_with_tfidf_ranker(self):
        # Three docs in the index, "good" only in two of them so idf > 0.
        # Higher tf wins. The third doc isn't a candidate at all.
        index = Index(
            documents={0: "low-tf", 1: "high-tf", 2: "no-good"},
            postings={
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(5, [0, 1, 2, 3, 4]),
                },
            },
            doc_lengths={0: 10, 1: 10, 2: 10},
        )

        results = document_at_a_time(index, ["good"], TFIDFRanker())

        self.assertEqual([doc_id for doc_id, _ in results], [1, 0])

    def test_works_with_bm25_ranker(self):
        # Same shape of test against BM25 — verifies the algorithm is
        # ranker-agnostic (open/closed: swap the ranker, behaviour holds).
        index = Index(
            documents={0: "low-tf", 1: "high-tf"},
            postings={
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(3, [0, 1, 2]),
                },
            },
            doc_lengths={0: 10, 1: 10},
        )

        results = document_at_a_time(index, ["good"], BM25Ranker())

        self.assertEqual([doc_id for doc_id, _ in results], [1, 0])


class TermAtATimeTests(unittest.TestCase):
    def _index_with_term(self, term: str, doc_ids: list[int]) -> Index:
        return Index(
            documents={did: f"page-{did}" for did in doc_ids},
            postings={term: {did: _posting(1, [0]) for did in doc_ids}},
            doc_lengths={did: 10 for did in doc_ids},
        )

    def test_returns_results_sorted_by_score_descending(self):
        index = self._index_with_term("good", [0, 1, 2])
        ranker = FixedScoreRanker({0: 1.0, 1: 3.0, 2: 2.0})

        results = term_at_a_time(index, ["good"], ranker)

        self.assertEqual(results, [(1, 3.0), (2, 2.0), (0, 1.0)])

    def test_breaks_ties_by_doc_id_ascending(self):
        index = self._index_with_term("good", [5, 2, 8])
        ranker = FixedScoreRanker({5: 1.0, 2: 1.0, 8: 1.0})

        results = term_at_a_time(index, ["good"], ranker)

        self.assertEqual([doc_id for doc_id, _ in results], [2, 5, 8])

    def test_top_k_limits_returned_results(self):
        index = self._index_with_term("good", [0, 1, 2, 3, 4])
        ranker = FixedScoreRanker({0: 1.0, 1: 3.0, 2: 2.0, 3: 5.0, 4: 4.0})

        results = term_at_a_time(index, ["good"], ranker, top_k=3)

        self.assertEqual(results, [(3, 5.0), (4, 4.0), (1, 3.0)])

    def test_returns_empty_for_empty_query(self):
        index = self._index_with_term("good", [0, 1])

        results = term_at_a_time(index, [], FixedScoreRanker({}))

        self.assertEqual(results, [])

    def test_works_with_tfidf_ranker(self):
        index = Index(
            documents={0: "low-tf", 1: "high-tf", 2: "no-good"},
            postings={
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(5, [0, 1, 2, 3, 4]),
                },
            },
            doc_lengths={0: 10, 1: 10, 2: 10},
        )

        results = term_at_a_time(index, ["good"], TFIDFRanker())

        self.assertEqual([doc_id for doc_id, _ in results], [1, 0])

    def test_works_with_bm25_ranker(self):
        index = Index(
            documents={0: "low-tf", 1: "high-tf"},
            postings={
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(3, [0, 1, 2]),
                },
            },
            doc_lengths={0: 10, 1: 10},
        )

        results = term_at_a_time(index, ["good"], BM25Ranker())

        self.assertEqual([doc_id for doc_id, _ in results], [1, 0])

    def test_produces_same_results_as_document_at_a_time_with_tfidf(self):
        # Lecture 13 claim: "the computed scores are exactly the same
        # as before, although the way we compute them is different."
        # Multi-doc, multi-term, varied tf — exercises both algorithms.
        index = Index(
            documents={0: "page-0", 1: "page-1", 2: "page-2", 3: "page-3"},
            postings={
                "alpha": {
                    0: _posting(2, [0, 5]),
                    2: _posting(1, [3]),
                },
                "beta": {
                    0: _posting(1, [1]),
                    1: _posting(3, [0, 1, 2]),
                    2: _posting(2, [4, 6]),
                    3: _posting(1, [0]),
                },
            },
            doc_lengths={0: 8, 1: 10, 2: 7, 3: 5},
        )
        ranker = TFIDFRanker()

        daat = document_at_a_time(index, ["alpha", "beta"], ranker)
        taat = term_at_a_time(index, ["alpha", "beta"], ranker)

        self.assertEqual(daat, taat)

    def test_produces_same_results_as_document_at_a_time_with_bm25(self):
        # Same equivalence claim must hold under BM25, since BM25 is
        # also additive across query terms.
        index = Index(
            documents={0: "page-0", 1: "page-1", 2: "page-2", 3: "page-3"},
            postings={
                "alpha": {
                    0: _posting(2, [0, 5]),
                    2: _posting(1, [3]),
                },
                "beta": {
                    0: _posting(1, [1]),
                    1: _posting(3, [0, 1, 2]),
                    2: _posting(2, [4, 6]),
                    3: _posting(1, [0]),
                },
            },
            doc_lengths={0: 8, 1: 10, 2: 7, 3: 5},
        )
        ranker = BM25Ranker()

        daat = document_at_a_time(index, ["alpha", "beta"], ranker)
        taat = term_at_a_time(index, ["alpha", "beta"], ranker)

        self.assertEqual(daat, taat)


class ConjunctiveMatchTests(unittest.TestCase):
    def _index_with_postings(self, postings: dict) -> Index:
        return Index(postings=postings)

    def test_finds_intersection_of_two_posting_lists(self):
        # Lecture 13 slide 17 uses the galago / animal worked example;
        # this is the same shape with smaller lists for legibility.
        index = self._index_with_postings(
            {
                "galago": {did: _posting(1, [0]) for did in [1, 4, 5, 9, 10]},
                "animal": {did: _posting(1, [0]) for did in [1, 2, 3, 4, 6, 8, 9, 10]},
            }
        )

        matches = conjunctive_match(index, ["galago", "animal"])

        self.assertEqual(matches, [1, 4, 9, 10])

    def test_finds_intersection_of_three_posting_lists(self):
        index = self._index_with_postings(
            {
                "alpha": {did: _posting(1, [0]) for did in [1, 2, 3]},
                "beta": {did: _posting(1, [0]) for did in [2, 3, 4]},
                "gamma": {did: _posting(1, [0]) for did in [3, 4, 5]},
            }
        )

        matches = conjunctive_match(index, ["alpha", "beta", "gamma"])

        # Only doc_id 3 appears in all three lists.
        self.assertEqual(matches, [3])

    def test_returns_empty_for_empty_query(self):
        index = self._index_with_postings(
            {"alpha": {1: _posting(1, [0])}}
        )

        self.assertEqual(conjunctive_match(index, []), [])

    def test_returns_empty_when_any_term_has_no_postings(self):
        index = self._index_with_postings(
            {"alpha": {1: _posting(1, [0]), 2: _posting(1, [0])}}
        )

        # "missing" isn't in the index → conjunctive match impossible.
        self.assertEqual(conjunctive_match(index, ["alpha", "missing"]), [])

    def test_handles_completely_disjoint_lists(self):
        index = self._index_with_postings(
            {
                "alpha": {did: _posting(1, [0]) for did in [1, 2]},
                "beta": {did: _posting(1, [0]) for did in [3, 4]},
            }
        )

        self.assertEqual(conjunctive_match(index, ["alpha", "beta"]), [])

    def test_handles_lists_of_very_different_sizes(self):
        # The realistic "rare term + common term" case (galago vs animal
        # in Lecture 13). The simple algorithm must still terminate
        # quickly even when one list dwarfs the other — exercises the
        # inner while-advance that walks the long list past the rare
        # term's single match in one pass.
        index = self._index_with_postings(
            {
                "rare": {500: _posting(1, [0])},
                "common": {did: _posting(1, [0]) for did in range(1000)},
            }
        )

        self.assertEqual(conjunctive_match(index, ["rare", "common"]), [500])

    def test_returns_doc_ids_in_ascending_order(self):
        # Even with non-deterministic dict insertion order, the sorted
        # walk produces ascending output by construction.
        index = self._index_with_postings(
            {
                "alpha": {7: _posting(1, [0]), 1: _posting(1, [0]), 5: _posting(1, [0])},
                "beta": {7: _posting(1, [0]), 5: _posting(1, [0]), 1: _posting(1, [0])},
            }
        )

        self.assertEqual(conjunctive_match(index, ["alpha", "beta"]), [1, 5, 7])

    def test_single_term_query_returns_that_terms_postings_sorted(self):
        index = self._index_with_postings(
            {"alpha": {3: _posting(1, [0]), 1: _posting(1, [0]), 5: _posting(1, [0])}}
        )

        self.assertEqual(conjunctive_match(index, ["alpha"]), [1, 3, 5])


class ConjunctiveRetrievalTests(unittest.TestCase):
    def test_filters_then_ranks_surviving_documents(self):
        # Doc 0 has only one query term → filtered out by AND.
        # Docs 1 and 2 have both; doc 2 has higher tf for "beta" so
        # ranks above doc 1.
        index = Index(
            documents={0: "page-0", 1: "page-1", 2: "page-2"},
            postings={
                "alpha": {0: _posting(1, [0]), 1: _posting(1, [0]), 2: _posting(1, [0])},
                "beta": {1: _posting(1, [0]), 2: _posting(5, [0, 1, 2, 3, 4])},
            },
            doc_lengths={0: 10, 1: 10, 2: 10},
        )

        results = conjunctive_retrieval(index, ["alpha", "beta"], TFIDFRanker())

        self.assertEqual([doc_id for doc_id, _ in results], [2, 1])

    def test_top_k_limits_results_after_ranking(self):
        index = Index(
            documents={i: f"page-{i}" for i in range(4)},
            postings={
                "alpha": {i: _posting(1, [0]) for i in range(4)},
                "beta": {i: _posting(i + 1, [0]) for i in range(4)},
            },
            doc_lengths={i: 10 for i in range(4)},
        )
        ranker = TFIDFRanker()

        full = conjunctive_retrieval(index, ["alpha", "beta"], ranker)
        limited = conjunctive_retrieval(index, ["alpha", "beta"], ranker, top_k=2)

        self.assertEqual(len(full), 4)
        self.assertEqual(limited, full[:2])

    def test_returns_empty_when_no_document_contains_all_terms(self):
        index = Index(
            documents={0: "page-0", 1: "page-1"},
            postings={
                "alpha": {0: _posting(1, [0])},
                "beta": {1: _posting(1, [0])},
            },
            doc_lengths={0: 10, 1: 10},
        )

        results = conjunctive_retrieval(index, ["alpha", "beta"], TFIDFRanker())

        self.assertEqual(results, [])


class PhraseMatchTests(unittest.TestCase):
    def test_finds_consecutive_phrase(self):
        # "good" at position 3, "friends" at position 4 → adjacent.
        # Also at positions 17 and 18 — two phrase occurrences in one doc.
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: _posting(3, [3, 17, 50])},
                "friends": {0: _posting(2, [4, 18])},
            },
            doc_lengths={0: 100},
        )

        self.assertEqual(phrase_match(index, ["good", "friends"]), [0])

    def test_rejects_non_consecutive_terms(self):
        # Both terms present but never adjacent → no phrase.
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: _posting(1, [3])},
                "friends": {0: _posting(1, [10])},
            },
            doc_lengths={0: 50},
        )

        self.assertEqual(phrase_match(index, ["good", "friends"]), [])

    def test_returns_empty_when_any_term_is_missing(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: _posting(1, [3])}},
            doc_lengths={0: 10},
        )

        # "friends" not in the index → no phrase candidate.
        self.assertEqual(phrase_match(index, ["good", "friends"]), [])

    def test_single_token_degenerates_to_conjunctive_match(self):
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={"good": {0: _posting(1, [0]), 1: _posting(1, [5])}},
            doc_lengths={0: 10, 1: 10},
        )

        # A one-token "phrase" is just every doc containing the token.
        self.assertEqual(phrase_match(index, ["good"]), [0, 1])

    def test_finds_phrase_in_some_documents_but_not_others(self):
        # Doc 0: alpha at 3, beta at 4 → adjacent → match.
        # Doc 1: alpha at 5, beta at 9 → not adjacent → no match.
        # Doc 2: only alpha; beta missing → AND prefilter eliminates it.
        index = Index(
            documents={0: "page-A", 1: "page-B", 2: "page-C"},
            postings={
                "alpha": {
                    0: _posting(1, [3]),
                    1: _posting(1, [5]),
                    2: _posting(1, [0]),
                },
                "beta": {
                    0: _posting(1, [4]),
                    1: _posting(1, [9]),
                },
            },
            doc_lengths={0: 10, 1: 10, 2: 10},
        )

        self.assertEqual(phrase_match(index, ["alpha", "beta"]), [0])

    def test_finds_three_word_phrase_via_offset_alignment(self):
        # The N-term case stresses the "subtract offset i" normalisation:
        # phrase "a b c" requires positions p, p+1, p+2 for the three
        # tokens. After subtracting 0, 1, 2 the normalised sets must
        # share at least one value (the phrase's starting position p).
        index = Index(
            documents={0: "page-1"},
            postings={
                "a": {0: _posting(2, [5, 20])},  # offset 0 → {5, 20}
                "b": {0: _posting(2, [6, 22])},  # offset 1 → {5, 21}
                "c": {0: _posting(1, [7])},       # offset 2 → {5}
            },
            doc_lengths={0: 30},
        )
        # Intersection {5, 20} ∩ {5, 21} ∩ {5} = {5} → phrase at position 5.

        self.assertEqual(phrase_match(index, ["a", "b", "c"]), [0])

    def test_returns_empty_for_empty_query(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: _posting(1, [0])}},
            doc_lengths={0: 10},
        )

        self.assertEqual(phrase_match(index, []), [])

    def test_drops_positions_that_would_align_before_zero(self):
        # "b" at position 0 with offset 1 would suggest a phrase
        # starting at position -1, which is nonsensical. The filter
        # ``if p >= offset`` discards it; the doc has no valid phrase.
        index = Index(
            documents={0: "page-1"},
            postings={
                "a": {0: _posting(1, [5])},
                "b": {0: _posting(1, [0])},
            },
            doc_lengths={0: 10},
        )

        self.assertEqual(phrase_match(index, ["a", "b"]), [])


class PhraseRetrievalTests(unittest.TestCase):
    def test_ranks_documents_containing_the_phrase(self):
        # Docs 0 and 1 both contain phrase "alpha beta"; doc 2 has the
        # terms but not adjacent; doc 3 has neither, giving df < N and
        # therefore non-zero idf so ranking is observable.
        index = Index(
            documents={0: "page-A", 1: "page-B", 2: "not-phrase", 3: "empty"},
            postings={
                "alpha": {
                    0: _posting(1, [3]),
                    1: _posting(3, [3, 10, 20]),
                    2: _posting(1, [5]),
                },
                "beta": {
                    0: _posting(1, [4]),
                    1: _posting(1, [4]),
                    2: _posting(1, [50]),
                },
            },
            doc_lengths={0: 10, 1: 30, 2: 100, 3: 5},
        )

        results = phrase_retrieval(index, ["alpha", "beta"], TFIDFRanker())

        # Doc 1 has higher tf for "alpha" → ranks above doc 0.
        # Doc 2 dropped because phrase isn't adjacent. Doc 3 dropped by
        # AND prefilter.
        self.assertEqual([doc_id for doc_id, _ in results], [1, 0])

    def test_top_k_limits_results_after_filter(self):
        index = Index(
            documents={i: f"page-{i}" for i in range(4)},
            postings={
                "alpha": {
                    0: _posting(1, [0]),
                    1: _posting(2, [0, 5]),
                    2: _posting(5, [0, 5, 10, 15, 20]),
                },
                "beta": {
                    0: _posting(1, [1]),
                    1: _posting(1, [1]),
                    2: _posting(1, [1]),
                },
            },
            doc_lengths={0: 10, 1: 10, 2: 30, 3: 5},
        )
        ranker = TFIDFRanker()

        full = phrase_retrieval(index, ["alpha", "beta"], ranker)
        limited = phrase_retrieval(index, ["alpha", "beta"], ranker, top_k=2)

        self.assertEqual(len(full), 3)
        self.assertEqual(limited, full[:2])


if __name__ == "__main__":
    unittest.main()
