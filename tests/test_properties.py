"""Property-based tests for invariants that should hold for *every* input.

Hand-written unit tests pin specific cases; these property tests pin
*shapes* of correctness across many randomly generated inputs. The
random generator uses a fixed seed per property so failures are
reproducible, but every trial exercises a different configuration —
catching corner cases hand-written tests miss.

The approach is the QuickCheck / Hypothesis pattern implemented with
Python's stdlib ``random`` module: we avoid pulling in the
``hypothesis`` package as a dependency but keep the testing style.
"""

import random
import unittest
from tempfile import TemporaryDirectory

from src.crawler import CrawledPage
from src.indexer import build_index, load_index, save_index
from src.ranker import BM25Ranker
from src.search import find_pages, find_phrase
from src.tokenizer import tokenize


def _random_pages(
    rng: random.Random,
    n_pages: int,
    vocab_size: int = 20,
    tokens_per_doc: tuple[int, int] = (3, 25),
) -> list[CrawledPage]:
    """Build ``n_pages`` synthetic pages with random text."""
    vocab = [f"word{i:03d}" for i in range(vocab_size)]
    pages: list[CrawledPage] = []
    for i in range(n_pages):
        length = rng.randint(*tokens_per_doc)
        text = " ".join(rng.choice(vocab) for _ in range(length))
        pages.append(
            CrawledPage(url=f"https://example.com/page-{i:03d}/", text=text)
        )
    return pages


class PropertyTests(unittest.TestCase):
    TRIALS = 20

    def test_save_and_load_round_trip_is_the_identity_function(self):
        """``load_index(save_index(idx)) == idx`` for any built index."""
        rng = random.Random(20260511)
        for trial in range(self.TRIALS):
            pages = _random_pages(rng, n_pages=rng.randint(2, 12))
            index = build_index(pages)

            with TemporaryDirectory() as temporary_directory:
                path = f"{temporary_directory}/index.json"
                save_index(index, path)
                loaded = load_index(path)

            self.assertEqual(
                loaded,
                index,
                f"trial {trial}: save→load is not the identity function",
            )

    def test_find_pages_always_returns_urls_from_indexed_documents(self):
        """``find_pages`` never invents URLs the index doesn't know about."""
        rng = random.Random(20260512)
        vocab_size = 20
        vocab = [f"word{i:03d}" for i in range(vocab_size)]
        for trial in range(self.TRIALS):
            pages = _random_pages(rng, n_pages=10, vocab_size=vocab_size)
            index = build_index(pages)
            indexed_urls = set(index.documents.values())

            for _ in range(5):
                query_size = rng.randint(1, 3)
                tokens = [rng.choice(vocab) for _ in range(query_size)]
                results = find_pages(index, " ".join(tokens))

                self.assertTrue(
                    set(results).issubset(indexed_urls),
                    f"trial {trial}: find_pages returned an out-of-index URL",
                )

    def test_find_phrase_results_are_always_a_subset_of_find_pages_results(self):
        """A phrase hit implies a conjunctive (AND) hit, never the reverse.

        ``find_phrase`` enforces both presence *and* adjacency, so its
        result set must be at most as large as ``find_pages`` on the
        same query — and is often strictly smaller.
        """
        rng = random.Random(20260513)
        vocab_size = 15
        vocab = [f"word{i:03d}" for i in range(vocab_size)]
        for trial in range(self.TRIALS):
            pages = _random_pages(
                rng,
                n_pages=10,
                vocab_size=vocab_size,
                tokens_per_doc=(5, 30),
            )
            index = build_index(pages)

            # 2-token queries make the property non-trivial:
            # a 1-token phrase query trivially equals the 1-token AND.
            for _ in range(5):
                tokens = [rng.choice(vocab) for _ in range(2)]
                query = " ".join(tokens)
                phrase_results = set(find_phrase(index, query))
                and_results = set(find_pages(index, query))

                self.assertTrue(
                    phrase_results.issubset(and_results),
                    f"trial {trial}, query {query!r}: phrase ⊄ AND result",
                )

    def test_bm25_score_is_never_negative(self):
        """Robertson IDF + non-negative tf guarantees BM25 ≥ 0 always."""
        rng = random.Random(20260514)
        ranker = BM25Ranker()
        vocab_size = 12
        vocab = [f"word{i:03d}" for i in range(vocab_size)]
        for trial in range(self.TRIALS):
            pages = _random_pages(rng, n_pages=8, vocab_size=vocab_size)
            index = build_index(pages)

            for token in vocab:
                for doc_id in index.documents:
                    score = ranker.score(index, [token], doc_id)
                    self.assertGreaterEqual(
                        score,
                        0.0,
                        f"trial {trial}: BM25 negative for token={token!r}, doc={doc_id}",
                    )

    def test_tokenize_is_idempotent_under_the_default_config(self):
        """Re-tokenising already-tokenised text returns the same tokens."""
        rng = random.Random(20260515)
        # Include letters, digits, apostrophe, common punctuation, and
        # whitespace — the cases the tokenizer must handle on real pages.
        charset = "abcdefghijklmnopqrstuvwxyz ABCDEF 0123456789 ,.!?'\"-\n\t"
        for trial in range(self.TRIALS):
            length = rng.randint(0, 120)
            text = "".join(rng.choice(charset) for _ in range(length))

            once = tokenize(text)
            twice = tokenize(" ".join(once))

            self.assertEqual(
                once,
                twice,
                f"trial {trial}: tokenize was not idempotent on {text!r}",
            )


if __name__ == "__main__":
    unittest.main()
