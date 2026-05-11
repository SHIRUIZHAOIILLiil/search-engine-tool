"""Tests for the benchmark support modules.

The benchmark scripts under ``benchmarks/`` are not exercised on CI
for runtime budget reasons, but the helpers they depend on are tested
here so a refactor cannot silently break the corpus contract.
"""

import unittest

from benchmarks.corpus import (
    DEFAULT_VOCAB_SIZE,
    synthesize_pages,
)


class SynthesizePagesTests(unittest.TestCase):
    def test_synthesize_pages_is_deterministic(self):
        # Same seed, same output — benchmark numbers across runs are
        # only comparable if the workload is byte-identical.
        first = synthesize_pages(50, seed=42)
        second = synthesize_pages(50, seed=42)
        self.assertEqual(len(first), len(second))
        for page_a, page_b in zip(first, second):
            self.assertEqual(page_a.url, page_b.url)
            self.assertEqual(page_a.text, page_b.text)

    def test_different_seeds_produce_different_text(self):
        # Sanity check the RNG actually responds to the seed — guards
        # against accidentally hard-coding a single random stream.
        a = synthesize_pages(20, seed=1)
        b = synthesize_pages(20, seed=2)
        self.assertNotEqual(
            [page.text for page in a],
            [page.text for page in b],
        )

    def test_synthesize_pages_size_and_url_uniqueness(self):
        pages = synthesize_pages(100)
        self.assertEqual(len(pages), 100)
        urls = [page.url for page in pages]
        self.assertEqual(len(set(urls)), 100, "URLs must be unique")

    def test_synthesize_pages_tokens_come_from_vocab(self):
        pages = synthesize_pages(30)
        expected_vocab = {f"word{i:04d}" for i in range(DEFAULT_VOCAB_SIZE)}
        for page in pages:
            for token in page.text.split():
                self.assertIn(token, expected_vocab)

    def test_synthesize_pages_respects_length_bounds(self):
        pages = synthesize_pages(40, tokens_per_page=(10, 15))
        for page in pages:
            n_tokens = len(page.text.split())
            self.assertGreaterEqual(n_tokens, 10)
            self.assertLessEqual(n_tokens, 15)

    def test_synthesize_pages_zero_returns_empty(self):
        # Edge case — generators that crash on n=0 are a frequent
        # source of off-by-one surprises in driver scripts.
        self.assertEqual(synthesize_pages(0), [])

    def test_synthesize_pages_rejects_bad_inputs(self):
        with self.assertRaises(ValueError):
            synthesize_pages(-1)
        with self.assertRaises(ValueError):
            synthesize_pages(10, vocab_size=0)
        with self.assertRaises(ValueError):
            synthesize_pages(10, tokens_per_page=(5, 3))


if __name__ == "__main__":
    unittest.main()
