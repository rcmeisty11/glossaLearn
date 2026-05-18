#!/usr/bin/env python3
"""Remove the definite article ὁ (pos=article, id=9) from the database."""

import sqlite3
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
LEMMA_ID = 9  # ὁ, article, 2,652,722 occurrences

conn = sqlite3.connect(str(DB_PATH))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
cur = conn.cursor()

print(f"Deleting ὁ (article, lemma_id={LEMMA_ID}) from all tables...")

cur.execute("DELETE FROM lemma_families WHERE lemma_id = ?", (LEMMA_ID,))
print(f"  lemma_families: {cur.rowcount} rows deleted")

cur.execute("DELETE FROM definitions WHERE lemma_id = ?", (LEMMA_ID,))
print(f"  definitions:    {cur.rowcount} rows deleted")

cur.execute("DELETE FROM work_lemma_counts WHERE lemma_id = ?", (LEMMA_ID,))
print(f"  work_lemma_counts: {cur.rowcount} rows deleted")

print("  occurrences: deleting 2.6M rows (this may take a minute)...")
cur.execute("DELETE FROM occurrences WHERE lemma_id = ?", (LEMMA_ID,))
print(f"  occurrences:    {cur.rowcount} rows deleted")

cur.execute("DELETE FROM forms WHERE lemma_id = ?", (LEMMA_ID,))
print(f"  forms:          {cur.rowcount} rows deleted")

cur.execute("DELETE FROM lemmas WHERE id = ?", (LEMMA_ID,))
print(f"  lemmas:         {cur.rowcount} rows deleted")

conn.commit()
conn.close()
print("Done.")
