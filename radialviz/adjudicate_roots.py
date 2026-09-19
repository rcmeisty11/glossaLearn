#!/usr/bin/env python3
"""
adjudicate_roots.py
Structural adjudication of two questions that string matching cannot settle.

A. "Roots should not contain affixes."
   432 families have a root that *starts with* a preverb's letters. Some really
   are wrongly-rooted (συλλέγω = σύν+λέγω, κατηγορ- = κατά+ἀγορ-, πρότερος =
   πρό+τερος). Most are false positives — genuine unanalysable stems that merely
   begin with those letters: δίδωμι is not διά+δωμι, ἔρχομαι is not ἐν+χομαι,
   ἐλεύθερος, ἐργάζομαι, ὑφαίνω, καθαίρω, ἀπατάω, ἐπίσταμαι are all simplex.
   Applying the rule mechanically would corrupt the data, so each is judged.

B. Root collisions with two or more distinct accented spellings, held back by
   cleanup_dupes.py because they are usually different words: εἰμί "to be" vs
   εἶμι "to go", ὅρος "boundary" vs ὄρος "mountain", ὥρα "season" vs ὤρα "care",
   ὁδ- "road" vs ὀδ- "tooth". Merging those would be wrong.

Uses the Batch API with Sonnet 5.

Usage:
    python3 adjudicate_roots.py build
    python3 adjudicate_roots.py submit
    python3 adjudicate_roots.py status
    python3 adjudicate_roots.py fetch
    python3 adjudicate_roots.py report
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).parent
AUDIT = HERE / "family_audit"
DB_PATH = HERE / "greek_vocab.db"
REQ_FILE = AUDIT / "roots_batch_requests.json"
IDS_FILE = AUDIT / "roots_batch_ids.txt"
RES_FILE = AUDIT / "roots_batch_results.jsonl"

MODEL = "claude-sonnet-5"
PER_REQUEST = 8

SYSTEM_A = """You are a specialist in Ancient Greek historical morphology.

Each item is a derivational word-family whose ROOT string happens to begin with the letters of a Greek preverb/preposition. Decide whether the root genuinely CONTAINS that prefix as a separable morpheme, or whether the resemblance is accidental.

A root should name the bare lexical morpheme. It should NOT carry a prefix.

Genuinely prefixed (the root should be corrected):
- συλλέγω  = σύν + λέγω
- κατηγορέω = κατά + ἀγορ- (ἀγορεύω)
- πρότερος = πρό + comparative -τερος
- ἔγκατα   = ἐν + κατα

NOT prefixed — simplex stems that merely start with those letters:
- δίδωμι (reduplicated √δω-, not διά+δωμι)
- ἔρχομαι, ἐλαύνω, ἐλεύθερος, ἐργάζομαι, ἑλίσσω (not ἐν+...)
- διδάσκω, διδάσκαλος (reduplicated √δακ-, not διά+...)
- ἐπίσταμαι (lexicalised; synchronically simplex)
- ὑφαίνω, καθαίρω, ἀπατάω, ἀρνέομαι

Judge by real morphology, not by spelling. When a compound is fully lexicalised but still transparently analysable (ἔγκατα, κατηγορέω), answer "true" and give the underlying root.

Return ONLY a JSON array, no prose, no markdown fence:
[{"family_id":123,"prefixed":true|false,"prefix":"<preposition or null>","true_root":"<bare root, or null>","confidence":0.0-1.0,"reason":"<12 words max>"}]"""

SYSTEM_B = """You are a specialist in Ancient Greek lexicography.

Each item is a group of word-families whose root strings are identical once accents and breathings are stripped, but which are spelled differently WITH accents. Decide which of them denote the SAME lexical root and should be merged, and which are DIFFERENT words that must stay separate.

Accent and breathing are phonemic in Greek. Different words:
- εἰμί "to be" vs εἶμι "to go"
- ὅρος "boundary" vs ὄρος "mountain"
- ὥρα "season, hour" vs ὤρα "care, concern"
- ὁδ- "road" (ὁδός) vs ὀδ- "tooth" (ὀδούς)
- Κήρ "doom-goddess" vs κῆρ "heart"

Same word, mere spelling variants (merge):
- an unaccented stem beside its accented form (αδελφ / ἀδελφ)
- ἅμαξα / ἄμαξα (attested variants of one noun)

When an UNACCENTED spelling sits beside two or more distinct accented words, decide which one it belongs to — or say "unclear" if its members are split between them.

You are given each family's id, root, label and sample members. Use the members as the primary evidence.

Return ONLY a JSON array, no prose, no markdown fence:
[{"bare_root":"...","merge_groups":[[id,id],...],"keep_separate":[id,...],"unclear":[id,...],"confidence":0.0-1.0,"reason":"<20 words max>"}]"""


def members_of(db, fid, limit=10):
    return [r[0] for r in db.execute(
        """SELECT l.lemma FROM lemma_families lf JOIN lemmas l ON l.id = lf.lemma_id
           WHERE lf.family_id = ? ORDER BY l.total_occurrences DESC LIMIT ?""",
        (fid, limit))]


def cmd_build(args):
    db = sqlite3.connect(str(DB_PATH))
    reqs = []

    # --- Part A: affixed roots ---
    cands = json.loads((AUDIT / "affixed_roots_candidates.json").read_text(encoding="utf-8"))
    live = []
    for c in cands:
        if db.execute("SELECT 1 FROM derivational_families WHERE id=?",
                      (c["family_id"],)).fetchone():
            c["members_sample"] = members_of(db, c["family_id"])
            live.append(c)
    for i in range(0, len(live), PER_REQUEST):
        chunk = live[i:i + PER_REQUEST]
        payload = [{"family_id": c["family_id"], "root": c["root"], "label": c["label"],
                    "apparent_prefix": c["apparent_prefix"],
                    "remainder_after_stripping": c["stripped"],
                    "members": c["members_sample"]} for c in chunk]
        reqs.append({
            "custom_id": f"rootA-{i:05d}",
            "params": {"model": MODEL, "max_tokens": 8000,
                       "system": [{"type": "text", "text": SYSTEM_A,
                                   "cache_control": {"type": "ephemeral"}}],
                       "messages": [{"role": "user", "content":
                                     "Judge each family:\n\n" +
                                     json.dumps(payload, ensure_ascii=False, indent=1)}]},
        })

    # --- Part B: held accent collisions ---
    held = json.loads((AUDIT / "held_for_review_roots.json").read_text(encoding="utf-8"))
    payload = []
    for h in held:
        fams = []
        for spelling, fids in h["spellings"].items():
            for fid in fids:
                row = db.execute(
                    "SELECT root, label FROM derivational_families WHERE id=?",
                    (fid,)).fetchone()
                if row:
                    fams.append({"family_id": fid, "root": row[0], "label": row[1],
                                 "members": members_of(db, fid)})
        if fams:
            payload.append({"bare_root": h["bare_root"], "families": fams})
    if payload:
        reqs.append({
            "custom_id": "rootB-00000",
            "params": {"model": MODEL, "max_tokens": 8000,
                       "system": [{"type": "text", "text": SYSTEM_B,
                                   "cache_control": {"type": "ephemeral"}}],
                       "messages": [{"role": "user", "content":
                                     "Decide each group:\n\n" +
                                     json.dumps(payload, ensure_ascii=False, indent=1)}]},
        })

    AUDIT.mkdir(exist_ok=True)
    REQ_FILE.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
    print(f"Part A — affixed-root families still live : {len(live)}")
    print(f"Part B — held collision groups            : {len(payload)}")
    print(f"requests built                            : {len(reqs)}")
    print(f"-> {REQ_FILE.relative_to(HERE)}")
    db.close()


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set in this shell.")
    import anthropic
    return anthropic.Anthropic()


def cmd_submit(args):
    client = get_client()
    reqs = json.loads(REQ_FILE.read_text(encoding="utf-8"))
    batch = client.messages.batches.create(requests=reqs)
    IDS_FILE.write_text(batch.id + "\n")
    print(f"submitted batch {batch.id} with {len(reqs)} requests")


def cmd_status(args):
    client = get_client()
    b = client.messages.batches.retrieve(IDS_FILE.read_text().strip())
    c = b.request_counts
    print(f"{b.id}  {b.processing_status}  succeeded={c.succeeded} "
          f"errored={c.errored} processing={c.processing}")


def cmd_fetch(args):
    client = get_client()
    bid = IDS_FILE.read_text().strip()
    b = client.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        sys.exit(f"batch not finished ({b.processing_status})")
    n = 0
    ti = to = 0
    with RES_FILE.open("w", encoding="utf-8") as fh:
        for result in client.messages.batches.results(bid):
            rec = {"custom_id": result.custom_id, "type": result.result.type}
            if result.result.type == "succeeded":
                msg = result.result.message
                rec["text"] = "".join(b.text for b in msg.content if b.type == "text")
                ti += msg.usage.input_tokens
                to += msg.usage.output_tokens
            else:
                rec["error"] = str(getattr(result.result, "error", ""))
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    cost = ti / 1e6 * 1.00 + to / 1e6 * 5.00
    print(f"fetched {n} results -> {RES_FILE.relative_to(HERE)}")
    print(f"ACTUAL: input {ti:,} output {to:,}  cost ${cost:.2f}")


def cmd_report(args):
    import re
    A, B = [], []
    for line in RES_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("type") != "succeeded":
            continue
        txt = re.sub(r"^```(?:json)?|```$", "", r["text"].strip(), flags=re.M).strip()
        try:
            parsed = json.loads(txt)
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", txt, re.S)
            parsed = json.loads(m.group(0)) if m else []
        (A if r["custom_id"].startswith("rootA") else B).extend(parsed)

    pref = [x for x in A if x.get("prefixed")]
    print(f"Part A — {len(A)} families judged")
    print(f"  genuinely prefixed (root needs fixing): {len(pref)}")
    print(f"  correctly simplex (leave alone)       : {len(A) - len(pref)}")
    for x in sorted(pref, key=lambda v: -float(v.get("confidence", 0)))[:25]:
        print(f"    fid={x['family_id']:6d} {x.get('prefix','?'):5s} + "
              f"{x.get('true_root')!r:14s} conf={x.get('confidence')}  {x.get('reason','')}")
    (AUDIT / "roots_partA_verdicts.json").write_text(
        json.dumps(A, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nPart B — {len(B)} collision groups judged")
    for x in B:
        print(f"  {x.get('bare_root'):12s} merge={x.get('merge_groups')} "
              f"separate={x.get('keep_separate')} unclear={x.get('unclear')}")
        print(f"      {x.get('reason','')}")
    (AUDIT / "roots_partB_verdicts.json").write_text(
        json.dumps(B, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> family_audit/roots_partA_verdicts.json, roots_partB_verdicts.json")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("submit", cmd_submit),
                     ("status", cmd_status), ("fetch", cmd_fetch),
                     ("report", cmd_report)):
        sub.add_parser(name).set_defaults(func=fn)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
