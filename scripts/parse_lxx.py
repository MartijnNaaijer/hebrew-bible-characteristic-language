"""MT / Old Greek comparison from Stipp's synopsis.

Source: the web edition of Hermann-Josef Stipp, Textkritische Synopse zum
Jeremiabuch, at https://martijnnaaijer.github.io/mt_greek_jeremiah/ . It covers
all chapters of Jeremiah and 2 Kings 25. Pages are cached in data/raw/.

Used by extract_bhsa.py:
  page_for(book, chapter)     page name, or None if the synopsis has no such chapter
  synopsis(page)              verses -> sentences (MT, retroversion, Greek, notes)
  align(verses, chapter)      status per BHSA word of the chapter, by aligning
                              Stipp's masoretic column with the BHSA letter by letter
Word status:
  common   in both editions
  plus     masoretic plus (absent from the Greek)
  var      qualitative variant (both editions have something, but not the same)
"""
import difflib
import os
import urllib.request
from html.parser import HTMLParser

BASE = "https://martijnnaaijer.github.io/mt_greek_jeremiah/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CREDIT = ("Hermann-Josef Stipp, Textkritische Synopse zum Jeremiabuch, "
          "15. korrigierte interne Auflage, 2021; web edition by Martijn Naaijer")

STATUS = {"common": "common", "plus": "plus", "mtvar": "var", "mtsup": "var",
          "minus": "minus", "ogvar": "var"}


def page_for(book, chapter):
    if book == "Jeremia" and 1 <= chapter <= 52:
        return f"jer{chapter:02d}"
    if book == "Reges_II" and chapter == 25:
        return "2kings25"
    return None


def letters(s):
    """Hebrew consonants only (final forms kept as they are)."""
    return "".join(c for c in s if "א" <= c <= "ת")


class Synopse(HTMLParser):
    def __init__(self):
        super().__init__()
        self.verses = []
        self.verse = None
        self.td = None          # class of the current <td>
        self.col = 0            # 0 = MT, 1 = retroversion
        self.span = None        # status of the current word span
        self.in_badge = self.in_note = False
        self.row = None
        self.colhead = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "section" and "v" in cls:
            self.verse = {"v": int(a["id"][1:]), "lxx_ref": None, "rows": []}
            self.verses.append(self.verse)
            self.col = 0
            self.row = None
        elif self.verse is None:
            return
        elif tag == "span" and "badge" in cls:
            self.in_badge = True
        elif tag == "tr":
            self.colhead = "colhead" in cls
        elif tag == "td" and not self.colhead:
            self.td = cls[0] if cls else ("notes" if a.get("colspan") else None)
            if self.td == "heb":
                if self.row is None or self.col == 1:
                    self.row = {"cl": "", "mt": [], "og": [], "gk": "", "notes": ""}
                    self.verse["rows"].append(self.row)
                    self.col = 0
                else:
                    self.col = 1
        elif tag == "span" and "w" in cls and self.td in ("heb", "grk"):
            st = next((STATUS[c] for c in cls if c in STATUS), "common")
            self.span = st
            if self.td == "heb":
                (self.row["mt"] if self.col == 0 else self.row["og"]).append(["", st])
        elif tag == "span" and "n" in cls:
            self.in_note = True
            if self.verse["rows"] and self.verse["rows"][-1]["notes"]:
                self.verse["rows"][-1]["notes"] += " "

    def handle_endtag(self, tag):
        if tag == "span":
            self.span = None
            self.in_badge = self.in_note = False
        elif tag == "td":
            self.td = None

    def handle_data(self, data):
        if self.verse is None:
            return
        if self.in_badge and data.startswith("Jer G"):
            self.verse["lxx_ref"] = data.strip()
        elif self.td == "cl" and self.row is not None:
            self.row["cl"] += data.strip()
        elif self.td == "heb" and self.span is not None:
            (self.row["mt"] if self.col == 0 else self.row["og"])[-1][0] += data
        elif self.td == "grk" and self.row is not None:
            self.row["gk"] += data
        elif self.in_note and self.verse["rows"]:
            self.verse["rows"][-1]["notes"] += data


def synopsis(page):
    path = os.path.join(RAW, page + ".html")
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        urllib.request.urlretrieve(BASE + page + ".html", path)
    p = Synopse()
    p.feed(open(path, encoding="utf8").read())
    for v in p.verses:
        v["rows"] = [r for r in v["rows"] if r["mt"] or r["og"] or r["gk"].strip()]
        for r in v["rows"]:
            r["gk"] = " ".join(r["gk"].split())
            r["notes"] = " ".join(r["notes"].split())
    return p.verses


def align(verses, chapter_verses, cons):
    """chapter_verses: [(verse number, [word index, ...])]; cons: consonants per word index.
    Returns (status per word index, verses aligned with differences)."""
    status = [None] * len(cons)
    by_v = {v["v"]: v for v in verses}
    mismatch = []
    for vn, ws in chapter_verses:
        sv = by_v.get(vn)
        if sv is None:
            continue
        s_chars, s_stat = [], []
        for r in sv["rows"]:
            for text, st in r["mt"]:
                for c in letters(text):
                    s_chars.append(c)
                    s_stat.append(st)
        b_chars, b_owner = [], []
        for wi in ws:
            for c in letters(cons[wi]):
                b_chars.append(c)
                b_owner.append(wi)
        if s_chars == b_chars:
            char_stat = s_stat
        else:
            mismatch.append(vn)
            char_stat = [None] * len(b_chars)
            sm = difflib.SequenceMatcher(None, s_chars, b_chars, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    char_stat[j1:j2] = s_stat[i1:i2]
        for c, wi in zip(char_stat, b_owner):
            if c and status[wi] is None:
                status[wi] = c
        # words without letters (elided article) or unmatched: take the next word's status
        for k in range(len(ws) - 1, -1, -1):
            if status[ws[k]] is None:
                status[ws[k]] = status[ws[k + 1]] if k + 1 < len(ws) else "common"
    return [s or "common" for s in status], mismatch
