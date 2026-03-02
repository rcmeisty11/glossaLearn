#!/usr/bin/env python3
"""
improve_families.py
═══════════════════════════════════════════════════════════════
Uses Perseus Morpheus stem data to improve derivational families
in the glossalearn database.

Morpheus provides linguistically accurate decompositions of Greek
compound words into prefix + base verb/noun, which replaces the
approximate string-stemming approach in build_database.py.

Data source:
    https://github.com/PerseusDL/morpheus/tree/master/stemlib/Greek

Usage:
    python3 improve_families.py                  # dry run (preview changes)
    python3 improve_families.py --apply          # apply changes to database
    python3 improve_families.py --apply --reset  # wipe existing families first

Requirements:
    - greek_vocab.db must exist (run build_database.py first)
    - Internet connection to download Morpheus data (cached after first run)
═══════════════════════════════════════════════════════════════
"""

import argparse
import os
import re
import sqlite3
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
CACHE_DIR = Path("./morpheus_cache")

# ═══════════════════════════════════════════════════════════════
# MORPHEUS DATA URLS
# ═══════════════════════════════════════════════════════════════

BASE_URL = "https://raw.githubusercontent.com/PerseusDL/morpheus/b1b33c56ef2338fe0dcd1893628ed638f00c0986/stemlib/Greek/stemsrc"

# Compound verb files — map compound verbs to prefix + base verb
COMPOUND_FILES = [
    "vbs.cmp.lsj",   # format: compound_beta  prefix/-base_beta
    "vbs.cmp.ml",     # format: prefix/-base_beta  compound_beta
]

# Simple verb files — contain :le: (lemma) and :de: (stem + class) entries
SIMPLE_VERB_FILES = [
    "vbs.simp.ml",
    "vbs.simp.02.new",
]

# Nominal stem files — contain :le: (lemma) and stem entries with prefix info
NOMINAL_FILES = [
    "nom01", "nom02", "nom03", "nom04", "nom05", "nom06", "nom07",
    "nom.irreg", "nom.comp",
]


# ═══════════════════════════════════════════════════════════════
# BETA CODE → UNICODE CONVERSION
# ═══════════════════════════════════════════════════════════════

# Beta code base letters → Unicode
BETA_LOWER = {
    'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε',
    'z': 'ζ', 'h': 'η', 'q': 'θ', 'i': 'ι', 'k': 'κ',
    'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο',
    'p': 'π', 'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ',
    'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω',
}

BETA_UPPER = {
    'A': 'Α', 'B': 'Β', 'G': 'Γ', 'D': 'Δ', 'E': 'Ε',
    'Z': 'Ζ', 'H': 'Η', 'Q': 'Θ', 'I': 'Ι', 'K': 'Κ',
    'L': 'Λ', 'M': 'Μ', 'N': 'Ν', 'C': 'Ξ', 'O': 'Ο',
    'P': 'Π', 'R': 'Ρ', 'S': 'Σ', 'T': 'Τ', 'U': 'Υ',
    'F': 'Φ', 'X': 'Χ', 'Y': 'Ψ', 'W': 'Ω',
}

# Unicode combining diacriticals
SMOOTH   = '\u0313'  # ̓  psili (smooth breathing)
ROUGH    = '\u0314'  # ̔  dasia (rough breathing)
ACUTE    = '\u0301'  # ́  oxia
GRAVE    = '\u0300'  # ̀  varia
CIRCUM   = '\u0342'  # ͂  perispomeni
IOTASUB  = '\u0345'  # ͅ  ypogegrammeni
DIAER    = '\u0308'  # ̈  dialytika


def beta_to_unicode(beta):
    """Convert Perseus Beta Code to Unicode Greek.

    Perseus Beta Code conventions:
        Letters: a=α, b=β, g=γ, etc. *A=Α (capital)
        Breathing: )=smooth, (=rough
        Accents: /=acute, \\=grave, ==circumflex
        Iota subscript: |
        Diaeresis: +
        Final sigma: s at end of word or before space/punctuation

    The tricky part: in Perseus beta code, diacriticals come BEFORE the letter
    for lowercase (e.g. a)/nqrwpos) but AFTER for capitals (*)/a).
    """
    if not beta:
        return ""

    result = []
    i = 0
    n = len(beta)

    while i < n:
        ch = beta[i]

        # Capital letter marker
        if ch == '*':
            # Collect diacriticals that may appear before the capital letter
            i += 1
            caps_diacrit = []
            while i < n and beta[i] in '()/\\=|+':
                caps_diacrit.append(beta[i])
                i += 1
            if i < n and beta[i].upper() in BETA_UPPER:
                letter = BETA_UPPER.get(beta[i].upper(), beta[i])
                i += 1
                # Collect any diacriticals after the letter too
                while i < n and beta[i] in '()/\\=|+':
                    caps_diacrit.append(beta[i])
                    i += 1
                result.append(letter + _diacrit_str(caps_diacrit))
            continue

        # Diacriticals before a lowercase letter
        if ch in '()/\\=|+':
            diacrit = []
            while i < n and beta[i] in '()/\\=|+':
                diacrit.append(beta[i])
                i += 1
            if i < n and beta[i].lower() in BETA_LOWER:
                letter = BETA_LOWER[beta[i].lower()]
                i += 1
                # Collect any trailing diacriticals
                while i < n and beta[i] in '()/\\=|+':
                    diacrit.append(beta[i])
                    i += 1
                result.append(letter + _diacrit_str(diacrit))
            else:
                # Stray diacritical with no letter — skip
                pass
            continue

        # Regular lowercase letter
        if ch.lower() in BETA_LOWER:
            letter = BETA_LOWER[ch.lower()]
            i += 1
            # Collect any trailing diacriticals
            diacrit = []
            while i < n and beta[i] in '()/\\=|+':
                diacrit.append(beta[i])
                i += 1
            result.append(letter + _diacrit_str(diacrit))
            continue

        # Anything else (numbers, spaces, punctuation) — pass through
        result.append(ch)
        i += 1

    text = "".join(result)

    # Fix final sigma: σ at end of word → ς
    text = re.sub(r'σ(?=\s|$|[,.:;·])', 'ς', text)
    # Also fix sigma before a non-Greek char at end
    text = re.sub(r'σ$', 'ς', text)

    import unicodedata
    return unicodedata.normalize("NFC", text)


def _diacrit_str(diacrit_chars):
    """Convert beta code diacritical markers to Unicode combining characters."""
    out = ""
    for d in diacrit_chars:
        if d == ')':
            out += SMOOTH
        elif d == '(':
            out += ROUGH
        elif d == '/':
            out += ACUTE
        elif d == '\\':
            out += GRAVE
        elif d == '=':
            out += CIRCUM
        elif d == '|':
            out += IOTASUB
        elif d == '+':
            out += DIAER
    return out


def normalize_lemma(text):
    """Normalize a Greek lemma for matching: NFC, strip trailing digits, lowercase."""
    import unicodedata
    text = unicodedata.normalize("NFC", text.strip())
    # Strip trailing digit suffixes (e.g. ba/llw1 → ba/llw)
    text = re.sub(r'\d+$', '', text)
    return text


# ═══════════════════════════════════════════════════════════════
# DOWNLOAD & CACHE MORPHEUS FILES
# ═══════════════════════════════════════════════════════════════

def download_file(filename):
    """Download a Morpheus file, caching locally."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = CACHE_DIR / filename

    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    url = f"{BASE_URL}/{filename}"
    print(f"  Downloading {filename}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "glossalearn/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = resp.read().decode("utf-8")
        cache_path.write_text(data, encoding="utf-8")
        return data
    except Exception as e:
        print(f"    WARNING: Failed to download {filename}: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# PARSE MORPHEUS DATA
# ═══════════════════════════════════════════════════════════════

def parse_compound_verbs_lsj(text):
    """Parse vbs.cmp.lsj: compound_beta prefix/-base_beta

    Returns list of (compound_unicode, base_unicode, prefix_unicode).
    """
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue

        compound_beta = parts[0]
        decomp = parts[1]

        # Parse prefix/-base  or  prefix/-base2
        # Can also be prefix1,prefix2/-base (double prefix)
        if '/-' in decomp:
            prefix_part, base_part = decomp.split('/-', 1)
        elif '-' in decomp:
            prefix_part, base_part = decomp.split('-', 1)
        else:
            continue

        compound = normalize_lemma(beta_to_unicode(compound_beta))
        base = normalize_lemma(beta_to_unicode(base_part))
        prefix = beta_to_unicode(prefix_part.replace(',', '+'))

        if compound and base:
            results.append((compound, base, prefix))

    return results


def parse_compound_verbs_ml(text):
    """Parse vbs.cmp.ml: prefix/-base_beta compound_beta

    Returns list of (compound_unicode, base_unicode, prefix_unicode).
    """
    results = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue

        decomp = parts[0]
        compound_beta = parts[1]

        if '/-' in decomp:
            prefix_part, base_part = decomp.split('/-', 1)
        elif '-' in decomp:
            prefix_part, base_part = decomp.split('-', 1)
        else:
            continue

        compound = normalize_lemma(beta_to_unicode(compound_beta))
        base = normalize_lemma(beta_to_unicode(base_part))
        prefix = beta_to_unicode(prefix_part.replace(',', '+'))

        if compound and base:
            results.append((compound, base, prefix))

    return results


def parse_simple_verbs(text):
    """Parse simple verb files for lemma → stem mappings.

    Returns dict of { lemma_unicode: stem_unicode }.
    """
    results = {}
    current_lemma = None

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('@') or line.startswith(';'):
            continue

        if line.startswith(':le:'):
            beta = line[4:].strip()
            current_lemma = normalize_lemma(beta_to_unicode(beta))
        elif line.startswith(':de:') and current_lemma:
            # :de:stem_beta class_info...
            parts = line[4:].strip().split(None, 1)
            if parts:
                stem = normalize_lemma(beta_to_unicode(parts[0]))
                if stem and current_lemma:
                    results[current_lemma] = stem

    return results

def parse_nominal_stems(text):
    """Parse nominal stem files for lemma → stem + prefix info.

    Returns list of (lemma_unicode, stem_unicode, prefix_or_none).
    The stem entries use 'a)-' notation for α-privative prefix, etc.
    """
    results = []
    current_lemma = None

    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('@') or line.startswith(';'):
            continue

        if line.startswith(':le:'):
            beta = line[4:].strip()
            current_lemma = normalize_lemma(beta_to_unicode(beta))
        elif current_lemma and (line.startswith(':no:') or line.startswith(':aj:') or line.startswith(':wd:')):
            # :no:stem_beta class_info...  or  :aj:stem_beta class_info...
            tag = line[:4]
            rest = line[4:].strip().split(None, 1)
            if rest:
                stem_beta = rest[0]
                # Check for prefix marker: a)- means α-privative
                prefix = None
                if '-' in stem_beta:
                    pfx_part, stem_part = stem_beta.split('-', 1)
                    pfx_unicode = beta_to_unicode(pfx_part)
                    stem_unicode = beta_to_unicode(stem_part)
                    if pfx_unicode:
                        prefix = pfx_unicode
                        results.append((current_lemma, stem_unicode, prefix))
                        continue
                stem_unicode = normalize_lemma(beta_to_unicode(stem_beta))
                if stem_unicode:
                    results.append((current_lemma, stem_unicode, None))

    return results

# ═══════════════════════════════════════════════════════════════
# DATABASE MATCHING & UPDATE
# ═══════════════════════════════════════════════════════════════

def build_lemma_index(conn):
    """Build lookup indexes for matching Morpheus data to our lemmas.

    Returns:
        by_exact: { lemma_text: [(id, pos, total_occ), ...] }
        by_stripped: { stripped_lemma: [(id, lemma, pos, total_occ), ...] }
    """
    import unicodedata
    cursor = conn.execute("SELECT id, lemma, pos, total_occurrences FROM lemmas")
    by_exact = defaultdict(list)
    by_stripped = defaultdict(list)

    for lid, lemma, pos, occ in cursor:
        nfc = unicodedata.normalize("NFC", lemma)
        by_exact[nfc].append((lid, pos, occ or 0))
        # Also index without accents for fuzzy matching
        stripped = strip_accents(nfc)
        by_stripped[stripped].append((lid, nfc, pos, occ or 0))

    return by_exact, by_stripped


def strip_accents(text):
    """Remove accents and breathing marks, keeping base Greek letters."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", text)
    # Keep only base letters (category L) and combining iota subscript
    out = []
    for ch in nfd:
        cat = unicodedata.category(ch)
        if cat.startswith('L'):
            out.append(ch)
        elif ch == IOTASUB:
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def find_lemma(text, by_exact, by_stripped):
    """Find the best matching lemma ID for a Greek word.

    Tries exact match first, then accent-stripped match.
    If multiple matches, prefer the one with highest occurrences.
    """
    import unicodedata
    text = unicodedata.normalize("NFC", text.strip())

    # Exact match
    if text in by_exact:
        matches = by_exact[text]
        if matches:
            return max(matches, key=lambda x: x[2])[0]  # highest occ

    # Try without accents
    stripped = strip_accents(text)
    if stripped in by_stripped:
        candidates = by_stripped[stripped]
        if candidates:
            return max(candidates, key=lambda x: x[3])[0]  # highest occ

    return None

def improve_families(conn, dry_run=True, reset=False):
    """Main logic: parse Morpheus data and improve derivational families."""
    cursor = conn.cursor()

    print("\n═══ Morpheus Family Improvement ═══\n")

    # ── Step 1: Download and parse Morpheus data ──
    print("Step 1: Downloading Morpheus data...\n")

    # Compound verbs
    compound_pairs = []
    for f in COMPOUND_FILES:
        text = download_file(f)
        if not text:
            continue
        if f.endswith("lsj"):
            pairs = parse_compound_verbs_lsj(text)
        else:
            pairs = parse_compound_verbs_ml(text)
        compound_pairs.extend(pairs)
        print(f"  {f}: {len(pairs)} compound decompositions")

    # Deduplicate compound pairs (same compound may appear in both files)
    seen = set()
    unique_compounds = []
    for compound, base, prefix in compound_pairs:
        key = (compound, base)
        if key not in seen:
            seen.add(key)
            unique_compounds.append((compound, base, prefix))
    print(f"  Total unique compound pairs: {len(unique_compounds)}")

    # Simple verb stems
    verb_stems = {}
    for f in SIMPLE_VERB_FILES:
        text = download_file(f)
        if text:
            stems = parse_simple_verbs(text)
            verb_stems.update(stems)
            print(f"  {f}: {len(stems)} verb stems")
    print(f"  Total verb stems: {len(verb_stems)}")

    # Nominal stems
    nominal_data = []
    for f in NOMINAL_FILES:
        text = download_file(f)
        if text:
            noms = parse_nominal_stems(text)
            nominal_data.extend(noms)
            print(f"  {f}: {len(noms)} nominal entries")
    print(f"  Total nominal entries: {len(nominal_data)}")

    # ── Step 2: Build lemma index ──
    print("\nStep 2: Building lemma index...")
    by_exact, by_stripped = build_lemma_index(conn)
    print(f"  {len(by_exact)} unique lemma forms indexed")

    # ── Step 3: Match compounds to database ──
    print("\nStep 3: Matching compound verbs to database...")

    # compound_lemma_id → (base_lemma_id, prefix_text)
    parent_links = {}
    matched = 0
    unmatched_compounds = []

    for compound, base, prefix in unique_compounds:
        compound_id = find_lemma(compound, by_exact, by_stripped)
        base_id = find_lemma(base, by_exact, by_stripped)

        if compound_id and base_id and compound_id != base_id:
            parent_links[compound_id] = (base_id, prefix, "compound")
            matched += 1
        elif compound_id and not base_id:
            unmatched_compounds.append((compound, base, prefix))

    print(f"  Matched: {matched} compound → base verb links")
    print(f"  Unmatched (base not in DB): {len(unmatched_compounds)}")

    # ── Step 4: Match nominal prefix derivations ──
    print("\nStep 4: Matching nominal derivations...")

    # Group nominals by stem to find shared-stem families
    stem_to_lemmas = defaultdict(list)
    nom_matched = 0

    for lemma_text, stem, prefix in nominal_data:
        lemma_id = find_lemma(lemma_text, by_exact, by_stripped)
        if lemma_id and prefix:
            # This nominal has a known prefix — find the base stem
            # Try to find a lemma matching just the stem
            base_id = find_lemma(stem, by_exact, by_stripped)
            if base_id and base_id != lemma_id:
                if lemma_id not in parent_links:
                    parent_links[lemma_id] = (base_id, prefix + "-", "prefix")
                    nom_matched += 1
        if lemma_id and stem:
            stripped_stem = strip_accents(stem) if stem else None
            if stripped_stem and len(stripped_stem) >= 3:
                stem_to_lemmas[stripped_stem].append((lemma_id, lemma_text, prefix))

    print(f"  Prefix-based nominal links: {nom_matched}")

    # ── Step 5: Build family groups from shared stems ──
    print("\nStep 5: Building stem-based family groups...")

    # Also group verb stems
    for lemma_text, stem in verb_stems.items():
        lemma_id = find_lemma(lemma_text, by_exact, by_stripped)
        if lemma_id and stem:
            stripped_stem = strip_accents(stem) if stem else None
            if stripped_stem and len(stripped_stem) >= 3:
                stem_to_lemmas[stripped_stem].append((lemma_id, lemma_text, None))

    # Filter to groups with 2+ members
    stem_families = {stem: members for stem, members in stem_to_lemmas.items()
                     if len(members) >= 2}
    print(f"  Stem groups with 2+ members: {len(stem_families)}")

    # ── Step 6: Apply changes ──
    print(f"\nStep 6: {'APPLYING' if not dry_run else 'PREVIEWING'} changes...")

    if reset and not dry_run:
        print("  Resetting existing families...")
        cursor.execute("DELETE FROM lemma_families")
        cursor.execute("DELETE FROM derivational_families")
        conn.commit()

    # Get existing families and memberships
    existing_families = {}  # lemma_id → family_id
    for row in cursor.execute("SELECT lemma_id, family_id FROM lemma_families"):
        existing_families[row[0]] = row[1]

    # Get existing family roots
    family_roots = {}  # family_id → root
    for row in cursor.execute("SELECT id, root FROM derivational_families"):
        family_roots[row[0]] = row[1]

    # Stats
    stats = {
        "families_created": 0,
        "members_added": 0,
        "parents_set": 0,
        "families_merged": 0,
    }

    # 6a: Create/update families from stem groups
    for stem, members in stem_families.items():
        # Deduplicate by lemma_id
        seen_ids = set()
        unique_members = []
        for lid, lemma_text, prefix in members:
            if lid not in seen_ids:
                seen_ids.add(lid)
                unique_members.append((lid, lemma_text, prefix))

        if len(unique_members) < 2:
            continue

        # Check if any members already have a family
        existing_fids = set()
        for lid, _, _ in unique_members:
            if lid in existing_families:
                existing_fids.add(existing_families[lid])

        if existing_fids:
            # Use the existing family with most members
            family_id = min(existing_fids)  # pick one consistently
        else:
            # Create new family
            if not dry_run:
                cursor.execute(
                    "INSERT INTO derivational_families (root, label) VALUES (?, ?)",
                    (stem, f"Root: {stem}-"),
                )
                family_id = cursor.lastrowid
            else:
                family_id = -1
            stats["families_created"] += 1

        # Add members that aren't already in a family
        for lid, lemma_text, prefix in unique_members:
            if lid not in existing_families:
                relation = f"prefix {prefix}" if prefix else "derived"
                if not dry_run:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation) VALUES (?, ?, ?)",
                            (lid, family_id, relation),
                        )
                        existing_families[lid] = family_id
                    except sqlite3.IntegrityError:
                        pass
                stats["members_added"] += 1

    # 6b: Set parent_lemma_id for compound/prefix words
    for child_id, (parent_id, prefix, rel_type) in parent_links.items():
        # Both child and parent need to be in the same family
        child_fid = existing_families.get(child_id)
        parent_fid = existing_families.get(parent_id)

        if child_fid and parent_fid and child_fid == parent_fid:
            # Same family — just set the parent link
            if not dry_run:
                cursor.execute(
                    "UPDATE lemma_families SET parent_lemma_id = ?, relation = ? WHERE lemma_id = ? AND family_id = ?",
                    (parent_id, f"{rel_type} ({prefix})" if prefix else rel_type, child_id, child_fid),
                )
            stats["parents_set"] += 1
        elif child_fid and parent_fid and child_fid != parent_fid:
            # Different families — merge them
            keep_fid = min(child_fid, parent_fid)
            merge_fid = max(child_fid, parent_fid)
            if not dry_run:
                cursor.execute(
                    "UPDATE lemma_families SET family_id = ? WHERE family_id = ?",
                    (keep_fid, merge_fid),
                )
                cursor.execute("DELETE FROM derivational_families WHERE id = ?", (merge_fid,))
                # Update our tracking
                for lid, fid in list(existing_families.items()):
                    if fid == merge_fid:
                        existing_families[lid] = keep_fid
                # Set parent link
                cursor.execute(
                    "UPDATE lemma_families SET parent_lemma_id = ?, relation = ? WHERE lemma_id = ? AND family_id = ?",
                    (parent_id, f"{rel_type} ({prefix})" if prefix else rel_type, child_id, keep_fid),
                )
            stats["families_merged"] += 1
            stats["parents_set"] += 1
        elif child_fid and not parent_fid:
            # Parent has no family — add it to the child's family
            if not dry_run:
                try:
                    cursor.execute(
                        "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation) VALUES (?, ?, ?)",
                        (parent_id, child_fid, "root"),
                    )
                    existing_families[parent_id] = child_fid
                    cursor.execute(
                        "UPDATE lemma_families SET parent_lemma_id = ?, relation = ? WHERE lemma_id = ? AND family_id = ?",
                        (parent_id, f"{rel_type} ({prefix})" if prefix else rel_type, child_id, child_fid),
                    )
                except sqlite3.IntegrityError:
                    pass
            stats["parents_set"] += 1
            stats["members_added"] += 1

    if not dry_run:
        conn.commit()

    # ── Summary ──
    print(f"\n{'═' * 50}")
    print(f"  Families created:     {stats['families_created']:>6}")
    print(f"  Members added:        {stats['members_added']:>6}")
    print(f"  Parent links set:     {stats['parents_set']:>6}")
    print(f"  Families merged:      {stats['families_merged']:>6}")
    print(f"{'═' * 50}")

    if dry_run:
        print("\n  DRY RUN — no changes written. Use --apply to write changes.")
    else:
        # Print final stats
        fam_count = cursor.execute("SELECT COUNT(*) FROM derivational_families").fetchone()[0]
        mem_count = cursor.execute("SELECT COUNT(*) FROM lemma_families").fetchone()[0]
        parent_count = cursor.execute("SELECT COUNT(*) FROM lemma_families WHERE parent_lemma_id IS NOT NULL").fetchone()[0]
        print(f"\n  Database now has:")
        print(f"    {fam_count:,} derivational families")
        print(f"    {mem_count:,} family memberships")
        print(f"    {parent_count:,} parent-child links")

    # Show some example improvements
    print("\n── Sample compound verb links ──")
    shown = 0
    for child_id, (parent_id, prefix, rel_type) in list(parent_links.items()):
        if shown >= 10:
            break
        child_name = cursor.execute("SELECT lemma FROM lemmas WHERE id = ?", (child_id,)).fetchone()
        parent_name = cursor.execute("SELECT lemma FROM lemmas WHERE id = ?", (parent_id,)).fetchone()
        if child_name and parent_name:
            print(f"    {child_name[0]}  ←  {prefix} + {parent_name[0]}")
            shown += 1


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Improve derivational families using Morpheus stem data"
    )
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes to database (default: dry run)")
    parser.add_argument("--reset", action="store_true",
                        help="Wipe existing families before rebuilding (use with --apply)")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run build_database.py first.")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-32000")

    # Ensure parent_lemma_id column exists
    try:
        conn.execute("ALTER TABLE lemma_families ADD COLUMN parent_lemma_id INTEGER")
        conn.commit()
        print("Added parent_lemma_id column to lemma_families")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        improve_families(conn, dry_run=not args.apply, reset=args.reset)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
