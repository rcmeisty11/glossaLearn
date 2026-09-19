#!/usr/bin/env python3
"""
build_prepositions.py
Step 2+3A of the compound-family refinement.

Step 2 — establish one canonical family per Greek preposition/preverb (18 of
them), creating the ones that are missing entirely (ἐν, εἰς, ἐκ) and
normalising root/label on the ones that already exist. The preposition lemma
itself becomes the family root.

Step 3A — attach every compound whose existing `relation` string already names
a preverb to that preverb's family. This is the free layer: the information is
already in the database, just written as inconsistent free text
("compound (σύν)", "prefix ἐπί-", "prefix ἐπι", ...). Longest-match allomorph
normalisation maps those onto the 18 canonical prepositions.

The result is the connection the project is after: συμβαίνω stays in
"Root: βαινω-" AND also appears in the σύν family, so the compound shows both
of its parents. Double preverbs ("compound (ἀπό̈δια)", U+0308 separator) attach
to both.

Every change is logged to family_edit_log with actions the production
/api/admin/sync endpoint replays.

Usage:
    python3 build_prepositions.py --dry-run
    python3 build_prepositions.py --apply
"""

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).parent / "greek_vocab.db"

# canonical preposition -> allomorphs as they appear in relation strings
# (accent-stripped, lowercase). Order within a list does not matter; the
# matcher sorts all allomorphs longest-first so κατα beats κατ.
PREPOSITIONS = {
    "ἀνά":  ["ανα"],
    "ἀντί": ["αντι", "αντ", "ανθ"],
    "ἀπό":  ["απο", "απ", "αφ"],
    "διά":  ["δια", "δι"],
    "εἰς":  ["εις", "εισ", "ες"],
    "ἐκ":   ["εκ", "εξ"],
    "ἐν":   ["εν", "εμ", "εγ", "ελ", "ερ"],
    "ἐπί":  ["επι", "επ", "εφ"],
    "κατά": ["κατα", "κατ", "καθ"],
    "μετά": ["μετα", "μετ", "μεθ"],
    "παρά": ["παρα", "παρ"],
    "περί": ["περι", "περ"],
    "πρό":  ["προ"],
    "πρός": ["προς", "προσ", "ποτι", "προτι"],
    "σύν":  ["συν", "συμ", "συγ", "συλ", "συρ", "συσ", "ξυν", "ξυμ"],
    "ὑπέρ": ["υπερ", "υπειρ"],
    "ὑπό":  ["υπο", "υπ", "υφ"],
    "ἀμφί": ["αμφι", "αμφ"],
}

GLOSS = {
    "ἀνά": "up, back, again", "ἀντί": "against, instead of", "ἀπό": "from, away",
    "διά": "through, across", "εἰς": "into, to", "ἐκ": "out of, from",
    "ἐν": "in, among", "ἐπί": "on, upon, at", "κατά": "down, against, according to",
    "μετά": "with, after", "παρά": "beside, from", "περί": "around, about",
    "πρό": "before, forth", "πρός": "toward, in addition", "σύν": "with, together",
    "ὑπέρ": "over, beyond", "ὑπό": "under, by", "ἀμφί": "on both sides, around",
}

ALLOMORPHS = sorted(
    ((form, canon) for canon, forms in PREPOSITIONS.items() for form in forms),
    key=lambda x: -len(x[0]),
)


def bare(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s).lower()


def log(db, action, family_id, lemma_id, detail, before=None):
    db.execute(
        """INSERT INTO family_edit_log (action, family_id, lemma_id, detail, before, user)
           VALUES (?,?,?,?,?,'build_prepositions')""",
        (action, family_id, lemma_id,
         json.dumps(detail, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False) if before else None),
    )


def parse_relation(rel: str):
    """Extract the canonical preposition(s) a relation string names.

    Handles "compound (σύν)", "prefix ἐπί-", "prefix ἐπι", and double preverbs
    written with a U+0308 separator ("compound (ἀπό̈δια)"). Returns [] when the
    relation names a non-prepositional prefix (ἀ- privative, εὐ-, δυσ- ...).
    """
    if not rel:
        return []
    m = re.search(r"\(([^)]*)\)", rel)
    if m and rel.startswith("compound"):
        token = m.group(1)
    elif rel.startswith("prefix"):
        token = re.sub(r"^prefix\s+", "", rel)
    else:
        return []

    # split double preverbs, then keep only the leading word of each piece
    pieces = re.split(r"[̈¨+/]", token)
    out = []
    for piece in pieces:
        piece = re.split(r"[\s(]", piece.strip())[0]
        t = bare(piece).strip("-_^ ")
        t = re.sub(r"[^Ͱ-Ͽἀ-῿]", "", t)
        if not t:
            continue
        canon = next((c for f, c in ALLOMORPHS if t == f), None)
        if canon and canon not in out:
            out.append(canon)
    return out


def ensure_families(db, apply):
    """Find or create one canonical family per preposition. Returns {prep: fid}."""
    fam = {}
    for prep, _ in PREPOSITIONS.items():
        lemma_row = db.execute(
            "SELECT id FROM lemmas WHERE lemma = ? AND pos = 'preposition'", (prep,)
        ).fetchone()
        lemma_id = lemma_row[0] if lemma_row else None

        fid = None
        if lemma_id:
            row = db.execute(
                """SELECT lf.family_id FROM lemma_families lf
                   JOIN derivational_families df ON df.id = lf.family_id
                   WHERE lf.lemma_id = ?
                   ORDER BY (SELECT COUNT(*) FROM lemma_families x
                             WHERE x.family_id = df.id) DESC LIMIT 1""",
                (lemma_id,)).fetchone()
            if row:
                fid = row[0]

        label = f"{prep} family — preposition/preverb ({GLOSS[prep]})"
        if fid is None:
            if not apply:
                fam[prep] = f"NEW:{prep}"
                continue
            cur = db.execute(
                "INSERT INTO derivational_families (root, label) VALUES (?,?)",
                (prep, label))
            fid = cur.lastrowid
            log(db, "create_family", fid, None, {"root": prep, "label": label})
        else:
            if apply:
                old = db.execute(
                    "SELECT root, label FROM derivational_families WHERE id=?", (fid,)).fetchone()
                if old[0] != prep or old[1] != label:
                    log(db, "update_family", fid, None,
                        {"root": prep, "label": label},
                        before={"root": old[0], "label": old[1]})
                    db.execute(
                        "UPDATE derivational_families SET root=?, label=? WHERE id=?",
                        (prep, label, fid))

        # the preposition lemma itself is the family root
        if apply and lemma_id:
            exists = db.execute(
                "SELECT 1 FROM lemma_families WHERE lemma_id=? AND family_id=?",
                (lemma_id, fid)).fetchone()
            if not exists:
                db.execute(
                    """INSERT INTO lemma_families (lemma_id, family_id, relation)
                       VALUES (?,?,'root')""", (lemma_id, fid))
                log(db, "add_member", fid, lemma_id,
                    {"relation": "root", "reason": "preposition heads its own family"})
            else:
                db.execute(
                    "UPDATE lemma_families SET relation='root' WHERE lemma_id=? AND family_id=?",
                    (lemma_id, fid))
        fam[prep] = fid
    return fam


def attach_compounds(db, fam, apply):
    """Attach every compound whose relation names a preverb to that family."""
    rows = db.execute(
        """SELECT lf.lemma_id, lf.family_id, lf.relation, lf.derivation_type
           FROM lemma_families lf
           WHERE lf.relation LIKE 'compound (%' OR lf.relation LIKE 'prefix %'"""
    ).fetchall()

    added, skipped, by_prep = 0, 0, {}
    for lemma_id, src_fid, rel, dtype in rows:
        preps = parse_relation(rel)
        if not preps:
            skipped += 1
            continue
        for prep in preps:
            fid = fam.get(prep)
            if not isinstance(fid, int):
                continue
            if fid == src_fid:
                continue
            exists = db.execute(
                "SELECT 1 FROM lemma_families WHERE lemma_id=? AND family_id=?",
                (lemma_id, fid)).fetchone()
            if exists:
                continue
            by_prep[prep] = by_prep.get(prep, 0) + 1
            added += 1
            if apply:
                new_rel = f"compound ({prep})"
                db.execute(
                    """INSERT INTO lemma_families
                       (lemma_id, family_id, relation, derivation_type)
                       VALUES (?,?,?,?)""",
                    (lemma_id, fid, new_rel, dtype or "compound_preverb"))
                log(db, "add_member", fid, lemma_id,
                    {"relation": new_rel,
                     "reason": f"preverb link derived from existing relation {rel!r}",
                     "source_family_id": src_fid})
    return added, skipped, by_prep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    db = sqlite3.connect(str(DB_PATH))
    before_fams = db.execute("SELECT COUNT(*) FROM derivational_families").fetchone()[0]
    before_mem = db.execute("SELECT COUNT(*) FROM lemma_families").fetchone()[0]
    print(f"{'APPLYING' if apply else 'DRY RUN'} — families={before_fams} memberships={before_mem}\n")

    fam = ensure_families(db, apply)
    created = [p for p, f in fam.items() if not isinstance(f, int)]
    print(f"  canonical preposition families: {len(fam)}")
    if created:
        print(f"    would create: {', '.join(created)}")

    added, skipped, by_prep = attach_compounds(db, fam, apply)
    print(f"\n  preverb links {'added' if apply else 'to add'}: {added}")
    print(f"  relations naming a NON-prepositional prefix (left alone): {skipped}")
    if by_prep:
        print("\n  per preposition:")
        for p in sorted(by_prep, key=lambda x: -by_prep[x]):
            print(f"    {p:6s} {by_prep[p]}")

    if apply:
        db.commit()
        print(f"\nDONE  families {before_fams} -> "
              f"{db.execute('SELECT COUNT(*) FROM derivational_families').fetchone()[0]}")
        print(f"      memberships {before_mem} -> "
              f"{db.execute('SELECT COUNT(*) FROM lemma_families').fetchone()[0]}")
    else:
        db.rollback()
        print("\nDry run — re-run with --apply to write.")
    db.close()


if __name__ == "__main__":
    main()
