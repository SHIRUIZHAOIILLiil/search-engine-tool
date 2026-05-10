"""Text tokenisation with optional stopword filtering and Porter stemming.

Implements Lecture 11's two extension topics on top of the regex
tokeniser the indexer already uses:

* **Stopword filtering** — drop common English function words (``the``,
  ``of``, ``and``...). L11 notes this "decreases index size, increases
  retrieval efficiency, and generally improves retrieval effectiveness"
  *but* warns that "removing too many of these will negatively impact
  retrieval effectiveness" (e.g. the query "to be or not to be" is all
  stopwords). The feature is therefore opt-in via :class:`TokenizerConfig`.

* **Porter stemming** — collapse inflected forms ("running" → "run",
  "cats" → "cat") so queries match variants. Implements Steps 1a, 1b,
  and 1c of Martin Porter's 1980 algorithm. Steps 2-5 (derivational
  suffixes like ``-ization`` / ``-fulness``) are omitted; L11 notes
  English stemming improvements are typically below 5%, so this subset
  captures most of the value with a fraction of the code surface.

Both features default to OFF so the tokeniser stays brief-compliant
(case-insensitive bag of regex tokens) unless the caller opts in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9']+")

# Hand-curated subset of the most universally non-content English
# function words. Sized conservatively (~25 entries) to avoid the
# "to be or not to be" failure mode Lecture 11 calls out.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "has", "have", "he", "in", "is", "it", "its", "of", "on", "that",
        "the", "this", "to", "was", "were", "will", "with",
    }
)


@dataclass(frozen=True)
class TokenizerConfig:
    """Opt-in tokenisation extensions.

    Both flags default to ``False`` so the tokeniser stays identical to
    the brief's requirement (case-insensitive, regex-based bag of words).
    """

    apply_stopword_filter: bool = False
    apply_stemming: bool = False


def tokenize(text: str, config: TokenizerConfig | None = None) -> list[str]:
    """Return the tokens of ``text`` per the (optional) config.

    With the default config, behaves exactly like the brief's
    requirement: split on the regex ``[A-Za-z0-9']+`` and lowercase.
    Stopword removal (if enabled) happens before stemming so the
    stopword list can stay in plain dictionary form.
    """
    if config is None:
        config = TokenizerConfig()
    tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]
    if config.apply_stopword_filter:
        tokens = [t for t in tokens if t not in STOPWORDS]
    if config.apply_stemming:
        tokens = [porter_stem(t) for t in tokens]
    return tokens


# --- Porter Step 1 implementation ------------------------------------

_VOWELS = "aeiou"


def _is_consonant(word: str, i: int) -> bool:
    """Porter's consonant test.

    ``y`` is a special case: it counts as a consonant only when
    preceded by a vowel (or when it's the very first character).
    """
    c = word[i]
    if c in _VOWELS:
        return False
    if c == "y":
        if i == 0:
            return True
        return not _is_consonant(word, i - 1)
    return True


def _measure(stem: str) -> int:
    """Porter's ``m`` measure: number of vowel-consonant pairs in stem.

    A word can be written as ``[C](VC){m}[V]``; ``m`` counts the ``VC``
    pairs after the optional leading consonant run and before the
    optional trailing vowel run.
    """
    n = len(stem)
    i = 0
    while i < n and _is_consonant(stem, i):
        i += 1
    m = 0
    while i < n:
        while i < n and not _is_consonant(stem, i):
            i += 1
        if i >= n:
            break
        while i < n and _is_consonant(stem, i):
            i += 1
        m += 1
    return m


def _contains_vowel(stem: str) -> bool:
    """Porter's ``*v*`` condition."""
    return any(not _is_consonant(stem, i) for i in range(len(stem)))


def _ends_with_double_consonant(stem: str) -> bool:
    """Porter's ``*d`` condition: stem ends with a doubled consonant."""
    if len(stem) < 2:
        return False
    return _is_consonant(stem, len(stem) - 1) and stem[-1] == stem[-2]


def _ends_with_cvc(stem: str) -> bool:
    """Porter's ``*o`` condition: stem ends with CVC, trailing C ∉ {w,x,y}."""
    n = len(stem)
    if n < 3:
        return False
    return (
        _is_consonant(stem, n - 3)
        and not _is_consonant(stem, n - 2)
        and _is_consonant(stem, n - 1)
        and stem[-1] not in "wxy"
    )


def _step1a(word: str) -> str:
    """Porter Step 1a: plurals."""
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _step1b(word: str) -> str:
    """Porter Step 1b: past tense / present participle."""
    if word.endswith("eed"):
        stem = word[:-3]
        if _measure(stem) > 0:
            return word[:-1]
        return word
    for suffix in ("ed", "ing"):
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if _contains_vowel(stem):
                return _step1b_cleanup(stem)
            return word
    return word


def _step1b_cleanup(stem: str) -> str:
    """Restore short stems mangled by step 1b."""
    if stem.endswith("at") or stem.endswith("bl") or stem.endswith("iz"):
        return stem + "e"
    if _ends_with_double_consonant(stem) and stem[-1] not in "lsz":
        return stem[:-1]
    if _measure(stem) == 1 and _ends_with_cvc(stem):
        return stem + "e"
    return stem


def _step1c(word: str) -> str:
    """Porter Step 1c: final ``y`` → ``i`` when stem contains a vowel."""
    if word.endswith("y"):
        stem = word[:-1]
        if _contains_vowel(stem):
            return stem + "i"
    return word


def porter_stem(word: str) -> str:
    """Apply Porter's Step 1 stemming to a single token.

    Implements steps 1a (plurals), 1b (past tense / participle), and
    1c (final ``y`` → ``i``) of Martin Porter's 1980 *An algorithm for
    suffix stripping*. The further steps (2-5) handle derivational
    suffixes; Lecture 11 notes English stemming impact is typically
    below 5%, so this subset is a defensible scope trade-off for the
    coursework.

    The input is expected to be lowercased; :func:`tokenize` handles
    that on the public path.
    """
    if not word:
        return word
    word = _step1a(word)
    word = _step1b(word)
    word = _step1c(word)
    return word
