#!/usr/bin/env python3
"""
cleanup_dupes.py
Step 1 of the compound-family refinement: remove duplicate/junk families.

Two problems this fixes:
  1. The δόγμ explosion — 1,381 identical singleton families (ids 8281-9661),
     each holding only the lemma δόγμα, which is already correctly placed in
     family 3278 (Root: δοκ-). Pure junk from a runaway earlier script.
  2. Accent/variant root collisions — families whose roots are identical once
     accents are stripped (e.g. 5321:παρα vs 18392:παρά, 5393:πρό vs 18074:πρό).
     Members are merged into the largest family of each collision group.

Every change is written to family_edit_log using the same action names the
production /api/admin/sync endpoint replays, so `sync_edits.py --push` can
mirror this to Lightsail. `before` state is recorded for /revert.

Usage:
    python3 cleanup_dupes.py --dry-run     # report only (default)
    python3 cleanup_dupes.py --apply       # write changes
    python3 cleanup_dupes.py --apply --skip-merges   # only the δόγμ purge
"""

import argparse
import json
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).parent / "greek_vocab.db"


def bare(s: str) -> str:
    """Strip accents/breathings and trailing hyphens for root comparison."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", s).lower().strip("- ")


def log(db, action, family_id, lemma_id, detail, before=None):
    db.execute(
        """INSERT INTO family_edit_log (action, family_id, lemma_id, detail, before, user)
           VALUES (?,?,?,?,?,'cleanup_dupes')""",
        (action, family_id, lemma_id,
         json.dumps(detail, ensure_ascii=False),
         json.dumps(before, ensure_ascii=False) if before else None),
    )


def purge_dogma(db, apply):
    """Remove the 1,381 junk δόγμ families."""
    fams = [r[0] for r in db.execute(
        "SELECT id FROM derivational_families WHERE root = 'δόγμ' ORDER BY id")]
    if not fams:
        print("  δόγμ purge: nothing to do (already clean)")
        return 0

    # Safety: every one of these must hold exactly the single lemma δόγμα,
    # and δόγμα must survive in at least one family outside this set.
    ph = ",".join("?" * len(fams))
    distinct = db.execute(
        f"SELECT COUNT(DISTINCT lemma_id) FROM lemma_families WHERE family_id IN ({ph})",
        fams).fetchone()[0]
    survivors = db.execute(
        f"""SELECT COUNT(*) FROM lemma_families
            WHERE lemma_id = (SELECT id FROM lemmas WHERE lemma='δόγμα')
              AND family_id NOT IN ({ph})""", fams).fetchone()[0]
    if distinct != 1:
        raise SystemExit(f"ABORT: expected 1 distinct lemma in δόγμ families, found {distinct}")
    if survivors < 1:
        raise SystemExit("ABORT: δόγμα would be orphaned — it has no family outside this set")

    print(f"  δόγμ purge: {len(fams)} families (ids {fams[0]}-{fams[-1]}), "
          f"δόγμα keeps {survivors} legitimate membership(s)")
    if not apply:
        return len(fams)

    for fid in fams:
        row = db.execute(
            "SELECT lemma_id, relation, parent_lemma_id, derivation_type "
            "FROM lemma_families WHERE family_id = ?", (fid,)).fetchone()
        fam = db.execute(
            "SELECT root, label FROM derivational_families WHERE id = ?", (fid,)).fetchone()
        if row:
            log(db, "remove_member", fid, row[0],
                {"reason": "duplicate junk family (δόγμ explosion)"},
                before={"relation": row[1], "parent_lemma_id": row[2],
                        "derivation_type": row[3],
                        "family": {"root": fam[0], "label": fam[1]}})
            db.execute("DELETE FROM lemma_families WHERE family_id = ?", (fid,))
        db.execute("DELETE FROM derivational_families WHERE id = ?", (fid,))
    return len(fams)


def exact(s: str) -> str:
    """Root string normalised only for NFC + trailing hyphen."""
    return unicodedata.normalize("NFC", (s or "").strip("- "))


def has_diacritic(s: str) -> bool:
    return any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", s or ""))


def merge_accent_dupes(db, apply, held_path=None):
    """Merge families whose roots collide once accents are stripped.

    Only safe when the group contains at most ONE accented spelling: then the
    variants are the same word written bare vs accented (αδελφ / ἀδελφ).

    When two or more DISTINCT accented spellings collide they are usually
    different words — εἰμί 'to be' vs εἶμι 'to go', ὅρος 'boundary' vs ὄρος
    'mountain', ὥρα 'season' vs ὤρα 'care', ὁδ- 'road' vs ὀδ- 'tooth'. Merging
    those would corrupt the data, so the group is held back for adjudication.
    """
    groups = defaultdict(list)
    # root='δόγμ' is owned by purge_dogma(); excluding it keeps --dry-run honest
    for fid, root in db.execute(
            "SELECT id, root FROM derivational_families WHERE root <> 'δόγμ'"):
        if root:
            groups[bare(root)].append((fid, root))

    merged, held = 0, []
    for key, entries in sorted(groups.items()):
        if len(entries) < 2:
            continue

        spellings = defaultdict(list)
        for fid, root in entries:
            spellings[exact(root)].append(fid)
        if sum(1 for s in spellings if has_diacritic(s)) > 1:
            held.append({
                "bare_root": key,
                "spellings": {s: sorted(f) for s, f in spellings.items()},
                "reason": "two or more distinct accented spellings — may be different words",
            })
            continue

        fids = [fid for fid, _ in entries]
        # Keep the family with the most members; ties break toward the lowest id.
        sized = sorted(
            ((db.execute("SELECT COUNT(*) FROM lemma_families WHERE family_id=?",
                         (f,)).fetchone()[0], -f, f) for f in fids),
            reverse=True)
        keep = sized[0][2]
        losers = [f for _, _, f in sized[1:]]

        for src in losers:
            members = db.execute(
                "SELECT lemma_id, relation, parent_lemma_id, derivation_type "
                "FROM lemma_families WHERE family_id = ?", (src,)).fetchall()
            srcfam = db.execute(
                "SELECT root, label FROM derivational_families WHERE id=?", (src,)).fetchone()
            if not apply:
                merged += 1
                continue
            log(db, "merge", keep, None,
                {"merged_from": src, "members_moved": len(members)},
                before={"merged_from": src,
                        "other_family": {"root": srcfam[0], "label": srcfam[1]},
                        "members": [{"lemma_id": m[0], "relation": m[1],
                                     "parent_lemma_id": m[2]} for m in members]})
            for lid, rel, par, dtype in members:
                db.execute(
                    """INSERT OR IGNORE INTO lemma_families
                       (lemma_id, family_id, relation, parent_lemma_id, derivation_type)
                       VALUES (?,?,?,?,?)""", (lid, keep, rel, par, dtype))
            db.execute("DELETE FROM lemma_families WHERE family_id = ?", (src,))
            db.execute("DELETE FROM derivational_families WHERE id = ?", (src,))
            merged += 1

    if held_path:
        Path(held_path).write_text(
            json.dumps(held, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged, held


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-merges", action="store_true", help="only run the δόγμ purge")
    args = ap.parse_args()
    apply = args.apply and not args.dry_run

    db = sqlite3.connect(str(DB_PATH))
    db.execute("PRAGMA foreign_keys=OFF")

    before = {
        "families": db.execute("SELECT COUNT(*) FROM derivational_families").fetchone()[0],
        "memberships": db.execute("SELECT COUNT(*) FROM lemma_families").fetchone()[0],
    }
    print(f"{'APPLYING' if apply else 'DRY RUN'} — families={before['families']} "
          f"memberships={before['memberships']}\n")

    purged = purge_dogma(db, apply)
    merged, held = 0, []
    if not args.skip_merges:
        held_path = Path(__file__).parent / "family_audit" / "held_for_review_roots.json"
        held_path.parent.mkdir(exist_ok=True)
        merged, held = merge_accent_dupes(db, apply, held_path)
        print(f"  accent-dupe merges: {merged} families folded into their canonical family")
        print(f"  held for adjudication: {len(held)} root groups "
              f"(distinct accented spellings) -> {held_path.name}")

    if apply:
        db.commit()
        after = {
            "families": db.execute("SELECT COUNT(*) FROM derivational_families").fetchone()[0],
            "memberships": db.execute("SELECT COUNT(*) FROM lemma_families").fetchone()[0],
        }
        print(f"\nDONE  families {before['families']} -> {after['families']}  "
              f"({before['families'] - after['families']} removed)")
        print(f"      memberships {before['memberships']} -> {after['memberships']}")
        print(f"      edit_log rows now: "
              f"{db.execute('SELECT COUNT(*) FROM family_edit_log').fetchone()[0]}")
    else:
        db.rollback()
        print(f"\nDry run — would remove {purged} δόγμ families and merge {merged} duplicates.")
        print("Re-run with --apply to write.")
    db.close()


if __name__ == "__main__":
    main()
