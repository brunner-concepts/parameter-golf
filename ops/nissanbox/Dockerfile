FROM python:3.12-slim

ARG RUNPODCTL_VERSION=1.14.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client tmux wget \
    && wget --quiet --show-progress https://github.com/Run-Pod/runpodctl/releases/download/v${RUNPODCTL_VERSION}/runpodctl-linux-amd64 -O /usr/local/bin/runpodctl \
    && chmod +x /usr/local/bin/runpodctl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/parameter-golf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python3", "scripts/serve_run_control_dashboard.py", "--host", "0.0.0.0", "--port", "8787", "--live-root", "11_RUN_CONTROL/live"]
