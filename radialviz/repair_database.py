#!/usr/bin/env python3
"""
repair_database.py
═══════════════════════════════════════════════════════════════
Picks up where build_database.py got stuck.
Fixes: frequency totals, indexes, lexica parsing, word families.

Usage:
    python3 repair_database.py

Run this in the same directory as greek_vocab.db
═══════════════════════════════════════════════════════════════
"""

import glob
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from lxml import etree as ET
    USING_LXML = True
except ImportError:
    import xml.etree.ElementTree as ET
    USING_LXML = False

DATA_DIR = Path.home() / "greek_data"
DB_PATH = Path("./greek_vocab.db")

if not DB_PATH.exists():
    print("ERROR: greek_vocab.db not found in current directory")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-128000")  # 128MB cache
conn.execute("PRAGMA temp_store=MEMORY")
cursor = conn.cursor()

print("═══════════════════════════════════════════════════════════")
print("  Database Repair Script")
print("═══════════════════════════════════════════════════════════")
print()

# Check current state
cursor.execute("SELECT COUNT(*) FROM lemmas")
lemma_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM occurrences")
occ_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM works")
work_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM work_lemma_counts")
wlc_count = cursor.fetchone()[0]

print(f"  Current state:")
print(f"    Lemmas:       {lemma_count:,}")
print(f"    Occurrences:  {occ_count:,}")
print(f"    Works:        {work_count:,}")
print(f"    Work↔Lemma:   {wlc_count:,}")
print()

# ═══════════════════════════════════════════════════════════════
# STEP 1: Fix author/title metadata
# The original script had wrong title mappings because TLG work
# codes collide across authors. Fix by re-deriving from filenames.
# ═══════════════════════════════════════════════════════════════
print("[1/6] Fixing work metadata...")

# Clear bad titles — set to work_code so they're at least honest
cursor.execute("""
    UPDATE works SET title = work_code
    WHERE title IN ('Iliad','Odyssey','Antigone','Electra',
                    'Oedipus at Colonus','Anabasis','Oedipus Tyrannus',
                    'Republic','Laws','Symposium')
    AND author_code NOT IN ('tlg0012','tlg0011','tlg0032','tlg0059')
""")

# Fix the ones we know are right
KNOWN_WORKS = {
    ("tlg0012", "tlg001"): "Iliad",
    ("tlg0012", "tlg002"): "Odyssey",
    ("tlg0011", "tlg003"): "Antigone",
    ("tlg0011", "tlg004"): "Electra",
    ("tlg0011", "tlg005"): "Oedipus at Colonus",
    ("tlg0011", "tlg007"): "Oedipus Tyrannus",
    ("tlg0011", "tlg006"): "Philoctetes",
    ("tlg0011", "tlg001"): "Ajax",
    ("tlg0011", "tlg002"): "Trachiniae",
    ("tlg0032", "tlg006"): "Anabasis",
    ("tlg0032", "tlg007"): "Cyropaedia",
    ("tlg0032", "tlg003"): "Memorabilia",
    ("tlg0032", "tlg001"): "Hellenica",
    ("tlg0059", "tlg030"): "Republic",
    ("tlg0059", "tlg034"): "Laws",
    ("tlg0059", "tlg011"): "Symposium",
    ("tlg0059", "tlg002"): "Apology",
    ("tlg0059", "tlg004"): "Phaedo",
    ("tlg0059", "tlg006"): "Cratylus",
    ("tlg0059", "tlg008"): "Phaedrus",
    ("tlg0059", "tlg012"): "Theaetetus",
    ("tlg0059", "tlg013"): "Sophist",
    ("tlg0059", "tlg016"): "Timaeus",
    ("tlg0085", "tlg001"): "Persians",
    ("tlg0085", "tlg002"): "Seven Against Thebes",
    ("tlg0085", "tlg003"): "Suppliants",
    ("tlg0085", "tlg004"): "Agamemnon",
    ("tlg0085", "tlg005"): "Libation Bearers",
    ("tlg0085", "tlg006"): "Eumenides",
    ("tlg0085", "tlg007"): "Prometheus Bound",
    ("tlg0006", "tlg003"): "Medea",
    ("tlg0006", "tlg001"): "Alcestis",
    ("tlg0006", "tlg008"): "Hippolytus",
    ("tlg0006", "tlg010"): "Hecuba",
    ("tlg0006", "tlg012"): "Bacchae",
    ("tlg0003", "tlg001"): "History of the Peloponnesian War",
    ("tlg0016", "tlg001"): "Histories",
    ("tlg0086", "tlg025"): "Metaphysics",
    ("tlg0086", "tlg031"): "Nicomachean Ethics",
    ("tlg0086", "tlg035"): "Politics",
    ("tlg0020", "tlg001"): "Theogony",
    ("tlg0020", "tlg002"): "Works and Days",
    ("tlg0019", "tlg011"): "Frogs",
    ("tlg0019", "tlg003"): "Clouds",
    ("tlg0019", "tlg007"): "Birds",
}

for (author_code, work_code), title in KNOWN_WORKS.items():
    cursor.execute(
        "UPDATE works SET title = ? WHERE author_code = ? AND work_code = ?",
        (title, author_code, work_code),
    )

conn.commit()
print("  ✓ Work metadata fixed")

# ═══════════════════════════════════════════════════════════════
# STEP 2: Build indexes FIRST (makes everything else fast)
# ═══════════════════════════════════════════════════════════════
print("[2/6] Building indexes (this makes all other steps fast)...")
t0 = time.time()

index_sql = """
CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma);
CREATE INDEX IF NOT EXISTS idx_lemmas_pos ON lemmas(pos);
CREATE INDEX IF NOT EXISTS idx_forms_lemma ON forms(lemma_id);
CREATE INDEX IF NOT EXISTS idx_forms_form ON forms(form);
CREATE INDEX IF NOT EXISTS idx_occ_lemma ON occurrences(lemma_id);
CREATE INDEX IF NOT EXISTS idx_occ_work ON occurrences(work_id);
CREATE INDEX IF NOT EXISTS idx_occ_passage ON occurrences(passage);
CREATE INDEX IF NOT EXISTS idx_wlc_work ON work_lemma_counts(work_id);
CREATE INDEX IF NOT EXISTS idx_wlc_lemma ON work_lemma_counts(lemma_id);
"""
conn.executescript(index_sql)
conn.commit()
print(f"  ✓ Indexes built in {time.time()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════
# STEP 3: Compute frequency totals using work_lemma_counts
# This is the step that was stuck. We use the pre-aggregated
# work_lemma_counts table instead of scanning all occurrences.
# ═══════════════════════════════════════════════════════════════
print("[3/6] Computing frequency totals (using pre-aggregated counts)...")
t0 = time.time()

# First check if work_lemma_counts has data
if wlc_count > 0:
    # Use the fast path — sum from the already-aggregated table
    cursor.execute("""
        CREATE TEMPORARY TABLE lemma_totals AS
        SELECT lemma_id, SUM(count) as total
        FROM work_lemma_counts
        GROUP BY lemma_id
    """)

    cursor.execute("""
        UPDATE lemmas SET total_occurrences = (
            SELECT total FROM lemma_totals
            WHERE lemma_totals.lemma_id = lemmas.id
        )
    """)

    cursor.execute("DROP TABLE lemma_totals")
else:
    # Fallback: count from occurrences table, but do it in batches
    print("  work_lemma_counts is empty, counting from occurrences (slower)...")
    cursor.execute("""
        CREATE TEMPORARY TABLE lemma_totals AS
        SELECT lemma_id, COUNT(*) as total
        FROM occurrences
        GROUP BY lemma_id
    """)

    cursor.execute("""
        UPDATE lemmas SET total_occurrences = (
            SELECT total FROM lemma_totals
            WHERE lemma_totals.lemma_id = lemmas.id
        )
    """)

    cursor.execute("DROP TABLE lemma_totals")

conn.commit()
print(f"  ✓ Totals computed in {time.time()-t0:.1f}s")

# Now compute frequency ranks
print("  Computing frequency ranks...")
t0 = time.time()

cursor.execute("""
    CREATE TEMPORARY TABLE ranked AS
    SELECT id, ROW_NUMBER() OVER (ORDER BY total_occurrences DESC) as rank
    FROM lemmas
    WHERE total_occurrences > 0
""")

cursor.execute("""
    UPDATE lemmas SET frequency_rank = (
        SELECT rank FROM ranked WHERE ranked.id = lemmas.id
    )
""")

cursor.execute("DROP TABLE ranked")
conn.commit()
print(f"  ✓ Ranks computed in {time.time()-t0:.1f}s")

# Quick sanity check
cursor.execute("""
    SELECT lemma, pos, total_occurrences, frequency_rank
    FROM lemmas ORDER BY frequency_rank LIMIT 10
""")
print("  Top 10 most frequent lemmas:")
for row in cursor.fetchall():
    print(f"    #{row[3]:>5}  {row[0]:<20} ({row[1]})  ×{row[2]:,}")

# ═══════════════════════════════════════════════════════════════
# STEP 4: Parse lexica
# The original script failed because it couldn't find the XML
# files. Let's search more broadly.
# ═══════════════════════════════════════════════════════════════
print()
print("[4/6] Parsing lexica...")

lexica_dir = DATA_DIR / "lexica"
if not lexica_dir.exists():
    print("  ⚠ lexica directory not found, skipping")
else:
    # Find ALL xml files in the lexica repo and check which ones are dictionaries
    all_xml = glob.glob(str(lexica_dir / "**" / "*.xml"), recursive=True)
    print(f"  Found {len(all_xml)} total XML files in lexica repo")

    # Filter for Greek lexicon files
    lsj_files = [f for f in all_xml if "lsj" in f.lower()]
    ml_files = [f for f in all_xml if "/ml/" in f or "middle" in f.lower() or ".ml." in f]

    print(f"  LSJ files: {len(lsj_files)}")
    print(f"  Middle Liddell files: {len(ml_files)}")

    # If we still can't find them, show what's actually there
    if not lsj_files and not ml_files:
        print("  Searching for any lexicon-like files...")
        for f in all_xml[:20]:
            print(f"    {f}")
        if len(all_xml) > 20:
            print(f"    ... and {len(all_xml)-20} more")

    def_count = 0

    for source_name, file_list in [("lsj", lsj_files), ("middle_liddell", ml_files)]:
        print(f"  Processing {source_name}: {len(file_list)} files...")

        for fpath in file_list:
            try:
                tree = ET.parse(fpath)
                root = tree.getroot()

                # Try multiple ways to find entries
                ns = {"tei": "http://www.tei-c.org/ns/1.0"}
                entries = []

                if USING_LXML:
                    entries = root.findall(".//tei:entry", ns)
                    if not entries:
                        entries = root.findall(".//{http://www.tei-c.org/ns/1.0}entry")
                    if not entries:
                        entries = root.findall(".//entry")
                else:
                    entries = root.findall(".//{http://www.tei-c.org/ns/1.0}entry")
                    if not entries:
                        entries = root.findall(".//entry")

                for entry in entries:
                    # Get headword
                    key = entry.get("key", "") or entry.get("n", "")

                    # Try multiple orth element lookups
                    orth = None
                    for xpath in ["{http://www.tei-c.org/ns/1.0}orth", "orth",
                                  "{http://www.tei-c.org/ns/1.0}form/{http://www.tei-c.org/ns/1.0}orth"]:
                        orth = entry.find(xpath)
                        if orth is not None:
                            break

                    headword = ""
                    if orth is not None and orth.text:
                        headword = orth.text.strip()
                    elif key:
                        # Clean up betacode or key format
                        headword = key.split("0")[0] if "0" in key else key

                    if not headword:
                        continue

                    # Get all text content as definition
                    full_text = "".join(entry.itertext()).strip()
                    if len(full_text) < 5:
                        continue

                    # Truncate sanely
                    short = full_text[:300]
                    full_def = full_text[:5000]

                    # Match to lemmas in our database
                    cursor.execute(
                        "SELECT id FROM lemmas WHERE lemma = ?", (headword,)
                    )
                    rows = cursor.fetchall()

                    for row in rows:
                        try:
                            cursor.execute(
                                """INSERT INTO definitions
                                   (lemma_id, source, entry_key, definition, short_def)
                                   VALUES (?,?,?,?,?)""",
                                (row[0], source_name, key, full_def, short),
                            )
                        except sqlite3.IntegrityError:
                            pass

                        if source_name == "middle_liddell":
                            cursor.execute(
                                """UPDATE lemmas SET middle_liddell = ?,
                                   short_def = COALESCE(short_def, ?)
                                   WHERE id = ?""",
                                (full_def, short, row[0]),
                            )
                        else:
                            cursor.execute(
                                """UPDATE lemmas SET lsj_def = ?,
                                   short_def = COALESCE(short_def, ?)
                                   WHERE id = ?""",
                                (full_def, short, row[0]),
                            )
                        def_count += 1

            except Exception as e:
                print(f"    ⚠ Error in {os.path.basename(fpath)}: {e}")

    conn.commit()
    print(f"  ✓ Loaded {def_count:,} definitions")

    # Show sample
    cursor.execute("""
        SELECT l.lemma, l.short_def
        FROM lemmas l
        WHERE l.short_def IS NOT NULL AND l.short_def != ''
        ORDER BY l.frequency_rank
        LIMIT 5
    """)
    rows = cursor.fetchall()
    if rows:
        print("  Sample definitions:")
        for lemma, sdef in rows:
            print(f"    {lemma}: {sdef[:80]}...")

# ═══════════════════════════════════════════════════════════════
# STEP 5: Build derivational families
# ═══════════════════════════════════════════════════════════════
print()
print("[5/6] Building derivational families...")
t0 = time.time()

GREEK_PREFIXES = [
    ("ἀνα", "ἀνα-"), ("ἀντι", "ἀντι-"), ("ἀπο", "ἀπο-"),
    ("δια", "δια-"), ("εἰσ", "εἰσ-"), ("ἐκ", "ἐκ-"), ("ἐξ", "ἐξ-"),
    ("ἐν", "ἐν-"), ("ἐπι", "ἐπι-"), ("κατα", "κατα-"),
    ("μετα", "μετα-"), ("παρα", "παρα-"), ("περι", "περι-"),
    ("προ", "προ-"), ("πρός", "πρός-"), ("σύν", "σύν-"), ("συν", "συν-"),
    ("ὑπέρ", "ὑπέρ-"), ("ὑπο", "ὑπο-"),
    ("ἀ", "ἀ- (privative)"), ("ἀν", "ἀν- (privative)"),
    ("δυσ", "δυσ-"), ("εὐ", "εὐ-"),
]

# Clear any existing families
cursor.execute("DELETE FROM lemma_families")
cursor.execute("DELETE FROM derivational_families")

cursor.execute("SELECT id, lemma, pos FROM lemmas WHERE total_occurrences > 2")
lemmas = cursor.fetchall()
print(f"  Processing {len(lemmas):,} lemmas...")

stem_groups = defaultdict(list)

for lid, lemma, pos in lemmas:
    stem = lemma
    prefix = ""

    for pfx, pfx_label in sorted(GREEK_PREFIXES, key=lambda x: -len(x[0])):
        if stem.startswith(pfx) and len(stem) > len(pfx) + 2:
            prefix = pfx_label
            stem = stem[len(pfx):]
            break

    # Strip common suffixes for grouping
    for suf in ["ία", "ίας", "ικός", "ική", "ισμός", "ιστής",
                 "εία", "εύς", "ος", "ον", "ή", "ης",
                 "ίζω", "όω", "έω", "άω", "ύω", "ειν", "ναι"]:
        if stem.endswith(suf) and len(stem) > len(suf) + 2:
            stem = stem[:-len(suf)]
            break

    if len(stem) >= 3:
        stem_groups[stem].append((lid, lemma, pos, prefix))

family_count = 0
for stem, members in stem_groups.items():
    if len(members) < 2:
        continue

    cursor.execute(
        "INSERT INTO derivational_families (root, label) VALUES (?, ?)",
        (stem, f"Root: {stem}-"),
    )
    family_id = cursor.lastrowid

    for lid, lemma, pos, prefix in members:
        relation = "root" if not prefix else f"prefix {prefix}"
        cursor.execute(
            "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation) VALUES (?,?,?)",
            (lid, family_id, relation),
        )
    family_count += 1

conn.commit()
print(f"  ✓ Built {family_count:,} derivational families in {time.time()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════
# STEP 6: Full-text search index
# ═══════════════════════════════════════════════════════════════
print()
print("[6/6] Building full-text search index...")
t0 = time.time()

# Drop and recreate FTS table
try:
    cursor.execute("DROP TABLE IF EXISTS lemmas_fts")
except:
    pass

cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS lemmas_fts USING fts5(
        lemma, short_def, lsj_def,
        content='lemmas',
        content_rowid='id'
    )
""")

cursor.execute("""
    INSERT INTO lemmas_fts(rowid, lemma, short_def, lsj_def)
    SELECT id, lemma, short_def, lsj_def FROM lemmas
""")

conn.commit()
print(f"  ✓ FTS index built in {time.time()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════
# FINAL STATS
# ═══════════════════════════════════════════════════════════════
print()
print("═══════════════════════════════════════════════════════════")
print("  Repair complete!")
print()

for table in ["works", "lemmas", "forms", "occurrences", "definitions",
              "derivational_families", "work_lemma_counts"]:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    c = cursor.fetchone()[0]
    print(f"  {table:<25} {c:>12,}")

# Count lemmas with definitions
cursor.execute("SELECT COUNT(*) FROM lemmas WHERE short_def IS NOT NULL AND short_def != ''")
defs = cursor.fetchone()[0]
print(f"  {'lemmas with definitions':<25} {defs:>12,}")

db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\n  Database size: {db_size:.0f} MB")

conn.execute("PRAGMA optimize")
conn.close()

print()
print("  ✓ Database is ready. Next step: python3 serve_api.py")
print("═══════════════════════════════════════════════════════════")