#!/usr/bin/env python3
"""
verify_refinement.py
Compare the working database against the pre-refinement backup and prove that
the refinement only added connections and removed junk — that no lemma lost its
place in the tree.

Usage:
    python3 verify_refinement.py [--backup <file>]
"""

import argparse
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "greek_vocab.db"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup")
    args = ap.parse_args()
    backup = args.backup or (HERE / ".last_backup").read_text().strip()

    db = sqlite3.connect(str(DB))
    db.execute("ATTACH ? AS bk", (str(HERE / backup),))
    q = lambda sql: db.execute(sql).fetchone()[0]

    print(f"backup: {backup}\n")
    rows = [
        ("families", "SELECT COUNT(*) FROM bk.derivational_families",
         "SELECT COUNT(*) FROM derivational_families"),
        ("memberships", "SELECT COUNT(*) FROM bk.lemma_families",
         "SELECT COUNT(*) FROM lemma_families"),
        ("lemmas in a family", "SELECT COUNT(DISTINCT lemma_id) FROM bk.lemma_families",
         "SELECT COUNT(DISTINCT lemma_id) FROM lemma_families"),
        ("lemmas in >1 family",
         "SELECT COUNT(*) FROM (SELECT lemma_id FROM bk.lemma_families GROUP BY lemma_id HAVING COUNT(*)>1)",
         "SELECT COUNT(*) FROM (SELECT lemma_id FROM lemma_families GROUP BY lemma_id HAVING COUNT(*)>1)"),
        ("empty families",
         "SELECT COUNT(*) FROM bk.derivational_families d WHERE NOT EXISTS(SELECT 1 FROM bk.lemma_families l WHERE l.family_id=d.id)",
         "SELECT COUNT(*) FROM derivational_families d WHERE NOT EXISTS(SELECT 1 FROM lemma_families l WHERE l.family_id=d.id)"),
        ("orphan memberships",
         "SELECT COUNT(*) FROM bk.lemma_families l WHERE NOT EXISTS(SELECT 1 FROM bk.derivational_families d WHERE d.id=l.family_id)",
         "SELECT COUNT(*) FROM lemma_families l WHERE NOT EXISTS(SELECT 1 FROM derivational_families d WHERE d.id=l.family_id)"),
    ]
    print(f"{'metric':26s} {'before':>10s} {'after':>10s} {'delta':>10s}")
    print("-" * 60)
    for name, a, b in rows:
        x, y = q(a), q(b)
        print(f"{name:26s} {x:>10,} {y:>10,} {y-x:>+10,}")

    # The safety property that matters: no lemma that had a family lost them all.
    lost = q("""SELECT COUNT(*) FROM (
                  SELECT DISTINCT lemma_id FROM bk.lemma_families
                  EXCEPT SELECT DISTINCT lemma_id FROM lemma_families)""")
    gained = q("""SELECT COUNT(*) FROM (
                  SELECT DISTINCT lemma_id FROM lemma_families
                  EXCEPT SELECT DISTINCT lemma_id FROM bk.lemma_families)""")
    print(f"\nlemmas that LOST every family : {lost}   (must be 0)")
    print(f"lemmas that GAINED a first family: {gained}")

    print("\nintegrity:", db.execute("PRAGMA quick_check").fetchone()[0])

    print("\nsample of newly connected compounds:")
    for lemma, roots in db.execute("""
            SELECT l.lemma, GROUP_CONCAT(df.root, ' + ')
            FROM lemma_families lf
            JOIN lemmas l ON l.id = lf.lemma_id
            JOIN derivational_families df ON df.id = lf.family_id
            WHERE lf.lemma_id IN (
                SELECT lemma_id FROM lemma_families
                WHERE derivation_type IN ('compound_lsj','compound_preverb'))
            GROUP BY l.id HAVING COUNT(*) > 1
            ORDER BY l.total_occurrences DESC LIMIT 15"""):
        print(f"   {lemma:22s} -> {roots}")
    db.close()


if __name__ == "__main__":
    main()
