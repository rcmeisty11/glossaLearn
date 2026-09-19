#!/usr/bin/env python3
"""
match_izo_bases.py
Find the base word each orphaned -ίζω verb was built from.

Two independent signals, combined:

  1. MORPHOLOGY — strip any stacked preverbs and the -ίζω/-ίζομαι suffix, then
     try the productive noun/adjective endings Greek uses to rebuild the base
     (θωρακ- -> θώραξ, κολαφ- -> κόλαφος, χιον- -> χιών). Consonant-stem nouns
     alternate (κ/γ/χ -> ξ, δ/τ/θ -> ς), so those are tried too.

  2. SEMANTICS — overlap between the verb's gloss and the candidate's gloss.
     θωρακίζω "arm with a breastplate" shares "breastplate" with θώραξ. This is
     what separates a real base from a lookalike: ὠθίζω "thrust, push" matches
     ὠθέω "push" on meaning, not just letters.

A candidate needs BOTH to score well, which is what keeps χιονίζω "snow upon"
away from the proper noun Χιόνη and pointed at χιών "snow".

Nothing is written. The output is a ranked proposal list for review.

Usage:
    python3 match_izo_bases.py            # ranked proposals
    python3 match_izo_bases.py --apply    # write the confident ones
"""

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_prepositions import ALLOMORPHS, bare   # noqa: E402

DB_PATH = Path(__file__).parent / "greek_vocab.db"
AUDIT = Path(__file__).parent / "family_audit"

STOP = set("""a an the to of and or in on at by for with from be is are was were
this that it its as into upon one's oneself etc cf esp pass med act v vb adj
make made makes making do does doing have has had not no so such which who whom
their his her them they he she you your my our us we i""".split())

# Endings a denominative -ίζω verb is built from, longest first.
NOUN_ENDINGS = ["ος", "ον", "ης", "ας", "ης", "α", "η", "ις", "υς", "ευς", "ωρ",
                "ων", "μα", "ξ", "ς", ""]
# Consonant-stem alternations: the verb keeps the stem, the noun shows the
# nominative's fused form. θωρακ- -> θώραξ, ἐλπιδ- -> ἐλπίς.
ALTERNATIONS = [("κ", "ξ"), ("γ", "ξ"), ("χ", "ξ"),
                ("δ", "ς"), ("τ", "ς"), ("θ", "ς"),
                ("ντ", "ς"), ("ματ", "μα")]


def words(text):
    text = re.sub(r"[^a-zA-Z\s']", " ", (text or "").lower())
    return {w for w in text.split() if len(w) > 2 and w not in STOP}


def strip_affixes(b):
    """Remove stacked preverbs and the -ίζω ending; return candidate stems."""
    bases = {b}
    for _ in range(3):
        for s in list(bases):
            for f, _c in ALLOMORPHS:
                if s.startswith(f) and len(s) - len(f) >= 4:
                    bases.add(s[len(f):])
    stems = set()
    for s in bases:
        for suf in ("ιζομαι", "ιζω", "ιζεσκε"):
            if s.endswith(suf) and len(s) - len(suf) >= 2:
                stems.add(s[:-len(suf)])
    return stems


def candidate_forms(stem):
    """Rebuild plausible nominatives from a verb stem."""
    out = set()
    for end in NOUN_ENDINGS:
        out.add(stem + end)
    for a, b in ALTERNATIONS:
        if stem.endswith(a):
            root = stem[:-len(a)]
            for end in ("ξ", "ς", "", "ος", "μα"):
                out.add(root + b + end)
    # verbs the -ίζω form may be a variant of
    for end in ("εω", "αω", "οω", "ω", "ομαι"):
        out.add(stem + end)
    return {o for o in out if len(o) >= 3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-score", type=float, default=2.0)
    args = ap.parse_args()

    db = sqlite3.connect(str(DB_PATH))
    by_bare = {}
    meta = {}
    for lid, lemma, pos, occ, sd in db.execute(
            "SELECT id, lemma, pos, total_occurrences, short_def FROM lemmas"):
        by_bare.setdefault(bare(lemma), []).append(lid)
        meta[lid] = (lemma, pos, occ or 0, sd or "")

    fams = {}
    for lid, fid, root, label, kind in db.execute(
            """SELECT lf.lemma_id, df.id, df.root, df.label, df.kind
               FROM lemma_families lf JOIN derivational_families df ON df.id = lf.family_id"""):
        fams.setdefault(lid, []).append((fid, root, label, kind))

    targets = json.loads((AUDIT / "izo_needs_base.json").read_text(encoding="utf-8"))
    proposals = []

    for t in targets:
        vb, vdef = t["lemma"], t["short_def"] or ""
        vwords = words(vdef)
        seen, scored = set(), []

        for stem in strip_affixes(bare(vb)):
            if len(stem) < 2:
                continue
            for form in candidate_forms(stem):
                for lid in by_bare.get(form, []):
                    if lid in seen or lid == t["lemma_id"]:
                        continue
                    seen.add(lid)
                    lemma, pos, occ, sd = meta[lid]
                    if pos not in ("noun", "adjective", "verb"):
                        continue
                    overlap = vwords & words(sd)
                    # morphology: how much of the verb stem the candidate keeps
                    morph = len(stem) / max(len(bare(vb)), 1)
                    score = 2.2 * len(overlap) + 3.0 * morph
                    if lemma[:1].isupper():
                        score -= 2.5          # proper nouns are rarely the base
                    if occ == 0:
                        score -= 0.4
                    cand_fams = [f for f in fams.get(lid, [])
                                 if f[3] not in ("preposition", "suffix")]
                    if not cand_fams:
                        score -= 1.2          # a base with no family gives us nothing
                    scored.append({
                        "base_lemma_id": lid, "base": lemma, "pos": pos,
                        "occurrences": occ, "short_def": sd[:70],
                        "shared_words": sorted(overlap),
                        "families": [{"family_id": f[0], "root": f[1]} for f in cand_fams],
                        "score": round(score, 2),
                    })
        scored.sort(key=lambda x: -x["score"])
        proposals.append({**t, "candidates": scored[:4]})

    good = [p for p in proposals if p["candidates"] and p["candidates"][0]["score"] >= args.min_score]
    weak = [p for p in proposals if p not in good]

    (AUDIT / "izo_base_proposals.json").write_text(
        json.dumps(proposals, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"targets                       : {len(proposals)}")
    print(f"confident match (score >= {args.min_score}) : {len(good)}")
    print(f"weak / no candidate           : {len(weak)}\n")
    print(f"{'verb':20s} {'->':2s} {'base':16s} {'sc':>5}  shared meaning")
    print("-" * 92)
    for p in good:
        c = p["candidates"][0]
        fam = c["families"][0]["root"] if c["families"] else "(no family)"
        print(f"{p['lemma']:20s} -> {c['base']:16s} {c['score']:>5}  "
              f"{','.join(c['shared_words'][:4]) or '—':28s} [{fam}]")
    print(f"\n--- weak / needs a human ({len(weak)}) ---")
    for p in weak:
        top = p["candidates"][0]["base"] if p["candidates"] else "—"
        print(f"  {p['lemma']:22s} best guess: {top}")
    print("\n-> family_audit/izo_base_proposals.json")

    if not args.apply:
        print("\n(no changes written — pass --apply to link the confident ones)")
        return

    added = 0
    for p in good:
        c = p["candidates"][0]
        for f in c["families"]:
            if db.execute("SELECT 1 FROM lemma_families WHERE lemma_id=? AND family_id=?",
                          (p["lemma_id"], f["family_id"])).fetchone():
                continue
            db.execute("""INSERT INTO lemma_families
                          (lemma_id, family_id, relation, derivation_type)
                          VALUES (?,?,?,?)""",
                       (p["lemma_id"], f["family_id"], "derived", "denominative_verb"))
            db.execute("""INSERT INTO family_edit_log (action, family_id, lemma_id, detail, user)
                          VALUES ('add_member',?,?,?,'match_izo_bases')""",
                       (f["family_id"], p["lemma_id"], json.dumps(
                           {"relation": "derived", "base": c["base"],
                            "score": c["score"], "shared_words": c["shared_words"]},
                           ensure_ascii=False)))
            added += 1
    db.commit()
    print(f"\napplied {added} new links")
    db.close()


if __name__ == "__main__":
    main()
