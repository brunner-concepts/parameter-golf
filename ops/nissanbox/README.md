# Nissanbox Operator

This directory holds the containerized operator scaffold for long-running RunPod supervision.

## Purpose

Run the operator loop on an always-on Nissanbox host so:

- RunPod launches do not depend on your laptop staying awake
- mirrored state survives chat turns
- Telegram notifications come from a durable host
- the dashboard stays available over an SSH tunnel

## Host prerequisites

- Docker + Docker Compose
- `runpodctl` installed on the host
- RunPod config under `~/.runpod/`
- Telegram bot token and chat id exported in the shell if you want phone pushes

Recommended host env:

```bash
export RUNPODCTL_PATH=$(which runpodctl)
export RUNPOD_HOME=$HOME/.runpod
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
```

## Start the dashboard container

```bash
docker compose -f docker-compose.nissanbox.yml up -d --build
```

The dashboard serves only on Nissanbox localhost:

- `http://127.0.0.1:8787`

Use an SSH tunnel from your Mac:

```bash
ssh -L 8787:127.0.0.1:8787 <nissanbox-host>
```

Then open:

- `http://127.0.0.1:8787`

## Launch a supervised run from inside the container

```bash
docker compose -f docker-compose.nissanbox.yml exec operator \
  python3 scripts/operator_supervisor.py run_specs/repro_pr414_smoke.json \
  --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
  --telegram-chat-id "$TELEGRAM_CHAT_ID"
```

For a full repro:

```bash
docker compose -f docker-compose.nissanbox.yml exec operator \
  python3 scripts/operator_supervisor.py run_specs/repro_pr414_full.json \
  --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
  --telegram-chat-id "$TELEGRAM_CHAT_ID"
```

## Isolation model

The container only gets:

- the repo checkout
- read-only RunPod credentials and SSH key from `~/.runpod`
- optional Telegram/webhook env vars
- the `runpodctl` binary bind-mounted read-only

This keeps the operator sandboxed away from the rest of the Nissanbox host while still letting it control RunPod pods.
