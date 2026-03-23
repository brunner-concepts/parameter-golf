#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path
from typing import Any


def find_ttt_function(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and "ttt" in node.name.lower():
            return node
    return None


def find_line(lines: list[str], start: int, end: int, pattern: str) -> int | None:
    regex = re.compile(pattern)
    for line_no in range(start, end + 1):
        if regex.search(lines[line_no - 1]):
            return line_no
    return None


def snippet(lines: list[str], line_no: int | None) -> str | None:
    if line_no is None:
        return None
    return lines[line_no - 1].strip()


def audit_file(path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    function = find_ttt_function(tree)
    if function is None:
        return {
            "path": str(path),
            "status": "fail",
            "reason": "No top-level TTT evaluation function found.",
            "checks": {},
            "evidence": {},
        }

    start = function.lineno
    end = function.end_lineno or len(lines)

    evidence = {
        "chunk_loop": find_line(lines, start, end, r"for\s+\w+\s+in\s+range\(num_chunks\):"),
        "inference_mode": find_line(lines, start, end, r"torch\.inference_mode\("),
        "score_accumulator": find_line(lines, start, end, r"loss_sum\s*\+=|token_count\s*\+="),
        "restore_raw_weights": find_line(lines, start, end, r"Restore raw weights"),
        "last_chunk_guard": find_line(lines, start, end, r"<\s*num_chunks\s*-\s*1"),
        "optimizer_step": find_line(lines, start, end, r"optimizer\.step\("),
    }
    training_read_start = evidence["last_chunk_guard"] or start
    evidence["training_reads_val_tokens"] = find_line(lines, training_read_start, end, r"val_tokens\[")

    checks = {
        "chunk_loop_present": evidence["chunk_loop"] is not None,
        "scores_under_inference_mode": evidence["inference_mode"] is not None,
        "scores_before_optimizer_step": (
            evidence["score_accumulator"] is not None
            and evidence["optimizer_step"] is not None
            and evidence["score_accumulator"] < evidence["optimizer_step"]
        ),
        "guards_last_chunk_from_training": (
            evidence["last_chunk_guard"] is not None
            and evidence["optimizer_step"] is not None
            and evidence["last_chunk_guard"] < evidence["optimizer_step"]
        ),
        "training_reads_validation_tokens": (
            evidence["training_reads_val_tokens"] is not None
            and evidence["optimizer_step"] is not None
            and evidence["training_reads_val_tokens"] < evidence["optimizer_step"]
        ),
    }

    status = "pass" if all(checks.values()) else "review"
    return {
        "path": str(path),
        "function": function.name,
        "status": status,
        "checks": checks,
        "evidence": {
            name: {
                "line": line_no,
                "snippet": snippet(lines, line_no),
            }
            for name, line_no in evidence.items()
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# TTT legality audit: `{report['path']}`",
        "",
        f"- Status: **{report['status']}**",
    ]
    if "function" in report:
        lines.append(f"- Function: `{report['function']}`")
    if report.get("reason"):
        lines.append(f"- Reason: {report['reason']}")
    lines.extend(["", "## Checks", ""])
    for name, passed in report.get("checks", {}).items():
        lines.append(f"- `{name}`: {'pass' if passed else 'review'}")
    lines.extend(["", "## Evidence", ""])
    for name, payload in report.get("evidence", {}).items():
        line_no = payload.get("line")
        text = payload.get("snippet")
        if line_no is None:
            lines.append(f"- `{name}`: not found")
        else:
            lines.append(f"- `{name}`: line {line_no} -> `{text}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit a train_gpt.py file for score-first TTT ordering.")
    parser.add_argument("path", help="Path to the train_gpt.py file to audit.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_file(Path(args.path))
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
