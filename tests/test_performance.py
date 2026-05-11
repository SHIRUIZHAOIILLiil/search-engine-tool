"""Performance regression tests.

These are *not* micro-benchmarks. The intent is to catch large-scale
regressions: if a future change makes ``build_index`` 100× slower or
``find_pages`` block for seconds on a few hundred documents, these
tests will fail. The time budgets are deliberately generous (10×+
typical wall-clock on a developer laptop) so the suite stays stable
across machines and CI runners.

A fixed random seed makes every run reproducible. The synthetic
documents draw from a small shared vocabulary so the resulting
posting lists are non-trivial (every word appears in many docs).
"""

import random
import time
import unittest
from tempfile import TemporaryDirectory

from src.crawler import CrawledPage
from src.indexer import build_index, load_index, save_index
from src.ranker import BM25Ranker, TFIDFRanker
from src.retrieval import (
    conjunctive_retrieval,
    document_at_a_time,
    term_at_a_time,
)
from src.search import find_pages

N_PAGES = 500
VOCAB_SIZE = 200
TOKENS_PER_PAGE = (30, 100)  # inclusive range


def _synthesize_pages(seed: int = 20260511) -> list[CrawledPage]:
    """Build a deterministic synthetic corpus for performance tests."""
    rng = random.Random(seed)
    vocab = [f"word{i:04d}" for i in range(VOCAB_SIZE)]
    pages: list[CrawledPage] = []
    for i in range(N_PAGES):
        length = rng.randint(*TOKENS_PER_PAGE)
        text = " ".join(rng.choice(vocab) for _ in range(length))
        pages.append(CrawledPage(url=f"https://example.com/page-{i:04d}/", text=text))
    return pages


class BuildPerformanceTests(unittest.TestCase):
    def test_build_index_completes_within_budget(self):
        pages = _synthesize_pages()

        start = time.perf_counter()
        index = build_index(pages)
        elapsed = time.perf_counter() - start

        # 500 pages × ~65 avg tokens fits comfortably in well under
        # one second on a developer laptop. The 5-second cap absorbs
        # CI noise without hiding a 100× regression.
        self.assertLess(
            elapsed, 5.0,
            f"build_index({N_PAGES} pages) took {elapsed:.3f}s — regression?",
        )
        self.assertEqual(len(index.documents), N_PAGES)


class SearchPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build the index once for every search test — the index is
        # immutable from these tests' perspective so this avoids paying
        # the build cost per test method.
        cls.pages = _synthesize_pages()
        cls.index = build_index(cls.pages)
        cls.query = "word0042 word0100"

    def test_find_pages_with_tfidf_completes_within_budget(self):
        start = time.perf_counter()
        results = find_pages(self.index, self.query, ranker=TFIDFRanker())
        elapsed = time.perf_counter() - start

        self.assertLess(
            elapsed, 0.5,
            f"find_pages(TFIDF) took {elapsed:.3f}s — regression?",
        )
        # Make sure we're not measuring an early-exit shortcut path.
        self.assertGreater(len(results), 0)

    def test_find_pages_with_bm25_completes_within_budget(self):
        start = time.perf_counter()
        results = find_pages(self.index, self.query, ranker=BM25Ranker())
        elapsed = time.perf_counter() - start

        self.assertLess(
            elapsed, 0.5,
            f"find_pages(BM25) took {elapsed:.3f}s — regression?",
        )
        self.assertGreater(len(results), 0)

    def test_all_retrieval_algorithms_complete_within_budget(self):
        tokens = self.query.split()
        ranker = TFIDFRanker()

        algorithms = (
            ("document_at_a_time", lambda: document_at_a_time(self.index, tokens, ranker)),
            ("term_at_a_time", lambda: term_at_a_time(self.index, tokens, ranker)),
            ("conjunctive_retrieval", lambda: conjunctive_retrieval(self.index, tokens, ranker)),
        )
        for name, algorithm in algorithms:
            with self.subTest(algorithm=name):
                start = time.perf_counter()
                algorithm()
                elapsed = time.perf_counter() - start
                self.assertLess(
                    elapsed, 0.5,
                    f"{name} took {elapsed:.3f}s — regression?",
                )


class PersistencePerformanceTests(unittest.TestCase):
    def test_save_and_load_complete_within_budget(self):
        pages = _synthesize_pages()
        index = build_index(pages)

        with TemporaryDirectory() as temporary_directory:
            path = f"{temporary_directory}/index.json"

            start = time.perf_counter()
            save_index(index, path)
            save_elapsed = time.perf_counter() - start

            start = time.perf_counter()
            loaded = load_index(path)
            load_elapsed = time.perf_counter() - start

        self.assertLess(
            save_elapsed, 5.0,
            f"save_index took {save_elapsed:.3f}s — regression?",
        )
        self.assertLess(
            load_elapsed, 5.0,
            f"load_index took {load_elapsed:.3f}s — regression?",
        )
        # Round-trip preserves document count (basic sanity).
        self.assertEqual(len(loaded.documents), len(index.documents))


if __name__ == "__main__":
    unittest.main()
