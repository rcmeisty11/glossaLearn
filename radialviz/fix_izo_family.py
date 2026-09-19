#!/usr/bin/env python3
"""
fix_izo_family.py
Split family 3402 — which conflates a root with a suffix.

Family 3402 is labelled "Root: ἵζω (sit, seat) — incl. καθίζω compounds" and
holds 475 members. Only 9 of them actually derive from ἵζω "to sit" (ἵζω itself
plus its preverb compounds καθίζω, παρίζω, προσίζω ...). The other 466 merely
END in -ίζω, which is Greek's most productive denominative verb suffix:

    βασανίζω   <- βάσανος  "touchstone"      not  βασαν + ἵζω
    συλλογίζομαι <- σύν + λογίζομαι          not  συλλογ + ἵζω
    ἀφανίζω    <- ἀφανής   "unseen"          not  ἀφαν + ἵζω

This is pre-existing in the database (the pre-refinement backup has the same
475), not something the compound-linking passes introduced.

The fix keeps every word in the tree — nothing is orphaned:

  1. The 9 genuine ἵζω members stay in 3402, whose label is corrected.
  2. ~190 members that are preverb + an existing base verb (συλλογίζομαι =
     σύν + λογίζομαι) are linked to that base verb's families. This is the
     link the user actually wants, and it is derivable locally for free.
  3. Every remaining -ίζω verb moves to a new family explicitly marked as a
     SUFFIX grouping, so the database stops claiming they descend from "sit".
     It is marked kind='suffix' so the UI renders it as a card rather than a
     400-member branch, exactly like the preposition families.

Usage:
    python3 fix_izo_family.py --dry-run
    python3 fix_izo_family.py --apply
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_prepositions import ALLOMORPHS, bare   # noqa: E402

DB_PATH = Path(__file__).parent / "greek_vocab.db"
IZO_FAMILY = 3402
SUFFIX_ROOT = "-ίζω"
SUFFIX_LABEL = "-ίζω (denominative verb suffix)"
SUFFIX_GLOSS = "verb-forming suffix: makes a verb from a noun or adjective"


def log(db, action, fid, lid, detail, before=None):
    db.execute(
        """INSERT INTO family_edit_log (action, family_id, lemma_id, detail, before, user)
           VALUES (?,?,?,?,?,'fix_izo_family')""",
        (action, fid, lid, json.dumps(detail, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False) if before else None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    db = sqlite3.connect(str(DB_PATH))

    lem = {}
    for lid, l, occ in db.execute("SELECT id, lemma, total_occurrences FROM lemmas"):
        lem.setdefault(bare(l), []).append((lid, l, occ or 0))
    for k in lem:
        lem[k].sort(key=lambda x: -x[2])

    def families_of(lid):
        return {r[0] for r in db.execute(
            "SELECT family_id FROM lemma_families WHERE lemma_id = ?", (lid,))}

    members = db.execute(
        """SELECT l.id, l.lemma FROM lemma_families lf
           JOIN lemmas l ON l.id = lf.lemma_id
           WHERE lf.family_id = ? ORDER BY l.total_occurrences DESC""",
        (IZO_FAMILY,)).fetchall()

    genuine, rebased, suffixed = [], [], []
    for lid, lemma in members:
        b = bare(lemma)
        p = next((f for f, c in ALLOMORPHS if b.startswith(f) and len(b) - len(f) >= 3), None)
        rest = b[len(p):] if p else b
        if rest in ("ιζω", "ιζομαι") or b == "ιζω":
            genuine.append((lid, lemma))
        elif p and rest in lem and lem[rest][0][1] != lemma:
            rebased.append((lid, lemma, lem[rest][0][0], lem[rest][0][1]))
        else:
            suffixed.append((lid, lemma))

    print(f"family {IZO_FAMILY}: {len(members)} members")
    print(f"  genuine ἵζω 'sit'                 : {len(genuine)}")
    print(f"  preverb + base verb (re-link)     : {len(rebased)}")
    print(f"  -ίζω denominatives (-> suffix fam): {len(suffixed)}")

    if not apply:
        print("\nsample re-links:")
        for _, l, _, base in rebased[:10]:
            print(f"    {l:20s} -> family of {base}")
        print("\nDry run — re-run with --apply to write.")
        db.rollback()
        db.close()
        return

    # 1. correct the ἵζω label
    old = db.execute("SELECT root, label FROM derivational_families WHERE id = ?",
                     (IZO_FAMILY,)).fetchone()
    new_label = "ἵζω family — sit, seat (ἵζω and its preverb compounds)"
    log(db, "update_family", IZO_FAMILY, None,
        {"root": "ἵζω", "label": new_label}, {"root": old[0], "label": old[1]})
    db.execute("UPDATE derivational_families SET root='ἵζω', label=? WHERE id=?",
               (new_label, IZO_FAMILY))

    # 2. create the suffix family
    cur = db.execute(
        "INSERT INTO derivational_families (root, label, kind, gloss) VALUES (?,?,?,?)",
        (SUFFIX_ROOT, SUFFIX_LABEL, "suffix", SUFFIX_GLOSS))
    suffix_fid = cur.lastrowid
    log(db, "create_family", suffix_fid, None,
        {"root": SUFFIX_ROOT, "label": SUFFIX_LABEL, "kind": "suffix"})
    print(f"\ncreated suffix family {suffix_fid} ({SUFFIX_ROOT})")

    # 3. re-link preverb compounds to their real base verb
    linked = 0
    for lid, lemma, base_id, base_lemma in rebased:
        for (fid,) in db.execute(
                "SELECT family_id FROM lemma_families WHERE lemma_id = ?", (base_id,)):
            if fid in (IZO_FAMILY,) or fid in families_of(lid):
                continue
            kind = db.execute("SELECT kind FROM derivational_families WHERE id=?",
                              (fid,)).fetchone()
            if kind and kind[0] in ("preposition", "suffix"):
                continue
            db.execute("""INSERT INTO lemma_families
                          (lemma_id, family_id, relation, derivation_type)
                          VALUES (?,?,?,?)""",
                       (lid, fid, "derived", "denominative_verb"))
            log(db, "add_member", fid, lid,
                {"relation": "derived",
                 "reason": f"{lemma} is a preverb compound of {base_lemma}; "
                           f"was wrongly filed under ἵζω 'sit'"})
            linked += 1

    # 4. move every non-genuine member out of ἵζω into the suffix family
    moved = 0
    for lid, lemma in [(a, b) for a, b, _, _ in rebased] + suffixed:
        row = db.execute(
            """SELECT relation, parent_lemma_id, derivation_type FROM lemma_families
               WHERE lemma_id = ? AND family_id = ?""", (lid, IZO_FAMILY)).fetchone()
        if not row:
            continue
        log(db, "remove_member", IZO_FAMILY, lid,
            {"reason": "-ίζω is a suffix, not the root ἵζω 'sit'"},
            {"relation": row[0], "parent_lemma_id": row[1], "derivation_type": row[2]})
        db.execute("DELETE FROM lemma_families WHERE lemma_id=? AND family_id=?",
                   (lid, IZO_FAMILY))
        if not db.execute("SELECT 1 FROM lemma_families WHERE lemma_id=? AND family_id=?",
                          (lid, suffix_fid)).fetchone():
            db.execute("""INSERT INTO lemma_families
                          (lemma_id, family_id, relation, derivation_type)
                          VALUES (?,?,?,?)""",
                       (lid, suffix_fid, "suffix -ίζω", "denominative_verb"))
            log(db, "add_member", suffix_fid, lid, {"relation": "suffix -ίζω"})
        moved += 1

    db.commit()
    print(f"  re-linked to base verbs   : {linked} new links")
    print(f"  moved out of ἵζω          : {moved}")
    print(f"  ἵζω family now holds      : "
          f"{db.execute('SELECT COUNT(*) FROM lemma_families WHERE family_id=?', (IZO_FAMILY,)).fetchone()[0]}")
    orphans = db.execute(
        """SELECT COUNT(*) FROM (SELECT l.id FROM lemmas l
           WHERE NOT EXISTS (SELECT 1 FROM lemma_families lf WHERE lf.lemma_id = l.id)
             AND l.id IN (SELECT lemma_id FROM family_edit_log
                          WHERE user='fix_izo_family' AND action='remove_member'))"""
    ).fetchone()[0]
    print(f"  orphaned by this change   : {orphans}  (must be 0)")
    db.close()


if __name__ == "__main__":
    main()
