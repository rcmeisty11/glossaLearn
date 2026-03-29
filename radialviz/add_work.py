#!/usr/bin/env python3
"""
add_work.py — Add a single new work to an existing greek_vocab.db

Usage:
    python3 add_work.py --author "Apostolic Fathers" --title "Didache"

This script:
  1. Finds the lemmatized XML for the work in ~/greek_data
  2. Parses tokens, lemmas, forms, occurrences
  3. Inserts into the existing database (no rebuild needed)
  4. Updates work_lemma_counts and lemma frequency totals
"""

import argparse
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from lxml import etree as ET
    print("Using lxml (fast mode)")
except ImportError:
    import xml.etree.ElementTree as ET
    print("Using stdlib xml.etree (slower)")

DATA_DIR = Path.home() / "greek_data"
DB_PATH = Path("./greek_vocab.db")

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
    if not tag or len(tag) < 9:
        return {}
    result = {}
    positions = ["pos", "person", "number", "tense", "mood", "voice", "gender", "case", "degree"]
    for i, name in enumerate(positions):
        if i < len(tag) and tag[i] != "-":
            result[name] = MORPH_VALUES.get(name, {}).get(tag[i], "")
    return result


def find_lemmatized_file(tlg_author, tlg_work):
    """Find the lemmatized XML file for a given TLG code."""
    pattern = f"{tlg_author}.{tlg_work}.*"
    lem_dir = DATA_DIR / "LemmatizedAncientGreekXML" / "texts"
    matches = list(lem_dir.glob(pattern))
    if matches:
        return matches[0]
    return None


def main():
    parser = argparse.ArgumentParser(description="Add a single work to greek_vocab.db")
    parser.add_argument("--tlg-author", required=True, help="TLG author code (e.g. tlg1311)")
    parser.add_argument("--tlg-work", required=True, help="TLG work code (e.g. tlg001)")
    parser.add_argument("--author", required=True, help="Author name (e.g. 'Apostolic Fathers')")
    parser.add_argument("--title", required=True, help="Work title (e.g. 'Didache')")
    parser.add_argument("--corpus", default="First1KGreek", help="Corpus name")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to database")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying DB")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    # Find the lemmatized XML
    lem_file = find_lemmatized_file(args.tlg_author, args.tlg_work)
    if not lem_file:
        print(f"ERROR: No lemmatized XML found for {args.tlg_author}.{args.tlg_work}")
        print(f"  Looked in: {DATA_DIR / 'LemmatizedAncientGreekXML' / 'texts'}")
        sys.exit(1)

    print(f"Found: {lem_file}")
    print(f"  Author: {args.author}")
    print(f"  Title:  {args.title}")
    print(f"  Corpus: {args.corpus}")

    if args.dry_run:
        print("\n[DRY RUN] Would parse and insert this work. Exiting.")
        sys.exit(0)

    # Connect to DB
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    # Check if work already exists
    filename = lem_file.name
    cts_urn = filename.replace(".xml", "")
    cursor.execute("SELECT id FROM works WHERE filename = ?", (filename,))
    existing = cursor.fetchone()
    if existing:
        print(f"\nWARNING: Work already exists with id={existing[0]}. Skipping.")
        conn.close()
        sys.exit(0)

    # Insert work
    cursor.execute(
        """INSERT INTO works (filename, cts_urn, author_code, work_code, author, title, corpus)
           VALUES (?,?,?,?,?,?,?)""",
        (filename, cts_urn, args.tlg_author, args.tlg_work, args.author, args.title, args.corpus),
    )
    work_id = cursor.lastrowid
    print(f"\nCreated work id={work_id}")

    # Build lemma/form caches from existing data
    print("Loading existing lemma cache...")
    lemma_cache = {}
    for row in cursor.execute("SELECT id, lemma, pos FROM lemmas"):
        lemma_cache[(row[1], row[2])] = row[0]
    print(f"  {len(lemma_cache)} lemmas in cache")

    form_cache = {}  # (lemma_id, word_form, morph_tag) → form_id

    # Parse the lemmatized XML
    print(f"Parsing {lem_file.name}...")
    t0 = time.time()

    tree = ET.parse(str(lem_file))
    root = tree.getroot()

    token_count = 0
    new_lemmas = 0
    new_forms = 0
    batch_occurrences = []
    batch_wlc = defaultdict(int)

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

            if morph_tag and len(morph_tag) >= 1 and morph_tag[0] == "u":
                continue

            lemma_el = token.find("l")
            lemma_text = None
            lemma_tag = morph_tag

            if lemma_el is not None:
                l1 = lemma_el.find("l1")
                if l1 is not None and l1.text:
                    lemma_text = l1.text.strip()
                    lemma_tag = l1.get("o", morph_tag)
                else:
                    l2 = lemma_el.find("l2")
                    if l2 is not None and l2.text:
                        lemma_text = l2.text.strip()

            if not lemma_text:
                continue

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
                        new_lemmas += 1
                    else:
                        cursor.execute("SELECT id FROM lemmas WHERE lemma=? AND pos=?", (lemma_text, pos))
                        row = cursor.fetchone()
                        lemma_cache[lemma_key] = row[0] if row else None
                except sqlite3.IntegrityError:
                    cursor.execute("SELECT id FROM lemmas WHERE lemma=? AND pos=?", (lemma_text, pos))
                    row = cursor.fetchone()
                    lemma_cache[lemma_key] = row[0] if row else None

            lemma_id = lemma_cache.get(lemma_key)
            if lemma_id is None:
                continue

            # Insert form
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
                    if cursor.rowcount > 0:
                        form_cache[form_key] = cursor.lastrowid
                        new_forms += 1
                    else:
                        row = cursor.execute(
                            "SELECT id FROM forms WHERE lemma_id=? AND form=? AND morph_tag=?",
                            (lemma_id, word_form, morph_tag),
                        ).fetchone()
                        form_cache[form_key] = row[0] if row else None
                except sqlite3.IntegrityError:
                    row = cursor.execute(
                        "SELECT id FROM forms WHERE lemma_id=? AND form=? AND morph_tag=?",
                        (lemma_id, word_form, morph_tag),
                    ).fetchone()
                    form_cache[form_key] = row[0] if row else None

            form_id = form_cache.get(form_key)

            # Queue occurrence
            batch_occurrences.append((
                lemma_id, form_id, work_id, passage,
                int(sent_n) if sent_n.isdigit() else None,
                int(token_n) if token_n and token_n.isdigit() else None,
            ))

            batch_wlc[(work_id, lemma_id)] += 1
            token_count += 1

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

    # Update total occurrence counts on lemmas
    print("Updating lemma occurrence counts...")
    cursor.execute("""
        UPDATE lemmas SET total_occurrences = (
            SELECT COALESCE(SUM(count), 0) FROM work_lemma_counts WHERE lemma_id = lemmas.id
        ) WHERE id IN (SELECT DISTINCT lemma_id FROM work_lemma_counts WHERE work_id = ?)
    """, (work_id,))

    conn.commit()

    # ── Build sentences and sentence_lemmas ──────────────────
    print("Building sentences...")
    tree2 = ET.parse(str(lem_file))
    root2 = tree2.getroot()

    sent_count = 0
    sent_link_count = 0

    for s_elem in root2.iter("s"):
        sentence_pos = int(s_elem.get("n", 0)) if s_elem.get("n", "").isdigit() else 0
        tokens = []
        lemma_ids = set()
        passage = None

        for t_elem in s_elem.iter("t"):
            if passage is None:
                passage = t_elem.get("p", "")

            f_elem = t_elem.find("f")
            if f_elem is None or f_elem.text is None:
                continue

            form_text = f_elem.text.strip()
            join = t_elem.get("join", "")

            if join == "b" and tokens:
                tokens[-1] = tokens[-1] + form_text
            elif join == "a":
                tokens.append(form_text)
            else:
                tokens.append(form_text)

            # Resolve lemma
            l_elem = t_elem.find("l")
            if l_elem is not None:
                lemma_text = None
                l1 = l_elem.find("l1")
                if l1 is not None and l1.text:
                    lemma_text = l1.text.strip()
                else:
                    l2 = l_elem.find("l2")
                    if l2 is not None and l2.text:
                        lemma_text = l2.text.strip()

                if lemma_text:
                    # Try all POS variants in cache
                    for pos_val in MORPH_VALUES["pos"].values():
                        lid = lemma_cache.get((lemma_text, pos_val))
                        if lid:
                            lemma_ids.add(lid)
                            break
                    else:
                        # Try empty POS
                        lid = lemma_cache.get((lemma_text, ""))
                        if lid:
                            lemma_ids.add(lid)

        if tokens:
            sentence_text = " ".join(tokens)
            for p in [" ,", " .", " ;", " :", " ·", " ;"]:
                sentence_text = sentence_text.replace(p, p.strip())

            cur2 = cursor.execute(
                "INSERT INTO sentences (work_id, passage, sentence_pos, sentence_text) VALUES (?,?,?,?)",
                (work_id, passage, sentence_pos, sentence_text),
            )
            sid = cur2.lastrowid
            if lemma_ids:
                cursor.executemany(
                    "INSERT OR IGNORE INTO sentence_lemmas (sentence_id, lemma_id) VALUES (?,?)",
                    [(sid, lid) for lid in lemma_ids],
                )
                sent_link_count += len(lemma_ids)
            sent_count += 1

    conn.commit()
    elapsed = time.time() - t0

    print(f"\nDone in {elapsed:.1f}s:")
    print(f"  Tokens processed:   {token_count}")
    print(f"  New lemmas:         {new_lemmas}")
    print(f"  New forms:          {new_forms}")
    print(f"  Work-lemma pairs:   {len(batch_wlc)}")
    print(f"  Sentences:          {sent_count}")
    print(f"  Sentence-lemma links: {sent_link_count}")

    conn.close()


if __name__ == "__main__":
    main()
