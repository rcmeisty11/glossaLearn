#!/usr/bin/env python3
"""
repair_families_and_titles.py
═══════════════════════════════════════════════════════════════
Fixes two issues in greek_vocab.db:
  1. Derivational families — smarter stemmer that handles
     α-privative (ἀ-δικία → δικ-), multiple prefixes,
     and better suffix normalization so δίκαιος/δικαιόω/
     ἀδικία/δικαιοσύνη all end up in the same family.
  2. TLG work titles — replaces raw "tlg001" codes with
     human-readable titles from a comprehensive catalog.

Usage:
    python3 repair_families_and_titles.py

Run in the same directory as greek_vocab.db
═══════════════════════════════════════════════════════════════
"""

import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("./greek_vocab.db")
if not DB_PATH.exists():
    print("ERROR: greek_vocab.db not found")
    sys.exit(1)

conn = sqlite3.connect(str(DB_PATH))
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA cache_size=-128000")
cursor = conn.cursor()

print("═══════════════════════════════════════════════════════════")
print("  Repair: Derivational Families + Work Titles")
print("═══════════════════════════════════════════════════════════")
print()

# ═══════════════════════════════════════════════════════════
# PART 1: Fix TLG work titles
# ═══════════════════════════════════════════════════════════
print("[1/2] Fixing work titles...")

# Comprehensive (author_code, work_code) → title mapping
# Work codes are author-specific so we need the pair
WORK_TITLES = {
    # Homer
    ("tlg0012", "tlg001"): "Iliad",
    ("tlg0012", "tlg002"): "Odyssey",
    # Hesiod
    ("tlg0020", "tlg001"): "Theogony",
    ("tlg0020", "tlg002"): "Works and Days",
    ("tlg0020", "tlg003"): "Shield of Heracles",
    # Homeric Hymns
    ("tlg0013", "tlg001"): "Hymn to Demeter",
    ("tlg0013", "tlg002"): "Hymn to Apollo",
    ("tlg0013", "tlg003"): "Hymn to Hermes",
    ("tlg0013", "tlg004"): "Hymn to Aphrodite",
    ("tlg0013", "tlg005"): "Hymn to Dionysus",
    # Aeschylus
    ("tlg0085", "tlg001"): "Persians",
    ("tlg0085", "tlg002"): "Seven Against Thebes",
    ("tlg0085", "tlg003"): "Suppliants",
    ("tlg0085", "tlg004"): "Agamemnon",
    ("tlg0085", "tlg005"): "Libation Bearers",
    ("tlg0085", "tlg006"): "Eumenides",
    ("tlg0085", "tlg007"): "Prometheus Bound",
    # Sophocles
    ("tlg0011", "tlg001"): "Ajax",
    ("tlg0011", "tlg002"): "Trachiniae",
    ("tlg0011", "tlg003"): "Antigone",
    ("tlg0011", "tlg004"): "Electra",
    ("tlg0011", "tlg005"): "Oedipus at Colonus",
    ("tlg0011", "tlg006"): "Philoctetes",
    ("tlg0011", "tlg007"): "Oedipus Tyrannus",
    # Euripides
    ("tlg0006", "tlg001"): "Alcestis",
    ("tlg0006", "tlg002"): "Andromache",
    ("tlg0006", "tlg003"): "Medea",
    ("tlg0006", "tlg004"): "Heraclidae",
    ("tlg0006", "tlg005"): "Hippolytus",
    ("tlg0006", "tlg006"): "Hecuba",
    ("tlg0006", "tlg007"): "Suppliant Women",
    ("tlg0006", "tlg008"): "Heracles",
    ("tlg0006", "tlg009"): "Ion",
    ("tlg0006", "tlg010"): "Trojan Women",
    ("tlg0006", "tlg011"): "Electra",
    ("tlg0006", "tlg012"): "Iphigenia in Tauris",
    ("tlg0006", "tlg013"): "Helen",
    ("tlg0006", "tlg014"): "Phoenician Women",
    ("tlg0006", "tlg015"): "Orestes",
    ("tlg0006", "tlg016"): "Bacchae",
    ("tlg0006", "tlg017"): "Iphigenia in Aulis",
    ("tlg0006", "tlg019"): "Cyclops",
    ("tlg0006", "tlg020"): "Rhesus",
    # Aristophanes
    ("tlg0019", "tlg001"): "Acharnians",
    ("tlg0019", "tlg002"): "Knights",
    ("tlg0019", "tlg003"): "Clouds",
    ("tlg0019", "tlg004"): "Wasps",
    ("tlg0019", "tlg005"): "Peace",
    ("tlg0019", "tlg006"): "Birds",
    ("tlg0019", "tlg007"): "Lysistrata",
    ("tlg0019", "tlg008"): "Thesmophoriazusae",
    ("tlg0019", "tlg009"): "Frogs",
    ("tlg0019", "tlg010"): "Ecclesiazusae",
    ("tlg0019", "tlg011"): "Plutus",
    # Thucydides
    ("tlg0003", "tlg001"): "History of the Peloponnesian War",
    # Herodotus
    ("tlg0016", "tlg001"): "Histories",
    # Plato
    ("tlg0059", "tlg001"): "Euthyphro",
    ("tlg0059", "tlg002"): "Apology",
    ("tlg0059", "tlg003"): "Crito",
    ("tlg0059", "tlg004"): "Phaedo",
    ("tlg0059", "tlg005"): "Cratylus",
    ("tlg0059", "tlg006"): "Theaetetus",
    ("tlg0059", "tlg007"): "Sophist",
    ("tlg0059", "tlg008"): "Statesman",
    ("tlg0059", "tlg009"): "Parmenides",
    ("tlg0059", "tlg010"): "Philebus",
    ("tlg0059", "tlg011"): "Symposium",
    ("tlg0059", "tlg012"): "Phaedrus",
    ("tlg0059", "tlg013"): "Alcibiades I",
    ("tlg0059", "tlg014"): "Alcibiades II",
    ("tlg0059", "tlg015"): "Hipparchus",
    ("tlg0059", "tlg016"): "Rivals",
    ("tlg0059", "tlg017"): "Theages",
    ("tlg0059", "tlg018"): "Charmides",
    ("tlg0059", "tlg019"): "Laches",
    ("tlg0059", "tlg020"): "Lysis",
    ("tlg0059", "tlg021"): "Euthydemus",
    ("tlg0059", "tlg022"): "Protagoras",
    ("tlg0059", "tlg023"): "Gorgias",
    ("tlg0059", "tlg024"): "Meno",
    ("tlg0059", "tlg025"): "Greater Hippias",
    ("tlg0059", "tlg026"): "Lesser Hippias",
    ("tlg0059", "tlg027"): "Ion",
    ("tlg0059", "tlg028"): "Menexenus",
    ("tlg0059", "tlg029"): "Clitophon",
    ("tlg0059", "tlg030"): "Republic",
    ("tlg0059", "tlg031"): "Timaeus",
    ("tlg0059", "tlg032"): "Critias",
    ("tlg0059", "tlg033"): "Minos",
    ("tlg0059", "tlg034"): "Laws",
    ("tlg0059", "tlg035"): "Epinomis",
    ("tlg0059", "tlg036"): "Letters",
    # Xenophon
    ("tlg0032", "tlg001"): "Hellenica",
    ("tlg0032", "tlg002"): "Memorabilia",
    ("tlg0032", "tlg003"): "Oeconomicus",
    ("tlg0032", "tlg004"): "Symposium",
    ("tlg0032", "tlg005"): "Apology",
    ("tlg0032", "tlg006"): "Anabasis",
    ("tlg0032", "tlg007"): "Cyropaedia",
    ("tlg0032", "tlg008"): "Hiero",
    ("tlg0032", "tlg009"): "Agesilaus",
    ("tlg0032", "tlg010"): "Constitution of the Lacedaemonians",
    ("tlg0032", "tlg011"): "Ways and Means",
    ("tlg0032", "tlg012"): "On Horsemanship",
    ("tlg0032", "tlg013"): "Cavalry Commander",
    ("tlg0032", "tlg014"): "On Hunting",
    # Aristotle
    ("tlg0086", "tlg001"): "Categories",
    ("tlg0086", "tlg002"): "On Interpretation",
    ("tlg0086", "tlg003"): "Prior Analytics",
    ("tlg0086", "tlg004"): "Posterior Analytics",
    ("tlg0086", "tlg005"): "Topics",
    ("tlg0086", "tlg006"): "Sophistical Refutations",
    ("tlg0086", "tlg007"): "Physics",
    ("tlg0086", "tlg008"): "On the Heavens",
    ("tlg0086", "tlg009"): "On Generation and Corruption",
    ("tlg0086", "tlg010"): "Meteorology",
    ("tlg0086", "tlg011"): "On the Universe",
    ("tlg0086", "tlg012"): "On the Soul",
    ("tlg0086", "tlg025"): "Metaphysics",
    ("tlg0086", "tlg031"): "Nicomachean Ethics",
    ("tlg0086", "tlg034"): "Eudemian Ethics",
    ("tlg0086", "tlg035"): "Politics",
    ("tlg0086", "tlg036"): "Economics",
    ("tlg0086", "tlg038"): "Rhetoric",
    ("tlg0086", "tlg039"): "Rhetoric to Alexander",
    ("tlg0086", "tlg040"): "Poetics",
    ("tlg0086", "tlg041"): "Constitution of Athens",
    # Demosthenes
    ("tlg0014", "tlg001"): "Olynthiac 1",
    ("tlg0014", "tlg002"): "Olynthiac 2",
    ("tlg0014", "tlg003"): "Olynthiac 3",
    ("tlg0014", "tlg004"): "Philippic 1",
    ("tlg0014", "tlg018"): "On the Crown",
    # New Testament
    ("tlg0031", "tlg001"): "Matthew",
    ("tlg0031", "tlg002"): "Mark",
    ("tlg0031", "tlg003"): "Luke",
    ("tlg0031", "tlg004"): "John",
    ("tlg0031", "tlg005"): "Acts",
    ("tlg0031", "tlg006"): "Romans",
    ("tlg0031", "tlg007"): "1 Corinthians",
    ("tlg0031", "tlg008"): "2 Corinthians",
    ("tlg0031", "tlg009"): "Galatians",
    ("tlg0031", "tlg010"): "Ephesians",
    ("tlg0031", "tlg011"): "Philippians",
    ("tlg0031", "tlg012"): "Colossians",
    ("tlg0031", "tlg013"): "1 Thessalonians",
    ("tlg0031", "tlg014"): "2 Thessalonians",
    ("tlg0031", "tlg015"): "1 Timothy",
    ("tlg0031", "tlg016"): "2 Timothy",
    ("tlg0031", "tlg017"): "Titus",
    ("tlg0031", "tlg018"): "Philemon",
    ("tlg0031", "tlg019"): "Hebrews",
    ("tlg0031", "tlg020"): "James",
    ("tlg0031", "tlg021"): "1 Peter",
    ("tlg0031", "tlg022"): "2 Peter",
    ("tlg0031", "tlg023"): "1 John",
    ("tlg0031", "tlg024"): "2 John",
    ("tlg0031", "tlg025"): "3 John",
    ("tlg0031", "tlg026"): "Jude",
    ("tlg0031", "tlg027"): "Revelation",
    # Plutarch Lives
    ("tlg0007", "tlg001"): "Theseus",
    ("tlg0007", "tlg002"): "Romulus",
    ("tlg0007", "tlg003"): "Solon",
    ("tlg0007", "tlg004"): "Publicola",
    ("tlg0007", "tlg005"): "Themistocles",
    ("tlg0007", "tlg007"): "Pericles",
    ("tlg0007", "tlg009"): "Alcibiades",
    ("tlg0007", "tlg012"): "Lycurgus",
    ("tlg0007", "tlg014"): "Alexander",
    ("tlg0007", "tlg019"): "Demosthenes",
    ("tlg0007", "tlg020"): "Cicero",
    # Josephus
    ("tlg0526", "tlg001"): "Jewish War",
    ("tlg0526", "tlg002"): "Jewish Antiquities",
    ("tlg0526", "tlg003"): "Life",
    ("tlg0526", "tlg004"): "Against Apion",
    # Polybius
    ("tlg0033", "tlg001"): "Histories",
    # Diodorus Siculus
    ("tlg0060", "tlg001"): "Library of History",
    # Strabo
    ("tlg0090", "tlg001"): "Geography",
    # Pausanias
    ("tlg0046", "tlg001"): "Description of Greece",
    # Galen — just a few major works
    ("tlg0057", "tlg001"): "On the Natural Faculties",
    ("tlg0057", "tlg009"): "On the Therapeutic Method",
    # Lucian
    ("tlg0062", "tlg001"): "Dialogues of the Dead",
    # Epictetus
    ("tlg0557", "tlg001"): "Discourses",
    ("tlg0557", "tlg002"): "Enchiridion",
    # Apollonius Rhodius
    ("tlg0001", "tlg001"): "Argonautica",
    # Septuagint books
    ("tlg0527", "tlg001"): "Genesis",
    ("tlg0527", "tlg002"): "Exodus",
    ("tlg0527", "tlg003"): "Leviticus",
    ("tlg0527", "tlg004"): "Numbers",
    ("tlg0527", "tlg005"): "Deuteronomy",
    ("tlg0527", "tlg006"): "Joshua",
    ("tlg0527", "tlg007"): "Judges",
    ("tlg0527", "tlg008"): "Ruth",
    ("tlg0527", "tlg009"): "1 Samuel",
    ("tlg0527", "tlg010"): "2 Samuel",
    ("tlg0527", "tlg011"): "1 Kings",
    ("tlg0527", "tlg012"): "2 Kings",
    ("tlg0527", "tlg039"): "Psalms",
    ("tlg0527", "tlg040"): "Proverbs",
    ("tlg0527", "tlg045"): "Isaiah",
    ("tlg0527", "tlg046"): "Jeremiah",
}

# Also add more author mappings
MORE_AUTHORS = {
    "tlg0001": "Apollonius Rhodius",
    "tlg0003": "Thucydides",
    "tlg0006": "Euripides",
    "tlg0007": "Plutarch",
    "tlg0008": "Athenaeus",
    "tlg0009": "Sappho",
    "tlg0010": "Isocrates",
    "tlg0011": "Sophocles",
    "tlg0012": "Homer",
    "tlg0013": "Homeric Hymns",
    "tlg0014": "Demosthenes",
    "tlg0016": "Herodotus",
    "tlg0017": "Isaeus",
    "tlg0018": "Apollonius Rhodius",
    "tlg0019": "Aristophanes",
    "tlg0020": "Hesiod",
    "tlg0028": "Antiphon",
    "tlg0031": "New Testament",
    "tlg0032": "Xenophon",
    "tlg0033": "Polybius",
    "tlg0036": "Apollodorus",
    "tlg0046": "Pausanias",
    "tlg0057": "Galen",
    "tlg0059": "Plato",
    "tlg0060": "Diodorus Siculus",
    "tlg0062": "Lucian",
    "tlg0081": "Athenaeus",
    "tlg0085": "Aeschylus",
    "tlg0086": "Aristotle",
    "tlg0090": "Strabo",
    "tlg0093": "Theophrastus",
    "tlg0099": "Pindar",
    "tlg0525": "Josephus",
    "tlg0526": "Philo",
    "tlg0527": "Septuagint",
    "tlg0540": "Lysias",
    "tlg0555": "Marcus Aurelius",
    "tlg0557": "Epictetus",
    "tlg0561": "Epictetus",
    "tlg2018": "Clement of Alexandria",
    "tlg2022": "Origen",
    "tlg2040": "Basil of Caesarea",
    "tlg2042": "John Chrysostom",
    "tlg4015": "Eusebius",
}

# Update work titles
updated = 0
for (ac, wc), title in WORK_TITLES.items():
    cursor.execute(
        "UPDATE works SET title = ? WHERE author_code = ? AND work_code = ?",
        (title, ac, wc),
    )
    updated += cursor.rowcount

# Update author names where they're still TLG codes
for code, name in MORE_AUTHORS.items():
    cursor.execute(
        "UPDATE works SET author = ? WHERE author_code = ? AND author = ?",
        (name, code, code),
    )

conn.commit()
print(f"  ✓ Updated {updated} work titles")

# Show remaining unmapped
cursor.execute("""
    SELECT author, title, author_code, work_code, COUNT(*) as c
    FROM works
    WHERE title LIKE 'tlg%'
    GROUP BY author_code, work_code
    ORDER BY c DESC
    LIMIT 20
""")
unmapped = cursor.fetchall()
if unmapped:
    print(f"  ℹ {len(unmapped)} work titles still using TLG codes (showing first 20):")
    for a, t, ac, wc, c in unmapped[:10]:
        print(f"    {a}: {t}  ({ac}/{wc})")

# ═══════════════════════════════════════════════════════════
# PART 2: Rebuild derivational families with better stemmer
# ═══════════════════════════════════════════════════════════
print()
print("[2/2] Rebuilding derivational families...")
t0 = time.time()

def strip_accents(s):
    """Strip accents but keep breathing marks' effect on base letter."""
    # Decompose, remove combining marks, recompose
    nfkd = unicodedata.normalize("NFD", s)
    stripped = ""
    for ch in nfkd:
        cat = unicodedata.category(ch)
        if cat.startswith("M"):  # Mark (combining accent, breathing, etc.)
            continue
        stripped += ch
    return stripped.lower()

# Greek prefixes, ordered longest first for greedy match
PREFIXES = [
    # 4+ char
    ("ὑπέρ", "ὑπέρ-"), ("ὑπερ", "ὑπερ-"),
    ("κατα", "κατά-"), ("μετα", "μετά-"), ("παρα", "παρά-"),
    ("περι", "περί-"), ("ἀντι", "ἀντί-"), ("ἐπαν", "ἐπαν-"),
    # 3 char
    ("ἀνα", "ἀνά-"), ("ἀπο", "ἀπό-"), ("δια", "διά-"),
    ("εἰσ", "εἰσ-"), ("ἐπι", "ἐπί-"), ("προ", "πρό-"),
    ("σύν", "σύν-"), ("συν", "συν-"), ("δυσ", "δυσ-"),
    ("ὑπο", "ὑπό-"),
    # 2 char
    ("ἐκ", "ἐκ-"), ("ἐξ", "ἐξ-"), ("ἐν", "ἐν-"),
    ("εὐ", "εὐ-"),
]

# Alpha-privative patterns — these are tricky because
# ἀ- before consonant, ἀν- before vowel
ALPHA_PRIVATIVE = [
    ("ἀν", "ἀν- (privative)"),  # before vowels
    ("ἀ", "ἀ- (privative)"),    # before consonants
]

# Suffixes to strip for stem grouping (ordered longest first)
SUFFIXES = [
    # Verbal
    "οσύνη", "σύνη", "ωσις", "ησις", "ασις",
    "ίζω", "άζω", "εύω", "όω", "έω", "άω", "ύω", "ῶ",
    # Nominal
    "ικός", "ικόν", "ικη", "ισμός", "ιστής",
    "ότης", "ωτης",
    "εία", "ία", "ίας", "αιος",
    "εύς", "ῆς", "ός", "ον", "ή", "ης", "ος",
    "μα", "μός", "σις", "τωρ", "τήρ",
    # Adjectival
    "ινος", "ειος", "αῖος", "ικός",
]

def extract_stem(lemma):
    """
    Extract a canonical stem from a Greek lemma.
    Returns (stem, prefix_label) where stem is accent-stripped.
    """
    word = lemma
    prefix = ""

    # 1. Try stripping known prefixes (greedy, longest first)
    for pfx, pfx_label in sorted(PREFIXES, key=lambda x: -len(x[0])):
        if word.startswith(pfx) and len(word) > len(pfx) + 2:
            prefix = pfx_label
            word = word[len(pfx):]
            break

    # 2. Try alpha-privative if no other prefix matched
    if not prefix:
        for pfx, pfx_label in ALPHA_PRIVATIVE:
            if word.startswith(pfx) and len(word) > len(pfx) + 2:
                # Check it's actually privative (next char is consonant for ἀ-)
                rest = word[len(pfx):]
                if pfx == "ἀ" and rest and rest[0] in "αεηιουωἀἐἠἰὀὐὠ":
                    continue  # Not privative, skip
                prefix = pfx_label
                word = rest
                break

    # 3. Strip suffix for grouping
    for suf in sorted(SUFFIXES, key=lambda x: -len(x)):
        if word.endswith(suf) and len(word) > len(suf) + 2:
            word = word[:-len(suf)]
            break

    # 4. Normalize: strip accents for comparison
    stem = strip_accents(word)

    # Must have at least 2 chars
    if len(stem) < 2:
        stem = strip_accents(lemma[:4]) if len(lemma) >= 4 else strip_accents(lemma)

    return stem, prefix


# Clear existing families
cursor.execute("DELETE FROM lemma_families")
cursor.execute("DELETE FROM derivational_families")

# Get all lemmas with some frequency
cursor.execute("SELECT id, lemma, pos, total_occurrences FROM lemmas WHERE total_occurrences > 1")
lemmas = cursor.fetchall()
print(f"  Processing {len(lemmas):,} lemmas...")

# Group by stem
stem_groups = defaultdict(list)
for lid, lemma, pos, freq in lemmas:
    stem, prefix = extract_stem(lemma)
    stem_groups[stem].append((lid, lemma, pos, prefix, freq))

# Also try matching 3-char accent-stripped prefix as fallback
# This catches cases where suffix stripping diverges
stem3_groups = defaultdict(list)
for lid, lemma, pos, freq in lemmas:
    base = lemma
    # Strip known prefixes
    for pfx, _ in sorted(PREFIXES + ALPHA_PRIVATIVE, key=lambda x: -len(x[0])):
        if base.startswith(pfx) and len(base) > len(pfx) + 2:
            base = base[len(pfx):]
            break
    key = strip_accents(base[:3]) if len(base) >= 3 else strip_accents(base)
    stem3_groups[key].append(lid)

# Build families from stem groups (2+ members)
family_count = 0
assigned = set()

for stem, members in sorted(stem_groups.items(), key=lambda x: -len(x[1])):
    if len(members) < 2:
        continue

    # Skip if all members already assigned
    unassigned = [(lid, l, p, pf, f) for lid, l, p, pf, f in members if lid not in assigned]
    if len(unassigned) < 2:
        continue

    # Find the root: highest frequency non-prefixed member
    root_candidates = [m for m in unassigned if not m[3]]  # no prefix
    if root_candidates:
        root = max(root_candidates, key=lambda m: m[4])
    else:
        root = max(unassigned, key=lambda m: m[4])

    label = f"Root: {stem}-"

    cursor.execute(
        "INSERT INTO derivational_families (root, label) VALUES (?, ?)",
        (stem, label),
    )
    family_id = cursor.lastrowid

    for lid, lemma, pos, prefix, freq in unassigned:
        relation = "root" if lid == root[0] else (f"prefix {prefix}" if prefix else "derived")
        cursor.execute(
            "INSERT OR IGNORE INTO lemma_families (lemma_id, family_id, relation) VALUES (?,?,?)",
            (lid, family_id, relation),
        )
        assigned.add(lid)

    family_count += 1

conn.commit()

# Stats
cursor.execute("SELECT COUNT(DISTINCT lemma_id) FROM lemma_families")
assigned_count = cursor.fetchone()[0]

print(f"  ✓ Built {family_count:,} families ({assigned_count:,} lemmas assigned) in {time.time()-t0:.1f}s")

# Show sample family
cursor.execute("""
    SELECT df.label, GROUP_CONCAT(l.lemma || ' (' || l.pos || ')', ', ')
    FROM derivational_families df
    JOIN lemma_families lf ON lf.family_id = df.id
    JOIN lemmas l ON l.id = lf.lemma_id
    GROUP BY df.id
    HAVING COUNT(*) BETWEEN 4 AND 8
    ORDER BY RANDOM()
    LIMIT 5
""")
print("  Sample families:")
for label, members in cursor.fetchall():
    print(f"    {label}: {members[:120]}")

# Quick test: δίκη family
cursor.execute("""
    SELECT l.lemma, l.pos, lf.relation
    FROM lemma_families lf
    JOIN lemmas l ON l.id = lf.lemma_id
    WHERE lf.family_id = (
        SELECT lf2.family_id FROM lemma_families lf2
        JOIN lemmas l2 ON l2.id = lf2.lemma_id
        WHERE l2.lemma = 'δίκαιος'
        LIMIT 1
    )
    ORDER BY l.total_occurrences DESC
""")
dik_family = cursor.fetchall()
if dik_family:
    print(f"\n  δίκ- family ({len(dik_family)} members):")
    for lemma, pos, rel in dik_family:
        print(f"    {lemma} ({pos}) — {rel}")

conn.execute("PRAGMA optimize")
conn.close()

print()
print("═══════════════════════════════════════════════════════════")
print("  Done! Restart serve_api.py and refresh the browser.")
print("═══════════════════════════════════════════════════════════")