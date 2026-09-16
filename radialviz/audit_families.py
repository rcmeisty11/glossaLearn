#!/usr/bin/env python3
"""
audit_families.py — LLM-assisted audit of derivational family groupings.

Uses Claude Opus 5 (via the Anthropic Message Batches API, 50% cheaper than
sync calls) to review every non-singleton derivational family in the local
greek_vocab.db, flagging members that don't belong, wrong parent/relation
links, and merge/split/link/rename candidates between neighboring families.

Nothing is applied blindly. Proposed edits are staged; conservative,
high-confidence member-level fixes (remove/reparent/change_relation) can be
auto-applied through the *local* superuser API — the same code path a human
edit takes, so every change lands in family_edit_log exactly like a manual
edit and is reversible the same way. Family-level edits (rename/merge/split/
link/unlink) and anything not high-confidence always go to a review queue.

Usage:
    python3 audit_families.py extract               # pull DB -> family_audit/families.json + manifest
    python3 audit_families.py smoke-test             # sync-API check on a few groups before spending on the batch
    python3 audit_families.py submit                 # submit the full batch job
    python3 audit_families.py status                 # poll batch job status
    python3 audit_families.py fetch                  # download + parse results once the batch has ended
    python3 audit_families.py apply [--dry-run] [--api http://127.0.0.1:5050]
                                                      # classify proposals; auto-apply conservative ones,
                                                      # queue the rest to family_audit/review_queue.json

Requires: ANTHROPIC_API_KEY in the environment (for extract/smoke-test/submit/status/fetch),
and for `apply`, a local serve_api.py running with GLOSSALEARN_SUPERUSER=1 against this
same greek_vocab.db (never point this at production).
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
OUT_DIR = Path("./family_audit")
MODEL = "claude-opus-5"

LARGE_FAMILY_THRESHOLD = 20   # families bigger than this get their own request
GROUP_TOKEN_BUDGET = 6000     # rough input-token budget per grouped request
MAX_FAMILIES_PER_GROUP = 40

BATCH_ID_FILE = OUT_DIR / "batch_id.txt"
FAMILIES_FILE = OUT_DIR / "families.json"
MANIFEST_FILE = OUT_DIR / "manifest.json"
RESULTS_FILE = OUT_DIR / "results.jsonl"
PROPOSALS_FILE = OUT_DIR / "proposals.json"
REVIEW_QUEUE_FILE = OUT_DIR / "review_queue.json"
REVIEW_DATA_FILE = OUT_DIR / "review_data.json"
APPLIED_LOG_FILE = OUT_DIR / "applied_log.json"


# ═══════════════════════════════════════════════════════════════
# DB EXTRACTION
# ═══════════════════════════════════════════════════════════════

def get_conn():
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run this from the project root.")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_families(conn):
    """Return {family_id: {root, label, members:[...], links:[...]}} for non-singleton families."""
    fam_rows = conn.execute("SELECT id, root, label FROM derivational_families").fetchall()
    families = {r["id"]: {"root": r["root"], "label": r["label"], "members": [], "links": []}
                for r in fam_rows}

    member_rows = conn.execute("""
        SELECT lf.family_id, lf.lemma_id, lf.relation, lf.parent_lemma_id,
               l.lemma, l.pos, l.short_def
        FROM lemma_families lf
        JOIN lemmas l ON l.id = lf.lemma_id
    """).fetchall()
    for r in member_rows:
        fam = families.get(r["family_id"])
        if fam is None:
            continue
        fam["members"].append({
            "lemma_id": r["lemma_id"],
            "lemma": r["lemma"],
            "pos": r["pos"],
            "short_def": (r["short_def"] or "").strip(),
            "relation": r["relation"],
            "parent_lemma_id": r["parent_lemma_id"],
        })

    link_rows = conn.execute("""
        SELECT fl.family_id_a, fl.family_id_b, fl.link_type, fl.note,
               fa.root AS root_a, fb.root AS root_b
        FROM family_links fl
        JOIN derivational_families fa ON fa.id = fl.family_id_a
        JOIN derivational_families fb ON fb.id = fl.family_id_b
    """).fetchall()
    for r in link_rows:
        if r["family_id_a"] in families:
            families[r["family_id_a"]]["links"].append(
                {"other_family_id": r["family_id_b"], "other_root": r["root_b"], "link_type": r["link_type"]})
        if r["family_id_b"] in families:
            families[r["family_id_b"]]["links"].append(
                {"other_family_id": r["family_id_a"], "other_root": r["root_a"], "link_type": r["link_type"]})

    # Drop singletons (nothing to audit — a lone word has no connections to get wrong)
    return {fid: f for fid, f in families.items() if len(f["members"]) > 1}


def family_payload(fid, fam):
    """Compact JSON-able dict sent to the model for one family."""
    members = sorted(fam["members"], key=lambda m: (m["relation"] != "root", m["lemma"]))
    payload = {
        "family_id": fid,
        "root": fam["root"],
        "label": fam["label"],
        "members": [
            {
                "lemma_id": m["lemma_id"],
                "lemma": m["lemma"],
                "pos": m["pos"],
                "def": m["short_def"],
                "relation": m["relation"],
                "parent_lemma_id": m["parent_lemma_id"],
            }
            for m in members
        ],
    }
    if fam["links"]:
        payload["existing_links"] = fam["links"]
    return payload


def estimate_tokens(obj):
    """Rough char-based estimate; refined against real usage in smoke-test."""
    return len(json.dumps(obj, ensure_ascii=False)) / 3.0


def sort_key(root):
    # Strip accents/breathing marks so near-duplicate roots (e.g. βαλ- vs βάλ-) sort adjacent.
    return "".join(c for c in unicodedata.normalize("NFD", root or "") if unicodedata.category(c) != "Mn")


def chunk_families(families):
    """Returns list of groups; each group is a list of family_ids.
    Large families always get their own group. Others are packed together,
    sorted by (accent-stripped) root, so likely duplicates/merge-candidates
    land in the same request."""
    large_ids = [fid for fid, f in families.items() if len(f["members"]) > LARGE_FAMILY_THRESHOLD]
    small_ids = [fid for fid, f in families.items() if len(f["members"]) <= LARGE_FAMILY_THRESHOLD]
    small_ids.sort(key=lambda fid: sort_key(families[fid]["root"]))

    groups = [[fid] for fid in large_ids]

    current, current_tokens = [], 0.0
    for fid in small_ids:
        t = estimate_tokens(family_payload(fid, families[fid]))
        if current and (current_tokens + t > GROUP_TOKEN_BUDGET or len(current) >= MAX_FAMILIES_PER_GROUP):
            groups.append(current)
            current, current_tokens = [], 0.0
        current.append(fid)
        current_tokens += t
    if current:
        groups.append(current)

    return groups


def cmd_extract(args):
    OUT_DIR.mkdir(exist_ok=True)
    conn = get_conn()
    all_fams = conn.execute("SELECT COUNT(*) FROM derivational_families").fetchone()[0]
    families = fetch_families(conn)
    n_singletons = all_fams - len(families)
    groups = chunk_families(families)

    FAMILIES_FILE.write_text(json.dumps(
        {str(fid): f for fid, f in families.items()}, ensure_ascii=False))
    MANIFEST_FILE.write_text(json.dumps(groups))

    large_groups = [g for g in groups if len(g) == 1 and len(families[g[0]]["members"]) > LARGE_FAMILY_THRESHOLD]
    total_est_tokens = sum(estimate_tokens(family_payload(fid, families[fid]))
                            for fid in families)
    n_reviews = len(families)

    print(f"Families to audit: {n_reviews} (skipped {n_singletons} singletons)")
    print(f"Requests to send:  {len(groups)}  ({len(large_groups)} single-family, "
          f"{len(groups) - len(large_groups)} grouped)")
    print(f"Estimated input tokens (family data only, excludes system prompt): ~{int(total_est_tokens):,}")
    sys_tokens_est = len(SYSTEM_PROMPT) / 3.0
    total_with_sys = total_est_tokens + sys_tokens_est * len(groups)
    print(f"Estimated input tokens incl. system prompt per request: ~{int(total_with_sys):,}")
    in_cost = total_with_sys / 1_000_000 * 5.0
    out_cost_est = n_reviews * 60 / 1_000_000 * 25.0  # ~60 output tokens/family, refine via smoke-test
    print(f"Rough standard-API cost estimate: ~${in_cost + out_cost_est:.2f} "
          f"(~${(in_cost + out_cost_est) / 2:.2f} with Batch API's 50% discount)")
    print(f"\nWrote {FAMILIES_FILE} and {MANIFEST_FILE}. Run `smoke-test` next.")


# ═══════════════════════════════════════════════════════════════
# PROMPT + SCHEMA
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert in Ancient Greek historical linguistics and derivational \
morphology, auditing a database of "derivational families" — clusters of Greek lemmas that \
were algorithmically grouped (by stem-stripping heuristics and Perseus Morpheus stem data) on \
the assumption that they share a common root or derivational chain, e.g. βάλλω -> διαβάλλω -> \
διάβολος. That automated process makes real mistakes: unrelated words swept in by a coincidental \
shared substring, plausible-looking but etymologically false groupings, wrong parent/child \
derivation links within a family, and occasionally a "junk drawer" family that absorbed dozens \
or hundreds of unrelated words under one root.

You will be given a JSON object with a "families" array. Each family has a family_id, a root \
stem, a label, and a members array (lemma_id, lemma, pos, a short English gloss, its assigned \
relation to the root, and parent_lemma_id — which other member, if any, it derives from within \
this family). A family may also list existing_links to other families already marked as related.

For each family, decide:

1. MEMBER-LEVEL ISSUES — for any member that is wrong, propose exactly one action:
   - "remove": the word does not actually derive from this root at all (false cognate, homonym,
     coincidental stem overlap, or simply misplaced). Use when it doesn't belong in this family
     under any relation.
   - "reparent": the word does derive within this family, but its parent_lemma_id is wrong —
     it should attach to a different member of the SAME family (or to the root itself, in which
     case set new_parent_lemma_id to null). new_parent_lemma_id must be a lemma_id present in
     this same family's members.
   - "change_relation": the derivation is correct but the relation label is imprecise or wrong
     (e.g. labeled "derived" when it's really a specific compound or prefix relation). Prefer
     reusing relation strings already seen elsewhere in this batch when they fit (e.g. "compound
     (κατα)", "prefix ἀ- (privative)"); coin a short new one only if nothing fits.
   Only propose an action when you are actually confident something is wrong — most members of
   most families are correctly placed, and "no issue" is the right answer far more often than not.

2. FAMILY-LEVEL ISSUES:
   - "rename": root and/or label are misleading or wrong for what the family actually contains.
   - "merge": this family and another family_id **present in this same batch** are really the
     same root/family and should be combined (give merge_target_family_id).
   - "split": a specific member (by lemma_id) roots a subtree within this family that is
     etymologically distinct enough to deserve its own linked family (give split_lemma_id — that
     member and its descendants would be split out).
   - "link": this family and another family_id **present in this same batch** are etymologically
     related but should stay separate (e.g. share a root with a sound change, or one is a
     compound base of the other) — propose a cross-family link.
   - "unlink": an existing_link listed for this family is wrong and should be removed.
   A family with an implausibly large member count (dozens to hundreds) is very likely a mis-merged
   catch-all — scrutinize it hard for subgroups that should be removed or split out, rather than
   assuming its size reflects real derivational breadth.

CONFIDENCE — be honest and conservative:
   - "high": you are confident this is a real error a careful Greek philologist would agree with.
   - "medium": likely an issue, but a specialist might reasonably disagree or want more context.
   - "low": worth a second look, but you are genuinely unsure.
Only high-confidence member-level fixes may be applied automatically downstream — do not inflate
confidence to get something actioned. When in doubt, use "low" or "medium" and explain why in
`reason` (one concise sentence, citing the actual linguistic reasoning: attested etymology,
sound changes, semantic drift, or why a resemblance is coincidental).

Merges and links may ONLY reference a family_id that appears in the current batch — you cannot
see or reference families outside this request.

Respond with structured JSON matching the provided schema exactly. Do not include any text
outside the JSON. Every family in the input must appear exactly once in "reviews", even if its
verdict is "ok" with empty edit lists."""


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "family_id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["ok", "needs_changes"]},
                    "note": {"type": "string"},
                    "member_edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lemma_id": {"type": "integer"},
                                "lemma": {"type": "string"},
                                "action": {"type": "string", "enum": ["remove", "reparent", "change_relation"]},
                                "new_parent_lemma_id": {"type": ["integer", "null"]},
                                "new_relation": {"type": ["string", "null"]},
                                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                                "reason": {"type": "string"},
                            },
                            "required": ["lemma_id", "lemma", "action", "new_parent_lemma_id",
                                         "new_relation", "confidence", "reason"],
                            "additionalProperties": False,
                        },
                    },
                    "family_edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string",
                                           "enum": ["rename", "merge", "split", "link", "unlink"]},
                                "new_root": {"type": ["string", "null"]},
                                "new_label": {"type": ["string", "null"]},
                                "merge_target_family_id": {"type": ["integer", "null"]},
                                "split_lemma_id": {"type": ["integer", "null"]},
                                "link_target_family_id": {"type": ["integer", "null"]},
                                "link_type": {"type": ["string", "null"]},
                                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                                "reason": {"type": "string"},
                            },
                            "required": ["action", "new_root", "new_label", "merge_target_family_id",
                                         "split_lemma_id", "link_target_family_id", "link_type",
                                         "confidence", "reason"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["family_id", "verdict", "note", "member_edits", "family_edits"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["reviews"],
    "additionalProperties": False,
}


def build_message_params(family_ids, families):
    payloads = [family_payload(fid, families[fid]) for fid in family_ids]
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "system": [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        "output_config": {"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}, "effort": "high"},
        "messages": [{"role": "user", "content": json.dumps({"families": payloads}, ensure_ascii=False)}],
    }


def load_families_and_groups():
    if not FAMILIES_FILE.exists() or not MANIFEST_FILE.exists():
        sys.exit("ERROR: run `extract` first.")
    families = {int(k): v for k, v in json.loads(FAMILIES_FILE.read_text()).items()}
    groups = json.loads(MANIFEST_FILE.read_text())
    return families, groups


def get_client():
    try:
        import anthropic
    except ImportError:
        sys.exit("ERROR: `anthropic` package not installed. Use the project's .audit_venv.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set in this shell.")
    return anthropic.Anthropic()


# ═══════════════════════════════════════════════════════════════
# SMOKE TEST — validate prompt/schema on the sync API before batching
# ═══════════════════════════════════════════════════════════════

def cmd_smoke_test(args):
    families, groups = load_families_and_groups()
    client = get_client()

    sample_groups = groups[args.start: args.start + args.n]
    total_in, total_out = 0, 0
    for i, group in enumerate(sample_groups):
        params = build_message_params(group, families)
        print(f"\n--- group {i+1}/{len(sample_groups)}: {len(group)} families "
              f"({', '.join(families[fid]['root'] for fid in group)}) ---")
        resp = client.messages.create(**params)
        total_in += resp.usage.input_tokens + (resp.usage.cache_creation_input_tokens or 0) \
            + (resp.usage.cache_read_input_tokens or 0)
        total_out += resp.usage.output_tokens
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  !! JSON parse failed: {e}\n  Raw (first 500 chars): {text[:500]}")
            continue
        n_reviews = len(data.get("reviews", []))
        n_flagged = sum(1 for r in data["reviews"] if r["verdict"] == "needs_changes")
        print(f"  ok: {n_reviews} reviews returned, {n_flagged} flagged needs_changes")
        for r in data["reviews"]:
            if r["verdict"] == "needs_changes":
                print(f"    family {r['family_id']}: {r['note']}")
                for me in r["member_edits"]:
                    print(f"      member  {me['action']:>15} lemma={me['lemma']} "
                          f"conf={me['confidence']}: {me['reason']}")
                for fe in r["family_edits"]:
                    print(f"      family  {fe['action']:>15} conf={fe['confidence']}: {fe['reason']}")
        print(f"  usage: {resp.usage.input_tokens} in "
              f"(+{resp.usage.cache_read_input_tokens or 0} cached) / {resp.usage.output_tokens} out")

    n_families_sampled = sum(len(g) for g in sample_groups)
    if n_families_sampled:
        per_family_in = total_in / n_families_sampled
        per_family_out = total_out / n_families_sampled
        n_all = sum(len(f["members"]) for f in families.values()) and len(families)
        proj_in = per_family_in * len(families)
        proj_out = per_family_out * len(families)
        std_cost = proj_in / 1e6 * 5.0 + proj_out / 1e6 * 25.0
        print(f"\n=== Projection from this sample across all {len(families)} families ===")
        print(f"~{int(proj_in):,} input tokens, ~{int(proj_out):,} output tokens")
        print(f"Standard API: ~${std_cost:.2f}   |   Batch API (-50%): ~${std_cost/2:.2f}")


def _sample_usage(client, groups, families, n):
    """Call the sync API on n groups, return list of (n_families, in_tok, out_tok)."""
    stats = []
    for group in groups[:n]:
        params = build_message_params(group, families)
        resp = client.messages.create(**params)
        total_in = (resp.usage.input_tokens + (resp.usage.cache_creation_input_tokens or 0)
                    + (resp.usage.cache_read_input_tokens or 0))
        stats.append((len(group), total_in, resp.usage.output_tokens))
    return stats


def cmd_estimate(args):
    families, groups = load_families_and_groups()
    client = get_client()

    import random
    rng = random.Random(42)
    large_groups = [g for g in groups if len(g) == 1
                     and len(families[g[0]]["members"]) > LARGE_FAMILY_THRESHOLD]
    grouped_groups = [g for g in groups if len(g) > 1]
    large_sample = rng.sample(large_groups, min(args.n, len(large_groups)))
    grouped_sample = rng.sample(grouped_groups, min(args.n, len(grouped_groups)))

    print(f"Sampling {len(large_sample)} large-family requests (of {len(large_groups)} total)...")
    large_stats = _sample_usage(client, large_sample, families, len(large_sample))
    print(f"Sampling {len(grouped_sample)} grouped requests (of {len(grouped_groups)} total)...")
    grouped_stats = _sample_usage(client, grouped_sample, families, len(grouped_sample))

    def avg(stats, idx):
        return sum(s[idx] for s in stats) / len(stats)

    large_in_avg, large_out_avg = avg(large_stats, 1), avg(large_stats, 2)
    grp_in_avg, grp_out_avg = avg(grouped_stats, 1), avg(grouped_stats, 2)

    total_in = large_in_avg * len(large_groups) + grp_in_avg * len(grouped_groups)
    total_out = large_out_avg * len(large_groups) + grp_out_avg * len(grouped_groups)
    std_cost = total_in / 1e6 * 5.0 + total_out / 1e6 * 25.0

    print(f"\nLarge-family requests: {len(large_groups)} x (~{large_in_avg:.0f} in, ~{large_out_avg:.0f} out)")
    print(f"Grouped requests:      {len(grouped_groups)} x (~{grp_in_avg:.0f} in, ~{grp_out_avg:.0f} out)")
    print(f"\nProjected total: ~{int(total_in):,} input tokens, ~{int(total_out):,} output tokens")
    print(f"Standard API: ~${std_cost:.2f}   |   Batch API (-50%): ~${std_cost/2:.2f}")


# ═══════════════════════════════════════════════════════════════
# BATCH SUBMIT / STATUS / FETCH
# ═══════════════════════════════════════════════════════════════

def cmd_submit(args):
    families, groups = load_families_and_groups()
    client = get_client()

    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests_ = []
    for i, group in enumerate(groups):
        is_large = len(group) == 1 and len(families[group[0]]["members"]) > LARGE_FAMILY_THRESHOLD
        custom_id = f"large_{group[0]}" if is_large else f"grp_{i:05d}"
        params = build_message_params(group, families)
        requests_.append(Request(custom_id=custom_id, params=MessageCreateParamsNonStreaming(**params)))

    print(f"Submitting {len(requests_)} requests covering {len(families)} families...")
    batch = client.messages.batches.create(requests=requests_)
    BATCH_ID_FILE.write_text(batch.id)
    print(f"Batch ID: {batch.id}")
    print(f"Status:   {batch.processing_status}")
    print(f"\nSaved to {BATCH_ID_FILE}. Check progress with `status`, then `fetch` once ended.")


def cmd_status(args):
    if not BATCH_ID_FILE.exists():
        sys.exit("ERROR: no batch submitted yet (missing family_audit/batch_id.txt).")
    client = get_client()
    batch = client.messages.batches.retrieve(BATCH_ID_FILE.read_text().strip())
    print(f"Status: {batch.processing_status}")
    rc = batch.request_counts
    print(f"  processing={rc.processing} succeeded={rc.succeeded} errored={rc.errored} "
          f"canceled={rc.canceled} expired={rc.expired}")
    if batch.processing_status == "ended":
        print("\nBatch has ended — run `fetch` to download results.")


def cmd_fetch(args):
    if not BATCH_ID_FILE.exists():
        sys.exit("ERROR: no batch submitted yet.")
    client = get_client()
    batch_id = BATCH_ID_FILE.read_text().strip()
    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        sys.exit(f"Batch not finished yet (status={batch.processing_status}). Run `status` to check.")

    families, _ = load_families_and_groups()
    all_reviews = {}
    n_ok, n_err = 0, 0
    with open(RESULTS_FILE, "w") as raw_f:
        for result in client.messages.batches.results(batch_id):
            raw_f.write(json.dumps({"custom_id": result.custom_id, "type": result.result.type}) + "\n")
            if result.result.type != "succeeded":
                n_err += 1
                print(f"  !! {result.custom_id}: {result.result.type}")
                continue
            text = next((b.text for b in result.result.message.content if b.type == "text"), "")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                n_err += 1
                print(f"  !! {result.custom_id}: invalid JSON in response")
                continue
            for review in data.get("reviews", []):
                fid = review["family_id"]
                if fid not in families:
                    continue  # model hallucinated an id outside the batch — drop it
                all_reviews[fid] = review
            n_ok += 1

    PROPOSALS_FILE.write_text(json.dumps(all_reviews, ensure_ascii=False, indent=1))
    print(f"\n{n_ok} requests succeeded, {n_err} failed.")
    print(f"Got reviews for {len(all_reviews)}/{len(families)} families -> {PROPOSALS_FILE}")
    missing = set(families) - set(all_reviews)
    if missing:
        print(f"WARNING: {len(missing)} families got no review (failed/dropped requests): "
              f"{sorted(missing)[:20]}{'...' if len(missing) > 20 else ''}")


# ═══════════════════════════════════════════════════════════════
# APPLY — classify + write
# ═══════════════════════════════════════════════════════════════

def classify_and_apply(args):
    if not PROPOSALS_FILE.exists():
        sys.exit("ERROR: run `fetch` first.")
    families = {int(k): v for k, v in json.loads(FAMILIES_FILE.read_text()).items()}
    reviews = json.loads(PROPOSALS_FILE.read_text())

    applied, queued, errors = [], [], []

    session = None
    if not args.dry_run:
        import requests
        session = requests.Session()

    def api(method, path, **kw):
        url = args.api.rstrip("/") + path
        if args.dry_run:
            return {"ok": True, "_dry_run": True}
        resp = session.request(method, url, timeout=15, **kw)
        resp.raise_for_status()
        return resp.json()

    for fid_str, review in reviews.items():
        fid = int(fid_str)
        fam = families.get(fid)
        member_ids = {m["lemma_id"] for m in fam["members"]} if fam else set()

        for me in review.get("member_edits", []):
            item = {"family_id": fid, "family_root": fam["root"] if fam else None, **me}
            auto = me["confidence"] == "high" and me["action"] in ("remove", "reparent", "change_relation")
            if auto and me["action"] == "reparent" and me["new_parent_lemma_id"] is not None \
                    and me["new_parent_lemma_id"] not in member_ids:
                auto = False  # model pointed outside the family — refuse to auto-apply
            if not auto:
                queued.append({"type": "member", **item})
                continue
            try:
                if me["action"] == "remove":
                    api("DELETE", f"/api/family/{fid}/member/{me['lemma_id']}")
                elif me["action"] == "reparent":
                    api("PATCH", f"/api/family/{fid}/member/{me['lemma_id']}",
                        json={"parent_lemma_id": me["new_parent_lemma_id"]})
                elif me["action"] == "change_relation":
                    api("PATCH", f"/api/family/{fid}/member/{me['lemma_id']}",
                        json={"relation": me["new_relation"]})
                applied.append({"type": "member", **item})
            except Exception as e:
                errors.append({"type": "member", "error": str(e), **item})

        # Family-level edits always go to the review queue (conservative policy) —
        # merges/splits/renames/links reshape the tree and are never auto-applied.
        for fe in review.get("family_edits", []):
            queued.append({"type": "family", "family_id": fid, "family_root": fam["root"] if fam else None, **fe})

    APPLIED_LOG_FILE.write_text(json.dumps(applied, ensure_ascii=False, indent=1))
    REVIEW_QUEUE_FILE.write_text(json.dumps(queued, ensure_ascii=False, indent=1))

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Applied: {len(applied)}   "
          f"Queued for review: {len(queued)}   Errors: {len(errors)}")
    if errors:
        print(f"See errors above; first few: {errors[:5]}")
    print(f"-> {APPLIED_LOG_FILE}\n-> {REVIEW_QUEUE_FILE}")


def cmd_apply(args):
    classify_and_apply(args)


# ═══════════════════════════════════════════════════════════════
# APPLY DECISIONS — apply reviewer-approved items from the review queue
# (member AND family-level edits), in dependency-safe order.
# ═══════════════════════════════════════════════════════════════

ORDER = ["remove", "change_relation", "reparent", "unlink", "link", "rename", "split", "merge"]


def cmd_apply_decisions(args):
    decisions = json.loads(Path(args.decisions).read_text())
    review = json.loads(REVIEW_DATA_FILE.read_text())
    by_id = {item["id"]: item for item in review}

    approved = [by_id[i] for i, d in decisions.items() if d == "approved" and i in by_id]
    approved.sort(key=lambda item: ORDER.index(item["action"]) if item["action"] in ORDER else 99)

    print(f"{len(approved)} approved items to apply (dry_run={args.dry_run})")

    session = None
    if not args.dry_run:
        import requests
        session = requests.Session()

    def api(method, path, **kw):
        if args.dry_run:
            return {"ok": True, "_dry_run": True}
        url = args.api.rstrip("/") + path
        resp = session.request(method, url, timeout=15, **kw)
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    applied, errors = [], []
    for item in approved:
        fid, action = item["family_id"], item["action"]
        try:
            if action == "remove":
                api("DELETE", f"/api/family/{fid}/member/{item['lemma_id']}")
            elif action == "reparent":
                api("PATCH", f"/api/family/{fid}/member/{item['lemma_id']}",
                    json={"parent_lemma_id": item["new_parent_lemma_id"]})
            elif action == "change_relation":
                api("PATCH", f"/api/family/{fid}/member/{item['lemma_id']}",
                    json={"relation": item["new_relation"]})
            elif action == "rename":
                body = {}
                if item.get("new_root"):
                    body["root"] = item["new_root"]
                if item.get("new_label"):
                    body["label"] = item["new_label"]
                if body:
                    api("PATCH", f"/api/family/{fid}", json=body)
            elif action == "merge":
                api("POST", f"/api/family/{fid}/merge/{item['merge_target_family_id']}")
            elif action == "split":
                api("POST", f"/api/family/{fid}/split/{item['split_lemma_id']}")
            elif action == "link":
                api("POST", f"/api/family/{fid}/link/{item['link_target_family_id']}",
                    json={"link_type": item.get("link_type") or "related"})
            elif action == "unlink":
                api("DELETE", f"/api/family/{fid}/link/{item['link_target_family_id']}")
            else:
                raise RuntimeError(f"unknown action {action}")
            applied.append(item)
        except Exception as e:
            errors.append({"item": item, "error": str(e)})

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Applied: {len(applied)}   Errors: {len(errors)}")
    by_action = {}
    for a in applied:
        by_action[a["action"]] = by_action.get(a["action"], 0) + 1
    for k, v in sorted(by_action.items()):
        print(f"  {k}: {v}")
    if errors:
        print(f"\n{len(errors)} errors (first 10):")
        for e in errors[:10]:
            print(f"  family {e['item']['family_id']} {e['item']['action']}: {e['error']}")

    Path(OUT_DIR / "decisions_applied_log.json").write_text(json.dumps(applied, ensure_ascii=False, indent=1))
    Path(OUT_DIR / "decisions_apply_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("extract").set_defaults(func=cmd_extract)

    p = sub.add_parser("smoke-test")
    p.add_argument("--n", type=int, default=3, help="number of request-groups to sample")
    p.add_argument("--start", type=int, default=0, help="index into the group manifest to start sampling from")
    p.set_defaults(func=cmd_smoke_test)

    p = sub.add_parser("estimate")
    p.add_argument("--n", type=int, default=3, help="requests to sample from each of the large/grouped buckets")
    p.set_defaults(func=cmd_estimate)

    sub.add_parser("submit").set_defaults(func=cmd_submit)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("fetch").set_defaults(func=cmd_fetch)

    p = sub.add_parser("apply")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--api", default="http://127.0.0.1:5050")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("apply-decisions")
    p.add_argument("--decisions", required=True, help="JSON file mapping item id -> 'approved'/'rejected'")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--api", default="http://127.0.0.1:8080")
    p.set_defaults(func=cmd_apply_decisions)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
