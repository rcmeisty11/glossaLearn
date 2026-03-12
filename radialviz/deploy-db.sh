#!/bin/bash
# deploy-db.sh — Upload the local greek_vocab.db to Fly.io
#
# Usage:
#   ./deploy-db.sh                    # upload from current directory
#   ./deploy-db.sh /path/to/db.db     # upload a specific file

set -e

DB_FILE="${1:-./greek_vocab.db}"
APP_NAME="glossalearn-api"

if [ ! -f "$DB_FILE" ]; then
    echo "ERROR: Database file not found: $DB_FILE"
    exit 1
fi

DB_SIZE=$(du -h "$DB_FILE" | cut -f1)
echo "═══ Deploying database to Fly.io ═══"
echo "  File: $DB_FILE ($DB_SIZE)"
echo ""

# Compress for faster upload
echo "Step 1: Compressing database..."
gzip -k -f "$DB_FILE"
GZ_SIZE=$(du -h "${DB_FILE}.gz" | cut -f1)
echo "  Compressed: ${DB_FILE}.gz ($GZ_SIZE)"

# Upload via fly ssh
echo ""
echo "Step 2: Uploading to Fly.io..."
echo "  (This may take a few minutes for large files)"
fly ssh sftp shell -a "$APP_NAME" <<EOF
put ${DB_FILE}.gz /data/greek_vocab.db.gz
EOF

# Decompress on server
echo ""
echo "Step 3: Decompressing on server..."
fly ssh console -a "$APP_NAME" -C "gunzip -f /data/greek_vocab.db.gz"

# Clean up local gz
rm -f "${DB_FILE}.gz"

# Restart the app to pick up the new DB
echo ""
echo "Step 4: Restarting app..."
fly apps restart "$APP_NAME"

echo ""
echo "═══ Done! Database deployed. ═══"
