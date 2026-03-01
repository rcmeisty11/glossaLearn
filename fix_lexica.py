#!/usr/bin/env python3
"""
fix_lexica.py
═══════════════════════════════════════════════════════════════
Loads LSJ definitions into greek_vocab.db.

The LSJ files use TEI P4 format with:
  - <entryFree key="baba/zw"> tags (not <entry>)
  - Beta code in the key attribute (not Unicode)
  - English translations in <tr> elements
  - Definitions spread across <sense> elements

This script converts beta code → Unicode Greek, then matches
to lemmas already in the database.

Usage:
    python3 fix_lexica.py
═══════════════════════════════════════════════════════════════
"""

import glob
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    from lxml import etree as ET
    USING_LXML = True
except ImportError:
    import xml.etree.ElementTree as ET
    USING_LXML = False

DB_PATH = Path("./greek_vocab.db")
LEXICA_DIR = Path.home() / "greek_data" / "lexica"

if not DB_PATH.exists():
    print("ERROR: greek_vocab.db not found")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# BETA CODE → UNICODE CONVERTER
# Perseus LSJ uses a simplified beta code in the key= attribute.
# Lowercase beta code = lowercase Greek, uppercase (*A) = uppercase.
# ═══════════════════════════════════════════════════════════════

BETA_LOWER = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε",
    "z": "ζ", "h": "η", "q": "θ", "i": "ι", "k": "κ",
    "l": "λ", "m": "μ", "n": "ν", "c": "ξ", "o": "ο",
    "p": "π", "r": "ρ", "s": "σ", "t": "τ", "u": "υ",
    "f": "φ", "x": "χ", "y": "ψ", "w": "ω",
}

BETA_UPPER = {
    "a": "Α", "b": "Β", "g": "Γ", "d": "Δ", "e": "Ε",
    "z": "Ζ", "h": "Η", "q": "Θ", "i": "Ι", "k": "Κ",
    "l": "Λ", "m": "Μ", "n": "Ν", "c": "Ξ", "o": "Ο",
    "p": "Π", "r": "Ρ", "s": "Σ", "t": "Τ", "u": "Υ",
    "f": "Φ", "x": "Χ", "y": "Ψ", "w": "Ω",
}

# Diacritics: these follow the letter in beta code
# We'll strip most diacritics for matching since our lemmas
# may or may not have them consistently.
BETA_DIACRITICS = {
    ")": "\u0313",   # smooth breathing  ᾿
    "(": "\u0314",   # rough breathing   ῾
    "/": "\u0301",   # acute accent      ´
    "\\": "\u0300",  # grave accent      `
    "=": "\u0342",   # circumflex        ῀
    "+": "\u0308",   # diaeresis         ¨
    "|": "\u0345",   # iota subscript    ͅ
}


def beta_to_unicode(beta):
    """Convert Perseus beta code string to Unicode Greek."""
    if not beta:
        return ""

    result = []
    i = 0
    uppercase_next = False

    while i < len(beta):
        ch = beta[i]

        # * means next letter is uppercase
        if ch == "*":
            uppercase_next = True
            i += 1
            continue

        # Check if it's a Greek letter
        if ch.lower() in BETA_LOWER:
            if uppercase_next:
                result.append(BETA_UPPER.get(ch.lower(), ch))
                uppercase_next = False
            else:
                result.append(BETA_LOWER.get(ch, ch))
            i += 1

            # Consume following diacritics
            while i < len(beta) and beta[i] in BETA_DIACRITICS:
                result.append(BETA_DIACRITICS[beta[i]])
                i += 1
            continue

        # Final sigma: s at end of word or before space/punctuation
        # (handled by checking after we build the string)

        # Skip other characters (numbers, punctuation in keys)
        if ch in "0123456789":
            # Some keys have numeric suffixes like "a)gaqo/s1"
            i += 1
            continue

        # Pass through spaces, hyphens, etc.
        result.append(ch)
        i += 1

    # Convert to string
    text = "".join(result)

    # Fix final sigmas: σ at end of word → ς
    import unicodedata
    words = text.split()
    fixed_words = []
    for word in words:
        if word and word[-1] == "σ":
            word = word[:-1] + "ς"
        # Also fix sigma before certain characters
        fixed_words.append(word)

    text = " ".join(fixed_words)

    # Normalize Unicode (combine diacritics with base letters)
    text = unicodedata.normalize("NFC", text)

    return text


def beta_to_unicode_plain(beta):
    """Convert beta code to Unicode Greek, stripping ALL diacritics.
    Used for matching against lemmas that may have inconsistent accents."""
    if not beta:
        return ""

    result = []
    i = 0
    uppercase_next = False

    while i < len(beta):
        ch = beta[i]
        if ch == "*":
            uppercase_next = True
            i += 1
            continue
        if ch.lower() in BETA_LOWER:
            if uppercase_next:
                result.append(BETA_UPPER.get(ch.lower(), ch))
                uppercase_next = False
            else:
                result.append(BETA_LOWER.get(ch, ch))
            i += 1
            # Skip diacritics
            while i < len(beta) and beta[i] in BETA_DIACRITICS:
                i += 1
            continue
        if ch in "0123456789":
            i += 1
            continue
        i += 1

    text = "".join(result)
    words = text.split()
    fixed = []
    for w in words:
        if w and w[-1] == "σ":
            w = w[:-1] + "ς"
        fixed.append(w)
    return " ".join(fixed)


def strip_greek_diacritics(text):
    """Remove accents/breathings from Unicode Greek for fuzzy matching."""
    import unicodedata
    # Decompose, remove combining marks, recompose
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        ch for ch in decomposed
        if unicodedata.category(ch) != "Mn"  # Mn = Mark, Nonspacing
    )
    return stripped.lower()


# ═══════════════════════════════════════════════════════════════
# PARSE LSJ
# ═══════════════════════════════════════════════════════════════

def main():
    print("═══════════════════════════════════════════════════════════")
    print("  LSJ Definition Loader")
    print("═══════════════════════════════════════════════════════════")
    print()

    # Test beta code conversion
    tests = [
        ("lo/gos", "λόγος"),
        ("a)lh/qeia", "ἀλήθεια"),
        ("*pla/twn", "Πλάτων"),
        ("po/lis", "πόλις"),
        ("a)nh/r", "ἀνήρ"),
        ("qu/ra", "θύρα"),
        ("yuxh/", "ψυχή"),
        ("baba/zw", "βαβάζω"),
    ]
    print("  Beta code conversion test:")
    all_pass = True
    for beta, expected in tests:
        got = beta_to_unicode(beta)
        ok = "✓" if got == expected else "✗"
        if got != expected:
            all_pass = False
        print(f"    {ok}  {beta:20s} → {got:15s} (expected {expected})")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-64000")
    cursor = conn.cursor()

    # Build a lookup of all lemmas (plain form → list of ids)
    print("  Building lemma lookup table...")
    cursor.execute("SELECT id, lemma FROM lemmas")
    all_lemmas = cursor.fetchall()

    # Multiple lookup strategies:
    # 1. Exact match on lemma text
    # 2. Match after stripping diacritics
    exact_lookup = {}
    stripped_lookup = {}
    for lid, lemma in all_lemmas:
        exact_lookup.setdefault(lemma, []).append(lid)
        stripped = strip_greek_diacritics(lemma)
        stripped_lookup.setdefault(stripped, []).append(lid)

    print(f"  {len(all_lemmas):,} lemmas loaded, {len(stripped_lookup):,} unique stripped forms")

    # Clear old definitions
    cursor.execute("DELETE FROM definitions")
    cursor.execute("UPDATE lemmas SET short_def = NULL, lsj_def = NULL")
    conn.commit()

    # Find LSJ files
    lsj_files = sorted(glob.glob(
        str(LEXICA_DIR / "CTS_XML_TEI" / "perseus" / "pdllex" / "grc" / "lsj" / "*.xml")
    ))
    print(f"  Found {len(lsj_files)} LSJ files")
    print()

    total_entries = 0
    matched = 0
    unmatched_samples = []

    for fi, fpath in enumerate(lsj_files):
        fname = os.path.basename(fpath)
        t0 = time.time()

        try:
            # Parse with recovery mode for malformed XML
            if USING_LXML:
                parser = ET.XMLParser(recover=True, encoding="utf-8")
                tree = ET.parse(fpath, parser)
            else:
                tree = ET.parse(fpath)
            root = tree.getroot()
        except Exception as e:
            print(f"  ⚠ Error parsing {fname}: {e}")
            continue

        # Find all entryFree elements
        entries = root.findall(".//entryFree")
        file_matched = 0

        for entry in entries:
            total_entries += 1
            key = entry.get("key", "")
            if not key:
                continue

            # Convert beta code key to Unicode
            headword = beta_to_unicode(key)
            headword_stripped = strip_greek_diacritics(headword)

            # Also try the plain (no diacritics) conversion
            headword_plain = beta_to_unicode_plain(key)
            headword_plain_stripped = strip_greek_diacritics(headword_plain)

            # Extract English translations from <tr> elements
            translations = []
            for tr in entry.findall(".//tr"):
                if tr.text and tr.text.strip():
                    translations.append(tr.text.strip())

            # Extract sense text
            senses = []
            for sense in entry.findall(".//sense"):
                # Get just the direct text content, skip nested references
                parts = []
                if sense.text:
                    parts.append(sense.text.strip())
                for child in sense:
                    if child.tag == "tr" and child.text:
                        parts.append(child.text.strip())
                    if child.tail:
                        parts.append(child.tail.strip())
                text = " ".join(parts).strip()
                if text and len(text) > 3:
                    senses.append(text[:500])

            # Build definition
            if translations:
                short_def = ", ".join(translations[:5])
            elif senses:
                short_def = senses[0][:200]
            else:
                # Get all text content
                all_text = "".join(entry.itertext()).strip()
                short_def = all_text[:200] if all_text else ""

            full_def = " | ".join(senses[:10]) if senses else short_def
            if not short_def:
                continue

            # Try to match lemma
            lemma_ids = []

            # Strategy 1: exact match
            if headword in exact_lookup:
                lemma_ids = exact_lookup[headword]
            # Strategy 2: match stripped diacritics
            elif headword_stripped in stripped_lookup:
                lemma_ids = stripped_lookup[headword_stripped]
            # Strategy 3: try plain conversion
            elif headword_plain in exact_lookup:
                lemma_ids = exact_lookup[headword_plain]
            elif headword_plain_stripped in stripped_lookup:
                lemma_ids = stripped_lookup[headword_plain_stripped]

            if lemma_ids:
                for lid in lemma_ids:
                    cursor.execute(
                        """INSERT OR IGNORE INTO definitions
                           (lemma_id, source, entry_key, definition, short_def)
                           VALUES (?,?,?,?,?)""",
                        (lid, "lsj", key, full_def[:5000], short_def[:500]),
                    )
                    cursor.execute(
                        """UPDATE lemmas SET
                           lsj_def = COALESCE(lsj_def, ?),
                           short_def = COALESCE(short_def, ?)
                           WHERE id = ?""",
                        (full_def[:5000], short_def[:500], lid),
                    )
                matched += 1
                file_matched += 1
            else:
                if len(unmatched_samples) < 20:
                    unmatched_samples.append((key, headword, short_def[:60]))

        conn.commit()
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(lsj_files)}] {fname}: "
              f"{len(entries)} entries, {file_matched} matched ({elapsed:.1f}s)")

    # Rebuild FTS index
    print()
    print("  Rebuilding full-text search index...")
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

    # Stats
    cursor.execute("SELECT COUNT(*) FROM definitions")
    def_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM lemmas WHERE short_def IS NOT NULL AND short_def != ''")
    has_def = cursor.fetchone()[0]

    print()
    print("═══════════════════════════════════════════════════════════")
    print(f"  Total LSJ entries found:    {total_entries:,}")
    print(f"  Matched to DB lemmas:       {matched:,}")
    print(f"  Definitions in DB:          {def_count:,}")
    print(f"  Lemmas with definitions:    {has_def:,} / {len(all_lemmas):,}")
    print()

    if unmatched_samples:
        print("  Sample unmatched entries (for debugging):")
        for key, hw, sdef in unmatched_samples[:10]:
            print(f"    key={key:25s}  →  {hw:20s}  def: {sdef}")
        print()

    # Show sample matched definitions
    cursor.execute("""
        SELECT l.lemma, l.short_def
        FROM lemmas l
        WHERE l.short_def IS NOT NULL AND l.short_def != ''
        ORDER BY l.frequency_rank
        LIMIT 15
    """)
    rows = cursor.fetchall()
    if rows:
        print("  Top lemmas with definitions:")
        for lemma, sdef in rows:
            print(f"    {lemma:20s}  {sdef[:70]}")

    conn.execute("PRAGMA optimize")
    conn.close()
    print()
    print("  ✓ Done!")
    print("═══════════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()