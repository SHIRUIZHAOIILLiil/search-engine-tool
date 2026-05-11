"""Performance benchmark scripts for the search engine tool.

Out-of-CI scripts that compare Lecture 13 retrieval algorithms
(DAAT, TAAT, conjunctive simple, conjunctive with skip pointers) on
synthetic corpora of varying scale. Kept separate from ``tests/`` so
the noisy timing data does not run on every CI invocation; invoked
manually when collecting numbers for the report.
"""
