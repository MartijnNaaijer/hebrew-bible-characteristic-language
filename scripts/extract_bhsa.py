"""Inventory of characteristic language for every chapter of the Hebrew Bible (BHSA).

For each chapter, the language of the chapter is compared with its own book (the
"home book"): what is unique to that book, shared with few other books, or clearly
preferred by it.

Usage:  python scripts/extract_bhsa.py                      all books
        python scripts/extract_bhsa.py Jeremia [25 ...]      one book (BHSA name), some chapters
Output: docs/data/index.js                 books, chapters, parameters
        docs/data/text/<book>.js           text of every verse (for the concordance)
        docs/data/ch/<book>/<chapter>.js   words and items of one chapter

Item types
  lex     single lexeme
  ngram   contiguous lexeme sequence (2-6 tokens) within a verse; the article
          and the conjunction waw are ignored when matching
  pair    two content lexemes in the same clause, in any order and distance
  syn     verb + head of its subject / object / complement phrase (with preposition)

Categories (relative to the home book; Samuel, Kings and Chronicles count as one book)
  hapax        lexeme that occurs only once in the MT
  only         (lexemes only) occurs >= 2 times, only in the home book
  restricted   occurs in the home book and in at most MAX_OTHER other books (for
               multi-word items this includes items found only in the home book)
  pref         widespread, but clearly more frequent in the home book (log-likelihood)
  rare         (lexemes only) at most RARE_MAX occurrences, spread over several books
Items that fit none of these are dropped.
"""
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations

from tf.fabric import Fabric

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_lxx  # noqa: E402

MAX_OTHER = 3          # "restricted" = home book + at most this many other books
MIN_TOTAL = 2          # multi-word items must occur at least this often in the MT
NGRAM_MAX = 6
G2_MIN = 10.83         # p < .001
RATIO_MIN = 2.5        # relative frequency in the home book / elsewhere
HOME_MIN = 4           # minimum occurrences in the home book for "pref"
CONTENT_SP = {"subs", "verb", "adjv", "nmpr"}
LIGHT = {"KL/"}        # not counted as a content word
RARE_MAX = 10          # lexemes with at most this many occurrences are "rare"
PAIR_LOGDICE = 7.0     # minimum collocation strength (logDice, clause level) for pairs
NGRAM_COVER = 0.8      # see "n-grams 2" in prune()
OCC_CAP = 400          # max. concordance verses stored per item (counts are always complete)
PRED_FUNCS = {"Pred", "PreO", "PreS", "PtcO", "PreC"}
ARG_FUNCS = {"Subj": "subject", "Objc": "object", "Cmpl": "complement"}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data")

BOOK_UNIT = {"Samuel_I": "Samuel", "Samuel_II": "Samuel",
             "Reges_I": "Kings", "Reges_II": "Kings",
             "Chronica_I": "Chronicles", "Chronica_II": "Chronicles"}
BOOK_EN = {"Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
           "Numeri": "Numbers", "Deuteronomium": "Deuteronomy", "Josua": "Joshua",
           "Judices": "Judges", "Samuel_I": "1 Samuel", "Samuel_II": "2 Samuel",
           "Reges_I": "1 Kings", "Reges_II": "2 Kings",
           "Jesaia": "Isaiah", "Jeremia": "Jeremiah", "Ezechiel": "Ezekiel",
           "Hosea": "Hosea", "Joel": "Joel", "Amos": "Amos", "Obadia": "Obadiah",
           "Jona": "Jonah", "Micha": "Micah", "Nahum": "Nahum", "Habakuk": "Habakkuk",
           "Zephania": "Zephaniah", "Haggai": "Haggai", "Sacharia": "Zechariah",
           "Maleachi": "Malachi", "Psalmi": "Psalms", "Iob": "Job",
           "Proverbia": "Proverbs", "Ruth": "Ruth", "Canticum": "Song of Songs",
           "Ecclesiastes": "Ecclesiastes", "Threni": "Lamentations",
           "Esther": "Esther", "Daniel": "Daniel", "Esra": "Ezra",
           "Nehemia": "Nehemiah", "Chronica_I": "1 Chronicles", "Chronica_II": "2 Chronicles",
           "Samuel": "Samuel", "Kings": "Kings", "Chronicles": "Chronicles"}
ABBR = {"Genesis": "Gen", "Exodus": "Exod", "Leviticus": "Lev", "Numeri": "Num",
        "Deuteronomium": "Deut", "Josua": "Josh", "Judices": "Judg", "Samuel_I": "1 Sam",
        "Samuel_II": "2 Sam", "Reges_I": "1 Kgs", "Reges_II": "2 Kgs", "Jesaia": "Isa",
        "Jeremia": "Jer", "Ezechiel": "Ezek", "Hosea": "Hos", "Joel": "Joel", "Amos": "Amos",
        "Obadia": "Obad", "Jona": "Jonah", "Micha": "Mic", "Nahum": "Nah", "Habakuk": "Hab",
        "Zephania": "Zeph", "Haggai": "Hag", "Sacharia": "Zech", "Maleachi": "Mal",
        "Psalmi": "Ps", "Iob": "Job", "Proverbia": "Prov", "Ruth": "Ruth", "Canticum": "Song",
        "Ecclesiastes": "Eccl", "Threni": "Lam", "Esther": "Esth", "Daniel": "Dan",
        "Esra": "Ezra", "Nehemia": "Neh", "Chronica_I": "1 Chr", "Chronica_II": "2 Chr"}

ACCENTS = re.compile("[֑-ֽ֯׀׃-׆]")


def plain(s):
    """Hebrew with vowels but without cantillation, meteg and punctuation marks."""
    return ACCENTS.sub("", s or "")


def write_js(path, call, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(call + "(" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ");\n")


t0 = time.time()
TF = Fabric(locations=os.path.expanduser("~/text-fabric-data/github/ETCBC/bhsa/tf/2021"),
            silent="deep")
api = TF.load("book chapter verse lex sp gloss voc_lex_utf8 g_word_utf8 g_cons_utf8 "
              "trailer_utf8 function language qere_utf8 vs vt ps nu gn st prs",
              silent="deep")
F, L = api.F, api.L

# ---------------------------------------------------------------- corpus tables
book_nodes = list(F.otype.s("book"))
book_ids = [F.book.v(b) for b in book_nodes]
units = []
words_per_unit = Counter()
for b, bk in zip(book_nodes, book_ids):
    u = BOOK_UNIT.get(bk, bk)
    if u not in units:
        units.append(u)
    words_per_unit[u] += len(L.d(b, "word"))
TOTAL_WORDS = sum(words_per_unit.values())

all_verses = list(F.otype.s("verse"))
vindex = {v: i for i, v in enumerate(all_verses)}
verse_unit = {v: BOOK_UNIT.get(F.book.v(v), F.book.v(v)) for v in all_verses}


def key(w):
    lx = F.lex.v(w)
    return lx if F.language.v(w) == "Hebrew" else lx + "@A"


def gloss(w):
    return F.gloss.v(L.u(w, "lex")[0]) or F.gloss.v(w) or ""


def is_ignored(w):
    """Tokens skipped when matching phrases: article and conjunction waw."""
    return F.sp.v(w) == "art" or F.lex.v(w) == "W"


def is_content(w):
    return F.sp.v(w) in CONTENT_SP and F.lex.v(w) not in LIGHT


def good_ngram(ws):
    """At least one content word; no dangling preposition/conjunction or construct
    noun at the end, no object marker or conjunction (other than asher) at the start."""
    if not any(is_content(w) for w in ws):
        return False
    first, last = ws[0], ws[-1]
    if F.lex.v(first) == ">T" or (F.sp.v(first) == "conj" and F.lex.v(first) != ">CR"):
        return False
    if F.sp.v(last) in ("prep", "conj", "art") or F.lex.v(last) == ">T":
        return False
    if F.st.v(last) == "c":  # construct state: the phrase breaks off before its genitive
        return False
    return True


lex_info = {}
for w in F.otype.s("word"):
    k = key(w)
    if k not in lex_info:
        lex_info[k] = {"heb": F.voc_lex_utf8.v(L.u(w, "lex")[0]) or F.voc_lex_utf8.v(w),
                       "gloss": gloss(w), "sp": F.sp.v(w)}

verse_seq = {v: [w for w in L.d(v, "word") if not is_ignored(w)] for v in all_verses}
verse_keys = {v: [key(w) for w in seq] for v, seq in verse_seq.items()}
print(f"loaded ({time.time() - t0:.0f}s)")

# ---------------------------------------------------------------- global indexes
lex_occ = defaultdict(list)
for v in all_verses:
    for w in verse_seq[v]:
        lex_occ[key(w)].append((v, [w]))

clause_first = {}       # clause -> {lexeme: first content word}
clause_freq = Counter()
pair_occ = defaultdict(list)
for c in F.otype.s("clause"):
    first = {}
    for w in L.d(c, "word"):
        if is_content(w):
            first.setdefault(key(w), w)
    clause_first[c] = first
    clause_freq.update(first.keys())
    for a, b in combinations(sorted(first), 2):
        if F.sp.v(first[a]) == "nmpr" and F.sp.v(first[b]) == "nmpr":
            continue
        ws = sorted([first[a], first[b]])
        pair_occ[(a, b)].append((L.u(ws[0], "verse")[0], ws))


def head_of(ph):
    ws = L.d(ph, "word")
    prep = next((w for w in ws if F.sp.v(w) == "prep" and F.lex.v(w) != ">T"), None)
    nouns = [w for w in ws if F.sp.v(w) in {"subs", "nmpr", "adjv"}]
    if not nouns:
        return None
    noun = nouns[0]
    if F.lex.v(noun) in LIGHT and len(nouns) > 1:
        noun = nouns[1]
    if prep is not None and prep > noun:
        prep = None
    return prep, noun


def syn_tuples(c):
    phs = L.d(c, "phrase")
    verbs = [w for ph in phs if F.function.v(ph) in PRED_FUNCS
             for w in L.d(ph, "word") if F.sp.v(w) == "verb"]
    if not verbs:
        return []
    vb = verbs[0]
    out = []
    for ph in phs:
        role = ARG_FUNCS.get(F.function.v(ph))
        if not role:
            continue
        h = head_of(ph)
        if not h:
            continue
        prep, noun = h
        t = (key(vb), role, key(prep) if prep else "", key(noun))
        out.append((t, sorted([vb, noun] + ([prep] if prep else []))))
    return out


clause_syn = {}
syn_occ = defaultdict(list)
for c in F.otype.s("clause"):
    st = syn_tuples(c)
    if st:
        clause_syn[c] = st
        for t, ws in st:
            syn_occ[t].append((L.u(ws[0], "verse")[0], ws))
print(f"indexes ({time.time() - t0:.0f}s)")


# ---------------------------------------------------------------- statistics
def g2(a, b, c, d):
    """Log-likelihood: a = hits in home book, b = hits elsewhere, c/d = corpus sizes."""
    e1 = c * (a + b) / (c + d)
    e2 = d * (a + b) / (c + d)
    s = 0.0
    if a:
        s += a * math.log(a / e1)
    if b:
        s += b * math.log(b / e2)
    return 2 * s


def classify(counts, is_lex, home):
    total = sum(counts.values())
    hc = counts.get(home, 0)
    others = [bk for bk in counts if bk != home and counts[bk]]
    rest = total - hc
    hw = words_per_unit[home]
    g = g2(hc, rest, hw, TOTAL_WORDS - hw)
    ratio = (hc / hw) / (rest / (TOTAL_WORDS - hw)) if rest else None
    stats = {"total": total, "home": hc, "nother": len(others),
             "g2": round(g, 1), "ratio": round(ratio, 1) if ratio else None}
    if is_lex and total == 1:
        return "hapax", stats
    if total < MIN_TOTAL:
        return None, stats
    if not others and is_lex:  # only vocabulary unique to the book is special;
        return "only", stats   # phrases found only in the book count as restricted
    if len(others) <= MAX_OTHER:
        return "restricted", stats
    if hc >= HOME_MIN and g >= G2_MIN and (ratio or 99) >= RATIO_MIN:
        return "pref", stats
    if is_lex and total <= RARE_MAX:
        return "rare", stats
    return None, stats


def counts_of(occ):
    c = Counter()
    for v, _ in occ:
        c[verse_unit[v]] += 1
    return c


# ---------------------------------------------------------------- pruning per chapter
def overlaps(a, b):
    return a[0] == b[0] and set(a[1]) & set(b[1])


def contains(u, t):
    return any(u[i:i + len(t)] == t for i in range(len(u) - len(t) + 1))


def prune(kept, chap_set):
    # n-grams 1: a long formula is cut into overlapping 6-grams; glue n-grams with the
    # same frequency whose occurrences overlap everywhere into one item
    ngrams = sorted((ik for ik in kept if ik[0] == "ngram"), key=lambda x: -len(x[1]))
    merged_into = {}
    for i, a in enumerate(ngrams):
        if a in merged_into:
            continue
        A = kept[a]
        occ = None
        for b in ngrams[i + 1:]:
            if b in merged_into or kept[b]["total"] != A["total"]:
                continue
            cur = occ if occ is not None else A["occ"]
            B = kept[b]
            if all(any(overlaps(o, p) for p in cur) for o in B["occ"]):
                if occ is None:
                    occ = [(v, list(ws)) for v, ws in A["occ"]]
                for o in B["occ"]:
                    for p in occ:
                        if overlaps(o, p):
                            p[1][:] = sorted(set(p[1]) | set(o[1]))
                            break
                merged_into[b] = a
        if occ is not None:
            A["occ"] = occ
            here = next(ws for v, ws in occ if ws[0] in chap_set)
            A["key"] = tuple(key(w) for w in here if not is_ignored(w))
    for b in merged_into:
        kept.pop(b, None)
    rekeyed = {}
    for a, it in kept.items():
        k = ("ngram", tuple(it["key"])) if a[0] == "ngram" else a
        if k not in rekeyed or rekeyed[k]["total"] < it["total"]:
            rekeyed[k] = it
    kept = rekeyed

    # n-grams 2: drop an n-gram when a longer kept n-gram contains it and covers at
    # least NGRAM_COVER of its occurrences (it is then mostly a fragment)
    ngrams = sorted((ik for ik in kept if ik[0] == "ngram"), key=lambda x: len(x[1]))
    for ik in ngrams:
        t = ik[1]
        for jk in ngrams:
            if len(jk[1]) > len(t) and jk in kept and contains(jk[1], t) and \
                    kept[jk]["total"] >= NGRAM_COVER * kept[ik]["total"]:
                kept.pop(ik, None)
                break

    # pairs / syn: drop when they add nothing to the rarer lexeme on its own (same set of
    # books); drop pairs whose occurrences in the chapter all lie inside one kept n-gram
    ngram_spans = [set(range(ws[0], ws[-1] + 1)) for ik, it in kept.items() if ik[0] == "ngram"
                   for v, ws in it["occ"] if ws[0] in chap_set]
    for ik in [k for k in kept if k[0] in ("pair", "syn")]:
        it = kept[ik]
        lexes = [ik[1][0], ik[1][3]] if ik[0] == "syn" else list(ik[1])
        rarest = min(lexes, key=lambda k: len(lex_occ.get(k, [])) or 10 ** 9)
        lit = kept.get(("lex", (rarest,)))
        if lit and set(lit["counts"]) == set(it["counts"]):
            del kept[ik]
            continue
        if ik[0] == "pair":
            here = [set(ws) for v, ws in it["occ"] if ws[0] in chap_set]
            if all(any(h <= s for s in ngram_spans) for h in here):
                del kept[ik]
                continue
            a, b = ik[1]
            for sk, s in kept.items():
                if sk[0] == "syn" and {sk[1][0], sk[1][3]} == {a, b} and s["total"] >= it["total"] * 0.8:
                    kept.pop(ik, None)
                    break
    return kept


# ---------------------------------------------------------------- per chapter
MORPH = ("sp", "vs", "vt", "ps", "nu", "gn", "st")


def word_json(w):
    m = {f: getattr(F, f).v(w) for f in MORPH}
    m = {f: x for f, x in m.items() if x and x not in ("NA", "unknown")}
    return {"t": plain(F.g_word_utf8.v(w)), "tr": plain(F.trailer_utf8.v(w)),
            "lex": key(w), "lexv": lex_info[key(w)]["heb"], "gl": gloss(w),
            "m": m, "q": plain(F.qere_utf8.v(w)) or None}


def label(kind, t):
    if kind == "syn":
        vb, role, prep, noun = t
        ks = [vb] + ([prep] if prep else []) + [noun]
        return {"lex": [lex_info[k]["heb"] for k in ks], "gl": [lex_info[k]["gloss"] for k in ks],
                "role": role}
    return {"lex": [lex_info[k]["heb"] for k in t], "gl": [lex_info[k]["gloss"] for k in t]}


def do_chapter(bk, ch_node, home, cache, ngram_occ):
    chn = F.chapter.v(ch_node)
    cverses = L.d(ch_node, "verse")
    cwords = [w for v in cverses for w in L.d(v, "word")]
    chap_set = set(cwords)
    clauses = []
    seen = set()
    for w in cwords:
        c = L.u(w, "clause")[0]
        if c not in seen:
            seen.add(c)
            clauses.append(c)

    cand = {}
    for w in cwords:
        if not is_ignored(w):
            cand[("lex", (key(w),))] = lex_occ[key(w)]
    for v in cverses:
        seq, keys = verse_seq[v], verse_keys[v]
        for n in range(2, NGRAM_MAX + 1):
            for i in range(len(seq) - n + 1):
                t = tuple(keys[i:i + n])
                if t in ngram_occ:
                    cand[("ngram", t)] = ngram_occ[t]
    for c in clauses:
        first = clause_first[c]
        for a, b in combinations(sorted(first), 2):
            if (a, b) in pair_occ:
                cand[("pair", (a, b))] = pair_occ[(a, b)]
        for t, _ in clause_syn.get(c, []):
            cand[("syn", t)] = syn_occ[t]

    kept = {}
    for ik, occ in cand.items():
        if ik not in cache:
            cnt = counts_of(occ)
            cache[ik] = classify(cnt, ik[0] == "lex", home) + (dict(cnt),)
        cat, stats, cnt = cache[ik]
        if cat is None:
            continue
        logdice = None
        if ik[0] == "pair":
            a, b = ik[1]
            logdice = round(14 + math.log2(2 * len(occ) / (clause_freq[a] + clause_freq[b])), 1)
            if logdice < PAIR_LOGDICE:
                continue
        if not any(ws[0] in chap_set for _, ws in occ):
            continue
        kept[ik] = {"key": ik[1], "occ": occ, "cat": cat, "logdice": logdice,
                    "counts": cnt, **stats}
    kept = prune(kept, chap_set)

    cindex = {w: i for i, w in enumerate(cwords)}
    out_items = []
    for n, (ik, it) in enumerate(sorted(kept.items(), key=lambda x: (x[0][0], -x[1]["home"]))):
        here, occ = [], []
        for v, ws in it["occ"]:
            if ws[0] in chap_set:
                if ik[0] == "ngram":  # highlight the whole span, including article and waw
                    ws = range(ws[0], ws[-1] + 1)
                here.append([cindex[w] for w in ws])
            else:
                occ.append((v, ws))
        n_occ = len(occ)
        if n_occ > OCC_CAP:  # keep a sample, round-robin over the books
            per_book = defaultdict(list)
            for o in occ:
                per_book[F.book.v(o[0])].append(o)
            queues = list(per_book.values())
            occ = []
            while len(occ) < OCC_CAP:
                for q in queues:
                    if q and len(occ) < OCC_CAP:
                        occ.append(q.pop(0))
            occ.sort(key=lambda o: vindex[o[0]])
        enc = []
        for v, ws in occ:  # compact: verse index * 256 + offset of first word, then the others
            first = L.d(v, "word")[0]
            offs = [w - first for w in ws]
            head = vindex[v] * 256 + offs[0]
            if ik[0] == "lex":
                enc.append(head)
            elif ik[0] == "ngram":
                enc.append([head, offs[-1]])
            else:
                enc.append([head] + offs[1:])
        occ = enc
        out_items.append({
            "id": n, "kind": ik[0], "key": list(ik[1]), "cat": it["cat"], **label(*ik),
            "sp": lex_info[ik[1][0]]["sp"] if ik[0] == "lex" else None,
            "freq": it["total"], "home": it["home"], "nother": it["nother"],
            "g2": it["g2"], "ratio": it["ratio"], "logdice": it["logdice"],
            "counts": it["counts"], "here": here, "occ": occ, "nocc": n_occ})

    data = {"book": bk, "chapter": chn, "home": home,
            "verses": [{"v": F.verse.v(v), "words": [cindex[w] for w in L.d(v, "word")]}
                       for v in cverses],
            "words": [word_json(w) for w in cwords], "items": out_items, "lxx": None}

    page = parse_lxx.page_for(bk, chn)
    if page:
        sv = parse_lxx.synopsis(page)
        status, mism = parse_lxx.align(sv, [(x["v"], x["words"]) for x in data["verses"]],
                                       [F.g_cons_utf8.v(w) for w in cwords])
        data["lxx"] = {"source": parse_lxx.BASE + page + ".html", "credit": parse_lxx.CREDIT,
                       "verses": sv, "word_status": status, "unaligned_verses": mism}
    write_js(os.path.join(OUT, "ch", bk, f"{chn}.js"), "__chapter", data)
    return len(out_items)


# ---------------------------------------------------------------- main
only_book = sys.argv[1] if len(sys.argv) > 1 else None
only_chapters = {int(x) for x in sys.argv[2:]}

# index and text files are always written in full
index = {"params": {"max_other": MAX_OTHER, "min_total": MIN_TOTAL, "g2_min": G2_MIN,
                    "ratio_min": RATIO_MIN, "home_min": HOME_MIN, "rare_max": RARE_MAX,
                    "pair_logdice": PAIR_LOGDICE, "ngram_max": NGRAM_MAX,
                    "occ_cap": OCC_CAP},
         "units": [{"id": u, "en": BOOK_EN[u], "words": words_per_unit[u]} for u in units],
         "books": [], "source": "BHSA 2021 (ETCBC)"}
for b, bk in zip(book_nodes, book_ids):
    vs = L.d(b, "verse")
    index["books"].append({"id": bk, "en": BOOK_EN[bk], "abbr": ABBR[bk],
                           "unit": BOOK_UNIT.get(bk, bk), "chapters": len(L.d(b, "chapter")),
                           "v0": vindex[vs[0]], "nv": len(vs),
                           "lxx": [c for c in range(1, len(L.d(b, "chapter")) + 1)
                                   if parse_lxx.page_for(bk, c)]})
    write_js(os.path.join(OUT, "text", f"{bk}.js"), "__text",
             {"book": bk, "verses": [[F.chapter.v(v), F.verse.v(v),
                                      [plain(F.g_word_utf8.v(w)) + plain(F.trailer_utf8.v(w))
                                       for w in L.d(v, "word")]] for v in vs]})
write_js(os.path.join(OUT, "index.js"), "__index", index)

for unit in units:
    books_here = [(b, bk) for b, bk in zip(book_nodes, book_ids) if BOOK_UNIT.get(bk, bk) == unit]
    if only_book and only_book not in [bk for _, bk in books_here]:
        continue
    # n-gram occurrences: candidates from this book unit, one scan of the corpus
    cand = set()
    for b, _ in books_here:
        for v in L.d(b, "verse"):
            seq, keys = verse_seq[v], verse_keys[v]
            for n in range(2, NGRAM_MAX + 1):
                for i in range(len(seq) - n + 1):
                    if good_ngram(seq[i:i + n]):
                        cand.add(tuple(keys[i:i + n]))
    ngram_occ = defaultdict(list)
    for v in all_verses:
        seq, keys = verse_seq[v], verse_keys[v]
        for n in range(2, NGRAM_MAX + 1):
            for i in range(len(seq) - n + 1):
                t = tuple(keys[i:i + n])
                if t in cand:
                    ngram_occ[t].append((v, seq[i:i + n]))
    cache = {}
    total = 0
    for b, bk in books_here:
        if only_book and bk != only_book:
            continue
        for chn in L.d(b, "chapter"):
            if only_chapters and F.chapter.v(chn) not in only_chapters:
                continue
            total += do_chapter(bk, chn, unit, cache, ngram_occ)
    print(f"{BOOK_EN[unit]}: {total} items ({time.time() - t0:.0f}s)")
print("done")
