# CLAUDE.md

## Project

Support for a group translating the book of Jeremiah, chapter by chapter (starting with Jer 25).
The tool now covers **every chapter of the Hebrew Bible**. For each chapter it builds an inventory
of **characteristic language**, measured against the chapter's own book (the "home book"):
vocabulary unique to the book, words and phrases shared with only a few other books, and
expressions the book clearly prefers. It is shown in one app page (`docs/index.html`) with
book/chapter navigation, which may later be published with GitHub Pages. See `README.md` for usage.

## Commands

```
python scripts/build.py                  # copy app to docs/ (extracts data only if missing)
python scripts/build.py --refresh        # re-extract the whole MT (~2 min, ~170 MB in docs/data)
python scripts/build.py Jeremia 25       # re-extract some chapters (BHSA book names: Samuel_I, Reges_II, ...)
```

On Windows, prefix with `PYTHONIOENCODING=utf8` when a script prints Hebrew.
To view the app in the browser tool, serve it (`python -m http.server 8765 --bind 127.0.0.1` in `docs/`).
The extension does not open `file://` URLs. Users can open it from `file://`.

## Architecture

- `scripts/extract_bhsa.py`: loads the BHSA 2021 with Text-Fabric from
  `~/text-fabric-data/github/ETCBC/bhsa/tf/2021`.
  - It builds global indexes once (lexemes, clause-level pairs, verb + argument).
  - It scans n-grams once per book unit (candidates from that unit, one corpus scan).
  - Each chapter is then classified and pruned.
  - It writes:
    - `docs/data/index.js` (`__index(...)`: books, units, parameters);
    - `docs/data/text/<book>.js` (`__text(...)`: verse texts for the concordance);
    - `docs/data/ch/<book>/<n>.js` (`__chapter(...)`).
- Data files are JS (`__name(json)`) loaded with `<script>` tags, so the app works from `file://`.
  Chapter files load on navigation. Text files load per book, only when a concordance needs them.
- Concordance occurrences are encoded compactly: `verseIndex*256 + firstOffset` (lex), `[head, lastOffset]`
  (ngram), `[head, other offsets...]` (pair/syn). The app's `decode()` reverses this.
  Each item keeps at most `OCC_CAP` = 400 verses (round-robin over books); `nocc` holds the true number.
  Per-book `counts` are always complete.
- `scripts/parse_lxx.py`: a module with `page_for`, `synopsis` and `align`. It covers Jeremiah 1–52 and 2 Kings 25, from
  https://martijnnaaijer.github.io/mt_greek_jeremiah/ (the user's own web edition of Stipp's
  *Textkritische Synopse*), cached in `data/raw/`. It aligns Stipp's MT column letter by letter with the BHSA words,
  giving per-word `common` / `plus` / `var`.
- The app opens on an overview of all books and chapters (empty hash); `☰ All books` returns there.
- `scripts/app.html` is the interface source. `build.py` copies it to `docs/index.html`. Edit `app.html`, never `docs/`.
  The URL hash `#<Book>/<chapter>[/item=<id>]` selects the chapter and item.

## Decisions made with the user (keep these)

- **Book counting:** 1–2 Samuel, 1–2 Kings and 1–2 Chronicles each count as one book. Ezra and
  Nehemiah are **two** books. Set in `BOOK_UNIT`.
- **"Unique word" / "Word only in <book>" (blue) is for single words (lexemes) only.** Phrases,
  collocations and verb + argument items found only in the home book are not special. They fall
  under `restricted` ("<book> + ≤ 3 other books", with 0 other books).
- Category ids: `hapax`, `only` (words only), `restricted` (≤ `MAX_OTHER` = 3 other books),
  `pref` (G² ≥ 10.83, ratio ≥ 2.5, ≥ 4× in the home book), `rare` (word ≤ 10× in the MT).
- Interface in **English**, with BHSA glosses. A local HTML site is enough; no hosted or shared-state features.
- The LXX layer exists only where Stipp has data (Jeremiah, 2 Kings 25). Elsewhere it is hidden, which the user accepted.
  Readings and retroversions are Stipp's; show them, don't alter them.

## Item types

- `lex`: single lexeme.
- `ngram`: 2–6 contiguous lexemes within a verse, matched with the article and waw removed.
  An n-gram is rejected if it starts with the object marker or a conjunction (except אשר), or ends
  in a preposition, conjunction, article or construct-state noun. Overlapping n-grams with equal
  frequency are merged. A shorter n-gram is dropped when a longer one covers ≥ 80% of it.
- `pair`: two content lexemes in one clause (כל not counted), logDice ≥ 7, no name + name pairs.
  Dropped if it is inside a kept n-gram or adds nothing to the rarer word.
- `syn`: predicate verb + head of subject/object/complement phrase (+ preposition).

## Gotchas

- BHSA splits prefixes into separate words (ב, ה, ו, ל). The elided article has an empty text.
  The app groups words into written words by `trailer`.
- A clause can span verses: get the verse from a word (`L.u(word, 'verse')`), not from the clause.
- Word nodes are consecutive integers, so n-gram spans use `range(first, last+1)`.
- Aramaic lexemes get the suffix `@A` in their key, so they are kept apart from Hebrew homographs.
- Category colours (blue / orange / aqua) passed the dataviz palette validator in light and dark mode.
  A 4th hue failed, so hapax/rare use a neutral dotted underline. Don't add hues without re-validating.
- Screenshots right after a render sometimes miss text underlines (a paint timing issue). Check the
  computed style before assuming a bug.
- Bash heredocs that contain Python with `r'''…'''` broke in Git Bash. For larger patches, write
  the script to a file first.
