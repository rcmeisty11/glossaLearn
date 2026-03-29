#!/usr/bin/env python3
"""
sync_edits.py
Sync local superuser edits to the production database on aws

Usage:
    python3 sync_edits.py --preview          # Show pending edits
    python3 sync_edits.py --push             # Push edits to production
    python3 sync_edits.py --reset            # Reset sync pointer to current state
    python3 sync_edits.py --set-token TOKEN  # Save admin token locally

The script reads the local family_edit_log table, finds edits newer than
the last sync, and replays them against the production API.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
SYNC_FILE = Path(".last_sync_id")
TOKEN_FILE = Path(".admin_token")
PROD_API = "https://apiaws.glossalearn.com"


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    return db


def get_last_sync_id():
    if SYNC_FILE.exists():
        return int(SYNC_FILE.read_text().strip())
    return 0


def save_last_sync_id(sync_id):
    SYNC_FILE.write_text(str(sync_id))


def get_token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return ""


def get_pending_edits(db, since_id):
    rows = db.execute(
        "SELECT id, action, family_id, lemma_id, detail, timestamp FROM family_edit_log WHERE id > ? ORDER BY id",
        (since_id,),
    ).fetchall()
    return rows


def format_edit(row):
    action = row["action"]
    fid = row["family_id"]
    lid = row["lemma_id"]
    detail = json.loads(row["detail"]) if row["detail"] else {}
    ts = row["timestamp"]

    if action == "update_member":
        parent = detail.get("parent_lemma_id")
        rel = detail.get("relation")
        parts = []
        if parent is not None:
            parts.append(f"parent → {parent}")
        if rel is not None:
            parts.append(f"relation → {rel}")
        return f"[{ts}] UPDATE family {fid}, lemma {lid}: {', '.join(parts)}"

    elif action == "add_member":
        return f"[{ts}] ADD lemma {lid} to family {fid} (relation: {detail.get('relation')}, parent: {detail.get('parent_lemma_id')})"

    elif action == "remove_member":
        return f"[{ts}] REMOVE lemma {lid} from family {fid}"

    elif action == "merge":
        return f"[{ts}] MERGE family {detail.get('merged_from')} into family {fid} ({detail.get('members_moved', '?')} members)"

    elif action == "split_family":
        return f"[{ts}] SPLIT lemma {lid} from family {fid} → new family {detail.get('new_family_id')} ({detail.get('subtree_size', '?')} members)"

    elif action == "move_member_cross_family":
        return f"[{ts}] MOVE lemma {lid} from family {fid} → family {detail.get('target_family_id')} (parent: {detail.get('new_parent_id')})"

    elif action == "update_family":
        parts = []
        if detail.get("root"):
            parts.append(f"root → {detail['root']}")
        if detail.get("label"):
            parts.append(f"label → {detail['label']}")
        return f"[{ts}] UPDATE family {fid}: {', '.join(parts)}"

    elif action == "create_link":
        return f"[{ts}] LINK family {fid} ↔ family {detail.get('other_family_id')} ({detail.get('link_type', 'related')})"

    elif action == "remove_link":
        return f"[{ts}] UNLINK family {fid} ↔ family {detail.get('other_family_id')}"

    else:
        return f"[{ts}] {action} family={fid} lemma={lid} detail={detail}"


def push_edits(edits, token, api_url):
    import urllib.request
    import urllib.error

    translated = []
    for row in edits:
        action = row["action"]
        detail = json.loads(row["detail"]) if row["detail"] else {}

        # Translate local action names to what the server expects
        if action == "link_families":
            action = "create_link"
            detail = {"other_family_id": detail.get("other_id"), "link_type": detail.get("link_type", "related")}
        elif action == "unlink_families":
            action = "remove_link"
            detail = {"other_family_id": detail.get("other_id")}
        elif action == "SPLIT":
            action = "split_family"

        translated.append({
            "action": action,
            "family_id": row["family_id"],
            "lemma_id": row["lemma_id"],
            "detail": detail,
        })

    payload = {"edits": translated}

    req = urllib.request.Request(
        f"{api_url}/api/admin/sync",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Admin-Token": token,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: HTTP {e.code} — {body}")
        return None
    except urllib.error.URLError as e:
        print(f"ERROR: Connection failed — {e.reason}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Sync local edits to production")
    parser.add_argument("--preview", action="store_true", help="Show pending edits without pushing")
    parser.add_argument("--push", action="store_true", help="Push pending edits to production")
    parser.add_argument("--reset", action="store_true", help="Reset sync pointer to latest edit ID")
    parser.add_argument("--set-token", metavar="TOKEN", help="Save admin token locally")
    parser.add_argument("--api", default=PROD_API, help=f"Production API URL (default: {PROD_API})")
    args = parser.parse_args()

    api_url = args.api

    if args.set_token:
        TOKEN_FILE.write_text(args.set_token)
        print(f"Token saved to {TOKEN_FILE}")
        return

    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = get_db()
    last_id = get_last_sync_id()

    if args.reset:
        max_id = db.execute("SELECT MAX(id) FROM family_edit_log").fetchone()[0] or 0
        save_last_sync_id(max_id)
        print(f"Sync pointer reset to edit #{max_id}")
        return

    edits = get_pending_edits(db, last_id)

    if not edits:
        print("No pending edits to sync.")
        return

    print(f"\n{len(edits)} edit(s) since last sync (#{last_id}):\n")
    for row in edits:
        print(f"  {row['id']}. {format_edit(row)}")
    print()

    if args.preview:
        return

    if args.push:
        token = get_token()
        if not token:
            print("ERROR: No admin token set. Run:")
            print(f"  python3 sync_edits.py --set-token YOUR_TOKEN")
            sys.exit(1)

        confirm = input(f"Push {len(edits)} edit(s) to {api_url}? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

        print("Pushing...")
        result = push_edits(edits, token, api_url)
        if result:
            print(f"\nDone! {result.get('synced', 0)}/{result.get('total', 0)} edits synced.")
            # Check for errors
            for r in result.get("results", []):
                if r.get("status") != "ok":
                    print(f"  WARNING: {r.get('action')} family={r.get('family_id')} lemma={r.get('lemma_id')}: {r.get('status')} — {r.get('error', r.get('reason', ''))}")

            # Update sync pointer to the last edit ID
            max_id = edits[-1]["id"]
            save_last_sync_id(max_id)
            print(f"Sync pointer updated to edit #{max_id}")
        else:
            print("Sync failed. No changes were saved.")
    else:
        print("Use --push to sync these edits, or --preview to just view them.")


if __name__ == "__main__":
    main()
