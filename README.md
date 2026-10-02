# hebrew-bible-characteristic-language

Characteristic language in the Hebrew Bible, chapter by chapter.

For every chapter of the Hebrew Bible (MT, BHSA 2021), this is an inventory of the
words and phrases that are typical of the chapter's book: vocabulary found only in
that book, language shared with at most a few other books, and expressions the book
clearly prefers. It comes with an interactive interface. For Jeremiah and 2 Kings 25
there is also an MT/LXX layer based on Stipp's *Textkritische Synopse*.

Open `docs/index.html` in a browser. It works straight from the file system, without
a server. Use the book and chapter menus, or a link such as `index.html#Jeremia/25`.
The `docs/` folder (about 170 MB) can be published as is with GitHub Pages.

## Rebuild

```
python scripts/build.py                  # copy the app (extracts the data only if it is missing)
python scripts/build.py --refresh        # re-extract the whole Hebrew Bible (about 2 minutes)
python scripts/build.py Jeremia 25 26    # re-extract only some chapters (BHSA book name)
```

Requires `text-fabric` and the BHSA 2021 data in `~/text-fabric-data/github/ETCBC/bhsa/tf/2021`.

| File | What it does |
|---|---|
| `scripts/extract_bhsa.py` | Builds the inventory for each chapter, writing `docs/data/ch/<book>/<chapter>.js`, the concordance text in `docs/data/text/<book>.js`, and `docs/data/index.js` |
| `scripts/parse_lxx.py` | Reads Stipp's synopsis (cached in `data/raw/`) and aligns it with the BHSA words |
| `scripts/app.html` | The interface; copied to `docs/index.html` |
| `scripts/build.py` | Runs the steps above |

The thresholds are at the top of `extract_bhsa.py`: `MAX_OTHER`, `G2_MIN`, `RATIO_MIN`,
`HOME_MIN`, `PAIR_LOGDICE`, `OCC_CAP`, and so on. The Method tab of the page explains them.

Book counting: 1–2 Samuel, 1–2 Kings and 1–2 Chronicles each count as one book.
Ezra and Nehemiah count as two separate books (`BOOK_UNIT` in `extract_bhsa.py`).
