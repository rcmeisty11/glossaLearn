#!/usr/bin/env python3
"""
Parse LSJLogeion XML files into a staging SQLite database.

Extracts:
  - entries (headword, key, orig_id, type)
  - senses (definitions from <i> tags)
  - etyma (root words from <etym> tags)
  - morphemes (hyphenated breakdowns from orth_orig)
  - cross-references (from <foreign> and inline refs)
  - part-of-speech (from <pos> and <gen> tags)

Then matches entries against the existing greek_vocab.db lemmas
and marks matches for definition review and family expansion.

Usage:
    python3 parse_lsj.py                         # parse + match
    python3 parse_lsj.py --parse-only             # just parse XML
    python3 parse_lsj.py --match-only             # just match against vocab db
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

LSJ_DIR = Path(os.path.expanduser("~/LSJLogeion"))
STAGING_DB = Path(__file__).parent / "lsj_staging.db"
VOCAB_DB = Path(__file__).parent / "greek_vocab.db"


# ═══════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════

SCHEMA = """
CREATE TABLE IF NOT EXISTS lsj_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    xml_id TEXT UNIQUE,
    orig_id TEXT,
    key TEXT,
    headword TEXT,
    orth_orig TEXT,
    entry_type TEXT,           -- 'main' or 'gloss'
    gender TEXT,
    pos TEXT,
    source_file TEXT
);

CREATE TABLE IF NOT EXISTS lsj_senses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES lsj_entries(id),
    sense_n TEXT,
    sense_level TEXT,
    definition TEXT,           -- extracted from <i> tags
    full_text TEXT             -- entire sense text content
);

CREATE TABLE IF NOT EXISTS lsj_etyma (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES lsj_entries(id),
    root_word TEXT             -- from <etym> tag
);

CREATE TABLE IF NOT EXISTS lsj_morphemes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES lsj_entries(id),
    orth_orig TEXT,            -- full hyphenated form e.g. 'νεκῠ-άμβᾰτος'
    prefix TEXT,               -- first morpheme
    stem TEXT                  -- remaining morpheme(s)
);

CREATE TABLE IF NOT EXISTS lsj_crossrefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES lsj_entries(id),
    target_key TEXT,           -- referenced entry key
    ref_type TEXT              -- 'see', 'cf', 'equals', 'variant'
);

-- Matching tables: link LSJ entries to existing vocab DB lemmas
CREATE TABLE IF NOT EXISTS lsj_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER REFERENCES lsj_entries(id),
    lemma_id INTEGER,          -- from greek_vocab.db lemmas table
    lemma TEXT,                -- the matched lemma text
    match_type TEXT,           -- 'exact', 'normalized', 'stripped'
    current_short_def TEXT,    -- current def in vocab db
    lsj_short_def TEXT,        -- proposed replacement from LSJ
    lsj_full_def TEXT,         -- full sense text (fallback when no italic def)
    missing_current_def INTEGER DEFAULT 0,  -- 1 if vocab lemma has NULL/empty short_def
    def_status TEXT DEFAULT 'pending',   -- 'pending', 'approved', 'rejected'
    def_reviewed_at TEXT
);

-- Family expansion candidates from morpheme/etym analysis
CREATE TABLE IF NOT EXISTS lsj_family_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_entry_id INTEGER REFERENCES lsj_entries(id),
    child_lemma_id INTEGER,
    child_headword TEXT,
    parent_headword TEXT,       -- the root/etym word
    parent_lemma_id INTEGER,
    relation_type TEXT,         -- 'etymon', 'morpheme_root', 'compound_prefix'
    family_status TEXT DEFAULT 'pending',  -- 'pending', 'approved', 'rejected'
    family_reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_entries_headword ON lsj_entries(headword);
CREATE INDEX IF NOT EXISTS idx_entries_key ON lsj_entries(key);
CREATE INDEX IF NOT EXISTS idx_entries_orig_id ON lsj_entries(orig_id);
CREATE INDEX IF NOT EXISTS idx_senses_entry ON lsj_senses(entry_id);
CREATE INDEX IF NOT EXISTS idx_etyma_entry ON lsj_etyma(entry_id);
CREATE INDEX IF NOT EXISTS idx_etyma_root ON lsj_etyma(root_word);
CREATE INDEX IF NOT EXISTS idx_morphemes_entry ON lsj_morphemes(entry_id);
CREATE INDEX IF NOT EXISTS idx_morphemes_prefix ON lsj_morphemes(prefix);
CREATE INDEX IF NOT EXISTS idx_matches_entry ON lsj_matches(entry_id);
CREATE INDEX IF NOT EXISTS idx_matches_lemma ON lsj_matches(lemma_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON lsj_matches(def_status);
CREATE INDEX IF NOT EXISTS idx_family_status ON lsj_family_candidates(family_status);
"""


# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════

def iter_text(el):
    """Recursively get all text content from an element."""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.extend(iter_text(child))
        if child.tail:
            parts.append(child.tail)
    return parts


def get_full_text(el):
    """Get all text content as a single string."""
    return " ".join("".join(iter_text(el)).split())


def extract_italic_defs(sense_el):
    """Extract text from <i> tags within a sense — these are the definitions."""
    defs = []
    for i_tag in sense_el.findall("i"):
        if i_tag.text:
            # Clean trailing punctuation
            txt = i_tag.text.strip().rstrip(",;:.").strip()
            if txt:
                defs.append(txt)
    return defs


def strip_diacritics_basic(text):
    """Strip common Greek diacritical marks for fuzzy matching."""
    import unicodedata
    # Decompose, remove combining marks, recompose
    nfkd = unicodedata.normalize("NFD", text)
    stripped = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", stripped).lower()


# Greek verb voice/form alternations to try when exact match fails
VERB_ALTERNATIONS = [
    # active → middle
    ("ω", "ομαι"),
    ("ω", "μαι"),
    # middle → active
    ("ομαι", "ω"),
    ("μαι", "ω"),
    ("αμαι", "άω"),
    ("αμαι", "αω"),
    # contract verbs
    ("έω", "εω"),
    ("άω", "αω"),
    ("όω", "οω"),
    ("εω", "έω"),
    ("αω", "άω"),
    ("οω", "όω"),
    # -ττω/-σσω variants
    ("ττω", "σσω"),
    ("σσω", "ττω"),
    # infinitive → finite
    ("εῖν", "εω"),
    ("εῖν", "έω"),
    ("εῖν", "ω"),
    ("ναι", "μι"),
    ("ναι", "μαι"),
    ("σθαι", "ω"),
    ("σθαι", "ομαι"),
    ("εσθαι", "ομαι"),
    ("εσθαι", "ω"),
]


def fuzzy_lookup(word, exact_map, stripped_map):
    """Try exact, stripped, verb alternations, and star-prefix removal to find a vocab match.
    Returns (lemma_id, lemma, short_def, match_type) or None."""
    if not word:
        return None

    # Clean the word
    word = word.strip().strip("()").strip()

    # Strip leading * (reconstructed forms)
    if word.startswith("*"):
        word = word[1:]

    # Exact match
    if word in exact_map:
        lid, lemma, sdef = exact_map[word]
        return (lid, lemma, sdef, "exact")

    # Stripped diacritics match
    key = strip_diacritics_basic(word)
    if key in stripped_map:
        lid, lemma, sdef = stripped_map[key][0]
        return (lid, lemma, sdef, "normalized")

    # Verb alternations
    for old_suffix, new_suffix in VERB_ALTERNATIONS:
        if word.endswith(old_suffix):
            alt = word[:-len(old_suffix)] + new_suffix
            if alt in exact_map:
                lid, lemma, sdef = exact_map[alt]
                return (lid, lemma, sdef, "verb_variant")
            alt_key = strip_diacritics_basic(alt)
            if alt_key in stripped_map:
                lid, lemma, sdef = stripped_map[alt_key][0]
                return (lid, lemma, sdef, "verb_variant")

    return None


def fuzzy_lookup_multi(text, exact_map, stripped_map):
    """Handle multi-word etyma like 'ἄγος, ἐλαύνω' — try each word.
    Returns list of (word, lemma_id, lemma, short_def, match_type)."""
    if not text:
        return []
    # Split on comma or semicolon
    words = re.split(r"[,;]\s*", text)
    results = []
    for w in words:
        w = w.strip()
        if not w or len(w) <= 1:
            continue
        # Skip if it's a prefix fragment
        if w.endswith("-") or w.startswith("-"):
            continue
        match = fuzzy_lookup(w, exact_map, stripped_map)
        if match:
            results.append((w, *match))
    return results


# ═══════════════════════════════════════════════════
# Parse XML files
# ═══════════════════════════════════════════════════

def parse_entry(div2, source_file):
    """Parse a single <div2> entry into a dict."""
    entry = {
        "xml_id": div2.get("id", ""),
        "orig_id": div2.get("orig_id", ""),
        "key": div2.get("key", ""),
        "entry_type": div2.get("type", ""),
        "source_file": source_file,
        "headword": None,
        "orth_orig": None,
        "gender": None,
        "pos": None,
        "senses": [],
        "etyma": [],
        "morphemes": [],
        "crossrefs": [],
    }

    # Head element
    head = div2.find("head")
    if head is not None:
        entry["headword"] = head.text
        entry["orth_orig"] = head.get("orth_orig", "")

    # Gender from <gen>
    gen = div2.find("gen")
    if gen is not None and gen.text:
        entry["gender"] = gen.text.strip()

    # POS from <pos>
    pos_el = div2.find(".//pos")
    if pos_el is not None and pos_el.text:
        entry["pos"] = pos_el.text.strip()

    # Senses with definitions
    for sense in div2.findall(".//sense"):
        defs = extract_italic_defs(sense)
        full = get_full_text(sense)
        entry["senses"].append({
            "n": sense.get("n", ""),
            "level": sense.get("level", ""),
            "definition": "; ".join(defs) if defs else None,
            "full_text": full,
        })

    # If no senses found, try to get <i> tags directly under div2
    if not entry["senses"]:
        top_defs = []
        for i_tag in div2.findall("i"):
            if i_tag.text:
                txt = i_tag.text.strip().rstrip(",;:.").strip()
                if txt:
                    top_defs.append(txt)
        if top_defs:
            entry["senses"].append({
                "n": "",
                "level": "1",
                "definition": "; ".join(top_defs),
                "full_text": get_full_text(div2),
            })

    # Etymology from <etym>
    for etym in div2.findall(".//etym"):
        root = etym.text
        if root:
            root = root.strip().strip("()").strip()
            if root:
                entry["etyma"].append(root)

    # Morpheme breakdown from orth_orig hyphens
    orth = entry["orth_orig"] or ""
    if "-" in orth:
        parts = orth.split("-")
        entry["morphemes"].append({
            "orth_orig": orth,
            "prefix": parts[0],
            "stem": "-".join(parts[1:]),
        })

    return entry


def parse_all_files(lsj_dir, db_path):
    """Parse all greatscott*.xml files into the staging DB."""
    files = sorted(glob.glob(str(lsj_dir / "greatscott*.xml")))
    if not files:
        print(f"ERROR: No greatscott*.xml files found in {lsj_dir}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    # Clear previous parse data
    for table in ["lsj_entries", "lsj_senses", "lsj_etyma", "lsj_morphemes", "lsj_crossrefs"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()

    total = 0
    for filepath in files:
        fname = os.path.basename(filepath)
        print(f"  Parsing {fname}...", end=" ", flush=True)
        tree = ET.parse(filepath)
        root = tree.getroot()
        entries = root.findall(".//div2")
        count = 0

        for div2 in entries:
            entry = parse_entry(div2, fname)

            cur = conn.execute(
                """INSERT OR IGNORE INTO lsj_entries (xml_id, orig_id, key, headword, orth_orig, entry_type, gender, pos, source_file)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (entry["xml_id"], entry["orig_id"], entry["key"],
                 entry["headword"], entry["orth_orig"], entry["entry_type"],
                 entry["gender"], entry["pos"], entry["source_file"]),
            )
            entry_id = cur.lastrowid

            for s in entry["senses"]:
                conn.execute(
                    "INSERT INTO lsj_senses (entry_id, sense_n, sense_level, definition, full_text) VALUES (?,?,?,?,?)",
                    (entry_id, s["n"], s["level"], s["definition"], s["full_text"]),
                )

            for root_word in entry["etyma"]:
                conn.execute(
                    "INSERT INTO lsj_etyma (entry_id, root_word) VALUES (?,?)",
                    (entry_id, root_word),
                )

            for m in entry["morphemes"]:
                conn.execute(
                    "INSERT INTO lsj_morphemes (entry_id, orth_orig, prefix, stem) VALUES (?,?,?,?)",
                    (entry_id, m["orth_orig"], m["prefix"], m["stem"]),
                )

            count += 1

        conn.commit()
        print(f"{count} entries")
        total += count

    conn.close()
    print(f"\n  Total: {total} entries parsed into {db_path}")
    return total


# ═══════════════════════════════════════════════════
# Match against existing greek_vocab.db
# ═══════════════════════════════════════════════════

def match_lemmas(staging_db, vocab_db):
    """Match LSJ entries to existing lemmas for definition review."""
    if not vocab_db.exists():
        print(f"WARNING: {vocab_db} not found — skipping matching")
        return

    stg = sqlite3.connect(str(staging_db))
    stg.row_factory = sqlite3.Row
    stg.executescript(SCHEMA)
    voc = sqlite3.connect(str(vocab_db))
    voc.row_factory = sqlite3.Row

    # Clear previous matches
    stg.execute("DELETE FROM lsj_matches")
    stg.execute("DELETE FROM lsj_family_candidates")
    stg.commit()

    # Load all vocab lemmas into a lookup dict
    print("  Loading vocab lemmas...")
    vocab_lemmas = voc.execute("SELECT id, lemma, short_def FROM lemmas").fetchall()

    # Build lookup dicts: exact, and stripped (no diacritics)
    exact_map = {}      # headword -> (lemma_id, lemma, short_def)
    stripped_map = {}    # stripped headword -> [(lemma_id, lemma, short_def)]

    for row in vocab_lemmas:
        lemma = row["lemma"]
        exact_map[lemma] = (row["id"], lemma, row["short_def"])
        key = strip_diacritics_basic(lemma)
        stripped_map.setdefault(key, []).append((row["id"], lemma, row["short_def"]))

    print(f"  Loaded {len(vocab_lemmas)} vocab lemmas")

    # Load LSJ entries with their primary definition and full text fallback
    lsj_entries = stg.execute("""
        SELECT e.id, e.headword, e.orth_orig,
               GROUP_CONCAT(CASE WHEN s.definition IS NOT NULL THEN s.definition END, '; ') as combined_def,
               GROUP_CONCAT(CASE WHEN s.full_text IS NOT NULL THEN s.full_text END, ' | ') as combined_full
        FROM lsj_entries e
        LEFT JOIN lsj_senses s ON s.entry_id = e.id
        GROUP BY e.id
    """).fetchall()

    print(f"  Matching {len(lsj_entries)} LSJ entries against vocab...")
    match_count = 0
    missing_def_count = 0

    for entry in lsj_entries:
        headword = entry["headword"]
        if not headword:
            continue

        lsj_def = entry["combined_def"]
        lsj_full = entry["combined_full"]
        entry_id = entry["id"]
        matched = False

        def insert_match(lid, lemma, cur_def, match_type):
            nonlocal match_count, missing_def_count
            missing = 1 if not cur_def or cur_def.strip() == "" else 0
            if missing:
                missing_def_count += 1
            stg.execute(
                """INSERT INTO lsj_matches (entry_id, lemma_id, lemma, match_type, current_short_def, lsj_short_def, lsj_full_def, missing_current_def)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (entry_id, lid, lemma, match_type, cur_def, lsj_def, lsj_full, missing),
            )
            match_count += 1

        # Try exact match
        if headword in exact_map:
            lid, lemma, cur_def = exact_map[headword]
            insert_match(lid, lemma, cur_def, "exact")
            matched = True

        # Try stripped match if no exact
        if not matched:
            key = strip_diacritics_basic(headword)
            if key in stripped_map:
                for lid, lemma, cur_def in stripped_map[key]:
                    insert_match(lid, lemma, cur_def, "normalized")
                    matched = True

        # Try verb variant match if still no match
        if not matched:
            result = fuzzy_lookup(headword, exact_map, stripped_map)
            if result:
                lid, lemma, cur_def, match_type = result
                insert_match(lid, lemma, cur_def, match_type)

    stg.commit()
    print(f"  Definition matches: {match_count}")
    print(f"  Lemmas with missing current def: {missing_def_count}")

    # Family expansion candidates from etyma
    print("  Building family expansion candidates from etyma...")
    etyma = stg.execute("""
        SELECT et.entry_id, et.root_word, e.headword
        FROM lsj_etyma et
        JOIN lsj_entries e ON e.id = et.entry_id
    """).fetchall()

    family_count = 0
    for et in etyma:
        child_headword = et["headword"]
        parent_headword = et["root_word"]
        if not child_headword or not parent_headword:
            continue

        # Look up child with fuzzy matching
        child_result = fuzzy_lookup(child_headword, exact_map, stripped_map)
        child_lid = child_result[0] if child_result else None

        # Look up parent(s) — may be multi-word like "ἄγος, ἐλαύνω"
        parent_results = fuzzy_lookup_multi(parent_headword, exact_map, stripped_map)

        if parent_results:
            # Create a candidate for each matched parent word
            for parent_word, parent_lid, parent_lemma, _, match_type in parent_results:
                stg.execute(
                    """INSERT INTO lsj_family_candidates
                       (child_entry_id, child_lemma_id, child_headword, parent_headword, parent_lemma_id, relation_type)
                       VALUES (?,?,?,?,?,?)""",
                    (et["entry_id"], child_lid, child_headword, parent_word, parent_lid, "etymon"),
                )
                family_count += 1
        else:
            # No match found — still record for manual review
            stg.execute(
                """INSERT INTO lsj_family_candidates
                   (child_entry_id, child_lemma_id, child_headword, parent_headword, parent_lemma_id, relation_type)
                   VALUES (?,?,?,?,?,?)""",
                (et["entry_id"], child_lid, child_headword, parent_headword, None, "etymon"),
            )
            family_count += 1

    # Family candidates from morpheme breakdowns
    print("  Building family candidates from morpheme breakdowns...")
    morphemes = stg.execute("""
        SELECT m.entry_id, m.prefix, m.stem, e.headword
        FROM lsj_morphemes m
        JOIN lsj_entries e ON e.id = m.entry_id
    """).fetchall()

    for m in morphemes:
        child_headword = m["headword"]
        prefix = m["prefix"]
        if not child_headword or not prefix:
            continue

        # Resolve child once for both prefix and stem checks
        child_result = fuzzy_lookup(child_headword, exact_map, stripped_map)
        child_lid = child_result[0] if child_result else None

        # Check if prefix itself is a word in vocab (compound detection)
        prefix_result = fuzzy_lookup(prefix, exact_map, stripped_map)
        if prefix_result:
            stg.execute(
                """INSERT INTO lsj_family_candidates
                   (child_entry_id, child_lemma_id, child_headword, parent_headword, parent_lemma_id, relation_type)
                   VALUES (?,?,?,?,?,?)""",
                (m["entry_id"], child_lid, child_headword,
                 prefix, prefix_result[0], "compound_prefix"),
            )
            family_count += 1

        # Also check if the stem (second morpheme) is a word in vocab
        stem = m["stem"]
        if stem:
            stem_result = fuzzy_lookup(stem, exact_map, stripped_map)
            if stem_result:
                stg.execute(
                    """INSERT INTO lsj_family_candidates
                       (child_entry_id, child_lemma_id, child_headword, parent_headword, parent_lemma_id, relation_type)
                       VALUES (?,?,?,?,?,?)""",
                    (m["entry_id"], child_lid, child_headword,
                     stem, stem_result[0], "compound_stem"),
                )
                family_count += 1

    stg.commit()
    stg.close()
    voc.close()
    print(f"  Family expansion candidates: {family_count}")


# ═══════════════════════════════════════════════════
# Summary stats
# ═══════════════════════════════════════════════════

def print_summary(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("\n" + "=" * 55)
    print("  LSJ Staging Database Summary")
    print("=" * 55)

    counts = {}
    for table in ["lsj_entries", "lsj_senses", "lsj_etyma", "lsj_morphemes",
                   "lsj_crossrefs", "lsj_matches", "lsj_family_candidates"]:
        try:
            c = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
        except Exception:
            c = 0
        counts[table] = c
        print(f"  {table}: {c:,}")

    if counts["lsj_matches"]:
        print("\n  Definition matches by type:")
        for row in conn.execute("SELECT match_type, COUNT(*) as c FROM lsj_matches GROUP BY match_type"):
            print(f"    {row['match_type']}: {row['c']:,}")
        pending = conn.execute("SELECT COUNT(*) as c FROM lsj_matches WHERE def_status='pending'").fetchone()["c"]
        print(f"\n  Pending definition reviews: {pending:,}")
        try:
            missing = conn.execute("SELECT COUNT(*) as c FROM lsj_matches WHERE missing_current_def = 1").fetchone()["c"]
            print(f"  Lemmas with MISSING current def (priority): {missing:,}")
            has_lsj = conn.execute("SELECT COUNT(*) as c FROM lsj_matches WHERE missing_current_def = 1 AND (lsj_short_def IS NOT NULL OR lsj_full_def IS NOT NULL)").fetchone()["c"]
            print(f"  Missing defs fillable from LSJ: {has_lsj:,}")
        except Exception:
            pass

    if counts["lsj_family_candidates"]:
        print("\n  Family candidates by type:")
        for row in conn.execute("SELECT relation_type, COUNT(*) as c FROM lsj_family_candidates GROUP BY relation_type"):
            print(f"    {row['relation_type']}: {row['c']:,}")

        # How many have both child and parent in vocab?
        both = conn.execute(
            "SELECT COUNT(*) as c FROM lsj_family_candidates WHERE child_lemma_id IS NOT NULL AND parent_lemma_id IS NOT NULL"
        ).fetchone()["c"]
        print(f"  Both child & parent in vocab: {both:,} (actionable)")

    # Sample some matches for preview
    if counts["lsj_matches"]:
        print("\n  Sample definition matches (current → LSJ):")
        samples = conn.execute("""
            SELECT lemma, current_short_def, lsj_short_def, match_type
            FROM lsj_matches WHERE lsj_short_def IS NOT NULL
            ORDER BY RANDOM() LIMIT 5
        """).fetchall()
        for s in samples:
            cur = (s["current_short_def"] or "")[:40]
            lsj = (s["lsj_short_def"] or "")[:60]
            print(f"    {s['lemma']}: \"{cur}\" → \"{lsj}\"")

    print("=" * 55)
    conn.close()


# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse LSJLogeion XML into staging DB")
    parser.add_argument("--parse-only", action="store_true", help="Only parse XML, skip matching")
    parser.add_argument("--match-only", action="store_true", help="Only match against vocab DB")
    parser.add_argument("--lsj-dir", default=str(LSJ_DIR), help="Path to LSJLogeion directory")
    parser.add_argument("--staging-db", default=str(STAGING_DB), help="Path to staging DB")
    parser.add_argument("--vocab-db", default=str(VOCAB_DB), help="Path to greek_vocab.db")
    args = parser.parse_args()

    lsj_dir = Path(args.lsj_dir)
    staging_db = Path(args.staging_db)
    vocab_db = Path(args.vocab_db)

    if not args.match_only:
        print(f"\n{'=' * 55}")
        print(f"  Parsing LSJ XML from {lsj_dir}")
        print(f"  Output: {staging_db}")
        print(f"{'=' * 55}\n")
        parse_all_files(lsj_dir, staging_db)

    if not args.parse_only:
        print(f"\n  Matching against {vocab_db}...")
        match_lemmas(staging_db, vocab_db)

    print_summary(staging_db)
