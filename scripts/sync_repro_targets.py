#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com/repos/openai/parameter-golf"
RAW_ROOT = "https://raw.githubusercontent.com/openai/parameter-golf"
USER_AGENT = "openai-project-golf-repro-sync/1.0"

TARGETS: dict[int, dict[str, Any]] = {
    414: {
        "label": "std414",
        "record_dir": "records/track_10min_16mb/2026-03-22_11L_EMA_GPTQ-lite_warmdown3500_QAT015_1.1233",
        "files": ["README.md", "submission.json", "train_gpt.py"],
    },
    505: {
        "label": "gepa505",
        "record_dir": "records/track_10min_16mb/2026-03-23_JoeProAI_SwiGLU_VE128_NoTTT",
        "files": ["README.md", "train_gpt.py"],
    },
    868: {
        "label": "ngram868",
        "record_dir": "records/track_10min_16mb/2026-03-26_Budgeted_TwoPass_Ngram_8xH100",
        "files": ["README.md", "submission.json", "requirements.txt", "train_gpt.py"],
    },
    913: {
        "label": "cache913",
        "record_dir": "records/track_10min_16mb/2026-03-27_CacheIsAllYouNeed_622KB_0.0887",
        "files": ["README.md", "submission.json", "requirements.txt", "train_gpt.py", "ngram_cache.py"],
    },
    933: {
        "label": "cache933",
        "record_dir": "records/track_10min_16mb/2026-03-27_CacheMoney_Full_6L256d",
        "files": ["README.md", "submission.json", "train_gpt.py"],
    },
}


def github_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def fetch_json(url: str) -> Any:
    with urllib.request.urlopen(github_request(url)) as response:
        return json.load(response)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return response.read()


def is_os_environ_get(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    base = func.value
    return (
        isinstance(base, ast.Attribute)
        and base.attr == "environ"
        and isinstance(base.value, ast.Name)
        and base.value.id == "os"
    )


def find_environ_get(node: ast.AST | None) -> ast.Call | None:
    if node is None:
        return None
    if is_os_environ_get(node):
        return node  # type: ignore[return-value]
    for child in ast.iter_child_nodes(node):
        env_call = find_environ_get(child)
        if env_call is not None:
            return env_call
    return None


def source_for_node(source: str, node: ast.AST | None) -> str | None:
    if node is None:
        return None
    segment = ast.get_source_segment(source, node)
    if segment is not None:
        return segment
    if sys.version_info >= (3, 9):
        return ast.unparse(node)
    return None


def extract_literal_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return source_for_node("", node)


def extract_hyperparameters(source: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    results: list[dict[str, Any]] = []
    hyperparameters_class = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Hyperparameters"),
        None,
    )
    if hyperparameters_class is None:
        return results

    for stmt in hyperparameters_class.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
            value = stmt.value
            lineno = stmt.lineno
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            value = stmt.value
            lineno = stmt.lineno
        else:
            continue

        env_call = find_environ_get(value)
        if env_call is None:
            continue

        env_name = None
        if env_call.args:
            first_arg = env_call.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                env_name = first_arg.value
            else:
                env_name = source_for_node(source, first_arg)
        default_node = env_call.args[1] if len(env_call.args) > 1 else None
        results.append(
            {
                "name": name,
                "env": env_name,
                "default": source_for_node(source, default_node),
                "line": lineno,
            }
        )

    return results


def infer_eval_modes(train_source: str) -> dict[str, bool]:
    lower = train_source.lower()
    return {
        "sliding_window": "def eval_val_sliding" in train_source,
        "ttt_eval": "def eval_val_sliding_ttt" in train_source or "TTT_EVAL_ENABLED" in train_source,
        "gptq": "gptq" in lower,
    }


def read_json_if_present(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def parse_bpb_from_text(text: str) -> float | None:
    labeled = re.search(r"val_bpb[^0-9]*(\d+\.\d+)", text, flags=re.IGNORECASE)
    if labeled:
        return float(labeled.group(1))

    candidates = [float(match) for match in re.findall(r"(?<!\d)(\d+\.\d+)(?!\d)", text)]
    bpb_candidates = [value for value in candidates if value >= 1.0]
    if bpb_candidates:
        return bpb_candidates[0]
    return candidates[0] if candidates else None


def extract_claimed_bpb(title: str, readme_text: str, submission: Any | None) -> dict[str, Any]:
    claimed = parse_bpb_from_text(title)
    if claimed is not None:
        return {"value": claimed, "source": "pr_title"}

    readme_patterns = (
        r"3-seed mean[^0-9]*(\d+\.\d+)",
        r"mean[^0-9]*(\d+\.\d+)",
        r"val_bpb[^0-9]*(\d+\.\d+)",
    )
    for pattern in readme_patterns:
        match = re.search(pattern, readme_text, flags=re.IGNORECASE)
        if match:
            return {"value": float(match.group(1)), "source": "readme"}

    if isinstance(submission, dict):
        for key in ("mean_val_bpb", "val_bpb"):
            value = submission.get(key)
            if isinstance(value, (int, float)):
                return {"value": float(value), "source": f"submission.{key}"}

    return {"value": None, "source": None}


def sync_target(pr_number: int, spec: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    pr_dir = out_dir / f"pr{pr_number}"
    pr_dir.mkdir(parents=True, exist_ok=True)

    pr_meta = fetch_json(f"{API_ROOT}/pulls/{pr_number}")
    files_meta = fetch_json(f"{API_ROOT}/pulls/{pr_number}/files?per_page=100")

    downloaded_files: list[str] = []
    for filename in spec["files"]:
        upstream_path = f"{spec['record_dir']}/{filename}"
        raw_url = f"{RAW_ROOT}/{pr_meta['head']['sha']}/{upstream_path}"
        destination = pr_dir / filename
        destination.write_bytes(fetch_bytes(raw_url))
        downloaded_files.append(filename)

    train_path = pr_dir / "train_gpt.py"
    train_source = train_path.read_text(encoding="utf-8")
    readme_text = (pr_dir / "README.md").read_text(encoding="utf-8")
    submission = read_json_if_present(pr_dir / "submission.json")

    changed_record_files = [
        item["filename"]
        for item in files_meta
        if item["filename"].startswith(f"{spec['record_dir']}/")
    ]

    return {
        "pr": pr_number,
        "label": spec["label"],
        "title": pr_meta["title"],
        "state": pr_meta["state"],
        "created_at": pr_meta["created_at"],
        "updated_at": pr_meta["updated_at"],
        "html_url": pr_meta["html_url"],
        "head_sha": pr_meta["head"]["sha"],
        "head_ref": pr_meta["head"]["ref"],
        "record_dir": spec["record_dir"],
        "downloaded_files": downloaded_files,
        "changed_record_files": changed_record_files,
        "changed_files_total": pr_meta["changed_files"],
        "commit_count": pr_meta["commits"],
        "claimed_bpb": extract_claimed_bpb(pr_meta["title"], readme_text, submission),
        "hyperparameters": extract_hyperparameters(train_source),
        "eval_modes": infer_eval_modes(train_source),
        "submission": submission,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync exact upstream record files for the active reproduction targets."
    )
    parser.add_argument(
        "--out-dir",
        default="third_party/upstream_prs",
        help="Directory where the fetched PR files should be stored.",
    )
    parser.add_argument(
        "--manifest",
        default="third_party/upstream_prs/manifest.json",
        help="Path for the generated manifest JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    manifest_path = Path(args.manifest)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "generated_by": "scripts/sync_repro_targets.py",
        "targets": [],
    }
    for pr_number, spec in TARGETS.items():
        try:
            manifest["targets"].append(sync_target(pr_number, spec, out_dir))
        except urllib.error.HTTPError as error:
            print(f"failed to sync PR #{pr_number}: HTTP {error.code} {error.reason}", file=sys.stderr)
            return 1
        except urllib.error.URLError as error:
            print(f"failed to sync PR #{pr_number}: {error.reason}", file=sys.stderr)
            return 1

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
