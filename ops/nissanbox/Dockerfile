FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git openssh-client tmux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/parameter-golf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python3", "scripts/serve_run_control_dashboard.py", "--host", "0.0.0.0", "--port", "8787", "--live-root", "11_RUN_CONTROL/live"]
