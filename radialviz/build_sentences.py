#!/usr/bin/env python3
"""
build_sentences.py
Parse the LemmatizedAncientGreekXML files and populate a sentences table
in greek_vocab.db, linked to works and lemmas.
"""

import os
import sys
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(os.environ.get("DB_PATH", "./greek_vocab.db"))
XML_DIR = Path(os.path.expanduser("~/greek_data/LemmatizedAncientGreekXML/texts"))

def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db

def create_tables(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_id INTEGER NOT NULL REFERENCES works(id),
            passage TEXT,
            sentence_pos INTEGER,
            sentence_text TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sentence_lemmas (
            sentence_id INTEGER NOT NULL REFERENCES sentences(id),
            lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
            PRIMARY KEY (sentence_id, lemma_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_sentence_lemmas_lemma ON sentence_lemmas(lemma_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sentences_work ON sentences(work_id)")
    db.commit()

def build_lemma_lookup(db):
    """Build a mapping from lemma text -> list of (lemma_id, set of work_ids)."""
    print("Building lemma lookup table...")

    # Step 1: lemma text -> list of lemma IDs
    lemma_rows = db.execute("SELECT id, lemma FROM lemmas").fetchall()
    lookup = defaultdict(list)
    id_to_idx = {}
    for r in lemma_rows:
        idx = len(lookup[r["lemma"]])
        lookup[r["lemma"]].append((r["id"], set()))
        id_to_idx[r["id"]] = (r["lemma"], idx)

    print(f"  {len(lookup)} unique lemma texts, {len(lemma_rows)} total lemmas")

    # Step 2: attach work_ids from work_lemma_counts (much smaller than occurrences)
    print("  Loading work-lemma counts for disambiguation...")
    wlc_rows = db.execute("SELECT work_id, lemma_id FROM work_lemma_counts").fetchall()
    for r in wlc_rows:
        key = id_to_idx.get(r["lemma_id"])
        if key:
            lemma_text, idx = key
            lookup[lemma_text][idx][1].add(r["work_id"])

    print(f"  Done ({len(wlc_rows)} work-lemma links loaded)")
    return lookup

def resolve_lemma_id(lemma_text, work_id, lemma_lookup):
    """Given a lemma text and work_id, find the best matching lemma_id."""
    candidates = lemma_lookup.get(lemma_text, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    # Prefer the candidate that has occurrences in this work
    for lid, wids in candidates:
        if work_id in wids:
            return lid
    # Fall back to the one with most work coverage
    return max(candidates, key=lambda c: len(c[1]))[0]

def parse_xml_file(xml_path, work_id, lemma_lookup):
    """Parse a lemmatized XML file and return list of (passage, sentence_pos, text, lemma_ids)."""
    sentences = []
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError as e:
        print(f"  XML parse error: {e}")
        return sentences

    root = tree.getroot()

    for s_elem in root.iter("s"):
        sentence_pos = int(s_elem.get("n", 0))
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

            # Handle join attribute for punctuation
            if join == "b" and tokens:
                # Join back (no space before this token)
                tokens[-1] = tokens[-1] + form_text
            elif join == "a":
                # Join after (no space after this token)
                tokens.append(form_text)
            else:
                tokens.append(form_text)

            # Extract lemma text
            l_elem = t_elem.find("l")
            if l_elem is not None:
                # Try l1 first, then l2
                lemma_text = None
                l1 = l_elem.find("l1")
                if l1 is not None and l1.text:
                    lemma_text = l1.text.strip()
                else:
                    l2 = l_elem.find("l2")
                    if l2 is not None and l2.text:
                        lemma_text = l2.text.strip()

                if lemma_text:
                    lid = resolve_lemma_id(lemma_text, work_id, lemma_lookup)
                    if lid:
                        lemma_ids.add(lid)

        if tokens:
            sentence_text = " ".join(tokens)
            # Clean up spacing around punctuation
            for p in [" ,", " .", " ;", " :", " ·", " ;"]:
                sentence_text = sentence_text.replace(p, p.strip())
            sentences.append((passage, sentence_pos, sentence_text, lemma_ids))

    return sentences

def main():
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)
    if not XML_DIR.exists():
        print(f"ERROR: XML directory not found at {XML_DIR}")
        sys.exit(1)

    db = get_db()

    # Check if sentences table already has data
    existing = 0
    try:
        existing = db.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    except:
        pass

    if existing > 0:
        if "--rebuild" not in sys.argv:
            resp = input(f"sentences table already has {existing} rows. Drop and rebuild? [y/N] ")
            if resp.lower() != "y":
                print("Aborted.")
                return
        db.execute("DELETE FROM sentence_lemmas")
        db.execute("DELETE FROM sentences")
        db.commit()

    create_tables(db)

    # Build work filename -> work_id mapping
    works = db.execute("SELECT id, filename FROM works").fetchall()
    work_map = {r["filename"]: r["id"] for r in works}
    print(f"Loaded {len(work_map)} works from database")

    # Build lemma lookup
    lemma_lookup = build_lemma_lookup(db)

    # List XML files
    xml_files = sorted(XML_DIR.glob("*.xml"))
    print(f"Found {len(xml_files)} XML files")

    total_sentences = 0
    total_links = 0
    matched_works = 0

    for i, xml_path in enumerate(xml_files):
        fname = xml_path.stem  # e.g. tlg0003.tlg001.perseus-grc2
        work_id = work_map.get(fname)

        if not work_id:
            # Try without trailing parts
            continue

        matched_works += 1
        sentences = parse_xml_file(xml_path, work_id, lemma_lookup)

        if not sentences:
            continue

        # Batch insert
        for passage, spos, text, lemma_ids in sentences:
            cur = db.execute(
                "INSERT INTO sentences (work_id, passage, sentence_pos, sentence_text) VALUES (?,?,?,?)",
                (work_id, passage, spos, text),
            )
            sid = cur.lastrowid
            if lemma_ids:
                db.executemany(
                    "INSERT OR IGNORE INTO sentence_lemmas (sentence_id, lemma_id) VALUES (?,?)",
                    [(sid, lid) for lid in lemma_ids],
                )
                total_links += len(lemma_ids)
            total_sentences += 1

        if (i + 1) % 50 == 0 or i == len(xml_files) - 1:
            db.commit()
            print(f"  [{i+1}/{len(xml_files)}] {matched_works} works matched, {total_sentences} sentences, {total_links} lemma links")

    db.commit()

    # Final stats
    print(f"\nDone!")
    print(f"  Works matched: {matched_works}/{len(xml_files)}")
    print(f"  Sentences inserted: {total_sentences}")
    print(f"  Lemma-sentence links: {total_links}")

    # Verify
    sample = db.execute("""
        SELECT s.sentence_text, s.passage, w.title, w.author
        FROM sentences s
        JOIN works w ON w.id = s.work_id
        JOIN sentence_lemmas sl ON sl.sentence_id = s.id
        JOIN lemmas l ON l.id = sl.lemma_id
        WHERE l.lemma = 'λόγος'
        LIMIT 5
    """).fetchall()

    if sample:
        print(f"\nSample sentences containing λόγος:")
        for r in sample:
            print(f"  [{r['author']}, {r['title']} {r['passage']}]")
            print(f"    {r['sentence_text'][:120]}...")

if __name__ == "__main__":
    main()
