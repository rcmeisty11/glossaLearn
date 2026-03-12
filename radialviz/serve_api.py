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

try:
    from flask import Flask, request, jsonify, g
    from flask_cors import CORS
except ImportError:
    print("ERROR: Flask not installed.")
    print("  pip3 install flask flask-cors")
    sys.exit(1)

DB_PATH = Path("./greek_vocab.db")

if not DB_PATH.exists():
    print(f"ERROR: {DB_PATH} not found. Run build_database.py first.")
    sys.exit(1)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from the frontend

# Superuser mode: enables write endpoints for manual family editing
SUPERUSER_MODE = os.environ.get("GLOSSALEARN_SUPERUSER", "0") == "1"


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
    limit = min(limit, 2000)

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

    # Derivational family
    family = None
    fam_row = db.execute(
        """SELECT df.id, df.root, df.label, lf.relation
           FROM lemma_families lf
           JOIN derivational_families df ON df.id = lf.family_id
           WHERE lf.lemma_id = ?
           LIMIT 1""",
        (lemma_id,),
    ).fetchone()

    if fam_row:
        fam_dict = row_to_dict(fam_row)
        # Get all members of this family
        members = rows_to_list(db.execute(
            """SELECT l.id, l.lemma, l.pos, l.short_def,
                      l.total_occurrences, lf.relation, lf.parent_lemma_id
               FROM lemma_families lf
               JOIN lemmas l ON l.id = lf.lemma_id
               WHERE lf.family_id = ?
               ORDER BY l.total_occurrences DESC""",
            (fam_dict["id"],),
        ).fetchall())
        family = {
            "id": fam_dict["id"],
            "root": fam_dict["root"],
            "label": fam_dict["label"],
            "relation": fam_dict["relation"],
            "members": members,
        }

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

def log_edit(db, action, family_id=None, lemma_id=None, detail=None):
    """Append a row to the audit log."""
    db.execute(
        "INSERT INTO family_edit_log (action, family_id, lemma_id, detail) VALUES (?,?,?,?)",
        (action, family_id, lemma_id, json.dumps(detail) if detail else None),
    )


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
    other = db.execute(
        """SELECT lf.family_id, df.label FROM lemma_families lf
           JOIN derivational_families df ON df.id = lf.family_id
           WHERE lf.lemma_id = ?""",
        (lemma_id,),
    ).fetchone()
    if other:
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

    log_edit(db, "remove_member", family_id, lemma_id, {"family_deleted": family_deleted})
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

    # Delete the old family
    db.execute("DELETE FROM lemma_families WHERE family_id = ?", (other_id,))
    db.execute("DELETE FROM derivational_families WHERE id = ?", (other_id,))

    log_edit(db, "merge", family_id, None, {
        "merged_from": other_id,
        "merged_label": other["label"],
        "members_moved": len(other_members),
    })
    db.commit()

    return get_family(family_id)


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
    log_edit(db, "update_member", family_id, lemma_id, {"relation": relation, "parent_lemma_id": parent_lemma_id})
    db.commit()

    return jsonify({"ok": True})


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
    log_edit(db, "update_family", family_id, None, {"root": root, "label": label})
    db.commit()

    return jsonify({"ok": True})


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

    conn.close()


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