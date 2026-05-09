import math
import unittest

from src.indexer import Index
from src.ranker import BM25Ranker, Ranker, TFIDFRanker


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


class BM25RankerTests(unittest.TestCase):
    def setUp(self):
        self.ranker = BM25Ranker(k1=1.5, b=0.75)

    def test_score_is_zero_for_empty_index(self):
        self.assertEqual(self.ranker.score(Index(), ["good"], 0), 0.0)

    def test_score_uses_textbook_bm25_formula(self):
        # 2 docs, each 10 tokens long → avgdl == dl == 10, so the length
        # term collapses to 1. "rare" appears only in doc 0 (df=1) with
        # tf=2. We can therefore predict the score by hand.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={"rare": {0: _posting(2, [0, 5])}},
            doc_lengths={0: 10, 1: 10},
        )
        n_docs, df, tf = 2, 1, 2
        expected_idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
        # length term simplifies because dl == avgdl
        expected = expected_idf * (tf * (1.5 + 1)) / (tf + 1.5)

        self.assertAlmostEqual(self.ranker.score(index, ["rare"], 0), expected)

    def test_score_saturates_with_increasing_tf(self):
        # BM25's defining behaviour: a 10× tf does NOT yield a 10× score.
        # We compare against TF-IDF (which is linear in tf) to make the
        # saturation visible numerically.
        low_tf = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={"rare": {0: _posting(1, [0])}},
            doc_lengths={0: 10, 1: 10},
        )
        high_tf = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={"rare": {0: _posting(10, list(range(10)))}},
            doc_lengths={0: 10, 1: 10},
        )

        low_score = self.ranker.score(low_tf, ["rare"], 0)
        high_score = self.ranker.score(high_tf, ["rare"], 0)

        # Score grows but does not scale linearly with tf.
        self.assertGreater(high_score, low_score)
        self.assertLess(high_score, 10 * low_score)

    def test_score_penalises_longer_documents(self):
        # Same tf in a short and a long doc: the short doc should win.
        index = Index(
            documents={0: "short", 1: "long"},
            postings={
                "rare": {
                    0: _posting(1, [0]),
                    1: _posting(1, [50]),
                },
            },
            doc_lengths={0: 5, 1: 100},
        )

        short_score = self.ranker.score(index, ["rare"], 0)
        long_score = self.ranker.score(index, ["rare"], 1)

        self.assertGreater(short_score, long_score)

    def test_score_uses_robertson_idf_so_common_terms_stay_non_negative(self):
        # Term in every document: plain log(N/df) would be 0 (and TF-IDF
        # would zero out the score), but Robertson smoothing keeps idf
        # strictly positive, so BM25 still ranks documents apart by tf.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "everywhere": {
                    0: _posting(1, [0]),
                    1: _posting(5, [0, 1, 2, 3, 4]),
                },
            },
            doc_lengths={0: 5, 1: 5},
        )

        score_low_tf = self.ranker.score(index, ["everywhere"], 0)
        score_high_tf = self.ranker.score(index, ["everywhere"], 1)

        self.assertGreater(score_low_tf, 0.0)
        self.assertGreater(score_high_tf, score_low_tf)

    def test_score_respects_custom_k1_and_b_parameters(self):
        # Using a larger k1 reduces saturation, so the gap between
        # low-tf and high-tf scores should widen relative to the default.
        index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "rare": {
                    0: _posting(1, [0]),
                    1: _posting(10, list(range(10))),
                },
            },
            doc_lengths={0: 10, 1: 10},
        )

        default_low = self.ranker.score(index, ["rare"], 0)
        default_high = self.ranker.score(index, ["rare"], 1)

        large_k1 = BM25Ranker(k1=5.0, b=0.75)
        large_low = large_k1.score(index, ["rare"], 0)
        large_high = large_k1.score(index, ["rare"], 1)

        # default_high / default_low gives the saturation ratio at k1=1.5.
        # Larger k1 means less saturation, so the high-tf doc pulls
        # further ahead of the low-tf doc.
        self.assertGreater(large_high / large_low, default_high / default_low)

    def test_bm25_ranker_satisfies_ranker_protocol(self):
        self.assertIsInstance(self.ranker, Ranker)


if __name__ == "__main__":
    unittest.main()
