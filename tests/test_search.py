import unittest

from src.crawler import CrawledPage
from src.indexer import Index, build_index
from src.ranker import TFIDFRanker
from src.search import (
    filter_by_facets,
    find_pages,
    find_pages_with_snippets,
    find_phrase,
    find_phrase_with_snippets,
    format_did_you_mean,
    parse_facets,
    print_word,
    suggest_for_query,
)
from src.tokenizer import TokenizerConfig


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = Index(
            documents={0: "page-1", 1: "page-2"},
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [4]},
                },
                "friends": {
                    1: {"frequency": 1, "positions": [5]},
                },
            },
        )

    def test_print_word_returns_posting_case_insensitively(self):
        expected = {
            "page-1": {"frequency": 1, "positions": [0]},
            "page-2": {"frequency": 1, "positions": [4]},
        }

        self.assertEqual(print_word(self.index, "GOOD"), expected)

    def test_print_word_returns_empty_dict_for_missing_word(self):
        self.assertEqual(print_word(self.index, "missing"), {})

    def test_print_word_returns_empty_dict_for_punctuation_only_input(self):
        self.assertEqual(print_word(self.index, "!!!"), {})

    def test_print_word_uses_first_token_only(self):
        expected = {
            "page-1": {"frequency": 1, "positions": [0]},
            "page-2": {"frequency": 1, "positions": [4]},
        }

        self.assertEqual(print_word(self.index, "good friends"), expected)

    def test_find_pages_returns_pages_containing_all_words(self):
        self.assertEqual(find_pages(self.index, "good friends"), ["page-2"])

    def test_find_pages_returns_single_word_matches(self):
        self.assertEqual(find_pages(self.index, "good"), ["page-1", "page-2"])

    def test_find_pages_is_case_insensitive(self):
        self.assertEqual(find_pages(self.index, "GOOD FRIENDS"), ["page-2"])

    def test_find_pages_ignores_query_punctuation(self):
        self.assertEqual(find_pages(self.index, "good, friends!"), ["page-2"])

    def test_find_pages_handles_repeated_query_terms(self):
        self.assertEqual(find_pages(self.index, "good good"), ["page-1", "page-2"])

    def test_find_pages_handles_empty_and_missing_queries(self):
        self.assertEqual(find_pages(self.index, ""), [])
        self.assertEqual(find_pages(self.index, "missing"), [])

    def test_find_pages_returns_empty_list_when_one_query_term_is_missing(self):
        self.assertEqual(find_pages(self.index, "good missing"), [])

    def test_find_pages_uses_index_tokenizer_config_for_query(self):
        # Same idea as the phrase test below: build with stemming on,
        # then a user query in surface form must still match the stems
        # stored in the index. This pins the build/search consistency
        # invariant that motivates storing the config on the index.
        config = TokenizerConfig(apply_stemming=True)
        pages = [CrawledPage(url="page-1", text="cats are running")]
        index = build_index(pages, config=config)

        self.assertEqual(find_pages(index, "cats"), ["page-1"])
        self.assertEqual(find_pages(index, "running"), ["page-1"])

    def test_find_pages_ranks_documents_by_tf_idf_score(self):
        # Three docs; "alpha" and "beta" each appear in two of them so
        # idf > 0. Doc 1 has higher tf for "alpha" and should rank first
        # for the query "alpha beta".
        index = Index(
            documents={0: "low-tf", 1: "high-tf", 2: "no-match"},
            postings={
                "alpha": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 5, "positions": [0, 1, 2, 3, 4]},
                },
                "beta": {
                    0: {"frequency": 1, "positions": [1]},
                    1: {"frequency": 1, "positions": [5]},
                },
            },
        )

        self.assertEqual(find_pages(index, "alpha beta"), ["high-tf", "low-tf"])

    def test_find_pages_default_ranker_is_tf_idf(self):
        # When idf is 0 (term in every document), TF-IDF returns 0 for
        # every candidate; ties resolve by doc_id ascending. Establishes
        # the default ranker's identity through observable behaviour.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "everywhere": {
                    0: {"frequency": 99, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                },
            },
        )

        # tf=99 doesn't beat tf=1 because both have idf=0; doc_id wins.
        self.assertEqual(find_pages(index, "everywhere"), ["page-A", "page-B"])

    def test_find_pages_accepts_custom_ranker_for_dependency_injection(self):
        # Stub ranker that prefers higher doc_id, the inverse of the
        # TFIDFRanker tiebreak. Demonstrates the ranker parameter is
        # honoured rather than ignored in favour of the default.
        class FavorHigherDocIdRanker:
            def score(self, index, query_tokens, doc_id):
                return float(doc_id)

        index = Index(
            documents={0: "page-A", 1: "page-B", 2: "page-C"},
            postings={
                "term": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                    2: {"frequency": 1, "positions": [0]},
                },
            },
        )

        # Default TFIDF would tie everything → ascending doc_id order.
        # The custom ranker reverses that.
        self.assertEqual(
            find_pages(index, "term", ranker=FavorHigherDocIdRanker()),
            ["page-C", "page-B", "page-A"],
        )

        # And re-confirm the default order without the override:
        self.assertEqual(
            find_pages(index, "term", ranker=TFIDFRanker()),
            ["page-A", "page-B", "page-C"],
        )


class FindPhraseTests(unittest.TestCase):
    def test_returns_pages_containing_consecutive_phrase(self):
        # Doc A has "good" at 3, "friends" at 4 → adjacent → match.
        # Doc B has "good" at 10, "friends" at 20 → not adjacent → miss.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [3]},
                    1: {"frequency": 1, "positions": [10]},
                },
                "friends": {
                    0: {"frequency": 1, "positions": [4]},
                    1: {"frequency": 1, "positions": [20]},
                },
            },
            doc_lengths={0: 10, 1: 30},
        )

        self.assertEqual(find_phrase(index, "good friends"), ["page-A"])

    def test_returns_empty_when_phrase_is_never_consecutive(self):
        index = Index(
            documents={0: "page-1"},
            postings={
                "good": {0: {"frequency": 1, "positions": [3]}},
                "friends": {0: {"frequency": 1, "positions": [10]}},
            },
            doc_lengths={0: 50},
        )

        self.assertEqual(find_phrase(index, "good friends"), [])

    def test_returns_empty_for_empty_query(self):
        index = Index(
            documents={0: "page-1"},
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
            doc_lengths={0: 10},
        )

        self.assertEqual(find_phrase(index, ""), [])

    def test_find_phrase_uses_index_tokenizer_config_for_query(self):
        # Build an index with stemming enabled, so "running" → "run".
        # The user types the un-stemmed surface form; find_phrase must
        # apply the same config when tokenising the query so the query
        # tokens line up with the index keys.
        config = TokenizerConfig(apply_stemming=True)
        pages = [CrawledPage(url="page-1", text="i love running marathons")]
        index = build_index(pages, config=config)

        # Without applying the index's config to the query, "running"
        # wouldn't match the indexed stem "run" and we'd get [].
        self.assertEqual(find_phrase(index, "running marathon"), ["page-1"])

    def test_default_ranker_orders_tied_phrase_matches_by_doc_id(self):
        # Both docs contain the phrase "alpha beta" and both terms occur
        # in every document → idf=0 → scores tie → fall back to doc_id.
        index = Index(
            documents={0: "page-A", 1: "page-B"},
            postings={
                "alpha": {
                    0: {"frequency": 1, "positions": [3]},
                    1: {"frequency": 1, "positions": [7]},
                },
                "beta": {
                    0: {"frequency": 1, "positions": [4]},
                    1: {"frequency": 1, "positions": [8]},
                },
            },
            doc_lengths={0: 10, 1: 20},
        )

        self.assertEqual(find_phrase(index, "alpha beta"), ["page-A", "page-B"])


class FindPagesWithSnippetsTests(unittest.TestCase):
    """v1.4.0: ``find_pages`` now has a sibling that pairs each URL
    with a context excerpt from the body. Preserves the original
    ranking/match contract so existing `find_pages` tests still hold;
    these new tests pin the snippet half of the pair.
    """

    def setUp(self):
        self.index = Index(
            documents={
                0: "page-1",
                1: "page-2",
            },
            documents_text={
                0: "Good friends are like stars; you don't always see them.",
                1: "Good morning, sunshine; the day is fresh and new.",
            },
            postings={
                "good": {
                    0: {"frequency": 1, "positions": [0]},
                    1: {"frequency": 1, "positions": [0]},
                },
                "friends": {
                    0: {"frequency": 1, "positions": [1]},
                },
            },
        )

    def test_returns_url_plus_snippet_pairs_for_each_match(self):
        results = find_pages_with_snippets(self.index, "good friends")

        self.assertEqual(len(results), 1)
        url, snippet = results[0]
        self.assertEqual(url, "page-1")
        self.assertIn("[Good]", snippet)
        self.assertIn("[friends]", snippet)

    def test_url_order_matches_find_pages(self):
        # Same retrieval contract -> same ordering. Locks the
        # invariant that switching the CLI to the snippet variant
        # cannot reshuffle the ranking under the user's feet.
        plain = find_pages(self.index, "good")
        snippet_urls = [url for url, _ in find_pages_with_snippets(self.index, "good")]

        self.assertEqual(snippet_urls, plain)

    def test_returns_empty_snippet_when_document_has_no_body_text(self):
        # A v4 legacy index has documents_text empty by default; the
        # find variant must still surface the URL — only the snippet
        # half degrades. Pins backward compatibility.
        legacy_index = Index(
            documents={0: "page-legacy"},
            documents_text={},  # explicitly empty -- pre-v1.4.0 shape
            postings={"good": {0: {"frequency": 1, "positions": [0]}}},
        )

        results = find_pages_with_snippets(legacy_index, "good")

        self.assertEqual(results, [("page-legacy", "")])

    def test_empty_query_returns_empty_list(self):
        self.assertEqual(find_pages_with_snippets(self.index, ""), [])

    def test_no_matches_returns_empty_list(self):
        self.assertEqual(find_pages_with_snippets(self.index, "nonexistent"), [])


class FindPhraseWithSnippetsTests(unittest.TestCase):
    def test_phrase_snippet_highlights_whole_phrase_as_one_unit(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={
                0: "We are all good friends here, sharing the day.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [3]}},
                "friends": {0: {"frequency": 1, "positions": [4]}},
            },
            doc_lengths={0: 10},
        )

        results = find_phrase_with_snippets(index, "good friends")

        self.assertEqual(len(results), 1)
        _, snippet = results[0]
        # Phrase mode brackets the contiguous match, not each token.
        self.assertIn("[good friends]", snippet)
        self.assertNotIn("[good] [friends]", snippet)

    def test_phrase_with_no_consecutive_match_returns_empty_list(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={
                0: "Good ideas come from many friends, but not together.",
            },
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [5]}},
            },
            doc_lengths={0: 10},
        )

        # The phrase filter rejects this; no result regardless of snippet.
        self.assertEqual(find_phrase_with_snippets(index, "good friends"), [])

    def test_phrase_snippet_with_empty_body_returns_url_and_empty_snippet(self):
        index = Index(
            documents={0: "page-1"},
            documents_text={},
            postings={
                "good": {0: {"frequency": 1, "positions": [0]}},
                "friends": {0: {"frequency": 1, "positions": [1]}},
            },
            doc_lengths={0: 2},
        )

        results = find_phrase_with_snippets(index, "good friends")

        self.assertEqual(results, [("page-1", "")])


def _build_faceted_index() -> Index:
    """Two-doc fixture with author/tag/quote_text fields populated.

    Hand-built rather than going through ``build_index`` so the test
    body exercises the facet matcher's contract on a fixed shape.
    Doc 0 is Einstein on science; Doc 1 is Wilde on wit.
    """
    return Index(
        documents={
            0: "https://example.com/einstein/",
            1: "https://example.com/wilde/",
        },
        documents_text={
            0: "imagination is more important than knowledge",
            1: "always forgive your enemies; nothing annoys them so much",
        },
        postings={
            # Body-level postings:
            "imagination": {0: {
                "frequency": 1,
                "positions": [0],
                "fields": {},
            }},
            "knowledge": {0: {
                "frequency": 1,
                "positions": [5],
                "fields": {},
            }},
            "always": {1: {
                "frequency": 1,
                "positions": [0],
                "fields": {},
            }},
            "forgive": {1: {
                "frequency": 1,
                "positions": [1],
                "fields": {},
            }},
            # Field postings (author / tag / quote_text). Each posting
            # carries the same body-level keys plus the per-field
            # entry — that is the on-disk shape build_index produces.
            "einstein": {0: {
                "frequency": 0,
                "positions": [],
                "fields": {"author": {"frequency": 1, "positions": [0]}},
            }},
            "wilde": {1: {
                "frequency": 0,
                "positions": [],
                "fields": {"author": {"frequency": 1, "positions": [1]}},
            }},
            "oscar": {1: {
                "frequency": 0,
                "positions": [],
                "fields": {"author": {"frequency": 1, "positions": [0]}},
            }},
            "science": {0: {
                "frequency": 0,
                "positions": [],
                "fields": {"tag": {"frequency": 1, "positions": [0]}},
            }},
            "wit": {1: {
                "frequency": 0,
                "positions": [],
                "fields": {"tag": {"frequency": 1, "positions": [0]}},
            }},
            "humour": {1: {
                "frequency": 0,
                "positions": [],
                "fields": {"tag": {"frequency": 1, "positions": [1]}},
            }},
        },
    )


class FilterByFacetsTests(unittest.TestCase):
    """``filter_by_facets`` is the core of v1.5.0 — verifies the
    OR-within-field / AND-across-field / AND-within-value semantics.
    """

    def setUp(self):
        self.index = _build_faceted_index()

    def test_empty_facets_returns_input_unchanged(self):
        # Brief-compliance escape hatch: no ``=`` in user input means
        # facets == {} and the filter pass is a pure passthrough.
        self.assertEqual(filter_by_facets(self.index, [0, 1], {}), [0, 1])

    def test_single_facet_keeps_matching_doc(self):
        result = filter_by_facets(self.index, [0, 1], {"author": ["einstein"]})

        self.assertEqual(result, [0])

    def test_single_facet_removes_non_matching_doc(self):
        result = filter_by_facets(self.index, [0, 1], {"author": ["wilde"]})

        self.assertEqual(result, [1])

    def test_or_within_field_multiple_values(self):
        # tag=science OR tag=wit keeps both docs.
        result = filter_by_facets(
            self.index, [0, 1], {"tag": ["science", "wit"]}
        )

        self.assertEqual(result, [0, 1])

    def test_or_within_field_when_only_one_value_matches(self):
        # tag=science OR tag=unknown — still keeps doc 0 via science.
        result = filter_by_facets(
            self.index, [0, 1], {"tag": ["science", "unknown"]}
        )

        self.assertEqual(result, [0])

    def test_and_across_fields_intersects(self):
        # author=wilde AND tag=wit — only doc 1 satisfies both.
        result = filter_by_facets(
            self.index, [0, 1], {"author": ["wilde"], "tag": ["wit"]}
        )

        self.assertEqual(result, [1])

    def test_and_across_fields_excludes_when_one_fails(self):
        # author=wilde AND tag=science — wilde is doc 1, science is
        # doc 0; intersection is empty.
        result = filter_by_facets(
            self.index, [0, 1], {"author": ["wilde"], "tag": ["science"]}
        )

        self.assertEqual(result, [])

    def test_and_within_multi_token_value(self):
        # ``author="oscar wilde"`` requires BOTH tokens in the author
        # field of the same doc. Doc 1 has both; doc 0 has neither.
        result = filter_by_facets(
            self.index, [0, 1], {"author": ["oscar wilde"]}
        )

        self.assertEqual(result, [1])

    def test_multi_token_value_fails_when_only_one_token_present(self):
        # ``author="oscar einstein"`` — doc 0 has einstein, doc 1 has
        # oscar; neither has BOTH in author → empty result.
        result = filter_by_facets(
            self.index, [0, 1], {"author": ["oscar einstein"]}
        )

        self.assertEqual(result, [])

    def test_filter_preserves_input_ordering(self):
        # Ranking order from upstream retrieval must survive the
        # filter — important for snippet pairs whose order reflects
        # the TF-IDF / BM25 ranking.
        result = filter_by_facets(
            self.index, [1, 0], {"tag": ["science", "wit"]}
        )

        self.assertEqual(result, [1, 0])

    def test_unknown_facet_value_yields_empty_for_that_field(self):
        # ``author=newton`` matches nothing — no doc survives.
        result = filter_by_facets(self.index, [0, 1], {"author": ["newton"]})

        self.assertEqual(result, [])


class FindWithFacetsTests(unittest.TestCase):
    """End-to-end ``find_pages_with_snippets`` and
    ``find_phrase_with_snippets`` paths with facets layered on.
    """

    def setUp(self):
        self.index = _build_faceted_index()

    def test_free_text_plus_facet_filters_to_intersection(self):
        # ``knowledge`` matches doc 0 by free text; author=einstein
        # facet keeps it. Doc 1 fails the free-text match.
        results = find_pages_with_snippets(
            self.index, "knowledge", facets={"author": ["einstein"]}
        )

        self.assertEqual(len(results), 1)
        url, snippet = results[0]
        self.assertEqual(url, "https://example.com/einstein/")
        self.assertIn("[knowledge]", snippet)

    def test_free_text_match_filtered_out_by_non_matching_facet(self):
        # ``knowledge`` matches doc 0, but author=wilde does not —
        # results must be empty even though the free-text match exists.
        results = find_pages_with_snippets(
            self.index, "knowledge", facets={"author": ["wilde"]}
        )

        self.assertEqual(results, [])

    def test_facet_only_browse_returns_all_matching_docs_with_preview(self):
        # No free text + tag=science: doc 0 alone is returned with a
        # plain head-of-body preview (no highlighted tokens since
        # there is nothing to highlight).
        results = find_pages_with_snippets(
            self.index, "", facets={"tag": ["science"]}
        )

        self.assertEqual(len(results), 1)
        url, snippet = results[0]
        self.assertEqual(url, "https://example.com/einstein/")
        # Preview is the head of the body, no brackets.
        self.assertNotIn("[", snippet)
        self.assertIn("imagination", snippet)

    def test_empty_query_and_empty_facets_returns_empty_list(self):
        # The "nothing requested" case must not browse the whole corpus.
        self.assertEqual(find_pages_with_snippets(self.index, "", facets={}), [])

    def test_phrase_query_plus_facet_intersects(self):
        # Phrase mode + facet: build a tiny phrase-friendly index.
        index = Index(
            documents={0: "https://example.com/page-1/"},
            documents_text={0: "We are all good friends here together."},
            postings={
                "good": {0: {
                    "frequency": 1,
                    "positions": [3],
                    "fields": {},
                }},
                "friends": {0: {
                    "frequency": 1,
                    "positions": [4],
                    "fields": {},
                }},
                "einstein": {0: {
                    "frequency": 0,
                    "positions": [],
                    "fields": {"author": {"frequency": 1, "positions": [0]}},
                }},
            },
            doc_lengths={0: 8},
        )

        # Phrase matches AND author=einstein matches → result returned.
        kept = find_phrase_with_snippets(
            index, "good friends", facets={"author": ["einstein"]}
        )
        self.assertEqual(len(kept), 1)
        self.assertIn("[good friends]", kept[0][1])

        # Phrase matches but author=wilde fails → result filtered out.
        dropped = find_phrase_with_snippets(
            index, "good friends", facets={"author": ["wilde"]}
        )
        self.assertEqual(dropped, [])


class ParseFacetsTests(unittest.TestCase):
    """Parser for ``field=value`` facet syntax (v1.5.0).

    Pins the brief-compatibility invariant: any args list that
    contains no ``=`` characters must route through unchanged so
    the existing ``find good friends`` semantics stay byte-identical.
    """

    def test_no_facets_returns_empty_dict_and_joined_free_text(self):
        # The brief-compliant path: zero "=" anywhere → all args
        # collapse to the free-text query body, no facets parsed.
        facets, free_text = parse_facets(["good", "friends"])

        self.assertEqual(facets, {})
        self.assertEqual(free_text, "good friends")

    def test_empty_args_returns_empty_facets_and_empty_text(self):
        self.assertEqual(parse_facets([]), ({}, ""))

    def test_single_facet_with_free_text(self):
        facets, free_text = parse_facets(["author=einstein", "wisdom"])

        self.assertEqual(facets, {"author": ["einstein"]})
        self.assertEqual(free_text, "wisdom")

    def test_facet_value_with_internal_space_via_shlex_handling(self):
        # ``shlex.split('find author="oscar wilde" wisdom')`` produces
        # ``["find", "author=oscar wilde", "wisdom"]`` — a single arg
        # with a space inside the value half. The parser must keep
        # the whole value intact, not split on the space.
        facets, free_text = parse_facets(["author=oscar wilde", "wisdom"])

        self.assertEqual(facets, {"author": ["oscar wilde"]})
        self.assertEqual(free_text, "wisdom")

    def test_multiple_facets_different_fields_aggregate(self):
        facets, _ = parse_facets(["author=einstein", "tag=science"])

        self.assertEqual(facets, {"author": ["einstein"], "tag": ["science"]})

    def test_multiple_values_same_field_aggregate_into_list_for_or_semantics(self):
        # Disjunctive multi-value on one field — matches conventional
        # facet UI behaviour ("tick both Science and Physics").
        facets, _ = parse_facets(["tag=science", "tag=physics"])

        self.assertEqual(facets, {"tag": ["science", "physics"]})

    def test_facet_only_query_returns_empty_free_text(self):
        # ``find author=einstein`` with no free-text words is valid —
        # browse all Einstein quotes.
        facets, free_text = parse_facets(["author=einstein"])

        self.assertEqual(facets, {"author": ["einstein"]})
        self.assertEqual(free_text, "")

    def test_facet_field_name_is_case_normalised(self):
        # ``Author=Einstein`` works the same as ``author=einstein``
        # so the user does not have to remember internal capitalisation.
        facets, _ = parse_facets(["Author=Einstein", "AUTHOR=newton"])

        self.assertEqual(facets, {"author": ["Einstein", "newton"]})

    def test_unknown_field_raises_value_error_listing_known_fields(self):
        # Typo detection. The error message must list what is allowed
        # so the user can correct without consulting the docs.
        with self.assertRaises(ValueError) as ctx:
            parse_facets(["athor=einstein", "wisdom"])

        msg = str(ctx.exception)
        self.assertIn("Unknown facet field", msg)
        self.assertIn("athor", msg)
        self.assertIn("author", msg)

    def test_empty_field_raises_value_error(self):
        # ``=einstein`` has nothing before the ``=`` — clear typo.
        with self.assertRaises(ValueError) as ctx:
            parse_facets(["=einstein"])

        self.assertIn("Empty facet field", str(ctx.exception))

    def test_empty_value_raises_value_error(self):
        # ``author=`` is an empty filter; refusing to interpret it
        # prevents a "matches everything" surprise.
        with self.assertRaises(ValueError) as ctx:
            parse_facets(["author=", "wisdom"])

        self.assertIn("Empty facet value", str(ctx.exception))

    def test_equals_in_free_text_word_is_caught_as_facet(self):
        # If a user inputs a token with an unintended ``=``, the
        # parser treats it as a facet attempt — which then fails the
        # field-name check with a clear error. Better than silently
        # routing odd input through the free-text path.
        with self.assertRaises(ValueError):
            parse_facets(["x=y"])


class SuggestForQueryTests(unittest.TestCase):
    def setUp(self):
        # A tiny vocabulary that gives us deliberate near-misses for
        # canonical typos: indi*erence / friend* / good*.
        self.index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
                "indignant": {0: {"frequency": 1, "positions": [1]}},
                "friend": {0: {"frequency": 1, "positions": [2]}},
                "friendly": {0: {"frequency": 1, "positions": [3]}},
                "good": {0: {"frequency": 1, "positions": [4]}},
                "goodness": {0: {"frequency": 1, "positions": [5]}},
            },
        )

    def test_returns_empty_when_every_token_in_vocabulary(self):
        # Known query is not a typo candidate — keeps "did you mean"
        # noise out of legitimate find calls that simply return zero
        # pages because of the AND filter.
        self.assertEqual(suggest_for_query(self.index, "good friend"), {})

    def test_returns_candidates_for_unknown_token(self):
        result = suggest_for_query(self.index, "indiference")
        self.assertIn("indiference", result)
        self.assertIn("indifference", result["indiference"])

    def test_applies_index_tokenizer_config_for_case_insensitivity(self):
        # Tokeniser lowercases by default; suggestion should follow
        # the same path so a typo with uppercase chars still resolves.
        result = suggest_for_query(self.index, "Indiference")
        self.assertIn("indiference", result)
        self.assertIn("indifference", result["indiference"])

    def test_empty_query_returns_empty_mapping(self):
        self.assertEqual(suggest_for_query(self.index, ""), {})

    def test_no_candidate_within_threshold_returns_empty_list(self):
        # "xyzqq" has nothing within edit distance 2 of any vocab term.
        result = suggest_for_query(self.index, "xyzqq")
        self.assertEqual(result, {"xyzqq": []})


class FormatDidYouMeanTests(unittest.TestCase):
    def setUp(self):
        self.index = Index(
            documents={0: "page-1"},
            postings={
                "indifference": {0: {"frequency": 1, "positions": [0]}},
                "friend": {0: {"frequency": 1, "positions": [1]}},
                "good": {0: {"frequency": 1, "positions": [2]}},
            },
        )

    def test_returns_none_when_every_token_in_vocab(self):
        # Zero results when query is valid is an AND-filter miss, not
        # a typo — a "did you mean" hint would mislead the user.
        self.assertIsNone(format_did_you_mean(self.index, "good friend"))

    def test_returns_none_for_empty_query(self):
        self.assertIsNone(format_did_you_mean(self.index, ""))

    def test_returns_reformulated_single_token_query(self):
        hint = format_did_you_mean(self.index, "indiference")
        self.assertEqual(hint, "Did you mean: indifference?")

    def test_returns_reformulated_multi_token_query_preserving_order(self):
        # Order matters — the reformulation must read in the original
        # word order so the user can copy-paste it back into find.
        hint = format_did_you_mean(self.index, "indiference godo")
        self.assertEqual(hint, "Did you mean: indifference good?")

    def test_keeps_known_tokens_verbatim_in_reformulation(self):
        hint = format_did_you_mean(self.index, "good indiference")
        # "good" is in vocab, passes through; "indiference" is corrected.
        self.assertEqual(hint, "Did you mean: good indifference?")

    def test_returns_none_when_no_unknown_token_has_a_candidate(self):
        # "xyzqq" is unknown but has nothing within edit distance 2
        # — nothing useful to suggest, stay silent.
        self.assertIsNone(format_did_you_mean(self.index, "xyzqq"))

    def test_keeps_uncorrectable_token_alongside_correctable_one(self):
        # If at least one token has a candidate, surface the line —
        # uncorrectable tokens pass through so the user still sees
        # every word they typed in the reformulation.
        hint = format_did_you_mean(self.index, "indiference xyzqq")
        self.assertEqual(hint, "Did you mean: indifference xyzqq?")


if __name__ == "__main__":
    unittest.main()
