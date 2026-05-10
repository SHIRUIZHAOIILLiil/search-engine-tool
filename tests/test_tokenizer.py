import unittest

from src.tokenizer import STOPWORDS, TokenizerConfig, porter_stem, tokenize


class TokenizeTests(unittest.TestCase):
    def test_default_config_lowercases_and_strips_punctuation(self):
        self.assertEqual(tokenize("Good, friends!"), ["good", "friends"])

    def test_default_config_keeps_stopwords_and_does_not_stem(self):
        # Brief-compliant default: nothing is filtered or transformed
        # beyond casing/punctuation, so "the running cats" stays intact.
        self.assertEqual(
            tokenize("the running cats"),
            ["the", "running", "cats"],
        )

    def test_stopword_filter_removes_common_function_words(self):
        config = TokenizerConfig(apply_stopword_filter=True)

        self.assertEqual(
            tokenize("the cat and the dog", config),
            ["cat", "dog"],
        )

    def test_stemming_reduces_inflected_forms(self):
        config = TokenizerConfig(apply_stemming=True)

        self.assertEqual(
            tokenize("running cats happy", config),
            ["run", "cat", "happi"],
        )

    def test_stopwords_and_stemming_compose_in_that_order(self):
        # Stopword filter first, then stemming. The order matters: if
        # stemming ran first, "the" might map to a non-stopword form.
        config = TokenizerConfig(apply_stopword_filter=True, apply_stemming=True)

        self.assertEqual(
            tokenize("the running cats", config),
            ["run", "cat"],
        )


class PorterStemTests(unittest.TestCase):
    def test_stems_simple_plural_s(self):
        self.assertEqual(porter_stem("cats"), "cat")
        self.assertEqual(porter_stem("dogs"), "dog")

    def test_stems_ies_plurals(self):
        self.assertEqual(porter_stem("ponies"), "poni")
        self.assertEqual(porter_stem("flies"), "fli")

    def test_stems_sses_plurals(self):
        self.assertEqual(porter_stem("caresses"), "caress")

    def test_preserves_ss_endings(self):
        self.assertEqual(porter_stem("caress"), "caress")

    def test_stems_present_participle_ing(self):
        self.assertEqual(porter_stem("running"), "run")
        self.assertEqual(porter_stem("swimming"), "swim")
        self.assertEqual(porter_stem("motoring"), "motor")

    def test_stems_past_tense_ed(self):
        self.assertEqual(porter_stem("plastered"), "plaster")

    def test_stems_eed_only_when_stem_has_positive_measure(self):
        # "agreed" → "agree": stem "agr" has m=1, rule applies (eed → ee).
        self.assertEqual(porter_stem("agreed"), "agree")
        # "feed" → "feed": stem "f" has m=0, rule does not apply.
        self.assertEqual(porter_stem("feed"), "feed")

    def test_stems_y_to_i_only_when_stem_contains_vowel(self):
        # "happy" → "happi": stem "happ" has a vowel.
        self.assertEqual(porter_stem("happy"), "happi")
        # "sky" → "sky": stem "sk" has no vowel, rule does not apply.
        self.assertEqual(porter_stem("sky"), "sky")

    def test_step1b_cleanup_restores_at_bl_iz_endings(self):
        # After stripping -ed/-ing, certain truncated stems get an 'e'
        # appended so the result stays a real word root.
        self.assertEqual(porter_stem("conflated"), "conflate")
        self.assertEqual(porter_stem("troubled"), "trouble")
        self.assertEqual(porter_stem("sized"), "size")

    def test_step1b_cleanup_collapses_double_consonants_except_lsz(self):
        # Doubled consonants get collapsed (hopp → hop) unless the doubled
        # letter is l/s/z (which would create real -ll, -ss, -zz words).
        self.assertEqual(porter_stem("hopping"), "hop")
        self.assertEqual(porter_stem("hissing"), "hiss")

    def test_returns_empty_for_empty_input(self):
        self.assertEqual(porter_stem(""), "")


class StopwordsTests(unittest.TestCase):
    def test_set_contains_common_function_words(self):
        for word in ("the", "a", "an", "and", "of", "is", "to"):
            self.assertIn(word, STOPWORDS, f"expected {word!r} in STOPWORDS")

    def test_set_excludes_content_words(self):
        for word in ("good", "happy", "indifference", "running"):
            self.assertNotIn(word, STOPWORDS, f"did not expect {word!r}")


class TokenizerConfigTests(unittest.TestCase):
    def test_defaults_to_brief_compliant_behaviour(self):
        config = TokenizerConfig()

        self.assertFalse(config.apply_stopword_filter)
        self.assertFalse(config.apply_stemming)

    def test_is_hashable_and_frozen(self):
        # frozen=True means we can put configs in sets / use as dict keys.
        a = TokenizerConfig(apply_stemming=True)
        b = TokenizerConfig(apply_stemming=True)

        # Equality and hash by value.
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        # And: mutation raises.
        with self.assertRaises(Exception):
            a.apply_stemming = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
