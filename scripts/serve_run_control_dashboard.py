#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_control_plane_payload(control_root: Path | None) -> dict[str, Any]:
    if control_root is None:
        return {}
    state_root = control_root / "state"
    return {
        "control_root": str(control_root),
        "operator_state": read_json_if_exists(state_root / "operator_state.json"),
        "frontier_snapshot": read_json_if_exists(state_root / "frontier_snapshot.json"),
        "budget_state": read_json_if_exists(state_root / "budget_state.json"),
        "queue": read_json_if_exists(state_root / "queue.json"),
        "events": read_text_if_exists(state_root / "events.jsonl"),
    }


def load_run_payload(run_dir: Path) -> dict[str, Any]:
    current = read_json_if_exists(run_dir / "current_state.json")
    heartbeat = read_json_if_exists(run_dir / "heartbeat.json")
    terminal = read_json_if_exists(run_dir / "terminal_result.json")
    mirror = read_json_if_exists(run_dir / "mirror_state.json")
    pod = read_json_if_exists(run_dir / "pod.json")
    launch = read_json_if_exists(run_dir / "launch.json")
    supervisor = read_json_if_exists(run_dir / "supervisor_state.json")
    return {
        "run_id": run_dir.name,
        "current_state": current,
        "heartbeat": heartbeat,
        "terminal_result": terminal,
        "mirror_state": mirror,
        "pod": pod,
        "launch": launch,
        "supervisor": supervisor,
        "summary": read_text_if_exists(run_dir / "summary.md"),
        "status_txt": read_text_if_exists(run_dir / "status.txt"),
        "next_action_txt": read_text_if_exists(run_dir / "next_action.txt"),
        "active_log_tail": read_text_if_exists(run_dir / "active_log.tail.txt"),
    }


def list_runs(live_root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if not live_root.exists():
        return runs
    for child in sorted(live_root.iterdir()):
        if not child.is_dir():
            continue
        payload = load_run_payload(child)
        mirrored_at = payload["mirror_state"].get("mirrored_at") or ""
        runs.append({**payload, "_sort_key": mirrored_at})
    runs.sort(key=lambda item: item["_sort_key"], reverse=True)
    return runs


def format_pre(text: str) -> str:
    return f"<pre>{html.escape(text.strip() or '(empty)')}</pre>"


def render_control_plane(control: dict[str, Any]) -> str:
    if not control:
        return ""
    operator = control.get("operator_state") or {}
    budget = control.get("budget_state") or {}
    queue = control.get("queue") or {}
    frontier = control.get("frontier_snapshot") or {}
    ranked = frontier.get("targets") or []
    ranked_items = [
        f"<li>PR #{html.escape(str(item.get('pr')))}: score={html.escape(str(item.get('ranking_score')))} "
        f"(claimed_bpb={html.escape(str(item.get('claimed_bpb')))}, legality={html.escape(str(item.get('legality_risk')))}, auto_run={html.escape(str(item.get('auto_run')))}"  # noqa: E501
        "</li>"
        for item in ranked[:5]
    ]
    if not ranked_items:
        ranked_items = ["<li>No ranked targets yet.</li>"]
    return "\n".join(
        [
            "<section class='control-plane'>",
            "<h2>Control Plane</h2>",
            "<div class='grid'>",
            "<article class='card'>",
            "<h3>Budget</h3>",
            f"<p><strong>balance</strong>: ${html.escape(str(budget.get('client_balance', 'unknown')))}</p>",
            f"<p><strong>active_pods</strong>: {html.escape(str(budget.get('active_pod_count', 'unknown')))}</p>",
            f"<p><strong>reserved_today</strong>: ${html.escape(str(budget.get('reserved_today_usd', 'unknown')))}</p>",
            f"<p><strong>daily_cap</strong>: ${html.escape(str(budget.get('daily_cap_usd', 'unknown')))}</p>",
            "</article>",
            "<article class='card'>",
            "<h3>Queue</h3>",
            f"<p><strong>blocked</strong>: {html.escape(str(queue.get('blocked', 'unknown')))}</p>",
            f"<p><strong>blocked_reason</strong>: {html.escape(str(queue.get('blocked_reason', '')))}</p>",
            f"<p><strong>next_run_id</strong>: {html.escape(str(queue.get('next_run_id', '')))}</p>",
            f"<p><strong>next_spec</strong>: {html.escape(str(queue.get('next_spec', '')))}</p>",
            "</article>",
            "<article class='card'>",
            "<h3>Operator</h3>",
            f"<p><strong>updated_at</strong>: {html.escape(str(operator.get('updated_at', 'unknown')))}</p>",
            f"<p><strong>dashboard_pid</strong>: {html.escape(str(operator.get('dashboard_pid', '')))}</p>",
            f"<p><strong>supervisor_pid</strong>: {html.escape(str(operator.get('supervisor_pid', '')))}</p>",
            f"<p><strong>top_ranked_target</strong>: {html.escape(str(operator.get('top_ranked_target', '')))}</p>",
            "</article>",
            "<article class='card'>",
            "<h3>Frontier Ranking</h3>",
            "<ol>",
            *ranked_items,
            "</ol>",
            "</article>",
            "</div>",
            "</section>",
        ]
    )


def render_index(live_root: Path, control_root: Path | None) -> str:
    runs = list_runs(live_root)
    control_payload = load_control_plane_payload(control_root)
    cards = []
    for run in runs:
        current = run["current_state"]
        mirror = run["mirror_state"]
        pod = run["pod"]
        cards.append(
            "\n".join(
                [
                    '<article class="card">',
                    f"<h2><a href=\"/runs/{urllib.parse.quote(run['run_id'])}\">{html.escape(run['run_id'])}</a></h2>",
                    f"<p><strong>classification</strong>: {html.escape(str(mirror.get('classification', 'unknown')))}</p>",
                    f"<p><strong>run_status</strong>: {html.escape(str(current.get('status', 'unknown')))}</p>",
                    f"<p><strong>phase</strong>: {html.escape(str(current.get('phase_id', 'none')))}</p>",
                    f"<p><strong>pod_status</strong>: {html.escape(str(pod.get('desiredStatus', 'unknown')))}</p>",
                    f"<p><strong>updated_at</strong>: {html.escape(str(current.get('updated_at', mirror.get('mirrored_at', ''))))}</p>",
                    "</article>",
                ]
            )
        )
    if not cards:
        cards_html = "<p>No mirrored runs yet.</p>"
    else:
        cards_html = "\n".join(cards)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='10'>"
        "<title>Run Control Dashboard</title>"
        "<style>"
        "body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#0c1016;color:#e6edf3;margin:0;padding:24px;}"
        "a{color:#7cc7ff;} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;}"
        ".card{background:#151b23;border:1px solid #30363d;border-radius:10px;padding:16px;}"
        "h1,h2{margin-top:0;} p{margin:8px 0;}"
        "</style></head><body>"
        "<h1>Run Control Dashboard</h1>"
        f"<p>Live root: <code>{html.escape(str(live_root))}</code></p>"
        f"{render_control_plane(control_payload)}"
        f"<section class='grid'>{cards_html}</section>"
        "</body></html>"
    )


def render_run_detail(live_root: Path, run_id: str) -> str:
    run_dir = live_root / run_id
    payload = load_run_payload(run_dir)
    if not run_dir.exists():
        return "<!doctype html><html><body><h1>Run not found</h1></body></html>"
    current = payload["current_state"]
    mirror = payload["mirror_state"]
    pod = payload["pod"]
    sections = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta http-equiv='refresh' content='10'>",
        f"<title>{html.escape(run_id)}</title>",
        "<style>"
        "body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#0c1016;color:#e6edf3;margin:0;padding:24px;}"
        "a{color:#7cc7ff;} .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-bottom:24px;}"
        ".card{background:#151b23;border:1px solid #30363d;border-radius:10px;padding:16px;}"
        "pre{white-space:pre-wrap;word-break:break-word;background:#0d1117;padding:12px;border-radius:8px;border:1px solid #30363d;}"
        "h1,h2{margin-top:0;}"
        "</style></head><body>",
        f"<p><a href='/'>Back</a></p>",
        f"<h1>{html.escape(run_id)}</h1>",
        "<section class='meta'>",
        f"<div class='card'><strong>classification</strong><br>{html.escape(str(mirror.get('classification', 'unknown')))}</div>",
        f"<div class='card'><strong>run_status</strong><br>{html.escape(str(current.get('status', 'unknown')))}</div>",
        f"<div class='card'><strong>phase</strong><br>{html.escape(str(current.get('phase_id', 'none')))}</div>",
        f"<div class='card'><strong>pod_status</strong><br>{html.escape(str(pod.get('desiredStatus', 'unknown')))}</div>",
        f"<div class='card'><strong>pod_cost_per_hr</strong><br>{html.escape(str(pod.get('costPerHr', 'unknown')))}</div>",
        f"<div class='card'><strong>updated_at</strong><br>{html.escape(str(current.get('updated_at', mirror.get('mirrored_at', ''))))}</div>",
        "</section>",
        "<h2>Summary</h2>",
        format_pre(payload["summary"]),
        "<h2>Log Tail</h2>",
        format_pre(payload["active_log_tail"]),
        "<h2>Next Action</h2>",
        format_pre(payload["next_action_txt"]),
        "<h2>Current State JSON</h2>",
        format_pre(json.dumps(payload["current_state"], indent=2, sort_keys=True)),
        "<h2>Terminal Result JSON</h2>",
        format_pre(json.dumps(payload["terminal_result"], indent=2, sort_keys=True)),
        "<h2>Supervisor State JSON</h2>",
        format_pre(json.dumps(payload["supervisor"], indent=2, sort_keys=True)),
        "</body></html>",
    ]
    return "".join(sections)


class DashboardHandler(BaseHTTPRequestHandler):
    live_root: Path
    control_root: Path | None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            return self.respond_html(render_index(self.live_root, self.control_root))
        if parsed.path == "/api/control-plane":
            return self.respond_json(load_control_plane_payload(self.control_root))
        if parsed.path == "/api/runs":
            runs = list_runs(self.live_root)
            return self.respond_json(runs)
        if parsed.path.startswith("/api/runs/"):
            run_id = urllib.parse.unquote(parsed.path.removeprefix("/api/runs/"))
            return self.respond_json(load_run_payload(self.live_root / run_id))
        if parsed.path.startswith("/runs/"):
            run_id = urllib.parse.unquote(parsed.path.removeprefix("/runs/"))
            return self.respond_html(render_run_detail(self.live_root, run_id))
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def respond_html(self, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def respond_json(self, payload_obj: Any) -> None:
        payload = json.dumps(payload_obj, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the mirrored run-control dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--live-root", default="11_RUN_CONTROL/live")
    parser.add_argument("--control-plane-root", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    live_root = Path(args.live_root).resolve()
    control_root = Path(args.control_plane_root).resolve() if args.control_plane_root else None
    handler_cls = type(
        "RunControlDashboardHandler",
        (DashboardHandler,),
        {"live_root": live_root, "control_root": control_root},
    )
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(f"Run Control Dashboard serving {live_root} on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
