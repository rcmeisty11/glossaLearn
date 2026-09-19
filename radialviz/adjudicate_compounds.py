#!/usr/bin/env python3
"""
adjudicate_compounds.py
Step 4 — decide which candidate family links for each compound are real.

Everything cheap has already been done for free by this point:
  * cleanup_dupes.py       removed 1,381 junk + 99 duplicate families
  * build_prepositions.py  added 5,040 preverb links from existing relations
  * extract_lsj_compounds.py  mined LSJ's own hyphenated compound splits

What remains genuinely needs judgment, because string matching is confidently
wrong a quarter to half of the time: συγκάλυμμα is σύν+κάλυμμα, not σύ; ἀνευρίσκω
is ἀνά+εὑρίσκω, not ἄνευ; ἀρνητικός is from ἀρνέομαι, not ἀρνός 'lamb';
-ίτης in φαλαγγίτης is a suffix, not the word ἴτης. So no string-matched link is
applied without adjudication.

Uses the Batch API (50% off). Reads ANTHROPIC_API_KEY from the environment.

Usage:
    python3 adjudicate_compounds.py build
    python3 adjudicate_compounds.py estimate --sample 25
    python3 adjudicate_compounds.py submit --limit 150      # committed tranche
    python3 adjudicate_compounds.py status
    python3 adjudicate_compounds.py fetch
    python3 adjudicate_compounds.py apply --min-confidence 0.8
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
AUDIT = HERE / "family_audit"
DB_PATH = HERE / "greek_vocab.db"

REQUESTS_FILE = AUDIT / "compound_batch_requests.json"
BATCH_IDS_FILE = AUDIT / "compound_batch_ids.txt"
RESULTS_FILE = AUDIT / "compound_batch_results.jsonl"
VERDICTS_FILE = AUDIT / "compound_verdicts.json"

MODEL = "claude-sonnet-5"
COMPOUNDS_PER_REQUEST = 6

SYSTEM_PROMPT = """You are a specialist in Ancient Greek historical and derivational morphology.

For each compound word you are given a list of CANDIDATE word families. Decide, for each candidate, whether the compound genuinely belongs to that family — that is, whether the family's root really is one of the compound's constituent morphemes.

Evidence you are given:
- `lsj_split`: how Liddell-Scott-Jones hyphenates the headword. LSJ's hyphen is usually the real morpheme boundary, but LSJ also uses it for plain stem+suffix splits, so it is strong evidence, not proof.
- `via_lemma`: the lemma that caused this family to be suggested, found by string matching.

Reject a candidate when the match is not genuine derivation. The common failure modes:
- A preverb misread as a different word: συγ- in συγκάλυμμα is σύν, NOT the pronoun σύ. ἀν- in ἀνευρίσκω is ἀνά, NOT ἄνευ.
- A homonym or unrelated root: ἀρνητικός is from ἀρνέομαι "deny", NOT ἀρνός "lamb".
- A derivational suffix mistaken for a word: -ίτης in φαλαγγίτης is a suffix, NOT the noun ἴτης. Likewise -τειρα, -τρίς, -ωδης.
- A proper noun matched by coincidence: ἀνδρό- is ἀνήρ, NOT the island Ἄνδρος.
- Coincidental letter overlap with no morphological relation at all: δίδωμι is not διά + δωμι; ἔρχομαι is not ἐν + χομαι.

Accept when the compound really does contain that root, including when the root appears in its combining form (λογο-/λογία for λόγος, ἀνδρο- for ἀνήρ, πυρι- for πῦρ) and when a regular sound change applies (σύν → συμ-/συγ-/συλ-, ἐκ → ἐξ-, ἀπό → ἀφ-).

Return ONLY a JSON array, no prose, no markdown fence. One object per (headword, family_id) pair you were given:

[{"headword":"...","family_id":123,"verdict":"accept"|"reject","confidence":0.0-1.0,"reason":"<12 words max>"}]

Give every pair a verdict. Use confidence below 0.7 when genuinely unsure."""


def load_actionable():
    path = AUDIT / "adjudication_input.json"
    if not path.exists():
        sys.exit("ERROR: run extract_lsj_compounds.py first (adjudication_input.json missing)")
    return json.loads(path.read_text(encoding="utf-8"))


def make_user_block(items):
    payload = []
    for c in items:
        payload.append({
            "headword": c["headword"],
            "pos": c["pos"],
            "occurrences": c["occurrences"],
            "lsj_split": c["lsj_split"],
            "already_in_families": [
                f["root"] for f in c["current_families"]
            ],
            "candidates": [
                {"family_id": f["family_id"], "root": f["root"],
                 "label": f["label"], "via_lemma": f["via_lemma"]}
                for f in c["candidate_families"]
            ],
        })
    return ("Adjudicate every candidate for each compound below.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=1))


def cmd_build(args):
    data = load_actionable()
    # Highest value first: compounds currently stranded in a single family.
    data.sort(key=lambda c: (len(c["current_family_ids"]), -c["occurrences"]))
    requests_ = []
    for i in range(0, len(data), COMPOUNDS_PER_REQUEST):
        chunk = data[i:i + COMPOUNDS_PER_REQUEST]
        requests_.append({
            "custom_id": f"cmp-{i:06d}",
            "params": {
                "model": MODEL,
                "max_tokens": 4000,
                "system": [{"type": "text", "text": SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": make_user_block(chunk)}],
            },
        })
    AUDIT.mkdir(exist_ok=True)
    REQUESTS_FILE.write_text(json.dumps(requests_, ensure_ascii=False), encoding="utf-8")
    pairs = sum(len(c["candidate_families"]) for c in data)
    print(f"compounds            : {len(data)}")
    print(f"link decisions       : {pairs}")
    print(f"requests ({COMPOUNDS_PER_REQUEST}/req) : {len(requests_)}")
    print(f"-> {REQUESTS_FILE.relative_to(HERE)}")


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set in this shell.\n"
                 "  export ANTHROPIC_API_KEY=$(tr -d '\\n' < ~/Desktop/claudeAPIKey.txt)")
    import anthropic
    return anthropic.Anthropic()


# Batch API is 50% off standard rates.
PRICES = {  # model -> (input $/MTok, output $/MTok) at standard rate
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


def cmd_estimate(args):
    """Measure real input tokens on a sample; extrapolate with explicit margin."""
    client = get_client()
    requests_ = json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
    sample = requests_[:args.sample]
    total_in = 0
    for r in sample:
        ct = client.messages.count_tokens(
            model=MODEL,
            system=r["params"]["system"],
            messages=r["params"]["messages"])
        total_in += ct.input_tokens
    avg_in = total_in / len(sample)

    # Output: each decision line is ~35 tokens; measure pairs per request.
    data = load_actionable()
    pairs = sum(len(c["candidate_families"]) for c in data)
    avg_pairs = pairs / len(requests_)
    avg_out = avg_pairs * 40

    n = len(requests_)
    pin, pout = PRICES[MODEL]
    pin, pout = pin / 2, pout / 2          # batch discount
    cost_in = n * avg_in / 1e6 * pin
    cost_out = n * avg_out / 1e6 * pout
    total = cost_in + cost_out

    print(f"model                 : {MODEL} (Batch API, 50% off)")
    print(f"requests              : {n}")
    print(f"measured avg input    : {avg_in:,.0f} tokens/request (sampled {len(sample)})")
    print(f"estimated avg output  : {avg_out:,.0f} tokens/request ({avg_pairs:.1f} decisions)")
    print(f"\ninput  cost : ${cost_in:6.2f}")
    print(f"output cost : ${cost_out:6.2f}")
    print(f"TOTAL       : ${total:6.2f}")
    print(f"\nwith 4x safety margin (see prior run's undershoot): ${total*4:6.2f}")
    print(f"cost per committed tranche of {args.tranche} requests: "
          f"${total/n*args.tranche:6.2f}  (4x margin ${total/n*args.tranche*4:6.2f})")


def cmd_submit(args):
    client = get_client()
    requests_ = json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
    done = set()
    if BATCH_IDS_FILE.exists():
        for line in BATCH_IDS_FILE.read_text().splitlines():
            if line.strip() and "\t" in line:
                _, lo, hi = line.split("\t")
                done.update(range(int(lo), int(hi)))
    todo = [i for i in range(len(requests_)) if i not in done]
    if not todo:
        print("All requests already submitted.")
        return
    take = todo[:args.limit]
    batch = client.messages.batches.create(
        requests=[requests_[i] for i in take])
    with BATCH_IDS_FILE.open("a") as fh:
        fh.write(f"{batch.id}\t{take[0]}\t{take[-1] + 1}\n")
    print(f"submitted batch {batch.id}")
    print(f"  requests {take[0]}..{take[-1]} ({len(take)} of {len(requests_)} total)")
    print(f"  remaining after this tranche: {len(todo) - len(take)}")


def cmd_status(args):
    client = get_client()
    if not BATCH_IDS_FILE.exists():
        sys.exit("No batches submitted yet.")
    for line in BATCH_IDS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        bid, lo, hi = line.split("\t")
        b = client.messages.batches.retrieve(bid)
        c = b.request_counts
        print(f"{bid}  [{lo}..{hi})  {b.processing_status}  "
              f"succeeded={c.succeeded} errored={c.errored} "
              f"processing={c.processing} canceled={c.canceled} expired={c.expired}")


def cmd_fetch(args):
    client = get_client()
    out = RESULTS_FILE.open("a", encoding="utf-8")
    seen = set()
    if RESULTS_FILE.exists():
        for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                seen.add(json.loads(line)["custom_id"])
    n = 0
    for line in BATCH_IDS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        bid = line.split("\t")[0]
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            print(f"{bid} not finished ({b.processing_status}) — skipping")
            continue
        for result in client.messages.batches.results(bid):
            if result.custom_id in seen:
                continue
            rec = {"custom_id": result.custom_id, "type": result.result.type}
            if result.result.type == "succeeded":
                msg = result.result.message
                rec["text"] = "".join(
                    blk.text for blk in msg.content if blk.type == "text")
                rec["usage"] = {
                    "input_tokens": msg.usage.input_tokens,
                    "output_tokens": msg.usage.output_tokens,
                    "cache_read_input_tokens": getattr(
                        msg.usage, "cache_read_input_tokens", 0),
                    "cache_creation_input_tokens": getattr(
                        msg.usage, "cache_creation_input_tokens", 0),
                }
            else:
                rec["error"] = str(getattr(result.result, "error", ""))
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    out.close()
    print(f"fetched {n} new results -> {RESULTS_FILE.relative_to(HERE)}")
    if n:
        report_spend()


def report_spend():
    """Report ACTUAL token usage and cost from fetched results."""
    ti = to = tcr = tcc = 0
    rows = 0
    for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        u = r.get("usage")
        if not u:
            continue
        rows += 1
        ti += u["input_tokens"]
        to += u["output_tokens"]
        tcr += u.get("cache_read_input_tokens", 0)
        tcc += u.get("cache_creation_input_tokens", 0)
    pin, pout = PRICES[MODEL]
    pin, pout = pin / 2, pout / 2
    cost = (ti / 1e6 * pin) + (to / 1e6 * pout) \
        + (tcr / 1e6 * pin * 0.1) + (tcc / 1e6 * pin * 1.25)
    print(f"\nACTUAL usage over {rows} completed requests:")
    print(f"  input {ti:,}  output {to:,}  cache_read {tcr:,}  cache_write {tcc:,}")
    print(f"  ACTUAL COST SO FAR: ${cost:.2f}")
    if rows:
        print(f"  per request: ${cost/rows:.4f}")


def cmd_apply(args):
    """Parse verdicts and apply accepted links to the database."""
    import sqlite3
    import re
    verdicts = []
    bad = 0
    for line in RESULTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("type") != "succeeded":
            continue
        txt = r.get("text", "").strip()
        txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.M).strip()
        try:
            verdicts.extend(json.loads(txt))
        except json.JSONDecodeError:
            m = re.search(r"\[.*\]", txt, re.S)
            if m:
                try:
                    verdicts.extend(json.loads(m.group(0)))
                    continue
                except json.JSONDecodeError:
                    pass
            bad += 1
    VERDICTS_FILE.write_text(json.dumps(verdicts, ensure_ascii=False, indent=1),
                             encoding="utf-8")
    acc = [v for v in verdicts if v.get("verdict") == "accept"]
    hi = [v for v in acc if float(v.get("confidence", 0)) >= args.min_confidence]
    print(f"verdicts parsed : {len(verdicts)}  (unparseable responses: {bad})")
    print(f"  accept        : {len(acc)}")
    print(f"  accept >= {args.min_confidence} : {len(hi)}")
    print(f"  reject        : {len(verdicts) - len(acc)}")
    if not args.write:
        print("\n(dry run — pass --write to apply to the database)")
        return

    data = {c["headword"]: c for c in load_actionable()}
    db = sqlite3.connect(str(DB_PATH))
    added = 0
    for v in hi:
        c = data.get(v["headword"])
        if not c:
            continue
        fid, lid = v["family_id"], c["head_lemma_id"]
        if db.execute("SELECT 1 FROM lemma_families WHERE lemma_id=? AND family_id=?",
                      (lid, fid)).fetchone():
            continue
        if not db.execute("SELECT 1 FROM derivational_families WHERE id=?",
                          (fid,)).fetchone():
            continue
        db.execute("""INSERT INTO lemma_families
                      (lemma_id, family_id, relation, derivation_type)
                      VALUES (?,?,?,?)""",
                   (lid, fid, "compound element", "compound_lsj"))
        db.execute("""INSERT INTO family_edit_log
                      (action, family_id, lemma_id, detail, user)
                      VALUES ('add_member',?,?,?,'adjudicate_compounds')""",
                   (fid, lid, json.dumps(
                       {"relation": "compound element",
                        "confidence": v.get("confidence"),
                        "reason": v.get("reason"),
                        "lsj_split": c["lsj_split"]}, ensure_ascii=False)))
        added += 1
    db.commit()
    db.close()
    print(f"\napplied {added} new family links")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(func=cmd_build)
    p = sub.add_parser("estimate")
    p.add_argument("--sample", type=int, default=25)
    p.add_argument("--tranche", type=int, default=150)
    p.set_defaults(func=cmd_estimate)
    p = sub.add_parser("submit")
    p.add_argument("--limit", type=int, default=150)
    p.set_defaults(func=cmd_submit)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("fetch").set_defaults(func=cmd_fetch)
    p = sub.add_parser("apply")
    p.add_argument("--min-confidence", type=float, default=0.8)
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_apply)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
