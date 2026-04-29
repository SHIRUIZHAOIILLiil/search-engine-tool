# Search Engine Tool

Coursework 2 project for COMP3011 Web Services and Web Data.

The tool crawls `https://quotes.toscrape.com/`, builds an inverted index of quote text, saves the index to disk, and lets a user search it from a command-line shell.

## Setup

```powershell
python -m pip install -r requirements.txt
```

## Usage

Run the command-line shell:

```powershell
python -m src.main
```

Available commands:

```text
build
load
print nonsense
find indifference
find good friends
exit
```

`build` crawls the website, creates the inverted index, and saves it to `data/index.json`.

`load` loads the saved index from `data/index.json`.

`print <word>` prints the posting list for a single word.

`find <query>` returns pages containing all words in the query.

## Testing

Run the test suite:

```powershell
python -m unittest discover
```

## Current Design

The code is split into four main components:

- `src/crawler.py`: crawls quote pages and respects a 6-second politeness delay.
- `src/indexer.py`: tokenizes quote text and builds a case-insensitive inverted index.
- `src/search.py`: implements word lookup and multi-word search.
- `src/main.py`: provides the interactive command-line interface.

The inverted index stores each word against the pages where it appears, including frequency and token positions.
