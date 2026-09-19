#!/bin/bash
# One-time bootstrap: deploy the API and install the auto-deploy timer.
# Run from the radialviz directory:  bash deploy/bootstrap.sh
#
# After this runs once, pushes to main deploy the API on their own and this
# script is never needed again.

set -euo pipefail

KEY="$HOME/Desktop/LightsailDefaultKey-us-east-2.pem"
HOST="ec2-user@2600:1f16:977:fe00:b263:8c48:20f3:38cf"
SCP_HOST="ec2-user@[2600:1f16:977:fe00:b263:8c48:20f3:38cf]"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 1/4  Pulling main and restarting the API container"
ssh -6 -i "$KEY" "$HOST" \
  'cd ~/glossalearn && git pull --ff-only origin main && docker restart backend'

echo
echo "==> 2/4  Copying deploy.sh to the box"
scp -6 -i "$KEY" "$HERE/deploy.sh" "$SCP_HOST:/home/ec2-user/deploy.sh"

echo
echo "==> 3/4  Installing the systemd timer"
ssh -6 -i "$KEY" "$HOST" \
  'chmod +x ~/deploy.sh \
   && sudo cp ~/glossalearn/radialviz/deploy/glossalearn-deploy.service /etc/systemd/system/ \
   && sudo cp ~/glossalearn/radialviz/deploy/glossalearn-deploy.timer /etc/systemd/system/ \
   && sudo systemctl daemon-reload \
   && sudo systemctl enable --now glossalearn-deploy.timer \
   && systemctl list-timers glossalearn-deploy.timer --no-pager'

echo
echo "==> 4/4  Verifying the API is serving the new fields"
# Fetch to a file first. Piping curl into `grep -q` makes grep exit on the
# first match, curl then fails writing to the closed pipe, and `pipefail`
# reports the whole pipeline as failed even though the match succeeded.
for i in $(seq 1 15); do
    if curl -fsS -m 10 -o /tmp/glossa-verify.json \
        "https://apiaws.glossalearn.com/api/lemma/by-name/%E1%BC%90%CF%80%CE%B9%CE%BD%CE%BF%CE%AD%CF%89" \
        && grep -q members_omitted /tmp/glossa-verify.json; then
        echo "OK — members_omitted is present. The prefix cards are live."
        rm -f /tmp/glossa-verify.json
        exit 0
    fi
    sleep 2
done
rm -f /tmp/glossa-verify.json

echo "API is up but members_omitted is still absent — tell Claude and it will dig in." >&2
exit 1
