#!/usr/bin/env python3
"""
extract_lsj_compounds.py
Step 3B — mine LSJ's own compound decompositions.

LSJ writes compound headwords hyphenated in the <orth> element:

    <orth extent="suff" lang="greek">ai)tio-logi/a</orth>   ->  αἰτιο-λογία

That hyphen is the lexicographers' own morpheme boundary, so it gives us an
authoritative split for free. The catch is that the same hyphen is also used
for plain stem+suffix splits (a)blab-h/s = ἀβλαβ-ής), so each split is
classified before use.

Outputs three files under family_audit/:
  lsj_compounds.json     every usable split, with both elements resolved
  lsj_auto_links.json    high-confidence links safe to apply without a model
  lsj_needs_review.json  ambiguous splits for the adjudication batch

Usage:
    python3 extract_lsj_compounds.py --lsj-dir <dir>
"""

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent / "greek_vocab.db"
OUT_DIR = Path(__file__).parent / "family_audit"

BETA = {'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η',
        'q': 'θ', 'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ',
        'o': 'ο', 'p': 'π', 'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ',
        'x': 'χ', 'y': 'ψ', 'w': 'ω'}
MARKS = {')': '̓', '(': '̔', '/': '́', '\\': '̀',
         '=': '͂', '+': '̈', '|': 'ͅ'}

# Derivational suffixes: a split whose SECOND element is one of these is
# stem+suffix (ἀβλαβ-ής), not a compound of two lexemes.
SUFFIXES = set("""ος ον η α ας ης ες ις ιος ιον εια ια ικος ικη ικον τος τη της
τηρ τωρ τρια μα ματος σις σια σμος μος νος ρος λος ευς ευω εω αω οω ιζω αζω
υνω αινω σσω ττω δης ωδης ωσις ωμα ητος ατος εος οος ινος ιμος ιστος τερος
τατος ωτερος συνη οσυνη ειον ιδιον αριον υλλιον ωδια ηδον δον θεν σε φι
τεον τεος ασις ησις οσις υσις ασμος ισμος αγμα εργος""".split())


def beta_to_greek(token: str) -> str:
    """Convert Perseus Beta Code to Unicode Greek."""
    token = token.replace('_', '').replace('^', '')
    out, i = [], 0
    while i < len(token):
        ch = token[i].lower()
        if ch not in BETA:
            i += 1
            continue
        base, i, marks = BETA[ch], i + 1, ''
        while i < len(token) and token[i] in MARKS:
            marks += MARKS[token[i]]
            i += 1
        out.append(unicodedata.normalize('NFC', base + marks))
    s = re.sub(r'σ$', 'ς', ''.join(out))
    return unicodedata.normalize('NFC', s)


def bare(s: str) -> str:
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize('NFC', s).lower()


def load_index(db):
    """Build lookup tables from the vocabulary database."""
    lemma_exact, stem_index = defaultdict(list), defaultdict(list)
    for lid, lemma, pos, occ in db.execute(
            "SELECT id, lemma, pos, total_occurrences FROM lemmas"):
        b = bare(lemma)
        lemma_exact[b].append((lid, lemma, pos, occ or 0))
        if len(b) >= 4:
            for n in range(4, min(len(b), 10) + 1):
                stem_index[b[:n]].append((lid, lemma, pos, occ or 0))
    for k in lemma_exact:
        lemma_exact[k].sort(key=lambda x: -x[3])
    for k in stem_index:
        stem_index[k].sort(key=lambda x: -x[3])

    lemma_fams = defaultdict(list)
    for lid, fid, root, label in db.execute(
            """SELECT lf.lemma_id, df.id, df.root, df.label
               FROM lemma_families lf JOIN derivational_families df ON df.id = lf.family_id"""):
        lemma_fams[lid].append({"family_id": fid, "root": root, "label": label})
    return lemma_exact, stem_index, lemma_fams


def resolve(tok, lemma_exact, stem_index):
    """Resolve a compound element to candidate lemmas."""
    b = bare(tok).strip('-_ ')
    if not b:
        return []
    if b in lemma_exact:
        return lemma_exact[b][:3]
    # compounding vowel: ἀγαθο- -> ἀγαθός, λογο- -> λόγος
    for trimmed in (b[:-1], b + 'ς', b + 'ος', b + 'η', b + 'ον'):
        if trimmed in lemma_exact:
            return lemma_exact[trimmed][:3]
    if len(b) >= 4 and b in stem_index:
        return stem_index[b][:3]
    if len(b) >= 5 and b[:-1] in stem_index:
        return stem_index[b[:-1]][:3]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lsj-dir", required=True)
    args = ap.parse_args()

    db = sqlite3.connect(str(DB_PATH))
    lemma_exact, stem_index, lemma_fams = load_index(db)
    OUT_DIR.mkdir(exist_ok=True)

    entry_re = re.compile(
        r'<entryFree\b[^>]*key="([^"]*)"[^>]*>(.*?)</entryFree>', re.S)
    orth_re = re.compile(r'<orth\b[^>]*>(.*?)</orth>', re.S)

    stats = defaultdict(int)
    compounds, auto, review = [], [], []

    for path in sorted(Path(args.lsj_dir).glob("*.xml")):
        data = path.read_text(encoding="utf-8", errors="replace")
        for key, body in entry_re.findall(data):
            stats["entries"] += 1
            m = orth_re.search(body)
            if not m:
                continue
            text = re.sub(r'<[^>]+>', '', m.group(1)).strip().rstrip(':,.; ')
            if '-' not in text:
                continue
            parts = [p for p in text.split('-') if p.strip()]
            if len(parts) != 2:
                stats["multi_part"] += 1
                continue

            first, second = beta_to_greek(parts[0]), beta_to_greek(parts[1])
            head = beta_to_greek(key)
            if bare(second) in SUFFIXES or len(bare(second)) <= 3:
                stats["suffix_split"] += 1
                continue
            stats["compound_split"] += 1

            head_hits = lemma_exact.get(bare(head), [])
            if not head_hits:
                stats["head_not_in_db"] += 1
                continue
            stats["head_in_db"] += 1
            head_id, head_lemma, head_pos, head_occ = head_hits[0]

            r1 = resolve(first, lemma_exact, stem_index)
            r2 = resolve(second, lemma_exact, stem_index)
            rec = {
                "headword": head_lemma, "head_lemma_id": head_id, "pos": head_pos,
                "occurrences": head_occ, "lsj_split": f"{first}-{second}",
                "element1": first, "element2": second,
                "element1_matches": [{"lemma_id": x[0], "lemma": x[1], "pos": x[2],
                                      "occurrences": x[3],
                                      "families": lemma_fams.get(x[0], [])} for x in r1],
                "element2_matches": [{"lemma_id": x[0], "lemma": x[1], "pos": x[2],
                                      "occurrences": x[3],
                                      "families": lemma_fams.get(x[0], [])} for x in r2],
                "current_families": lemma_fams.get(head_id, []),
            }
            compounds.append(rec)

            # High confidence: both elements resolve to exactly one strong lemma
            # that already sits in a family, and the headword is not in it yet.
            cur = {f["family_id"] for f in rec["current_families"]}
            gains = []
            for side in ("element1_matches", "element2_matches"):
                if len(rec[side]) == 1 and rec[side][0]["families"]:
                    for fam in rec[side][0]["families"]:
                        if fam["family_id"] not in cur:
                            gains.append({"family_id": fam["family_id"],
                                          "root": fam["root"],
                                          "via": rec[side][0]["lemma"]})
            if gains and len(r1) <= 1 and len(r2) <= 1:
                auto.append({**rec, "proposed_links": gains})
            elif r1 or r2:
                review.append(rec)
            else:
                stats["no_element_match"] += 1

    print(f"LSJ entries scanned      : {stats['entries']}")
    print(f"  suffix splits (skipped): {stats['suffix_split']}")
    print(f"  compound splits        : {stats['compound_split']}")
    print(f"    headword in our DB   : {stats['head_in_db']}")
    print(f"    headword not in DB   : {stats['head_not_in_db']}")
    print(f"\nusable compound records  : {len(compounds)}")
    print(f"  high-confidence auto   : {len(auto)}")
    print(f"  needs adjudication     : {len(review)}")
    print(f"  no element resolved    : {stats['no_element_match']}")

    for name, payload in (("lsj_compounds.json", compounds),
                          ("lsj_auto_links.json", auto),
                          ("lsj_needs_review.json", review)):
        (OUT_DIR / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  -> family_audit/{name}")
    db.close()


if __name__ == "__main__":
    main()
