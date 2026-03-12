#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# download_greek_data.sh
# Step 1: Download all Greek corpus data from GitHub
#
# This clones the repositories you need:
#   1. Lemmatized texts (tokens → lemmas + morphology for all Greek)
#   2. Perseus canonical Greek literature (TEI XML originals)
#   3. First 1000 Years of Greek (additional texts)
#   4. Lexica (LSJ, Middle Liddell definitions)
#   5. Treebank data (syntactic annotations)
#
# Usage:
#   chmod +x download_greek_data.sh
#   ./download_greek_data.sh
#
# Total download: ~3-5 GB. Takes 10-30 min depending on connection.
# ═══════════════════════════════════════════════════════════════

set -e

DATA_DIR="$HOME/greek_data"
mkdir -p "$DATA_DIR"
cd "$DATA_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "  Greek Vocabulary Data Downloader"
echo "  Target directory: $DATA_DIR"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ───────────────────────────────────────────────
# 1. LEMMATIZED ANCIENT GREEK XML
#    This is the MOST IMPORTANT repo. Contains every token
#    in the Perseus/First1K corpus with POS tags and lemmas.
#    ~21.5 million lemma assignments across ~25.5 million tokens.
# ───────────────────────────────────────────────
if [ -d "LemmatizedAncientGreekXML" ]; then
    echo "[1/5] LemmatizedAncientGreekXML already exists, pulling updates..."
    cd LemmatizedAncientGreekXML && git pull && cd ..
else
    echo "[1/5] Cloning LemmatizedAncientGreekXML (~500 MB)..."
    echo "       This has tokenized + lemmatized + POS-tagged texts."
    git clone --depth 1 https://github.com/gcelano/LemmatizedAncientGreekXML.git
fi
echo "  ✓ Lemmatized texts ready"
echo ""

# ───────────────────────────────────────────────
# 2. PERSEUS CANONICAL GREEK LITERATURE
#    TEI XML source texts — Homer, tragedians, Plato,
#    Thucydides, NT, Aristotle, historians, orators, etc.
#    We use sparse checkout to get just the data/ folder.
# ───────────────────────────────────────────────
if [ -d "canonical-greekLit" ]; then
    echo "[2/5] canonical-greekLit already exists, pulling updates..."
    cd canonical-greekLit && git pull && cd ..
else
    echo "[2/5] Cloning PerseusDL/canonical-greekLit (~800 MB)..."
    echo "       TEI XML for all Perseus Greek texts."
    git clone --depth 1 https://github.com/PerseusDL/canonical-greekLit.git
fi
echo "  ✓ Perseus Greek texts ready"
echo ""

# ───────────────────────────────────────────────
# 3. FIRST 1000 YEARS OF GREEK
#    Additional texts not in Perseus — church fathers,
#    medical writers, geographers, etc.
# ───────────────────────────────────────────────
if [ -d "First1KGreek" ]; then
    echo "[3/5] First1KGreek already exists, pulling updates..."
    cd First1KGreek && git pull && cd ..
else
    echo "[3/5] Cloning OpenGreekAndLatin/First1KGreek (~1.5 GB)..."
    echo "       Additional Greek texts, first millennium."
    git clone --depth 1 https://github.com/OpenGreekAndLatin/First1KGreek.git
fi
echo "  ✓ First1K texts ready"
echo ""

# ───────────────────────────────────────────────
# 4. LEXICA (LSJ, Middle Liddell)
#    TEI XML dictionary entries with definitions.
#    This gives us English glosses for each lemma.
# ───────────────────────────────────────────────
if [ -d "lexica" ]; then
    echo "[4/5] lexica already exists, pulling updates..."
    cd lexica && git pull && cd ..
else
    echo "[4/5] Cloning PerseusDL/lexica (~200 MB)..."
    echo "       LSJ and Middle Liddell Greek-English lexica."
    git clone --depth 1 https://github.com/PerseusDL/lexica.git
fi
echo "  ✓ Lexica ready"
echo ""

# ───────────────────────────────────────────────
# 5. TREEBANK DATA
#    Dependency syntax annotations — gives us sentence
#    structure and helps with translation alignment.
# ───────────────────────────────────────────────
if [ -d "treebank_data" ]; then
    echo "[5/5] treebank_data already exists, pulling updates..."
    cd treebank_data && git pull && cd ..
else
    echo "[5/5] Cloning PerseusDL/treebank_data (~100 MB)..."
    echo "       Syntactic dependency treebanks."
    git clone --depth 1 https://github.com/PerseusDL/treebank_data.git
fi
echo "  ✓ Treebank data ready"
echo ""

# ───────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════"
echo "  Download complete!"
echo ""
echo "  Location: $DATA_DIR"
echo ""
echo "  Contents:"
du -sh "$DATA_DIR"/LemmatizedAncientGreekXML 2>/dev/null || echo "    LemmatizedAncientGreekXML  (calculating...)"
du -sh "$DATA_DIR"/canonical-greekLit 2>/dev/null || echo "    canonical-greekLit         (calculating...)"
du -sh "$DATA_DIR"/First1KGreek 2>/dev/null || echo "    First1KGreek               (calculating...)"
du -sh "$DATA_DIR"/lexica 2>/dev/null || echo "    lexica                     (calculating...)"
du -sh "$DATA_DIR"/treebank_data 2>/dev/null || echo "    treebank_data              (calculating...)"
echo ""
echo "  Next step: Run the database builder"
echo "    python3 build_database.py"
echo "═══════════════════════════════════════════════════════════"