#!/usr/bin/env python3
"""
serve_api.py
═══════════════════════════════════════════════════════════════
Local API server for the Greek Vocabulary database.

Sits on top of greek_vocab.db and provides REST endpoints for:
  - Vocabulary by corpus/work (with frequency filtering)
  - Lemma details (forms, definitions, occurrences)
  - Derivational families
  - Search (lemma text, definitions, glosses)
  - Work/corpus listing

Usage:
    python3 serve_api.py                # starts on port 5000
    python3 serve_api.py --port 8080    # custom port

Requirements:
    pip3 install flask flask-cors

The API is designed to be consumed by the radial vocabulary
visualization and is structured for easy Scaife Viewer integration.
═══════════════════════════════════════════════════════════════
"""

import argparse
import json
import sqlite3
import sys
import os
from functools import wraps
from pathlib import Path

import tempfile
import subprocess
from flask_cors import CORS
from pydub import AudioSegment
from io import BytesIO
import base64

from flask import Flask, request, jsonify, send_file, g

from collections import defaultdict
import random

try:
    from openai import OpenAI
    client = OpenAI()
except Exception:
    client = None

languages = defaultdict(list)

def init_language(language):
    try:
        with open(f'datasets/{language}.directory', "r", encoding="utf-8") as f:
            for line in f.readlines():
                trans, dir = line.split('|')
                trans = trans.strip()
                dir = dir.strip()
                languages[language].append({'file': dir, 'transcription': trans})
    except FileNotFoundError:
        pass

def startup_task():
    # skip speech production on server if requested
    if 'SKIP_SPEECH' not in os.environ:
        init_language('english')
        init_language('arabic')
        init_language('greek')

startup_task()

DB_PATH = Path(os.environ.get("DB_PATH", "./greek_vocab.db"))

if not DB_PATH.exists():
    print(f"WARNING: {DB_PATH} not found. API will return 503 until database is available.")

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from the frontend

# Superuser mode: enables write endpoints for manual family editing
SUPERUSER_MODE = os.environ.get("GLOSSALEARN_SUPERUSER", "0") == "1"

# Admin token for remote sync
ADMIN_TOKEN = os.environ.get("GLOSSALEARN_ADMIN_TOKEN", "")


def require_superuser(f):
    """Decorator that gates write endpoints behind superuser mode."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not SUPERUSER_MODE:
            return jsonify({"error": "Superuser mode not enabled"}), 403
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════════════
# DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════

def get_db():
    """Get a read-only database connection for the current request."""
    if not DB_PATH.exists():
        from flask import abort
        abort(503, description="Database not available. Upload greek_vocab.db to the server.")
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row  # return dicts instead of tuples
        g.db.execute("PRAGMA cache_size=-32000")  # 32MB cache
        g.db.execute("PRAGMA query_only=ON")       # read-only safety
    return g.db


def get_write_db():
    """Get a writable database connection. Only used by superuser endpoints."""
    if "write_db" not in g:
        g.write_db = sqlite3.connect(str(DB_PATH))
        g.write_db.row_factory = sqlite3.Row
        g.write_db.execute("PRAGMA cache_size=-32000")
        g.write_db.execute("PRAGMA journal_mode=WAL")
    return g.write_db


@app.teardown_appcontext
def close_db(exception):
    for key in ("db", "write_db"):
        conn = g.pop(key, None)
        if conn is not None:
            conn.close()


def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    """Convert a list of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]



# ═══════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────
# GET /api/status
# Health check and database stats
# ─────────────────────────────────────────────
@app.route("/api/status")
def status():
    db = get_db()
    stats = {}
    for table in ["works", "lemmas", "forms", "occurrences",
                   "definitions", "derivational_families", "work_lemma_counts"]:
        row = db.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
        stats[table] = row["c"]

    row = db.execute(
        "SELECT COUNT(*) as c FROM lemmas WHERE short_def IS NOT NULL AND short_def != ''"
    ).fetchone()
    stats["lemmas_with_definitions"] = row["c"]

    return jsonify({"status": "ok", "database": str(DB_PATH), "stats": stats, "superuser": SUPERUSER_MODE})


# ─────────────────────────────────────────────
# GET /api/download-db
# Download the full SQLite database
# ─────────────────────────────────────────────
DOWNLOAD_TOKEN = os.environ.get("DOWNLOAD_TOKEN", "glossalearn2026")

@app.route("/api/download-db")
def download_db():
    if request.args.get("token") != DOWNLOAD_TOKEN:
        return jsonify({"error": "Invalid or missing token"}), 403
    if not DB_PATH.exists():
        return jsonify({"error": "Database not available"}), 503
    from flask import send_file
    return send_file(str(DB_PATH), as_attachment=True, download_name="greek_vocab.db")


# ─────────────────────────────────────────────
# GET /api/works
# List all works, optionally filtered by author
#
# Query params:
#   author=Homer          filter by author name
#   corpus=perseus        filter by corpus (perseus, first1k)
# ─────────────────────────────────────────────
@app.route("/api/works")
def list_works():
    db = get_db()
    conditions = []
    params = []

    author = request.args.get("author")
    if author:
        conditions.append("author LIKE ?")
        params.append(f"%{author}%")

    corpus = request.args.get("corpus")
    if corpus:
        conditions.append("corpus = ?")
        params.append(corpus)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = db.execute(
        f"""SELECT id, filename, cts_urn, author_code, work_code,
                   author, title, corpus
            FROM works {where}
            ORDER BY author, title""",
        params,
    ).fetchall()

    return jsonify({"works": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────
# GET /api/authors
# List all unique authors with work counts
# ─────────────────────────────────────────────
@app.route("/api/authors")
def list_authors():
    db = get_db()
    rows = db.execute("""
        SELECT author, author_code, COUNT(*) as work_count,
               SUM(wlc_total) as total_tokens
        FROM (
            SELECT w.author, w.author_code, w.id,
                   COALESCE(SUM(wlc.count), 0) as wlc_total
            FROM works w
            LEFT JOIN work_lemma_counts wlc ON wlc.work_id = w.id
            GROUP BY w.id
        )
        GROUP BY author
        ORDER BY total_tokens DESC
    """).fetchall()

    return jsonify({"authors": rows_to_list(rows), "count": len(rows)})


# ─────────────────────────────────────────────
# GET /api/vocab
# Get vocabulary for a specific work or author.
# This is the PRIMARY endpoint for corpus filtering.
#
# Query params:
#   work_id=123           filter by specific work
#   author=Homer          filter by author name
#   author_code=tlg0012   filter by TLG code
#   min_freq=5            minimum occurrences in this work
#   max_rank=1000         only top N most frequent corpus-wide
#   pos=noun              filter by part of speech
#   limit=100             max results (default 200)
#   offset=0              pagination offset
#   sort=frequency        sort by: frequency (in work), rank (corpus-wide), alpha
# ─────────────────────────────────────────────
@app.route("/api/vocab")
def get_vocab():
    db = get_db()
    conditions = ["1=1"]
    params = []
    join_wlc = False

    # Work filter
    work_id = request.args.get("work_id", type=int)
    if work_id:
        join_wlc = True
        conditions.append("wlc.work_id = ?")
        params.append(work_id)

    # Author filter (can match multiple works)
    author = request.args.get("author")
    author_code = request.args.get("author_code")
    if author:
        join_wlc = True
        conditions.append("w.author LIKE ?")
        params.append(f"%{author}%")
    elif author_code:
        join_wlc = True
        conditions.append("w.author_code = ?")
        params.append(author_code)

    # Frequency filter (within the selected work/author)
    # This must go in HAVING, not WHERE, since work_freq is a SUM()
    min_freq = request.args.get("min_freq", type=int)
    having_clause = ""
    having_params = []
    if min_freq and join_wlc:
        having_clause = "HAVING work_freq >= ?"
        having_params = [min_freq]

    # Corpus-wide rank filter
    max_rank = request.args.get("max_rank", type=int)
    if max_rank:
        conditions.append("l.frequency_rank <= ?")
        params.append(max_rank)

    # POS filter
    pos = request.args.get("pos")
    if pos:
        conditions.append("l.pos = ?")
        params.append(pos)

    # Sorting
    sort = request.args.get("sort", "frequency")
    if sort == "alpha":
        order = "l.lemma ASC"
    elif sort == "rank":
        order = "l.frequency_rank ASC"
    else:
        order = "work_freq DESC" if join_wlc else "l.total_occurrences DESC"

    limit = request.args.get("limit", 200, type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = min(limit, 15000)

    where = "WHERE " + " AND ".join(conditions)

    if join_wlc:
        query = f"""
            SELECT l.id, l.lemma, l.pos, l.short_def,
                   l.total_occurrences, l.frequency_rank,
                   SUM(wlc.count) as work_freq
            FROM lemmas l
            JOIN work_lemma_counts wlc ON wlc.lemma_id = l.id
            JOIN works w ON w.id = wlc.work_id
            {where}
            GROUP BY l.id
            {having_clause}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """
        params.extend(having_params)
    else:
        query = f"""
            SELECT l.id, l.lemma, l.pos, l.short_def,
                   l.total_occurrences, l.frequency_rank,
                   l.total_occurrences as work_freq
            FROM lemmas l
            {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """

    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()

    return jsonify({
        "vocab": rows_to_list(rows),
        "count": len(rows),
        "limit": limit,
        "offset": offset,
    })


# ─────────────────────────────────────────────
# GET /api/lemma/<lemma_id>
# Full details for one lemma: forms, definitions,
# derivational family, sample occurrences
# ─────────────────────────────────────────────
@app.route("/api/lemma/<int:lemma_id>")
def get_lemma(lemma_id):
    db = get_db()

    # Basic lemma info
    lemma = row_to_dict(db.execute(
        """SELECT id, lemma, pos, short_def, lsj_def, middle_liddell,
                  total_occurrences, frequency_rank
           FROM lemmas WHERE id = ?""",
        (lemma_id,),
    ).fetchone())

    if not lemma:
        return jsonify({"error": "Lemma not found"}), 404

    # All morphological forms — optionally filtered by work_id
    work_id = request.args.get("work_id", type=int)
    if work_id:
        forms = rows_to_list(db.execute(
            """SELECT DISTINCT f.form, f.morph_tag, f.pos, f.person, f.number, f.tense,
                      f.mood, f.voice, f.gender, f.gram_case, f.degree
               FROM forms f
               JOIN occurrences o ON o.form_id = f.id
               WHERE f.lemma_id = ? AND o.work_id = ?
               ORDER BY f.morph_tag""",
            (lemma_id, work_id),
        ).fetchall())
    else:
        forms = rows_to_list(db.execute(
            """SELECT form, morph_tag, pos, person, number, tense,
                      mood, voice, gender, gram_case, degree
               FROM forms WHERE lemma_id = ?
               ORDER BY morph_tag""",
            (lemma_id,),
        ).fetchall())

    # Definitions
    definitions = rows_to_list(db.execute(
        """SELECT source, entry_key, definition, short_def
           FROM definitions WHERE lemma_id = ?""",
        (lemma_id,),
    ).fetchall())

    # Derivational families (a lemma can belong to more than one)
    family = None
    all_families = []
    fam_rows = db.execute(
        """SELECT df.id, df.root, df.label, lf.relation
           FROM lemma_families lf
           JOIN derivational_families df ON df.id = lf.family_id
           WHERE lf.lemma_id = ?""",
        (lemma_id,),
    ).fetchall()

    for fam_row in fam_rows:
        fam_dict = row_to_dict(fam_row)
        members = rows_to_list(db.execute(
            """SELECT l.id, l.lemma, l.pos, l.short_def,
                      l.total_occurrences, lf.relation, lf.parent_lemma_id
               FROM lemma_families lf
               JOIN lemmas l ON l.id = lf.lemma_id
               WHERE lf.family_id = ?
               ORDER BY l.total_occurrences DESC""",
            (fam_dict["id"],),
        ).fetchall())
        fam_obj = {
            "id": fam_dict["id"],
            "root": fam_dict["root"],
            "label": fam_dict["label"],
            "relation": fam_dict["relation"],
            "members": members,
        }
        all_families.append(fam_obj)
    if all_families:
        family = all_families[0]

    # Top works this lemma appears in
    top_works = rows_to_list(db.execute(
        """SELECT w.id, w.author, w.title, w.cts_urn, wlc.count
           FROM work_lemma_counts wlc
           JOIN works w ON w.id = wlc.work_id
           WHERE wlc.lemma_id = ?
           ORDER BY wlc.count DESC
           LIMIT 20""",
        (lemma_id,),
    ).fetchall())

    # Sample passages
    passages = rows_to_list(db.execute(
        """SELECT DISTINCT passage
           FROM occurrences
           WHERE lemma_id = ? AND passage IS NOT NULL AND passage != ''
           LIMIT 20""",
        (lemma_id,),
    ).fetchall())

    lemma["forms"] = forms
    lemma["definitions"] = definitions
    lemma["family"] = family
    lemma["families"] = all_families
    lemma["top_works"] = top_works
    lemma["sample_passages"] = [p["passage"] for p in passages]

    return jsonify(lemma)


# ─────────────────────────────────────────────
# GET /api/lemma/by-name/<lemma_text>
# Look up a lemma by its Greek text
#
# Query params:
#   pos=noun       optional POS filter
# ─────────────────────────────────────────────
@app.route("/api/lemma/by-name/<lemma_text>")
def get_lemma_by_name(lemma_text):
    db = get_db()
    pos = request.args.get("pos")

    if pos:
        row = db.execute(
            "SELECT id FROM lemmas WHERE lemma = ? AND pos = ?",
            (lemma_text, pos),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT id FROM lemmas WHERE lemma = ? ORDER BY total_occurrences DESC LIMIT 1",
            (lemma_text,),
        ).fetchone()

    if not row:
        return jsonify({"error": f"Lemma '{lemma_text}' not found"}), 404

    # Redirect to the full lemma endpoint
    return get_lemma(row["id"])


# ─────────────────────────────────────────────
# GET /api/lemma/<lemma_id>/sentences
# Example sentences containing this lemma
# Query params:
#   work_id=6    optional: filter to a specific work
#   offset=0     skip N sentences (for cycling through)
#   limit=5      max sentences to return (default 5)
# ─────────────────────────────────────────────
@app.route("/api/lemma/<int:lemma_id>/sentences")
def get_lemma_sentences(lemma_id):
    db = get_db()
    work_id = request.args.get("work_id", type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = request.args.get("limit", 5, type=int)
    limit = min(limit, 20)

    # Check if sentences table exists
    table_check = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sentences'"
    ).fetchone()
    if not table_check:
        return jsonify({"sentences": [], "note": "Sentences table not yet built"})

    # Get the lemma text for highlighting
    lemma_row = db.execute("SELECT lemma FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    if not lemma_row:
        return jsonify({"error": "Lemma not found"}), 404

    if work_id:
        # Get total count for this lemma+work so frontend knows when to wrap
        total = db.execute("""
            SELECT COUNT(*) as c FROM sentence_lemmas sl
            JOIN sentences s ON s.id = sl.sentence_id
            WHERE sl.lemma_id = ? AND s.work_id = ?
        """, (lemma_id, work_id)).fetchone()["c"]

        rows = db.execute("""
            SELECT s.id, s.passage, s.sentence_text, w.title, w.author, w.id as work_id
            FROM sentence_lemmas sl
            JOIN sentences s ON s.id = sl.sentence_id
            JOIN works w ON w.id = s.work_id
            WHERE sl.lemma_id = ? AND s.work_id = ?
            ORDER BY s.sentence_pos
            LIMIT 1 OFFSET ?
        """, (lemma_id, work_id, offset)).fetchall()
    else:
        # One sentence per work (grouped), up to limit works
        rows = db.execute("""
            SELECT s.id, s.passage, s.sentence_text, w.title, w.author, w.id as work_id
            FROM sentence_lemmas sl
            JOIN sentences s ON s.id = sl.sentence_id
            JOIN works w ON w.id = s.work_id
            WHERE sl.lemma_id = ?
            GROUP BY s.work_id
            ORDER BY s.sentence_pos
            LIMIT ?
        """, (lemma_id, limit)).fetchall()

    sentences = []
    for r in rows:
        sentences.append({
            "id": r["id"],
            "passage": r["passage"],
            "text": r["sentence_text"],
            "work_title": r["title"],
            "work_author": r["author"],
            "work_id": r["work_id"],
        })

    result = {"sentences": sentences, "lemma": lemma_row["lemma"]}
    if work_id:
        result["total"] = total
    return jsonify(result)


# ─────────────────────────────────────────────
# GET /api/family/<family_id>
# Full derivational family with all members
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>")
def get_family(family_id):
    db = get_db()

    family = row_to_dict(db.execute(
        "SELECT id, root, label FROM derivational_families WHERE id = ?",
        (family_id,),
    ).fetchone())

    if not family:
        return jsonify({"error": "Family not found"}), 404

    members = rows_to_list(db.execute(
        """SELECT l.id, l.lemma, l.pos, l.short_def,
                  l.total_occurrences, l.frequency_rank, lf.relation
           FROM lemma_families lf
           JOIN lemmas l ON l.id = lf.lemma_id
           WHERE lf.family_id = ?
           ORDER BY l.total_occurrences DESC""",
        (family_id,),
    ).fetchall())

    family["members"] = members
    return jsonify(family)


# ─────────────────────────────────────────────
# GET /api/search
# Search lemmas and definitions
#
# Query params:
#   q=logos           search query (Greek or English)
#   limit=20          max results
# ─────────────────────────────────────────────
@app.route("/api/search")
def search():
    db = get_db()
    q = request.args.get("q", "").strip()
    limit = request.args.get("limit", 30, type=int)

    if not q:
        return jsonify({"results": [], "count": 0})

    results = []

    # Strategy 1: exact lemma match
    exact = rows_to_list(db.execute(
        """SELECT id, lemma, pos, short_def, total_occurrences, frequency_rank
           FROM lemmas WHERE lemma = ?
           ORDER BY total_occurrences DESC""",
        (q,),
    ).fetchall())
    for r in exact:
        r["match_type"] = "exact"
    results.extend(exact)

    # Strategy 2: lemma prefix match
    if len(results) < limit:
        prefix = rows_to_list(db.execute(
            """SELECT id, lemma, pos, short_def, total_occurrences, frequency_rank
               FROM lemmas WHERE lemma LIKE ? AND lemma != ?
               ORDER BY total_occurrences DESC
               LIMIT ?""",
            (q + "%", q, limit - len(results)),
        ).fetchall())
        for r in prefix:
            r["match_type"] = "prefix"
        results.extend(prefix)

    # Strategy 3: FTS search on definitions (for English queries)
    if len(results) < limit:
        try:
            # FTS5 query — escape special chars
            fts_q = q.replace('"', '').replace("'", "")
            fts_rows = rows_to_list(db.execute(
                """SELECT l.id, l.lemma, l.pos, l.short_def,
                          l.total_occurrences, l.frequency_rank
                   FROM lemmas_fts fts
                   JOIN lemmas l ON l.id = fts.rowid
                   WHERE lemmas_fts MATCH ?
                   ORDER BY l.total_occurrences DESC
                   LIMIT ?""",
                (fts_q, limit - len(results)),
            ).fetchall())

            seen_ids = {r["id"] for r in results}
            for r in fts_rows:
                if r["id"] not in seen_ids:
                    r["match_type"] = "definition"
                    results.append(r)
        except Exception:
            pass  # FTS query might fail on weird input

    # Strategy 4: substring match on definitions
    if len(results) < limit:
        seen_ids = {r["id"] for r in results}
        substr = rows_to_list(db.execute(
            """SELECT id, lemma, pos, short_def, total_occurrences, frequency_rank
               FROM lemmas
               WHERE short_def LIKE ? AND id NOT IN ({})
               ORDER BY total_occurrences DESC
               LIMIT ?""".format(",".join("?" * len(seen_ids)) if seen_ids else "0"),
            (f"%{q}%", *seen_ids, limit - len(results)),
        ).fetchall())
        for r in substr:
            r["match_type"] = "substring"
        results.extend(substr)

    return jsonify({"results": results[:limit], "count": len(results), "query": q})


# ─────────────────────────────────────────────
# GET /api/compare
# Compare vocabulary between two works/authors
#
# Query params:
#   a=Homer           first author (or a_id=work_id)
#   b=New Testament   second author (or b_id=work_id)
#   mode=shared       shared | unique_a | unique_b
#   limit=100
# ─────────────────────────────────────────────
@app.route("/api/compare")
def compare_vocab():
    db = get_db()

    a_author = request.args.get("a", "")
    b_author = request.args.get("b", "")
    a_id = request.args.get("a_id", type=int)
    b_id = request.args.get("b_id", type=int)
    mode = request.args.get("mode", "shared")
    limit = request.args.get("limit", 100, type=int)

    # Build subqueries for each side
    def make_subquery(author, work_id, alias):
        if work_id:
            return (
                f"""(SELECT wlc.lemma_id, SUM(wlc.count) as freq
                     FROM work_lemma_counts wlc
                     WHERE wlc.work_id = ?
                     GROUP BY wlc.lemma_id) {alias}""",
                [work_id],
            )
        else:
            return (
                f"""(SELECT wlc.lemma_id, SUM(wlc.count) as freq
                     FROM work_lemma_counts wlc
                     JOIN works w ON w.id = wlc.work_id
                     WHERE w.author LIKE ?
                     GROUP BY wlc.lemma_id) {alias}""",
                [f"%{author}%"],
            )

    sq_a, params_a = make_subquery(a_author, a_id, "a")
    sq_b, params_b = make_subquery(b_author, b_id, "b")

    if mode == "shared":
        query = f"""
            SELECT l.id, l.lemma, l.pos, l.short_def,
                   a.freq as freq_a, b.freq as freq_b,
                   l.total_occurrences, l.frequency_rank
            FROM {sq_a}
            JOIN {sq_b} ON a.lemma_id = b.lemma_id
            JOIN lemmas l ON l.id = a.lemma_id
            ORDER BY a.freq + b.freq DESC
            LIMIT ?
        """
        params = params_a + params_b + [limit]
    elif mode == "unique_a":
        query = f"""
            SELECT l.id, l.lemma, l.pos, l.short_def,
                   a.freq as freq_a, 0 as freq_b,
                   l.total_occurrences, l.frequency_rank
            FROM {sq_a}
            LEFT JOIN {sq_b} ON a.lemma_id = b.lemma_id
            JOIN lemmas l ON l.id = a.lemma_id
            WHERE b.lemma_id IS NULL
            ORDER BY a.freq DESC
            LIMIT ?
        """
        params = params_a + params_b + [limit]
    else:  # unique_b
        query = f"""
            SELECT l.id, l.lemma, l.pos, l.short_def,
                   0 as freq_a, b.freq as freq_b,
                   l.total_occurrences, l.frequency_rank
            FROM {sq_b}
            LEFT JOIN {sq_a} ON b.lemma_id = a.lemma_id
            JOIN lemmas l ON l.id = b.lemma_id
            WHERE a.lemma_id IS NULL
            ORDER BY b.freq DESC
            LIMIT ?
        """
        params = params_b + params_a + [limit]

    rows = db.execute(query, params).fetchall()

    return jsonify({
        "results": rows_to_list(rows),
        "count": len(rows),
        "a": a_author or f"work:{a_id}",
        "b": b_author or f"work:{b_id}",
        "mode": mode,
    })


# ─────────────────────────────────────────────
# GET /api/pos-stats
# Part-of-speech breakdown, optionally per work
#
# Query params:
#   author=Homer
#   work_id=123
# ─────────────────────────────────────────────
@app.route("/api/pos-stats")
def pos_stats():
    db = get_db()

    author = request.args.get("author")
    work_id = request.args.get("work_id", type=int)

    if work_id:
        rows = db.execute("""
            SELECT l.pos, COUNT(DISTINCT l.id) as lemma_count,
                   SUM(wlc.count) as token_count
            FROM work_lemma_counts wlc
            JOIN lemmas l ON l.id = wlc.lemma_id
            WHERE wlc.work_id = ?
            GROUP BY l.pos
            ORDER BY token_count DESC
        """, (work_id,)).fetchall()
    elif author:
        rows = db.execute("""
            SELECT l.pos, COUNT(DISTINCT l.id) as lemma_count,
                   SUM(wlc.count) as token_count
            FROM work_lemma_counts wlc
            JOIN lemmas l ON l.id = wlc.lemma_id
            JOIN works w ON w.id = wlc.work_id
            WHERE w.author LIKE ?
            GROUP BY l.pos
            ORDER BY token_count DESC
        """, (f"%{author}%",)).fetchall()
    else:
        rows = db.execute("""
            SELECT pos, COUNT(*) as lemma_count,
                   SUM(total_occurrences) as token_count
            FROM lemmas
            WHERE pos IS NOT NULL AND pos != ''
            GROUP BY pos
            ORDER BY token_count DESC
        """).fetchall()

    return jsonify({"stats": rows_to_list(rows)})


# ═══════════════════════════════════════════════════════════════
# SUPERUSER WRITE ENDPOINTS — Family editing
# ═══════════════════════════════════════════════════════════════

def log_edit(db, action, family_id=None, lemma_id=None, detail=None, before=None):
    """Append a row to the audit log with optional before-state for reversal."""
    db.execute(
        "INSERT INTO family_edit_log (action, family_id, lemma_id, detail, before) VALUES (?,?,?,?,?)",
        (action, family_id, lemma_id,
         json.dumps(detail) if detail else None,
         json.dumps(before) if before else None),
    )


# ─────────────────────────────────────────────
# PATCH /api/lemma/<lemma_id>
# Edit a lemma's short_def, pos, or lsj_def
# Body: { short_def, pos, lsj_def }
# ─────────────────────────────────────────────
@app.route("/api/lemma/<int:lemma_id>", methods=["PATCH"])
@require_superuser
def update_lemma(lemma_id):
    db = get_write_db()
    data = request.get_json()

    lemma = db.execute("SELECT id FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    if not lemma:
        return jsonify({"error": "Lemma not found"}), 404

    updates, params = [], []
    for field in ("short_def", "pos", "lsj_def"):
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])

    if not updates:
        return jsonify({"error": "No fields to update"}), 400

    # Capture before state
    old = db.execute("SELECT short_def, pos, lsj_def FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    before_state = {k: old[k] for k in ("short_def", "pos", "lsj_def")} if old else {}

    params.append(lemma_id)
    db.execute(f"UPDATE lemmas SET {', '.join(updates)} WHERE id = ?", params)

    # Also update definitions table short_def if provided
    if "short_def" in data:
        existing_def = db.execute(
            "SELECT id FROM definitions WHERE lemma_id = ? AND source = 'manual'", (lemma_id,)
        ).fetchone()
        if existing_def:
            db.execute(
                "UPDATE definitions SET short_def = ?, definition = ? WHERE id = ?",
                (data["short_def"], data["short_def"], existing_def["id"]),
            )
        else:
            db.execute(
                "INSERT INTO definitions (lemma_id, source, definition, short_def) VALUES (?,?,?,?)",
                (lemma_id, "manual", data["short_def"], data["short_def"]),
            )

    log_edit(db, "update_lemma", lemma_id=lemma_id,
             detail={k: data[k] for k in ("short_def", "pos", "lsj_def") if k in data},
             before=before_state)
    db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# POST /api/lemma/<lemma_id>/merge/<other_id>
# Merge two lemma entries (move all references from other into this one)
# ─────────────────────────────────────────────
@app.route("/api/lemma/<int:lemma_id>/merge/<int:other_id>", methods=["POST"])
@require_superuser
def merge_lemmas(lemma_id, other_id):
    db = get_write_db()

    keep = db.execute("SELECT id, lemma FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    remove = db.execute("SELECT id, lemma FROM lemmas WHERE id = ?", (other_id,)).fetchone()
    if not keep or not remove:
        return jsonify({"error": "One or both lemmas not found"}), 404
    if lemma_id == other_id:
        return jsonify({"error": "Cannot merge a lemma with itself"}), 400

    # Move forms
    db.execute("UPDATE OR IGNORE forms SET lemma_id = ? WHERE lemma_id = ?", (lemma_id, other_id))
    db.execute("DELETE FROM forms WHERE lemma_id = ?", (other_id,))

    # Move occurrences
    db.execute("UPDATE OR IGNORE occurrences SET lemma_id = ? WHERE lemma_id = ?", (lemma_id, other_id))
    db.execute("DELETE FROM occurrences WHERE lemma_id = ?", (other_id,))

    # Move work_lemma_counts (sum counts if both exist)
    other_wlc = db.execute("SELECT work_id, count FROM work_lemma_counts WHERE lemma_id = ?", (other_id,)).fetchall()
    for row in other_wlc:
        existing = db.execute(
            "SELECT count FROM work_lemma_counts WHERE lemma_id = ? AND work_id = ?",
            (lemma_id, row["work_id"]),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE work_lemma_counts SET count = count + ? WHERE lemma_id = ? AND work_id = ?",
                (row["count"], lemma_id, row["work_id"]),
            )
        else:
            db.execute(
                "UPDATE work_lemma_counts SET lemma_id = ? WHERE lemma_id = ? AND work_id = ?",
                (lemma_id, other_id, row["work_id"]),
            )
    db.execute("DELETE FROM work_lemma_counts WHERE lemma_id = ?", (other_id,))

    # Move family memberships
    db.execute("UPDATE OR IGNORE lemma_families SET lemma_id = ? WHERE lemma_id = ?", (lemma_id, other_id))
    db.execute("DELETE FROM lemma_families WHERE lemma_id = ?", (other_id,))

    # Update parent_lemma_id references
    db.execute("UPDATE lemma_families SET parent_lemma_id = ? WHERE parent_lemma_id = ?", (lemma_id, other_id))

    # Move definitions
    db.execute("UPDATE OR IGNORE definitions SET lemma_id = ? WHERE lemma_id = ?", (lemma_id, other_id))
    db.execute("DELETE FROM definitions WHERE lemma_id = ?", (other_id,))

    # Move sentence_lemmas
    db.execute("UPDATE OR IGNORE sentence_lemmas SET lemma_id = ? WHERE lemma_id = ?", (lemma_id, other_id))
    db.execute("DELETE FROM sentence_lemmas WHERE lemma_id = ?", (other_id,))

    # Update total_occurrences on the kept lemma
    total = db.execute(
        "SELECT SUM(count) as t FROM work_lemma_counts WHERE lemma_id = ?", (lemma_id,)
    ).fetchone()["t"] or 0
    db.execute("UPDATE lemmas SET total_occurrences = ? WHERE id = ?", (total, lemma_id))

    # Delete the merged lemma
    db.execute("DELETE FROM lemmas WHERE id = ?", (other_id,))

    log_edit(db, "merge_lemmas", lemma_id=lemma_id, detail={
        "merged_from_id": other_id,
        "merged_from_lemma": remove["lemma"],
    })
    db.commit()

    return jsonify({"ok": True, "kept": lemma_id, "removed": other_id})


# ─────────────────────────────────────────────
# POST /api/family/create
# Create a new derivational family
# Body: { root, label, lemma_id, relation }
# ─────────────────────────────────────────────
@app.route("/api/family/create", methods=["POST"])
@require_superuser
def create_family():
    db = get_write_db()
    data = request.get_json()
    root = data.get("root", "").strip()
    label = data.get("label", "").strip()
    lemma_id = data.get("lemma_id")
    relation = data.get("relation", "root")

    if not root or not lemma_id:
        return jsonify({"error": "root and lemma_id are required"}), 400

    # Verify lemma exists
    lemma = db.execute("SELECT id, lemma FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    if not lemma:
        return jsonify({"error": "Lemma not found"}), 404

    if not label:
        label = f"Root: {root}-"

    cur = db.execute("INSERT INTO derivational_families (root, label) VALUES (?,?)", (root, label))
    family_id = cur.lastrowid
    db.execute(
        "INSERT INTO lemma_families (lemma_id, family_id, relation) VALUES (?,?,?)",
        (lemma_id, family_id, relation),
    )
    log_edit(db, "create", family_id, lemma_id, {"root": root, "label": label, "relation": relation})
    db.commit()

    return get_family(family_id)


# ─────────────────────────────────────────────
# POST /api/family/<id>/add-member
# Add a word to an existing family
# Body: { lemma_id, relation }
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/add-member", methods=["POST"])
@require_superuser
def add_family_member(family_id):
    db = get_write_db()
    data = request.get_json()
    lemma_id = data.get("lemma_id")
    relation = data.get("relation", "derived")
    parent_lemma_id = data.get("parent_lemma_id")  # optional: which member this derives from

    if not lemma_id:
        return jsonify({"error": "lemma_id is required"}), 400

    # Verify family exists
    fam = db.execute("SELECT id FROM derivational_families WHERE id = ?", (family_id,)).fetchone()
    if not fam:
        return jsonify({"error": "Family not found"}), 404

    # Verify lemma exists
    lemma = db.execute("SELECT id, lemma FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    if not lemma:
        return jsonify({"error": "Lemma not found"}), 404

    # Check if already in this family
    existing = db.execute(
        "SELECT family_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
        (lemma_id, family_id),
    ).fetchone()
    if existing:
        return jsonify({"error": "Already in this family"}), 409

    # Check if in a different family
    allow_multi = request.args.get("allow_multi") == "1"
    other = db.execute(
        """SELECT lf.family_id, df.label FROM lemma_families lf
           JOIN derivational_families df ON df.id = lf.family_id
           WHERE lf.lemma_id = ?""",
        (lemma_id,),
    ).fetchone()
    if other and not allow_multi:
        return jsonify({
            "error": "Word belongs to another family",
            "conflict": {
                "existing_family_id": other["family_id"],
                "existing_family_label": other["label"],
            }
        }), 409

    db.execute(
        "INSERT INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
        (lemma_id, family_id, relation, parent_lemma_id),
    )
    log_edit(db, "add_member", family_id, lemma_id, {"relation": relation, "parent_lemma_id": parent_lemma_id})
    db.commit()

    return get_family(family_id)


# ─────────────────────────────────────────────
# DELETE /api/family/<id>/member/<lemma_id>
# Remove a word from a family
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/member/<int:lemma_id>", methods=["DELETE"])
@require_superuser
def remove_family_member(family_id, lemma_id):
    db = get_write_db()

    # Capture before state
    old = db.execute(
        "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
        (lemma_id, family_id),
    ).fetchone()
    before_state = {"relation": old["relation"], "parent_lemma_id": old["parent_lemma_id"]} if old else {}

    db.execute(
        "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
        (lemma_id, family_id),
    )

    # Check if family is now empty
    remaining = db.execute(
        "SELECT COUNT(*) as c FROM lemma_families WHERE family_id = ?", (family_id,)
    ).fetchone()["c"]

    family_deleted = False
    if remaining == 0:
        db.execute("DELETE FROM derivational_families WHERE id = ?", (family_id,))
        family_deleted = True

    log_edit(db, "remove_member", family_id, lemma_id, {"family_deleted": family_deleted}, before=before_state)
    db.commit()

    return jsonify({"ok": True, "family_deleted": family_deleted})


# ─────────────────────────────────────────────
# POST /api/family/<id>/merge/<other_id>
# Merge other family into this one
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/merge/<int:other_id>", methods=["POST"])
@require_superuser
def merge_families(family_id, other_id):
    db = get_write_db()

    # Verify both exist
    fam = db.execute("SELECT id, label FROM derivational_families WHERE id = ?", (family_id,)).fetchone()
    other = db.execute("SELECT id, label FROM derivational_families WHERE id = ?", (other_id,)).fetchone()
    if not fam or not other:
        return jsonify({"error": "One or both families not found"}), 404

    if family_id == other_id:
        return jsonify({"error": "Cannot merge a family with itself"}), 400

    # Get members of the other family
    other_members = db.execute(
        "SELECT lemma_id, relation, parent_lemma_id FROM lemma_families WHERE family_id = ?", (other_id,)
    ).fetchall()

    # Move each member, skipping duplicates
    for m in other_members:
        existing = db.execute(
            "SELECT 1 FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
            (m["lemma_id"], family_id),
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                (m["lemma_id"], family_id, m["relation"], m["parent_lemma_id"]),
            )

    # Snapshot merged family for reversal (before deleting)
    other_fam = db.execute("SELECT root, label FROM derivational_families WHERE id = ?", (other_id,)).fetchone()
    before_state = {
        "other_family": {"id": other_id, "root": other_fam["root"] if other_fam else None, "label": other_fam["label"] if other_fam else None},
        "other_members": [{"lemma_id": m["lemma_id"], "relation": m["relation"], "parent_lemma_id": m["parent_lemma_id"]} for m in other_members],
    }

    # Delete the old family
    db.execute("DELETE FROM lemma_families WHERE family_id = ?", (other_id,))
    db.execute("DELETE FROM derivational_families WHERE id = ?", (other_id,))
    log_edit(db, "merge", family_id, None, {
        "merged_from": other_id,
        "merged_label": other["label"],
        "members_moved": len(other_members),
    }, before=before_state)
    db.commit()

    return get_family(family_id)


# ─────────────────────────────────────────────
# POST /api/family/<id>/split/<lemma_id>
# Split a subtree into a new linked family.
# Takes the given lemma + all its descendants,
# moves them to a new family, and links back.
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/split/<int:lemma_id>", methods=["POST"])
@require_superuser
def split_to_linked_family(family_id, lemma_id):
    db = get_write_db()

    # Ensure family_links table exists
    db.execute("""CREATE TABLE IF NOT EXISTS family_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_id_a INTEGER NOT NULL REFERENCES derivational_families(id),
        family_id_b INTEGER NOT NULL REFERENCES derivational_families(id),
        link_type TEXT DEFAULT 'related',
        note TEXT,
        UNIQUE(family_id_a, family_id_b)
    )""")

    # Verify the member exists in this family
    member = db.execute(
        "SELECT lemma_id, relation, parent_lemma_id FROM lemma_families WHERE family_id = ? AND lemma_id = ?",
        (family_id, lemma_id),
    ).fetchone()
    if not member:
        return jsonify({"error": "Member not found in this family"}), 404

    # Get lemma info for the new family root
    lemma_info = db.execute("SELECT lemma, pos FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
    if not lemma_info:
        return jsonify({"error": "Lemma not found"}), 404

    # Find all descendants of this lemma in the family
    all_members = db.execute(
        "SELECT lemma_id, parent_lemma_id FROM lemma_families WHERE family_id = ?",
        (family_id,),
    ).fetchall()

    children_of = {}
    for m in all_members:
        pid = m["parent_lemma_id"]
        if pid not in children_of:
            children_of[pid] = []
        children_of[pid].append(m["lemma_id"])

    # BFS to collect all descendants
    subtree_ids = set()
    stack = [lemma_id]
    while stack:
        cur = stack.pop()
        subtree_ids.add(cur)
        for child in children_of.get(cur, []):
            if child not in subtree_ids:
                stack.append(child)

    # Snapshot subtree members before moving (for reversal)
    before_members = []
    for mid in subtree_ids:
        row = db.execute(
            "SELECT relation, parent_lemma_id FROM lemma_families WHERE family_id = ? AND lemma_id = ?",
            (family_id, mid),
        ).fetchone()
        if row:
            before_members.append({"lemma_id": mid, "relation": row["relation"], "parent_lemma_id": row["parent_lemma_id"]})

    # Create new family
    new_root = lemma_info["lemma"]
    new_label = f"{new_root} family"
    cursor = db.execute(
        "INSERT INTO derivational_families (root, label) VALUES (?, ?)",
        (new_root, new_label),
    )
    new_family_id = cursor.lastrowid

    # Move subtree members to new family
    for mid in subtree_ids:
        old = db.execute(
            "SELECT relation, parent_lemma_id FROM lemma_families WHERE family_id = ? AND lemma_id = ?",
            (family_id, mid),
        ).fetchone()
        if not old:
            continue
        # The split root becomes "root" in the new family; keep parent refs for others
        new_relation = "root" if mid == lemma_id else old["relation"]
        new_parent = None if mid == lemma_id else old["parent_lemma_id"]
        # If parent is not in subtree, attach to the new root
        if new_parent and new_parent not in subtree_ids:
            new_parent = lemma_id

        db.execute(
            "INSERT INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?, ?, ?, ?)",
            (mid, new_family_id, new_relation, new_parent),
        )
        db.execute(
            "DELETE FROM lemma_families WHERE family_id = ? AND lemma_id = ?",
            (family_id, mid),
        )

    # Create a link between old and new family
    a, b = min(family_id, new_family_id), max(family_id, new_family_id)
    try:
        db.execute(
            "INSERT INTO family_links (family_id_a, family_id_b, link_type, note) VALUES (?, ?, ?, ?)",
            (a, b, "related", f"Split from {new_root}"),
        )
    except sqlite3.IntegrityError:
        pass  # link already exists

    log_edit(db, "split_family", family_id, lemma_id, {
        "new_family_id": new_family_id,
        "subtree_size": len(subtree_ids),
    }, before={"members": before_members})
    db.commit()

    return jsonify({"ok": True, "new_family_id": new_family_id})


# ─────────────────────────────────────────────
# PATCH /api/family/<id>/member/<lemma_id>
# Update a member's relation label
# Body: { relation }
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/member/<int:lemma_id>", methods=["PATCH"])
@require_superuser
def update_member_relation(family_id, lemma_id):
    db = get_write_db()
    data = request.get_json()
    relation = data.get("relation")
    parent_lemma_id = data.get("parent_lemma_id")  # can be int or null

    if not relation and "parent_lemma_id" not in data:
        return jsonify({"error": "relation or parent_lemma_id is required"}), 400

    # Capture before state
    old = db.execute(
        "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
        (lemma_id, family_id),
    ).fetchone()
    before_state = {"relation": old["relation"], "parent_lemma_id": old["parent_lemma_id"]} if old else {}

    updates, params = [], []
    if relation:
        updates.append("relation = ?")
        params.append(relation.strip())
    if "parent_lemma_id" in data:
        updates.append("parent_lemma_id = ?")
        params.append(parent_lemma_id)
    params.extend([lemma_id, family_id])

    db.execute(
        f"UPDATE lemma_families SET {', '.join(updates)} WHERE lemma_id = ? AND family_id = ?",
        params,
    )
    log_edit(db, "update_member", family_id, lemma_id, {"relation": relation, "parent_lemma_id": parent_lemma_id}, before=before_state)
    db.commit()

    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# POST /api/family/<source_id>/move-member/<lemma_id>/to/<target_id>
# Move a member (and optionally its descendants) from one family to another
# Body: { new_parent_id, move_descendants (bool, default true) }
# ─────────────────────────────────────────────
@app.route("/api/family/<int:source_id>/move-member/<int:lemma_id>/to/<int:target_id>", methods=["POST"])
@require_superuser
def move_member_cross_family(source_id, lemma_id, target_id):
    db = get_write_db()
    data = request.get_json() or {}
    new_parent_id = data.get("new_parent_id")
    move_descendants = data.get("move_descendants", True)

    if source_id == target_id:
        return jsonify({"error": "Source and target families are the same"}), 400

    # Verify both families exist
    src = db.execute("SELECT id FROM derivational_families WHERE id = ?", (source_id,)).fetchone()
    tgt = db.execute("SELECT id FROM derivational_families WHERE id = ?", (target_id,)).fetchone()
    if not src or not tgt:
        return jsonify({"error": "One or both families not found"}), 404

    # Verify lemma is in source family
    member = db.execute(
        "SELECT lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
        (lemma_id, source_id),
    ).fetchone()
    if not member:
        return jsonify({"error": "Lemma not in source family"}), 404

    # Collect IDs to move
    ids_to_move = [lemma_id]
    if move_descendants:
        # BFS to find all descendants in source family
        all_members = db.execute(
            "SELECT lemma_id, parent_lemma_id FROM lemma_families WHERE family_id = ?",
            (source_id,),
        ).fetchall()
        children_of = {}
        for m in all_members:
            pid = m["parent_lemma_id"]
            if pid:
                children_of.setdefault(pid, []).append(m["lemma_id"])
        queue = list(children_of.get(lemma_id, []))
        while queue:
            cid = queue.pop(0)
            ids_to_move.append(cid)
            queue.extend(children_of.get(cid, []))

    # Snapshot members before moving (for reversal)
    before_members = []
    for mid in ids_to_move:
        row = db.execute(
            "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
            (mid, source_id),
        ).fetchone()
        if row:
            before_members.append({"lemma_id": mid, "family_id": source_id, "relation": row["relation"], "parent_lemma_id": row["parent_lemma_id"]})

    # Move each member: delete from source, insert into target
    for mid in ids_to_move:
        row = db.execute(
            "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
            (mid, source_id),
        ).fetchone()
        if not row:
            continue

        # Determine parent in target family
        if mid == lemma_id:
            pid = new_parent_id  # the drop target
        else:
            # Keep original parent if that parent is also being moved
            pid = row["parent_lemma_id"] if row["parent_lemma_id"] in ids_to_move else new_parent_id

        # Remove from source
        db.execute(
            "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
            (mid, source_id),
        )

        # Check not already in target
        existing = db.execute(
            "SELECT 1 FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
            (mid, target_id),
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                (mid, target_id, row["relation"], pid),
            )

    # Clean up empty source family
    remaining = db.execute(
        "SELECT COUNT(*) as c FROM lemma_families WHERE family_id = ?", (source_id,)
    ).fetchone()["c"]
    source_deleted = False
    if remaining == 0:
        db.execute("DELETE FROM derivational_families WHERE id = ?", (source_id,))
        # Also clean up any family_links referencing the deleted family
        db.execute("DELETE FROM family_links WHERE family_id_a = ? OR family_id_b = ?", (source_id, source_id))
        source_deleted = True

    log_edit(db, "move_member_cross_family", source_id, lemma_id, {
        "target_family_id": target_id,
        "new_parent_id": new_parent_id,
        "ids_moved": ids_to_move,
        "source_deleted": source_deleted,
    }, before={"members": before_members})
    db.commit()

    return jsonify({"ok": True, "ids_moved": ids_to_move, "source_deleted": source_deleted})


# ─────────────────────────────────────────────
# GET /api/family/search?q=...
# Search families by root or label
# ─────────────────────────────────────────────
@app.route("/api/family/search")
def search_families():
    db = get_db()
    q = request.args.get("q", "").strip()
    limit = request.args.get("limit", 20, type=int)

    if not q:
        return jsonify({"results": []})

    rows = rows_to_list(db.execute(
        """SELECT df.id, df.root, df.label, COUNT(lf.lemma_id) as member_count
           FROM derivational_families df
           LEFT JOIN lemma_families lf ON lf.family_id = df.id
           WHERE df.root LIKE ? OR df.label LIKE ?
           GROUP BY df.id
           ORDER BY member_count DESC
           LIMIT ?""",
        (f"%{q}%", f"%{q}%", limit),
    ).fetchall())

    # Also include families that contain a lemma matching the query
    seen = {r["id"] for r in rows}
    if len(rows) < limit:
        by_lemma = rows_to_list(db.execute(
            """SELECT df.id, df.root, df.label, COUNT(lf2.lemma_id) as member_count
               FROM lemmas l
               JOIN lemma_families lf ON lf.lemma_id = l.id
               JOIN derivational_families df ON df.id = lf.family_id
               LEFT JOIN lemma_families lf2 ON lf2.family_id = df.id
               WHERE l.lemma LIKE ?
               GROUP BY df.id
               ORDER BY member_count DESC
               LIMIT ?""",
            (f"%{q}%", limit - len(rows)),
        ).fetchall())
        for r in by_lemma:
            if r["id"] not in seen:
                rows.append(r)
                seen.add(r["id"])

    return jsonify({"results": rows})


# ─────────────────────────────────────────────
# PATCH /api/family/<id>
# Rename a family's root and/or label
# Body: { root, label }
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>", methods=["PATCH"])
@require_superuser
def update_family(family_id):
    db = get_write_db()
    data = request.get_json()
    root = data.get("root")
    label = data.get("label")

    if not root and not label:
        return jsonify({"error": "root or label is required"}), 400

    # Capture before state
    old = db.execute("SELECT root, label FROM derivational_families WHERE id = ?", (family_id,)).fetchone()
    before_state = {"root": old["root"], "label": old["label"]} if old else {}

    updates, params = [], []
    if root:
        updates.append("root = ?")
        params.append(root.strip())
    if label:
        updates.append("label = ?")
        params.append(label.strip())
    params.append(family_id)

    db.execute(
        f"UPDATE derivational_families SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    log_edit(db, "update_family", family_id, None, {"root": root, "label": label}, before=before_state)
    db.commit()

    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# POST /api/family/<id>/link/<other_id>
# Create a cross-family link
# Body: { link_type, note }  (optional)
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/link/<int:other_id>", methods=["POST"])
@require_superuser
def create_family_link(family_id, other_id):
    if family_id == other_id:
        return jsonify({"error": "Cannot link a family to itself"}), 400
    db = get_write_db()
    data = request.get_json() or {}
    link_type = data.get("link_type", "related")
    note = data.get("note", "")
    # Ensure consistent ordering so UNIQUE constraint works
    a, b = min(family_id, other_id), max(family_id, other_id)
    # Check for existing link (for before state)
    old_link = db.execute("SELECT link_type, note FROM family_links WHERE family_id_a = ? AND family_id_b = ?", (a, b)).fetchone()
    before_state = {"link_type": old_link["link_type"], "note": old_link["note"]} if old_link else None
    try:
        db.execute(
            "INSERT INTO family_links (family_id_a, family_id_b, link_type, note) VALUES (?, ?, ?, ?)",
            (a, b, link_type, note),
        )
        log_edit(db, "link_families", family_id, None, {"other_id": other_id, "link_type": link_type}, before=before_state)
        db.commit()
    except sqlite3.IntegrityError:
        # Link already exists, update it
        db.execute(
            "UPDATE family_links SET link_type = ?, note = ? WHERE family_id_a = ? AND family_id_b = ?",
            (link_type, note, a, b),
        )
        log_edit(db, "link_families", family_id, None, {"other_id": other_id, "link_type": link_type}, before=before_state)
        db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# DELETE /api/family/<id>/link/<other_id>
# Remove a cross-family link
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/link/<int:other_id>", methods=["DELETE"])
@require_superuser
def delete_family_link(family_id, other_id):
    db = get_write_db()
    a, b = min(family_id, other_id), max(family_id, other_id)
    old_link = db.execute("SELECT link_type, note FROM family_links WHERE family_id_a = ? AND family_id_b = ?", (a, b)).fetchone()
    before_state = {"link_type": old_link["link_type"], "note": old_link["note"]} if old_link else None
    db.execute("DELETE FROM family_links WHERE family_id_a = ? AND family_id_b = ?", (a, b))
    log_edit(db, "unlink_families", family_id, None, {"other_id": other_id}, before=before_state)
    db.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────
# GET /api/family/<id>/linked
# Get a family plus all linked families
# ─────────────────────────────────────────────
@app.route("/api/family/<int:family_id>/linked")
def get_linked_families(family_id):
    db = get_db()

    seen_ids = {family_id}
    linked = []

    def fetch_family(fid):
        fam = db.execute(
            "SELECT id, root, label FROM derivational_families WHERE id = ?", (fid,),
        ).fetchone()
        if not fam:
            return None
        fam_dict = row_to_dict(fam)
        fam_dict["members"] = rows_to_list(db.execute(
            """SELECT l.id, l.lemma, l.pos, l.short_def,
                      l.total_occurrences, lf.relation, lf.parent_lemma_id
               FROM lemma_families lf
               JOIN lemmas l ON l.id = lf.lemma_id
               WHERE lf.family_id = ?
               ORDER BY l.total_occurrences DESC""",
            (fid,),
        ).fetchall())
        return fam_dict

    # 1) Explicit family_links
    links = db.execute(
        """SELECT family_id_a, family_id_b, link_type, note
           FROM family_links
           WHERE family_id_a = ? OR family_id_b = ?""",
        (family_id, family_id),
    ).fetchall()

    for row in links:
        r = row_to_dict(row)
        other_id = r["family_id_b"] if r["family_id_a"] == family_id else r["family_id_a"]
        if other_id in seen_ids:
            continue
        seen_ids.add(other_id)
        fam_dict = fetch_family(other_id)
        if not fam_dict:
            continue
        fam_dict["link_type"] = r["link_type"]
        fam_dict["note"] = r["note"]
        fam_dict["shared_members"] = []
        linked.append(fam_dict)

    # 2) Families connected through shared members (multi-family words)
    shared_rows = db.execute(
        """SELECT lf2.family_id, lf1.lemma_id
           FROM lemma_families lf1
           JOIN lemma_families lf2 ON lf2.lemma_id = lf1.lemma_id AND lf2.family_id != lf1.family_id
           WHERE lf1.family_id = ?""",
        (family_id,),
    ).fetchall()

    # Group by target family
    cross_map = {}  # family_id -> [lemma_id, ...]
    for r in shared_rows:
        rd = row_to_dict(r)
        fid = rd["family_id"]
        cross_map.setdefault(fid, []).append(rd["lemma_id"])

    for fid, lemma_ids in cross_map.items():
        # Check if this family was already added via explicit links
        existing = next((f for f in linked if f["id"] == fid), None)
        if existing:
            existing["shared_members"] = lemma_ids
            continue
        if fid in seen_ids:
            continue
        seen_ids.add(fid)
        fam_dict = fetch_family(fid)
        if not fam_dict:
            continue
        fam_dict["link_type"] = "shared word"
        fam_dict["note"] = None
        fam_dict["shared_members"] = lemma_ids
        linked.append(fam_dict)

    return jsonify({"linked_families": linked})
@app.route("/transcribe", methods=["POST"])
def transcribe():

    if "file" not in request.files:
        return jsonify({"error": "no file field"}), 400

    file = request.files["file"]

    tmpdir = tempfile.mkdtemp()

    input_path = os.path.join(tmpdir, "input.webm")
    wav_path = os.path.join(tmpdir, "audio.wav")
    file.save(input_path)
    if not os.path.exists(input_path):
        return jsonify({"error": "file not saved"}), 500

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        wav_path
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if not os.path.exists(wav_path):
        return jsonify({"error": "ffmpeg conversion failed"}), 500


    language = "en"
    if request.form.get("language").strip() == 'arabic':
        language = 'ar'
    if request.form.get("language").strip() == 'greek':
        language = 'el'

    with open(wav_path, "rb") as audio:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=audio,
            language=language
        )


    return jsonify({
        "text": transcript.text
    })

@app.route("/get_perception_task", methods=["GET"])
def get_perception_task():

    item_key = 'english'
    if request.args.get("arabic") is not None:
        item_key = 'arabic'
    if request.args.get("greek") is not None:
        item_key = 'greek'


    item = random.choice(languages[item_key])

    file_path = item["file"]
    transcription = item["transcription"]

    audio = AudioSegment.from_file(file_path)

    mp3_buffer = BytesIO()
    audio.export(mp3_buffer, format="mp3", bitrate="192k")
    mp3_buffer.seek(0)

    response = send_file(
        mp3_buffer,
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name="audio.mp3"
    )

    response.headers["X-Transcription"] = base64.b64encode(bytes(transcription, 'utf-8')).decode("ascii")
    response.headers["Access-Control-Expose-Headers"] = "X-Transcription"
    return response

@app.route("/get_production_task", methods=["GET"])
def get_production_task():
    transcription = random.choice(languages[request.args.get("language")])["transcription"]
    
    return jsonify({
        "text": base64.b64encode(bytes(transcription, 'utf-8')).decode("ascii")
    })


# ═══════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════

def ensure_schema():
    """Create tables needed for superuser editing (safe to call repeatedly)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS family_edit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        action TEXT NOT NULL,
        family_id INTEGER,
        lemma_id INTEGER,
        detail TEXT,
        user TEXT DEFAULT 'local'
    )""")
    conn.commit()

    # Add parent_lemma_id for hierarchical family trees
    try:
        conn.execute("ALTER TABLE lemma_families ADD COLUMN parent_lemma_id INTEGER REFERENCES lemmas(id)")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add before column for edit reversal
    try:
        conn.execute("ALTER TABLE family_edit_log ADD COLUMN before TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Cross-family links (for multi-root visualization)
    conn.execute("""CREATE TABLE IF NOT EXISTS family_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_id_a INTEGER NOT NULL REFERENCES derivational_families(id),
        family_id_b INTEGER NOT NULL REFERENCES derivational_families(id),
        link_type TEXT DEFAULT 'related',
        note TEXT,
        UNIQUE(family_id_a, family_id_b)
    )""")
    conn.commit()

    conn.close()


# ─────────────────────────────────────────────
# GET /api/edit-history
# Returns recent edits with parsed detail/before
# Query: ?limit=50&offset=0
# ─────────────────────────────────────────────
@app.route("/api/edit-history")
@require_superuser
def get_edit_history():
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    db = get_db()
    rows = db.execute("""
        SELECT e.id, e.timestamp, e.action, e.family_id, e.lemma_id,
               e.detail, e.before, e.user,
               l.lemma AS lemma_name,
               f.root AS family_root, f.label AS family_label
        FROM family_edit_log e
        LEFT JOIN lemmas l ON l.id = e.lemma_id
        LEFT JOIN derivational_families f ON f.id = e.family_id
        ORDER BY e.id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset)).fetchall()

    result = []
    for r in rows:
        entry = {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "action": r["action"],
            "family_id": r["family_id"],
            "lemma_id": r["lemma_id"],
            "user": r["user"],
            "lemma_name": r["lemma_name"],
            "family_root": r["family_root"],
            "family_label": r["family_label"],
            "detail": json.loads(r["detail"]) if r["detail"] else None,
            "before": json.loads(r["before"]) if r["before"] else None,
            "reversible": r["before"] is not None,
        }
        result.append(entry)

    total = db.execute("SELECT COUNT(*) as c FROM family_edit_log").fetchone()["c"]
    return jsonify({"edits": result, "total": total, "limit": limit, "offset": offset})


# ─────────────────────────────────────────────
# POST /api/edit-history/<id>/revert
# Reverts a single edit using its before-state
# ─────────────────────────────────────────────
@app.route("/api/edit-history/<int:edit_id>/revert", methods=["POST"])
@require_superuser
def revert_edit(edit_id):
    db = get_write_db()
    row = db.execute("SELECT * FROM family_edit_log WHERE id = ?", (edit_id,)).fetchone()
    if not row:
        return jsonify({"error": "Edit not found"}), 404

    before = json.loads(row["before"]) if row["before"] else None
    if not before:
        return jsonify({"error": "No before-state recorded — cannot revert"}), 400

    action = row["action"]
    family_id = row["family_id"]
    lemma_id = row["lemma_id"]
    detail = json.loads(row["detail"]) if row["detail"] else {}

    try:
        if action == "update_lemma":
            updates, params = [], []
            for col in ("short_def", "pos", "lsj_def"):
                if col in before:
                    updates.append(f"{col} = ?")
                    params.append(before[col])
            if updates:
                params.append(lemma_id)
                db.execute(f"UPDATE lemmas SET {', '.join(updates)} WHERE id = ?", params)

        elif action == "update_member_relation":
            db.execute(
                "UPDATE lemma_families SET relation = ?, parent_lemma_id = ? WHERE lemma_id = ? AND family_id = ?",
                (before.get("relation"), before.get("parent_lemma_id"), lemma_id, family_id),
            )

        elif action in ("update_member",):
            db.execute(
                "UPDATE lemma_families SET relation = ?, parent_lemma_id = ? WHERE lemma_id = ? AND family_id = ?",
                (before.get("relation"), before.get("parent_lemma_id"), lemma_id, family_id),
            )

        elif action == "remove_member":
            db.execute(
                "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                (lemma_id, family_id, before.get("relation"), before.get("parent_lemma_id")),
            )

        elif action == "add_member":
            db.execute(
                "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                (lemma_id, family_id),
            )

        elif action == "merge_families":
            other_id = before.get("merged_from")
            other_fam = before.get("other_family")
            members = before.get("members", [])
            if other_id and other_fam:
                db.execute(
                    "INSERT OR IGNORE INTO derivational_families (id, root, label) VALUES (?,?,?)",
                    (other_id, other_fam["root"], other_fam["label"]),
                )
                for m in members:
                    db.execute(
                        "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                        (m["lemma_id"], family_id),
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                        (m["lemma_id"], other_id, m["relation"], m["parent_lemma_id"]),
                    )

        elif action == "update_family":
            db.execute(
                "UPDATE derivational_families SET root = ?, label = ? WHERE id = ?",
                (before.get("root"), before.get("label"), family_id),
            )

        elif action == "create_link":
            other_id = detail.get("other_family_id")
            existing = before.get("existing_link")
            if existing:
                db.execute(
                    "UPDATE family_links SET link_type = ?, note = ? WHERE (family_id_a = ? AND family_id_b = ?) OR (family_id_a = ? AND family_id_b = ?)",
                    (existing["link_type"], existing["note"], family_id, other_id, other_id, family_id),
                )
            else:
                db.execute(
                    "DELETE FROM family_links WHERE (family_id_a = ? AND family_id_b = ?) OR (family_id_a = ? AND family_id_b = ?)",
                    (family_id, other_id, other_id, family_id),
                )

        elif action in ("delete_link", "remove_link", "unlink_families"):
            other_id = detail.get("other_family_id")
            db.execute(
                "INSERT OR IGNORE INTO family_links (family_id_a, family_id_b, link_type, note) VALUES (?,?,?,?)",
                (family_id, other_id, before.get("link_type", "related"), before.get("note")),
            )

        elif action == "split_to_linked_family":
            members_before = before.get("members_before", [])
            new_family_id = detail.get("new_family_id")
            if new_family_id:
                db.execute("DELETE FROM lemma_families WHERE family_id = ?", (new_family_id,))
                db.execute("DELETE FROM derivational_families WHERE id = ?", (new_family_id,))
                db.execute(
                    "DELETE FROM family_links WHERE family_id_a = ? OR family_id_b = ?",
                    (new_family_id, new_family_id),
                )
                db.execute("DELETE FROM lemma_families WHERE family_id = ?", (family_id,))
                for m in members_before:
                    db.execute(
                        "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                        (m["lemma_id"], family_id, m["relation"], m["parent_lemma_id"]),
                    )

        elif action == "split_family":
            members_before = before.get("members_before", [])
            new_family_id = detail.get("new_family_id")
            if new_family_id:
                db.execute("DELETE FROM lemma_families WHERE family_id = ?", (new_family_id,))
                db.execute("DELETE FROM derivational_families WHERE id = ?", (new_family_id,))
                db.execute(
                    "DELETE FROM family_links WHERE family_id_a = ? OR family_id_b = ?",
                    (new_family_id, new_family_id),
                )
                db.execute("DELETE FROM lemma_families WHERE family_id = ?", (family_id,))
                for m in members_before:
                    db.execute(
                        "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                        (m["lemma_id"], family_id, m["relation"], m["parent_lemma_id"]),
                    )

        elif action == "move_member_cross_family":
            source_fid = before.get("source_family_id")
            target_id = detail.get("target_family_id")
            members = before.get("members", [])
            for m in members:
                db.execute(
                    "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                    (m["lemma_id"], target_id),
                )
                db.execute(
                    "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                    (m["lemma_id"], source_fid, m["relation"], m["parent_lemma_id"]),
                )

        else:
            return jsonify({"error": f"Revert not implemented for action: {action}"}), 400

        log_edit(db, f"revert_{action}", family_id, lemma_id,
                 {"reverted_edit_id": edit_id, "original_detail": detail},
                 before=None)
        db.commit()
        return jsonify({"status": "ok", "reverted_edit_id": edit_id, "action": action})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# POST /api/admin/sync
# Replay edit operations from a local machine
# Requires GLOSSALEARN_ADMIN_TOKEN header
# Body: { "edits": [ { action, family_id, lemma_id, detail }, ... ] }
# ─────────────────────────────────────────────
@app.route("/api/admin/sync", methods=["POST"])
def admin_sync():
    token = request.headers.get("X-Admin-Token", "")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    edits = data.get("edits", [])
    if not edits:
        return jsonify({"error": "No edits provided"}), 400

    db = get_write_db()
    results = []

    for edit in edits:
        action = edit.get("action")
        family_id = edit.get("family_id")
        lemma_id = edit.get("lemma_id")
        detail = edit.get("detail", {})
        if isinstance(detail, str):
            detail = json.loads(detail)

        try:
            before = None

            if action == "update_member":
                row = db.execute(
                    "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                    (lemma_id, family_id),
                ).fetchone()
                if row:
                    before = {"relation": row["relation"], "parent_lemma_id": row["parent_lemma_id"]}
                updates, params = [], []
                if detail.get("relation") is not None:
                    updates.append("relation = ?")
                    params.append(detail["relation"])
                if "parent_lemma_id" in detail:
                    updates.append("parent_lemma_id = ?")
                    params.append(detail["parent_lemma_id"])
                if updates:
                    params.extend([lemma_id, family_id])
                    db.execute(
                        f"UPDATE lemma_families SET {', '.join(updates)} WHERE lemma_id = ? AND family_id = ?",
                        params,
                    )

            elif action == "add_member":
                db.execute(
                    "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                    (lemma_id, family_id, detail.get("relation", "derived"), detail.get("parent_lemma_id")),
                )

            elif action == "remove_member":
                row = db.execute(
                    "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                    (lemma_id, family_id),
                ).fetchone()
                if row:
                    before = {"relation": row["relation"], "parent_lemma_id": row["parent_lemma_id"]}
                db.execute(
                    "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                    (lemma_id, family_id),
                )
                remaining = db.execute(
                    "SELECT COUNT(*) as c FROM lemma_families WHERE family_id = ?", (family_id,)
                ).fetchone()["c"]
                if remaining == 0:
                    db.execute("DELETE FROM derivational_families WHERE id = ?", (family_id,))

            elif action == "merge":
                other_id = detail.get("merged_from")
                if other_id:
                    members = db.execute(
                        "SELECT lemma_id, relation, parent_lemma_id FROM lemma_families WHERE family_id = ?",
                        (other_id,),
                    ).fetchall()
                    other_fam = db.execute(
                        "SELECT root, label FROM derivational_families WHERE id = ?", (other_id,)
                    ).fetchone()
                    before = {
                        "merged_from": other_id,
                        "other_family": {"root": other_fam["root"], "label": other_fam["label"]} if other_fam else None,
                        "members": [{"lemma_id": m["lemma_id"], "relation": m["relation"], "parent_lemma_id": m["parent_lemma_id"]} for m in members],
                    }
                    for m in members:
                        existing = db.execute(
                            "SELECT 1 FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                            (m["lemma_id"], family_id),
                        ).fetchone()
                        if not existing:
                            db.execute(
                                "INSERT INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                                (m["lemma_id"], family_id, m["relation"], m["parent_lemma_id"]),
                            )
                    db.execute("DELETE FROM lemma_families WHERE family_id = ?", (other_id,))
                    db.execute("DELETE FROM derivational_families WHERE id = ?", (other_id,))

            elif action == "split_family":
                new_family_id = detail.get("new_family_id")
                if new_family_id:
                    # Snapshot members before split for revert
                    pre_members = db.execute(
                        "SELECT lemma_id, relation, parent_lemma_id FROM lemma_families WHERE family_id = ?",
                        (family_id,),
                    ).fetchall()
                    before = {
                        "source_family_id": family_id,
                        "members_before": [{"lemma_id": m["lemma_id"], "relation": m["relation"], "parent_lemma_id": m["parent_lemma_id"]} for m in pre_members],
                    }
                    # Collect the subtree via BFS
                    all_members = db.execute(
                        "SELECT lemma_id, parent_lemma_id, relation FROM lemma_families WHERE family_id = ?",
                        (family_id,),
                    ).fetchall()
                    children_of = {}
                    for m in all_members:
                        pid = m["parent_lemma_id"]
                        if pid:
                            children_of.setdefault(pid, []).append(m["lemma_id"])
                    ids_to_move = [lemma_id]
                    queue = list(children_of.get(lemma_id, []))
                    while queue:
                        cid = queue.pop(0)
                        ids_to_move.append(cid)
                        queue.extend(children_of.get(cid, []))

                    # Create new family
                    root_row = db.execute("SELECT lemma FROM lemmas WHERE id = ?", (lemma_id,)).fetchone()
                    root_label = root_row["lemma"] if root_row else str(lemma_id)
                    db.execute(
                        "INSERT OR IGNORE INTO derivational_families (id, root, label) VALUES (?,?,?)",
                        (new_family_id, root_label, f"Root: {root_label}"),
                    )
                    for mid in ids_to_move:
                        row = db.execute(
                            "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                            (mid, family_id),
                        ).fetchone()
                        if row:
                            pid = row["parent_lemma_id"] if row["parent_lemma_id"] in ids_to_move else None
                            db.execute(
                                "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                                (mid, new_family_id, row["relation"], pid),
                            )
                            db.execute(
                                "DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                                (mid, family_id),
                            )
                    # Create link
                    db.execute(
                        "INSERT OR IGNORE INTO family_links (family_id_a, family_id_b, link_type) VALUES (?,?,?)",
                        (family_id, new_family_id, "split"),
                    )

            elif action == "move_member_cross_family":
                target_id = detail.get("target_family_id")
                new_parent = detail.get("new_parent_id")
                ids_moved = detail.get("ids_moved", [lemma_id])
                before_members = []
                for mid in ids_moved:
                    brow = db.execute(
                        "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                        (mid, family_id),
                    ).fetchone()
                    if brow:
                        before_members.append({"lemma_id": mid, "relation": brow["relation"], "parent_lemma_id": brow["parent_lemma_id"]})
                before = {"source_family_id": family_id, "members": before_members}
                for mid in ids_moved:
                    row = db.execute(
                        "SELECT relation, parent_lemma_id FROM lemma_families WHERE lemma_id = ? AND family_id = ?",
                        (mid, family_id),
                    ).fetchone()
                    if row:
                        pid = new_parent if mid == lemma_id else (row["parent_lemma_id"] if row["parent_lemma_id"] in ids_moved else new_parent)
                        db.execute("DELETE FROM lemma_families WHERE lemma_id = ? AND family_id = ?", (mid, family_id))
                        db.execute(
                            "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation, parent_lemma_id) VALUES (?,?,?,?)",
                            (mid, target_id, row["relation"], pid),
                        )
                # Clean up empty source
                remaining = db.execute(
                    "SELECT COUNT(*) as c FROM lemma_families WHERE family_id = ?", (family_id,)
                ).fetchone()["c"]
                if remaining == 0:
                    db.execute("DELETE FROM derivational_families WHERE id = ?", (family_id,))
                    db.execute("DELETE FROM family_links WHERE family_id_a = ? OR family_id_b = ?", (family_id, family_id))

            elif action == "update_family":
                frow = db.execute(
                    "SELECT root, label FROM derivational_families WHERE id = ?", (family_id,)
                ).fetchone()
                if frow:
                    before = {"root": frow["root"], "label": frow["label"]}
                updates, params = [], []
                if detail.get("root") is not None:
                    updates.append("root = ?")
                    params.append(detail["root"])
                if detail.get("label") is not None:
                    updates.append("label = ?")
                    params.append(detail["label"])
                if updates:
                    params.append(family_id)
                    db.execute(
                        f"UPDATE derivational_families SET {', '.join(updates)} WHERE id = ?",
                        params,
                    )

            elif action == "create_link":
                other_id = detail.get("other_family_id")
                link_type = detail.get("link_type", "related")
                note = detail.get("note")
                if other_id:
                    existing = db.execute(
                        "SELECT link_type, note FROM family_links WHERE (family_id_a = ? AND family_id_b = ?) OR (family_id_a = ? AND family_id_b = ?)",
                        (family_id, other_id, other_id, family_id),
                    ).fetchone()
                    before = {"existing_link": {"link_type": existing["link_type"], "note": existing["note"]} if existing else None}
                    db.execute(
                        "INSERT OR REPLACE INTO family_links (family_id_a, family_id_b, link_type, note) VALUES (?,?,?,?)",
                        (family_id, other_id, link_type, note),
                    )

            elif action == "remove_link":
                other_id = detail.get("other_family_id")
                if other_id:
                    existing = db.execute(
                        "SELECT link_type, note FROM family_links WHERE (family_id_a = ? AND family_id_b = ?) OR (family_id_a = ? AND family_id_b = ?)",
                        (family_id, other_id, other_id, family_id),
                    ).fetchone()
                    if existing:
                        before = {"link_type": existing["link_type"], "note": existing["note"]}
                    db.execute(
                        "DELETE FROM family_links WHERE (family_id_a = ? AND family_id_b = ?) OR (family_id_a = ? AND family_id_b = ?)",
                        (family_id, other_id, other_id, family_id),
                    )

            else:
                results.append({"action": action, "status": "skipped", "reason": "unknown action"})
                continue

            log_edit(db, action, family_id, lemma_id, detail, before=before)
            results.append({"action": action, "family_id": family_id, "lemma_id": lemma_id, "status": "ok"})

        except Exception as e:
            results.append({"action": action, "family_id": family_id, "lemma_id": lemma_id, "status": "error", "error": str(e)})

    db.commit()
    ok_count = sum(1 for r in results if r.get("status") == "ok")
    return jsonify({"results": results, "synced": ok_count, "total": len(edits)})


def main():
    parser = argparse.ArgumentParser(description="Greek Vocabulary API Server")
    parser.add_argument("--port", type=int, default=5000, help="Port (default 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    if SUPERUSER_MODE:
        ensure_schema()

    db_size = os.path.getsize(DB_PATH) / (1024 * 1024)

    # Quick stats
    conn = sqlite3.connect(str(DB_PATH))
    stats = {}
    for t in ["works", "lemmas", "forms", "occurrences"]:
        stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    conn.close()

    print("═══════════════════════════════════════════════════════════")
    print("  Greek Vocabulary API Server")
    if SUPERUSER_MODE:
        print("  ** SUPERUSER MODE ENABLED — write endpoints active **")
    print(f"  Database: {DB_PATH} ({db_size:.0f} MB)")
    print(f"  {stats['lemmas']:,} lemmas · {stats['forms']:,} forms · "
          f"{stats['occurrences']:,} occurrences · {stats['works']} works")
    print("═══════════════════════════════════════════════════════════")
    print()
    print("  Endpoints:")
    print(f"    GET http://{args.host}:{args.port}/api/status")
    print(f"    GET http://{args.host}:{args.port}/api/works")
    print(f"    GET http://{args.host}:{args.port}/api/authors")
    print(f"    GET http://{args.host}:{args.port}/api/vocab?author=Homer")
    print(f"    GET http://{args.host}:{args.port}/api/vocab?author=New+Testament&min_freq=10")
    print(f"    GET http://{args.host}:{args.port}/api/lemma/1")
    print(f"    GET http://{args.host}:{args.port}/api/lemma/by-name/λόγος")
    print(f"    GET http://{args.host}:{args.port}/api/family/1")
    print(f"    GET http://{args.host}:{args.port}/api/search?q=justice")
    print(f"    GET http://{args.host}:{args.port}/api/compare?a=Homer&b=New+Testament&mode=shared")
    print(f"    GET http://{args.host}:{args.port}/api/pos-stats?author=Homer")
    print()
    print(f"  Starting on http://{args.host}:{args.port}")
    print("  Press Ctrl+C to stop")
    print()

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()