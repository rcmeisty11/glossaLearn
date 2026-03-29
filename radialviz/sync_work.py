#!/usr/bin/env python3
"""
sync_work.py — Push a newly ingested work from local DB to Lightsail

Usage:
    python3 sync_work.py --title "Didache"              # preview
    python3 sync_work.py --title "Didache" --push        # push to production

This script:
  1. Finds the work in local greek_vocab.db
  2. Exports the work row, new lemmas, forms, occurrences, work_lemma_counts as SQL
  3. SCPs the SQL file to Lightsail
  4. Runs it on the remote database via SSH
"""

import argparse
import sqlite3
import sys
import subprocess
import tempfile
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
REMOTE_USER = "ec2-user"
REMOTE_IPV6 = "2600:1f16:977:fe00:b263:8c48:20f3:38cf"
REMOTE_DB = "/home/ec2-user/data/greek_vocab.db"
SSH_KEY = Path.home() / "Desktop" / "mykey.pem"


def escape_sql(val):
    """Escape a value for SQL insertion."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val).replace("'", "''")
    return f"'{s}'"


def main():
    parser = argparse.ArgumentParser(description="Sync a new work to Lightsail")
    parser.add_argument("--title", required=True, help="Title of the work to sync")
    parser.add_argument("--push", action="store_true", help="Actually push (default is preview)")
    parser.add_argument("--db", default=str(DB_PATH), help="Local database path")
    parser.add_argument("--ssh-key", default=str(SSH_KEY), help="SSH key path")
    parser.add_argument("--sql-only", action="store_true", help="Just write the SQL file, don't push")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Find the work
    cur.execute("SELECT * FROM works WHERE title = ?", (args.title,))
    work = cur.fetchone()
    if not work:
        print(f"ERROR: No work found with title '{args.title}'")
        print("Available works:")
        for r in cur.execute("SELECT id, title, author FROM works ORDER BY id DESC LIMIT 20"):
            print(f"  {r['id']}: {r['title']} ({r['author']})")
        sys.exit(1)

    work_id = work["id"]
    print(f"Found work: {work['title']} by {work['author']} (id={work_id})")

    # Count data
    occ_count = cur.execute("SELECT COUNT(*) FROM occurrences WHERE work_id = ?", (work_id,)).fetchone()[0]
    wlc_count = cur.execute("SELECT COUNT(*) FROM work_lemma_counts WHERE work_id = ?", (work_id,)).fetchone()[0]

    print(f"  Occurrences:      {occ_count}")
    print(f"  Work-lemma pairs: {wlc_count}")

    # Find lemmas that appear in this work — we need to ensure they exist on remote
    lemma_ids = [r[0] for r in cur.execute(
        "SELECT DISTINCT lemma_id FROM work_lemma_counts WHERE work_id = ?", (work_id,)
    )]
    print(f"  Unique lemmas:    {len(lemma_ids)}")

    # Find forms used in this work's occurrences
    form_ids = [r[0] for r in cur.execute(
        "SELECT DISTINCT form_id FROM occurrences WHERE work_id = ? AND form_id IS NOT NULL", (work_id,)
    )]
    print(f"  Unique forms:     {len(form_ids)}")

    if not args.push and not args.sql_only:
        print(f"\n[PREVIEW] Run with --push to send to Lightsail, or --sql-only to export SQL file.")
        conn.close()
        return

    # Build SQL
    print("\nGenerating SQL...")
    lines = []
    lines.append("BEGIN TRANSACTION;")

    # 1. Insert work (skip if exists)
    lines.append(f"INSERT OR IGNORE INTO works (id, filename, cts_urn, author_code, work_code, author, title, corpus) VALUES ("
                 f"{work['id']}, {escape_sql(work['filename'])}, {escape_sql(work['cts_urn'])}, "
                 f"{escape_sql(work['author_code'])}, {escape_sql(work['work_code'])}, "
                 f"{escape_sql(work['author'])}, {escape_sql(work['title'])}, {escape_sql(work['corpus'])});")

    # 2. Insert lemmas (OR IGNORE so existing ones are skipped)
    print("  Exporting lemmas...")
    for lid in lemma_ids:
        row = cur.execute("SELECT * FROM lemmas WHERE id = ?", (lid,)).fetchone()
        if row:
            lines.append(
                f"INSERT OR IGNORE INTO lemmas (id, lemma, pos, short_def, lsj_def, middle_liddell, total_occurrences, frequency_rank) VALUES ("
                f"{row['id']}, {escape_sql(row['lemma'])}, {escape_sql(row['pos'])}, "
                f"{escape_sql(row['short_def'])}, {escape_sql(row['lsj_def'])}, "
                f"{escape_sql(row['middle_liddell'])}, {row['total_occurrences']}, "
                f"{escape_sql(row['frequency_rank'])});"
            )

    # 3. Insert forms (OR IGNORE)
    print("  Exporting forms...")
    for fid in form_ids:
        row = cur.execute("SELECT * FROM forms WHERE id = ?", (fid,)).fetchone()
        if row:
            lines.append(
                f"INSERT OR IGNORE INTO forms (id, lemma_id, form, morph_tag, pos, person, number, tense, mood, voice, gender, gram_case, degree) VALUES ("
                f"{row['id']}, {row['lemma_id']}, {escape_sql(row['form'])}, "
                f"{escape_sql(row['morph_tag'])}, {escape_sql(row['pos'])}, "
                f"{escape_sql(row['person'])}, {escape_sql(row['number'])}, "
                f"{escape_sql(row['tense'])}, {escape_sql(row['mood'])}, "
                f"{escape_sql(row['voice'])}, {escape_sql(row['gender'])}, "
                f"{escape_sql(row['gram_case'])}, {escape_sql(row['degree'])});"
            )

    # 4. Insert occurrences
    print("  Exporting occurrences...")
    for row in cur.execute("SELECT * FROM occurrences WHERE work_id = ?", (work_id,)):
        lines.append(
            f"INSERT INTO occurrences (lemma_id, form_id, work_id, passage, sentence_n, token_n) VALUES ("
            f"{row['lemma_id']}, {escape_sql(row['form_id'])}, {row['work_id']}, "
            f"{escape_sql(row['passage'])}, {escape_sql(row['sentence_n'])}, {escape_sql(row['token_n'])});"
        )

    # 5. Insert work_lemma_counts
    print("  Exporting work_lemma_counts...")
    for row in cur.execute("SELECT * FROM work_lemma_counts WHERE work_id = ?", (work_id,)):
        lines.append(
            f"INSERT OR REPLACE INTO work_lemma_counts (work_id, lemma_id, count) VALUES ("
            f"{row['work_id']}, {row['lemma_id']}, {row['count']});"
        )

    # 6. Insert sentences
    sent_count = cur.execute("SELECT COUNT(*) FROM sentences WHERE work_id = ?", (work_id,)).fetchone()[0]
    print(f"  Exporting sentences... ({sent_count})")
    for row in cur.execute("SELECT * FROM sentences WHERE work_id = ?", (work_id,)):
        lines.append(
            f"INSERT INTO sentences (id, work_id, passage, sentence_pos, sentence_text) VALUES ("
            f"{row['id']}, {row['work_id']}, {escape_sql(row['passage'])}, "
            f"{escape_sql(row['sentence_pos'])}, {escape_sql(row['sentence_text'])});"
        )

    # 7. Insert sentence_lemmas
    print("  Exporting sentence_lemmas...")
    for row in cur.execute("""
        SELECT sl.sentence_id, sl.lemma_id FROM sentence_lemmas sl
        JOIN sentences s ON s.id = sl.sentence_id
        WHERE s.work_id = ?
    """, (work_id,)):
        lines.append(
            f"INSERT OR IGNORE INTO sentence_lemmas (sentence_id, lemma_id) VALUES ("
            f"{row['sentence_id']}, {row['lemma_id']});"
        )

    # 8. Update total_occurrences for affected lemmas
    lines.append(f"""
UPDATE lemmas SET total_occurrences = (
    SELECT COALESCE(SUM(count), 0) FROM work_lemma_counts WHERE lemma_id = lemmas.id
) WHERE id IN (SELECT DISTINCT lemma_id FROM work_lemma_counts WHERE work_id = {work_id});
""")

    lines.append("COMMIT;")

    sql_content = "\n".join(lines)
    sql_size = len(sql_content.encode("utf-8"))
    print(f"\n  SQL size: {sql_size / 1024:.0f} KB ({len(lines)} statements)")

    conn.close()

    if args.sql_only:
        outfile = f"sync_{args.title.lower().replace(' ', '_')}.sql"
        Path(outfile).write_text(sql_content, encoding="utf-8")
        print(f"\nSQL written to: {outfile}")
        return

    # Push to Lightsail
    print(f"\nPushing to Lightsail...")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(sql_content)
        tmp_sql = f.name

    try:
        # SCP the SQL file
        remote_sql = "/tmp/sync_work.sql"
        ssh_target = f"{REMOTE_USER}@{REMOTE_IPV6}"
        # SCP needs brackets around IPv6 addresses in the destination
        scp_target = f"{REMOTE_USER}@[{REMOTE_IPV6}]"

        print(f"  Uploading SQL file...")
        scp_cmd = ["scp", "-6", "-i", args.ssh_key, tmp_sql, f"{scp_target}:{remote_sql}"]
        result = subprocess.run(scp_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR (scp): {result.stderr}")
            sys.exit(1)

        # Run the SQL on remote
        print(f"  Executing SQL on remote database...")
        ssh_cmd = ["ssh", "-6", "-i", args.ssh_key, ssh_target,
                    f"sqlite3 {REMOTE_DB} < {remote_sql} && echo 'SUCCESS' || echo 'FAILED'"]
        result = subprocess.run(ssh_cmd, capture_output=True, text=True)
        print(f"  Remote output: {result.stdout.strip()}")
        if result.stderr:
            print(f"  Remote stderr: {result.stderr.strip()}")

        # Cleanup remote file
        subprocess.run(["ssh", "-6", "-i", args.ssh_key, ssh_target, f"rm -f {remote_sql}"],
                       capture_output=True)

        if "SUCCESS" in result.stdout:
            print(f"\nDone! '{args.title}' is now on production.")
        else:
            print(f"\nSync may have failed. Check the remote database.")

    finally:
        Path(tmp_sql).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
