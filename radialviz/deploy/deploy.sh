#!/bin/bash
# Poll origin/main and redeploy the GlossaLearn API if it moved.
#
# Runs on the Lightsail box via glossalearn-deploy.timer. This replaces the
# original ~/deploy.sh (Mar 2026), which was never scheduled and whose
# assumptions had all drifted: it managed a container named glossalearn-api,
# bound port 80 (nginx has owned that since Apr 3), and mounted the DB from
# ~/data (empty; the real DB is in the repo dir).
#
# The live container bind-mounts the source, so a restart picks up new code —
# no image rebuild.

set -euo pipefail

REPO=/home/ec2-user/glossalearn
CONTAINER=backend
BRANCH=main
HEALTH=http://127.0.0.1:5000/api/status

cd "$REPO"

git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "No changes at $(date -Is) ($(git rev-parse --short HEAD))"
    exit 0
fi

echo "Changes detected: $(git rev-parse --short HEAD) -> $(git rev-parse --short "origin/$BRANCH"), deploying..."

# --ff-only so a divergence or a locally-modified tracked file aborts the
# deploy instead of silently merging or clobbering. The box carries local
# edits to docker-compose.yml and speech/, which must survive.
git pull --ff-only origin "$BRANCH"

# ec2-user is in the docker group; no sudo.
docker restart "$CONTAINER"

for _ in $(seq 1 30); do
    if curl -fsS -m 5 "$HEALTH" >/dev/null 2>&1; then
        echo "Deployed $(git rev-parse --short HEAD) at $(date -Is)"
        exit 0
    fi
    sleep 2
done

echo "ERROR: API did not answer $HEALTH within 60s of restart" >&2
exit 1
