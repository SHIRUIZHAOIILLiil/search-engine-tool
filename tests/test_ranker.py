import math
import unittest

from src.indexer import Index
from src.ranker import Ranker, TFIDFRanker


def _posting(frequency: int, positions: list[int]) -> dict:
    return {"frequency": frequency, "positions": positions, "fields": {}}


class TFIDFRankerTests(unittest.TestCase):
    def setUp(self):
        self.ranker = TFIDFRanker()

    def test_score_is_zero_for_empty_index(self):
        self.assertEqual(self.ranker.score(Index(), ["good"], 0), 0.0)

    def test_score_is_zero_when_query_term_not_in_index(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: _posting(1, [0])}},
        )

        self.assertEqual(self.ranker.score(index, ["missing"], 0), 0.0)

    def test_score_is_zero_when_document_lacks_query_term(self):
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={"good": {0: _posting(1, [0])}},
        )

        # doc_id 1 has no entry for "good".
        self.assertEqual(self.ranker.score(index, ["good"], 1), 0.0)

    def test_score_is_zero_when_term_appears_in_every_document(self):
        # idf = log(N / df) = log(2 / 2) = 0 → no discrimination.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "good": {
                    0: _posting(5, [0, 1, 2, 3, 4]),
                    1: _posting(3, [0, 1, 2]),
                },
            },
        )

        self.assertEqual(self.ranker.score(index, ["good"], 0), 0.0)
        self.assertEqual(self.ranker.score(index, ["good"], 1), 0.0)

    def test_score_uses_textbook_tf_idf_formula(self):
        index = Index(
            documents={0: "page-1", 1: "page-2", 2: "page-3"},
            postings={
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(5, [0, 1, 2, 3, 4]),
                },
            },
        )
        idf = math.log(3 / 2)

        self.assertAlmostEqual(self.ranker.score(index, ["good"], 0), 1 * idf)
        self.assertAlmostEqual(self.ranker.score(index, ["good"], 1), 5 * idf)

    def test_score_sums_contributions_from_each_query_term(self):
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                # "good" in both → idf 0, contributes nothing.
                "good": {
                    0: _posting(1, [0]),
                    1: _posting(1, [4]),
                },
                # "rare" only in doc 1 → idf = log(2).
                "rare": {1: _posting(2, [5, 7])},
            },
        )

        # Doc 0 has "good" only; "good" contributes 0.
        self.assertEqual(self.ranker.score(index, ["good", "rare"], 0), 0.0)
        # Doc 1: "good" → 0, "rare" → 2 * log(2).
        self.assertAlmostEqual(
            self.ranker.score(index, ["good", "rare"], 1),
            2 * math.log(2),
        )

    def test_score_repeats_contribution_for_repeated_query_terms(self):
        # The current formula treats each query token independently, so
        # a repeated term double-counts its contribution. This documents
        # the chosen behaviour (matches a bag-of-tokens query model).
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={"rare": {1: _posting(1, [0])}},
        )
        idf = math.log(2)

        self.assertAlmostEqual(
            self.ranker.score(index, ["rare", "rare"], 1),
            2 * idf,
        )

    def test_tfidf_ranker_satisfies_ranker_protocol(self):
        # Sanity check: future rankers (BM25, etc.) must also be Ranker
        # instances under runtime structural typing.
        self.assertIsInstance(self.ranker, Ranker)


if __name__ == "__main__":
    unittest.main()
