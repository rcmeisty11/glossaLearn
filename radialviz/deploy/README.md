# API deploy (AWS Lightsail)

The frontend deploys itself: the **Cloudflare Pages GitHub App** builds `vocab-viz/`
on every push to `main` and ships it to the edge. The API has never had an
equivalent — this directory is that equivalent.

## What actually runs in production

| | |
|---|---|
| Host | Lightsail, `ec2-user@2600:1f16:977:fe00:b263:8c48:20f3:38cf` |
| Serving | Docker container **`backend`** (image `localhost/glossalearn:lti-deploy`), host `:5000` → container `:8080` |
| Front door | nginx on `:80`/`:443` |
| Checkout | `/home/ec2-user/glossalearn`, branch `main` |
| Source | bind-mounted `radialviz/` → `/app` **and** `/data`, so a restart picks up new code with **no image rebuild** |
| Database | `DB_PATH=/data/greek_vocab.db` → `~/glossalearn/radialviz/greek_vocab.db` |

Two things on that box are **not** the API and should be ignored:

- `glossalearn.service` — a systemd unit that has been crash-looping on
  `ModuleNotFoundError: flask_caching` since ~June (restart counter >1.6M).
  It serves nothing. Restarting it does nothing.
- `~/deploy.sh` (the original, Mar 2026) — superseded by this directory.

## Install

    scp -6 -i ~/Desktop/LightsailDefaultKey-us-east-2.pem \
      radialviz/deploy/deploy.sh \
      'ec2-user@[2600:1f16:977:fe00:b263:8c48:20f3:38cf]:/home/ec2-user/deploy.sh'

    ssh -6 -i ~/Desktop/LightsailDefaultKey-us-east-2.pem \
      ec2-user@2600:1f16:977:fe00:b263:8c48:20f3:38cf

    chmod +x ~/deploy.sh
    sudo cp /home/ec2-user/glossalearn/radialviz/deploy/glossalearn-deploy.* \
      /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now glossalearn-deploy.timer

Verify:

    systemctl list-timers glossalearn-deploy.timer
    journalctl -u glossalearn-deploy.service -f

## Manual deploy

    cd ~/glossalearn && git pull origin main && docker restart backend

## Design notes

**Poller, not webhook.** The timer checks `origin/main` every 5 minutes. A real
webhook would mean an inbound endpoint, a shared secret and an nginx route; a
poller needs no new attack surface and 5 minutes of latency is fine here. The
repo is public, so the fetch needs no credentials.

**`--ff-only` is deliberate.** The box carries local edits to
`radialviz/docker-compose.yml` and two files under `speech/`. A fast-forward
refuses and exits non-zero rather than merging or clobbering, so a conflict
surfaces in the journal instead of silently changing production.

**Health gate.** After the restart the script polls `/api/status` for up to 60s
and exits non-zero if the API does not come back, so a bad deploy is visible in
`systemctl status` rather than silent.

**This auto-deploys `main` to production.** Anything merged is live within five
minutes, with no staging step. That matches how the frontend already behaves.
To require a deliberate action instead, leave the timer disabled and run
`~/deploy.sh` by hand, or point `BRANCH` at a dedicated `production` branch.
