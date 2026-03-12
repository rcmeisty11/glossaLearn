#!/usr/bin/env python3
"""
build_database.py
═══════════════════════════════════════════════════════════════
Parses downloaded Greek corpus data and builds a local SQLite
database optimized for vocabulary exploration.

Run AFTER download_greek_data.sh has completed.

Usage:
    python3 build_database.py

This will create: greek_vocab.db (~500MB-1GB depending on corpus size)

Requirements:
    pip3 install lxml    (for fast XML parsing)

The script processes:
    1. LemmatizedAncientGreekXML → lemmas, forms, occurrences
    2. PerseusDL/lexica → definitions (LSJ, Middle Liddell)
    3. Work metadata from filenames (TLG codes → author/title)
═══════════════════════════════════════════════════════════════
"""

import glob
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

# Try lxml first (much faster), fall back to stdlib
try:
    from lxml import etree as ET
    USING_LXML = True
    print("Using lxml for XML parsing (fast mode)")
except ImportError:
    import xml.etree.ElementTree as ET
    USING_LXML = False
    print("lxml not found, using stdlib xml.etree (slower)")
    print("  Install lxml for 5-10x speedup: pip3 install lxml")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path.home() / "greek_data"
DB_PATH = Path("./greek_vocab.db")

# TLG codes → (author_name, language)
# This maps the file naming convention to human-readable metadata
TLG_AUTHORS = {
    "tlg0012": "Homer",
    "tlg0011": "Sophocles",
    "tlg0006": "Euripides",
    "tlg0085": "Aeschylus",
    "tlg0003": "Thucydides",
    "tlg0016": "Herodotus",
    "tlg0059": "Plato",
    "tlg0086": "Aristotle",
    "tlg0032": "Xenophon",
    "tlg0007": "Plutarch",
    "tlg0013": "Homeric Hymns",
    "tlg0020": "Hesiod",
    "tlg0031": "New Testament",
    "tlg0527": "Septuagint",
    "tlg0014": "Demosthenes",
    "tlg0010": "Isocrates",
    "tlg0028": "Antiphon",
    "tlg0017": "Isaeus",
    "tlg0540": "Lysias",
    "tlg0019": "Aristophanes",
    "tlg0060": "Diodorus Siculus",
    "tlg0062": "Lucian",
    "tlg0057": "Galen",
    "tlg0018": "Apollonius Rhodius",
    "tlg0099": "Pindar",
    "tlg0009": "Sappho",
    "tlg0033": "Polybius",
    "tlg0093": "Theophrastus",
    "tlg0525": "Josephus",
    "tlg0081": "Athenaeus",
    "tlg0036": "Apollodorus",
    "tlg0046": "Pausanias",
    "tlg0090": "Strabo",
    "tlg0561": "Epictetus",
    "tlg0555": "Marcus Aurelius",
    "tlg4015": "Eusebius",
    "tlg0526": "Philo",
    "tlg2018": "Clement of Alexandria",
    "tlg2042": "John Chrysostom",
    "tlg2040": "Basil of Caesarea",
    "tlg2022": "Origen",
    "tlg0008": "Athenaeus",
}

TLG_WORKS = {
    "tlg001": "Iliad",
    "tlg002": "Odyssey",
    "tlg003": "Antigone",
    "tlg004": "Electra",
    "tlg005": "Oedipus at Colonus",
    "tlg006": "Anabasis",
    "tlg007": "Oedipus Tyrannus",
    "tlg011": "Republic",
    "tlg012": "Laws",
    "tlg030": "Republic",
    "tlg031": "Symposium",
}

# Morpheus 9-character tag positions
MORPH_POSITIONS = {
    0: "pos",
    1: "person",
    2: "number",
    3: "tense",
    4: "mood",
    5: "voice",
    6: "gender",
    7: "case",
    8: "degree",
}

MORPH_VALUES = {
    "pos": {
        "n": "noun", "v": "verb", "a": "adjective", "d": "adverb",
        "l": "article", "g": "particle", "c": "conjunction",
        "r": "preposition", "p": "pronoun", "m": "numeral",
        "i": "interjection", "u": "punctuation", "x": "irregular",
    },
    "person": {"1": "1st", "2": "2nd", "3": "3rd"},
    "number": {"s": "singular", "p": "plural", "d": "dual"},
    "tense": {
        "p": "present", "i": "imperfect", "r": "perfect",
        "l": "pluperfect", "t": "future perfect", "f": "future",
        "a": "aorist",
    },
    "mood": {
        "i": "indicative", "s": "subjunctive", "o": "optative",
        "n": "infinitive", "m": "imperative", "p": "participle",
    },
    "voice": {
        "a": "active", "p": "passive", "m": "middle",
        "e": "medio-passive",
    },
    "gender": {"m": "masculine", "f": "feminine", "n": "neuter"},
    "case": {
        "n": "nominative", "g": "genitive", "d": "dative",
        "a": "accusative", "v": "vocative", "l": "locative",
    },
    "degree": {"c": "comparative", "s": "superlative"},
}


def parse_morph_tag(tag):
    """Parse a 9-character Morpheus morphology tag into a dict."""
    if not tag or len(tag) < 9:
        return {}
    result = {}
    for i, field_name in MORPH_POSITIONS.items():
        if i < len(tag) and tag[i] != "-":
            lookup = MORPH_VALUES.get(field_name, {})
            result[field_name] = lookup.get(tag[i], tag[i])
    return result


# ═══════════════════════════════════════════════════════════════
# DATABASE SCHEMA
# ═══════════════════════════════════════════════════════════════

SCHEMA = """
-- ─────────────────────────────────
-- Works: each Greek text
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS works (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL UNIQUE,
    cts_urn     TEXT,
    author_code TEXT,
    work_code   TEXT,
    author      TEXT,
    title       TEXT,
    corpus      TEXT DEFAULT 'perseus'
);

-- ─────────────────────────────────
-- Lemmas: dictionary headwords
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS lemmas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma           TEXT NOT NULL,
    pos             TEXT,
    short_def       TEXT,
    lsj_def         TEXT,
    middle_liddell   TEXT,
    total_occurrences INTEGER DEFAULT 0,
    frequency_rank  INTEGER,
    UNIQUE(lemma, pos)
);

-- ─────────────────────────────────
-- Forms: all morphological inflections
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS forms (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id        INTEGER NOT NULL REFERENCES lemmas(id),
    form            TEXT NOT NULL,
    morph_tag       TEXT,
    pos             TEXT,
    person          TEXT,
    number          TEXT,
    tense           TEXT,
    mood            TEXT,
    voice           TEXT,
    gender          TEXT,
    gram_case       TEXT,
    degree          TEXT,
    UNIQUE(lemma_id, form, morph_tag)
);

-- ─────────────────────────────────
-- Occurrences: where each token appears
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS occurrences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    form_id     INTEGER REFERENCES forms(id),
    work_id     INTEGER NOT NULL REFERENCES works(id),
    passage     TEXT,
    sentence_n  INTEGER,
    token_n     INTEGER
);

-- ─────────────────────────────────
-- Definitions from lexica
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS definitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    source      TEXT NOT NULL,
    entry_key   TEXT,
    definition  TEXT NOT NULL,
    short_def   TEXT
);

-- ─────────────────────────────────
-- Derivational families
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS derivational_families (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    root        TEXT NOT NULL,
    label       TEXT
);

CREATE TABLE IF NOT EXISTS lemma_families (
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    family_id   INTEGER NOT NULL REFERENCES derivational_families(id),
    relation    TEXT,
    PRIMARY KEY(lemma_id, family_id)
);

-- ─────────────────────────────────
-- Corpus filter helper: per-work lemma counts
-- This makes filtering by work FAST
-- ─────────────────────────────────
CREATE TABLE IF NOT EXISTS work_lemma_counts (
    work_id     INTEGER NOT NULL REFERENCES works(id),
    lemma_id    INTEGER NOT NULL REFERENCES lemmas(id),
    count       INTEGER DEFAULT 1,
    PRIMARY KEY(work_id, lemma_id)
);
"""

INDEXES = """
-- Lemma lookups
CREATE INDEX IF NOT EXISTS idx_lemmas_lemma ON lemmas(lemma);
CREATE INDEX IF NOT EXISTS idx_lemmas_pos ON lemmas(pos);
CREATE INDEX IF NOT EXISTS idx_lemmas_freq ON lemmas(frequency_rank);
CREATE INDEX IF NOT EXISTS idx_lemmas_total ON lemmas(total_occurrences);

-- Form lookups
CREATE INDEX IF NOT EXISTS idx_forms_lemma ON forms(lemma_id);
CREATE INDEX IF NOT EXISTS idx_forms_form ON forms(form);

-- Occurrence lookups
CREATE INDEX IF NOT EXISTS idx_occ_lemma ON occurrences(lemma_id);
CREATE INDEX IF NOT EXISTS idx_occ_work ON occurrences(work_id);
CREATE INDEX IF NOT EXISTS idx_occ_passage ON occurrences(passage);

-- Work-lemma cross-reference (the key index for corpus filtering)
CREATE INDEX IF NOT EXISTS idx_wlc_work ON work_lemma_counts(work_id);
CREATE INDEX IF NOT EXISTS idx_wlc_lemma ON work_lemma_counts(lemma_id);
CREATE INDEX IF NOT EXISTS idx_wlc_count ON work_lemma_counts(count);

-- Definition lookups
CREATE INDEX IF NOT EXISTS idx_def_lemma ON definitions(lemma_id);

-- Family lookups
CREATE INDEX IF NOT EXISTS idx_lf_lemma ON lemma_families(lemma_id);
CREATE INDEX IF NOT EXISTS idx_lf_family ON lemma_families(family_id);

-- Full text search on lemmas
-- (SQLite FTS5 for fast prefix/substring search)
CREATE VIRTUAL TABLE IF NOT EXISTS lemmas_fts USING fts5(
    lemma, short_def, lsj_def,
    content='lemmas',
    content_rowid='id'
);
"""

FTS_POPULATE = """
INSERT INTO lemmas_fts(rowid, lemma, short_def, lsj_def)
SELECT id, lemma, short_def, lsj_def FROM lemmas;
"""


# ═══════════════════════════════════════════════════════════════
# PARSING: LEMMATIZED XML
# ═══════════════════════════════════════════════════════════════

def extract_work_metadata(filename):
    """Extract author/work codes from filename like tlg0012.tlg001.perseus-grc2.xml"""
    base = os.path.basename(filename).replace(".xml", "")
    parts = base.split(".")
    author_code = parts[0] if len(parts) > 0 else ""
    work_code = parts[1] if len(parts) > 1 else ""
    edition = parts[2] if len(parts) > 2 else ""

    author = TLG_AUTHORS.get(author_code, author_code)
    title = TLG_WORKS.get(work_code, work_code)

    # Build a CTS URN
    cts_urn = f"urn:cts:greekLit:{author_code}.{work_code}"
    if edition:
        cts_urn += f".{edition}"

    # Determine corpus
    corpus = "perseus"
    if "1st1K" in edition or "opp-" in edition:
        corpus = "first1k"

    return {
        "filename": base,
        "cts_urn": cts_urn,
        "author_code": author_code,
        "work_code": work_code,
        "author": author,
        "title": title,
        "corpus": corpus,
    }


def process_lemmatized_file(filepath, conn, lemma_cache, form_cache, work_id):
    """
    Parse one LemmatizedAncientGreekXML file.

    XML structure (per the repo docs):
        <s n="1">                          ← sentence
          <t p="1" n="1" o="n-s---mn-">    ← token (passage, position, morph tag)
            <f>λόγος</f>                    ← word form
            <l i="123">                     ← lemma container
              <l1 o="...">λόγος</l1>        ← lemma from MorpheusUnderPhilologic
              <l2>λόγος</l2>                ← lemma from Morpheus
            </l>
          </t>
        </s>
    """
    cursor = conn.cursor()

    try:
        if USING_LXML:
            tree = ET.parse(filepath)
            root = tree.getroot()
        else:
            tree = ET.parse(filepath)
            root = tree.getroot()
    except Exception as e:
        print(f"    ⚠ Error parsing {filepath}: {e}")
        return 0

    token_count = 0
    batch_occurrences = []
    batch_wlc = defaultdict(int)  # (work_id, lemma_id) → count

    for sentence in root.iter("s"):
        sent_n = sentence.get("n", "")

        for token in sentence.iter("t"):
            form_el = token.find("f")
            if form_el is None or not form_el.text:
                continue

            word_form = form_el.text.strip()
            if not word_form or word_form in (".", ",", ";", "·", ":", "\"", "'"):
                continue

            morph_tag = token.get("o", "")
            passage = token.get("p", "")
            token_n = token.get("n", "")

            # Skip punctuation
            if morph_tag and len(morph_tag) >= 1 and morph_tag[0] == "u":
                continue

            # Extract lemmas — prefer l1 (MorpheusUnderPhilologic), then l2
            lemma_el = token.find("l")
            lemma_text = None
            lemma_tag = morph_tag

            if lemma_el is not None:
                # Try l1 first
                l1 = lemma_el.find("l1")
                if l1 is not None and l1.text:
                    lemma_text = l1.text.strip()
                    lemma_tag = l1.get("o", morph_tag)
                else:
                    # Fall back to l2
                    l2 = lemma_el.find("l2")
                    if l2 is not None and l2.text:
                        lemma_text = l2.text.strip()

            if not lemma_text:
                continue

            # Determine POS from tag
            pos_char = morph_tag[0] if morph_tag and len(morph_tag) >= 1 else ""
            pos = MORPH_VALUES["pos"].get(pos_char, "")

            # Get or create lemma
            lemma_key = (lemma_text, pos)
            if lemma_key not in lemma_cache:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO lemmas (lemma, pos) VALUES (?, ?)",
                        (lemma_text, pos),
                    )
                    if cursor.lastrowid:
                        lemma_cache[lemma_key] = cursor.lastrowid
                    else:
                        cursor.execute(
                            "SELECT id FROM lemmas WHERE lemma=? AND pos=?",
                            (lemma_text, pos),
                        )
                        row = cursor.fetchone()
                        lemma_cache[lemma_key] = row[0] if row else None
                except sqlite3.IntegrityError:
                    cursor.execute(
                        "SELECT id FROM lemmas WHERE lemma=? AND pos=?",
                        (lemma_text, pos),
                    )
                    row = cursor.fetchone()
                    lemma_cache[lemma_key] = row[0] if row else None

            lemma_id = lemma_cache.get(lemma_key)
            if lemma_id is None:
                continue

            # Get or create form
            form_key = (lemma_id, word_form, morph_tag)
            if form_key not in form_cache:
                parsed = parse_morph_tag(morph_tag)
                try:
                    cursor.execute(
                        """INSERT OR IGNORE INTO forms
                           (lemma_id, form, morph_tag, pos, person, number,
                            tense, mood, voice, gender, gram_case, degree)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            lemma_id, word_form, morph_tag,
                            parsed.get("pos", ""), parsed.get("person", ""),
                            parsed.get("number", ""), parsed.get("tense", ""),
                            parsed.get("mood", ""), parsed.get("voice", ""),
                            parsed.get("gender", ""), parsed.get("case", ""),
                            parsed.get("degree", ""),
                        ),
                    )
                    form_cache[form_key] = cursor.lastrowid or 0
                except sqlite3.IntegrityError:
                    form_cache[form_key] = 0

            form_id = form_cache.get(form_key, None)

            # Queue occurrence
            batch_occurrences.append((
                lemma_id, form_id, work_id, passage,
                int(sent_n) if sent_n.isdigit() else None,
                int(token_n) if token_n and token_n.isdigit() else None,
            ))

            # Count for work_lemma_counts
            batch_wlc[(work_id, lemma_id)] += 1

            token_count += 1

            # Batch insert every 5000 tokens
            if len(batch_occurrences) >= 5000:
                cursor.executemany(
                    """INSERT INTO occurrences
                       (lemma_id, form_id, work_id, passage, sentence_n, token_n)
                       VALUES (?,?,?,?,?,?)""",
                    batch_occurrences,
                )
                batch_occurrences = []

    # Flush remaining
    if batch_occurrences:
        cursor.executemany(
            """INSERT INTO occurrences
               (lemma_id, form_id, work_id, passage, sentence_n, token_n)
               VALUES (?,?,?,?,?,?)""",
            batch_occurrences,
        )

    # Insert work-lemma counts
    for (wid, lid), count in batch_wlc.items():
        cursor.execute(
            """INSERT INTO work_lemma_counts (work_id, lemma_id, count)
               VALUES (?,?,?)
               ON CONFLICT(work_id, lemma_id)
               DO UPDATE SET count = count + ?""",
            (wid, lid, count, count),
        )

    return token_count


# ═══════════════════════════════════════════════════════════════
# PARSING: LEXICA (LSJ, Middle Liddell)
# ═══════════════════════════════════════════════════════════════

def parse_lexica(conn, data_dir):
    """Parse LSJ and Middle Liddell XML to populate definitions."""
    cursor = conn.cursor()
    lexica_dir = data_dir / "lexica"

    if not lexica_dir.exists():
        print("  ⚠ lexica directory not found, skipping definitions")
        return

    # Middle Liddell — simpler, good short definitions
    ml_pattern = str(lexica_dir / "CTS_XML_TEI" / "perseus" / "pdllex" /
                     "grc" / "ml" / "*.xml")
    ml_files = glob.glob(ml_pattern)

    # Also try alternate path structures
    if not ml_files:
        ml_pattern = str(lexica_dir / "**" / "ml" / "*.xml")
        ml_files = glob.glob(ml_pattern, recursive=True)

    # LSJ
    lsj_pattern = str(lexica_dir / "CTS_XML_TEI" / "perseus" / "pdllex" /
                      "grc" / "lsj" / "*.xml")
    lsj_files = glob.glob(lsj_pattern)
    if not lsj_files:
        lsj_pattern = str(lexica_dir / "**" / "lsj" / "*.xml")
        lsj_files = glob.glob(lsj_pattern, recursive=True)

    ns = {"tei": "http://www.tei-c.org/ns/1.0"}
    def_count = 0

    for source_name, file_list in [("middle_liddell", ml_files), ("lsj", lsj_files)]:
        print(f"  Parsing {source_name}: {len(file_list)} files...")
        for fpath in file_list:
            try:
                if USING_LXML:
                    tree = ET.parse(fpath)
                    root = tree.getroot()
                    entries = root.findall(".//tei:entry", ns) + root.findall(".//entry")
                else:
                    tree = ET.parse(fpath)
                    root = tree.getroot()
                    # Handle namespace
                    entries = root.findall(
                        ".//{http://www.tei-c.org/ns/1.0}entry"
                    )
                    if not entries:
                        entries = root.findall(".//entry")

                for entry in entries:
                    # Get headword
                    key = entry.get("key", "")
                    orth = entry.find("{http://www.tei-c.org/ns/1.0}orth")
                    if orth is None:
                        orth = entry.find("orth")

                    headword = ""
                    if orth is not None and orth.text:
                        headword = orth.text.strip()
                    elif key:
                        headword = key

                    if not headword:
                        continue

                    # Get definition text (concatenate all text in senses)
                    def_parts = []
                    senses = entry.findall(".//{http://www.tei-c.org/ns/1.0}sense")
                    if not senses:
                        senses = entry.findall(".//sense")

                    for sense in senses:
                        text = "".join(sense.itertext()).strip()
                        if text:
                            def_parts.append(text[:500])  # cap per sense

                    full_def = " | ".join(def_parts[:10])  # cap at 10 senses
                    if not full_def:
                        # Try getting any text content
                        full_def = "".join(entry.itertext()).strip()[:1000]

                    if not full_def:
                        continue

                    # Make a short definition (first sense, truncated)
                    short = def_parts[0][:200] if def_parts else full_def[:200]

                    # Find matching lemma
                    cursor.execute(
                        "SELECT id FROM lemmas WHERE lemma = ?",
                        (headword,),
                    )
                    rows = cursor.fetchall()

                    for row in rows:
                        cursor.execute(
                            """INSERT OR IGNORE INTO definitions
                               (lemma_id, source, entry_key, definition, short_def)
                               VALUES (?,?,?,?,?)""",
                            (row[0], source_name, key, full_def[:2000], short),
                        )
                        def_count += 1

                        # Also update the lemma row directly
                        if source_name == "middle_liddell":
                            cursor.execute(
                                "UPDATE lemmas SET middle_liddell=?, short_def=COALESCE(short_def, ?) WHERE id=?",
                                (full_def[:2000], short, row[0]),
                            )
                        else:
                            cursor.execute(
                                "UPDATE lemmas SET lsj_def=?, short_def=COALESCE(short_def, ?) WHERE id=?",
                                (full_def[:5000], short, row[0]),
                            )

            except Exception as e:
                print(f"    ⚠ Error parsing {fpath}: {e}")
                continue

    print(f"  ✓ Loaded {def_count} definitions")


# ═══════════════════════════════════════════════════════════════
# POST-PROCESSING: Frequency ranks, totals, derivational families
# ═══════════════════════════════════════════════════════════════

def compute_frequency_ranks(conn):
    """Compute total occurrences and frequency rank for each lemma."""
    cursor = conn.cursor()
    print("  Computing occurrence totals...")
    cursor.execute("""
        UPDATE lemmas SET total_occurrences = (
            SELECT COALESCE(SUM(count), 0)
            FROM work_lemma_counts
            WHERE work_lemma_counts.lemma_id = lemmas.id
        )
    """)

    print("  Computing frequency ranks...")
    cursor.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY total_occurrences DESC) as rank
            FROM lemmas
            WHERE total_occurrences > 0
        )
        UPDATE lemmas SET frequency_rank = (
            SELECT rank FROM ranked WHERE ranked.id = lemmas.id
        )
    """)
    conn.commit()
    print("  ✓ Frequency ranks computed")


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

def build_derivational_families(conn):
    """
    Simple derivational family builder based on shared stems.
    Groups lemmas that share a common root after stripping known prefixes.
    This is approximate — a full solution needs Morpheus stem tables.
    """
    cursor = conn.cursor()
    print("  Building derivational families (approximate)...")

    # Get all lemmas
    cursor.execute("SELECT id, lemma, pos FROM lemmas WHERE total_occurrences > 2")
    lemmas = cursor.fetchall()

    # Simple stemming: strip known prefixes, then group by first 3+ chars
    stem_groups = defaultdict(list)

    for lid, lemma, pos in lemmas:
        stem = lemma
        prefix = ""

        # Strip prefix
        for pfx, pfx_label in sorted(GREEK_PREFIXES, key=lambda x: -len(x[0])):
            if stem.startswith(pfx) and len(stem) > len(pfx) + 2:
                prefix = pfx_label
                stem = stem[len(pfx):]
                break

        # Normalize: strip common suffixes for grouping
        for suf in ["ία", "ίας", "ικός", "ικη", "ισμός", "ιστής",
                     "εία", "εύς", "ος", "ον", "ή", "ης", "ης",
                     "ίζω", "όω", "έω", "άω", "ύω", "ειν", "ναι"]:
            if stem.endswith(suf) and len(stem) > len(suf) + 2:
                stem = stem[:-len(suf)]
                break

        if len(stem) >= 3:
            stem_groups[stem].append((lid, lemma, pos, prefix))

    # Only keep groups with 2+ members
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
            relation = "root"
            if prefix:
                relation = f"prefix {prefix}"
            cursor.execute(
                "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation) VALUES (?,?,?)",
                (lid, family_id, relation),
            )
        family_count += 1

    conn.commit()
    print(f"  ✓ Built {family_count} derivational families")


# ═══════════════════════════════════════════════════════════════
# MAIN BUILD PROCESS
# ═══════════════════════════════════════════════════════════════

def main():
    print("═══════════════════════════════════════════════════════════")
    print("  Greek Vocabulary Database Builder")
    print(f"  Data source: {DATA_DIR}")
    print(f"  Database: {DB_PATH}")
    print("═══════════════════════════════════════════════════════════")
    print()

    # Check data exists
    lemma_dir = DATA_DIR / "LemmatizedAncientGreekXML" / "texts"
    if not lemma_dir.exists():
        print(f"ERROR: Lemmatized texts not found at {lemma_dir}")
        print("Run download_greek_data.sh first.")
        sys.exit(1)

    # Delete old DB if exists
    if DB_PATH.exists():
        print(f"Removing old database: {DB_PATH}")
        os.remove(DB_PATH)

    # Create database
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")

    print("[1/5] Creating schema...")
    conn.executescript(SCHEMA)
    conn.commit()

    # ─── Parse lemmatized XML files ───
    print("[2/5] Parsing lemmatized texts...")
    xml_files = sorted(glob.glob(str(lemma_dir / "*.xml")))
    print(f"  Found {len(xml_files)} text files")

    lemma_cache = {}  # (lemma, pos) → id
    form_cache = {}   # (lemma_id, form, tag) → id
    total_tokens = 0
    cursor = conn.cursor()

    for i, filepath in enumerate(xml_files):
        meta = extract_work_metadata(filepath)

        # Insert work
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO works
                   (filename, cts_urn, author_code, work_code, author, title, corpus)
                   VALUES (?,?,?,?,?,?,?)""",
                (meta["filename"], meta["cts_urn"], meta["author_code"],
                 meta["work_code"], meta["author"], meta["title"], meta["corpus"]),
            )
            work_id = cursor.lastrowid
            if not work_id:
                cursor.execute("SELECT id FROM works WHERE filename=?", (meta["filename"],))
                row = cursor.fetchone()
                work_id = row[0] if row else None
        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM works WHERE filename=?", (meta["filename"],))
            row = cursor.fetchone()
            work_id = row[0] if row else None

        if work_id is None:
            continue

        tokens = process_lemmatized_file(filepath, conn, lemma_cache, form_cache, work_id)
        total_tokens += tokens

        if (i + 1) % 10 == 0 or i == len(xml_files) - 1:
            conn.commit()
            pct = ((i + 1) / len(xml_files)) * 100
            print(f"  [{i+1}/{len(xml_files)}] {pct:.0f}% — {total_tokens:,} tokens, "
                  f"{len(lemma_cache):,} lemmas — {meta['author']}: {meta['title']}")

    conn.commit()
    print(f"  ✓ Parsed {total_tokens:,} tokens, {len(lemma_cache):,} unique lemmas")

    # ─── Parse lexica ───
    print("[3/5] Parsing lexica (LSJ, Middle Liddell)...")
    parse_lexica(conn, DATA_DIR)
    conn.commit()

    # ─── Post-processing ───
    print("[4/5] Post-processing...")
    compute_frequency_ranks(conn)
    build_derivational_families(conn)

    # ─── Build indexes and FTS ───
    print("[5/5] Building indexes and full-text search...")
    conn.executescript(INDEXES)
    try:
        conn.executescript(FTS_POPULATE)
    except Exception as e:
        print(f"  ⚠ FTS population note: {e}")
    conn.commit()

    # ─── Summary stats ───
    cursor = conn.cursor()
    stats = {}
    for table in ["works", "lemmas", "forms", "occurrences", "definitions",
                   "derivational_families", "work_lemma_counts"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        stats[table] = cursor.fetchone()[0]

    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)

    conn.execute("PRAGMA optimize")
    conn.close()

    print()
    print("═══════════════════════════════════════════════════════════")
    print("  Database build complete!")
    print(f"  File: {DB_PATH} ({db_size:.0f} MB)")
    print()
    print(f"  Works:          {stats['works']:>10,}")
    print(f"  Lemmas:         {stats['lemmas']:>10,}")
    print(f"  Forms:          {stats['forms']:>10,}")
    print(f"  Occurrences:    {stats['occurrences']:>10,}")
    print(f"  Definitions:    {stats['definitions']:>10,}")
    print(f"  Word families:  {stats['derivational_families']:>10,}")
    print(f"  Work↔Lemma idx: {stats['work_lemma_counts']:>10,}")
    print()
    print("  Next step: Start the API server")
    print("    python3 serve_api.py")
    print("═══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    start = time.time()
    main()
    elapsed = time.time() - start
    print(f"\n  Total time: {elapsed/60:.1f} minutes")
