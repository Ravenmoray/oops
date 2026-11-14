#!/usr/bin/env python3
"""Validate OOPS entries and build the published dataset.

  python tools/oops_validate.py                     # validate entries/
  python tools/oops_validate.py --build dist        # validate + write index.json, dataset.jsonl, sft.jsonl
  python tools/oops_validate.py --sync-package      # copy schema/taxonomy/index into the MCP package
  python tools/oops_validate.py --check-sync        # fail if the MCP package copies are stale
  python tools/oops_validate.py --issue-body F      # check a submission issue body; prints a markdown report

Requires: PyYAML, jsonschema.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

from oops_mcp.scrub import lint_entry, redact_entry  # noqa: E402
from oops_mcp.store import entry_to_yaml, load_entry_file, normalize  # noqa: E402

SCHEMA_PATH = ROOT / "schema" / "entry.schema.json"
TAXONOMY_PATH = ROOT / "schema" / "taxonomy.json"
ENTRIES_DIR = ROOT / "entries"
PACKAGE_DATA = ROOT / "mcp-server" / "oops_mcp" / "data"
SUBMISSION_MARKER = "<!-- oops-submission v1 -->"
FEEDBACK_MARKER = "<!-- oops-feedback v1 -->"
LICENSE_ID = "CC0-1.0"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def check_taxonomy_consistency(schema: dict, taxonomy: dict) -> list[str]:
    errors = []
    pairs = [
        ("root_cause", "root_causes"),
        ("domain", "domains"),
        ("detected_by", "detected_by"),
        ("status", "statuses"),
        ("severity", "severities"),
    ]
    for prop, key in pairs:
        enum = set(schema["properties"][prop]["enum"])
        tax = set(taxonomy[key])
        if enum != tax:
            errors.append(f"schema.{prop} enum and taxonomy.{key} differ: {sorted(enum ^ tax)}")
    return errors


def validate_entries(entries_dir: Path) -> tuple[list[dict], list[str], list[str]]:
    schema = load_schema()
    taxonomy = load_taxonomy()
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = check_taxonomy_consistency(schema, taxonomy)
    warnings: list[str] = []
    entries: list[dict] = []
    seen: dict[str, str] = {}

    for path in sorted(entries_dir.glob("*")):
        if path.name.startswith(".") or path.name == "README.md":
            continue
        if path.suffix != ".yaml":
            errors.append(f"{path.name}: entries must be .yaml files")
            continue
        try:
            entry = load_entry_file(path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: cannot parse: {exc}")
            continue

        for err in sorted(validator.iter_errors(entry), key=lambda e: list(e.path)):
            loc = ".".join(map(str, err.path)) or "(entry)"
            errors.append(f"{path.name}: {loc}: {err.message}")

        eid = entry.get("id", "")
        if path.stem != eid:
            errors.append(f"{path.name}: id '{eid}' does not match file name")
        if eid in seen:
            errors.append(f"{path.name}: duplicate id {eid} (also in {seen[eid]})")
        seen[eid] = path.name

        for issue in lint_entry(entry):
            (errors if issue.level == "error" else warnings).append(f"{path.name}: {issue}")

        entries.append(entry)

    ids = set(seen)
    for e in entries:
        refs = list(e.get("related", [])) + [e[k] for k in ("supersedes", "superseded_by") if k in e]
        for ref in refs:
            if ref not in ids:
                errors.append(f"{e.get('id')}.yaml: references unknown entry {ref}")
            if ref == e.get("id"):
                errors.append(f"{e.get('id')}.yaml: references itself")
        if e.get("superseded_by") and e.get("status") != "deprecated":
            warnings.append(f"{e.get('id')}.yaml: superseded_by is set but status is not 'deprecated'")

    return entries, errors, warnings


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_index(entries: list[dict]) -> dict:
    return {
        "format": "oops-index",
        "version": 1,
        "license": LICENSE_ID,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "taxonomy": load_taxonomy(),
        "entries": sorted(entries, key=lambda e: e["id"]),
    }


SFT_SYSTEM = (
    "You are an AI assistant reviewing your own plan before acting. "
    "Name the most likely mistake in this situation and the rule that prevents it."
)


def to_sft(entry: dict, taxonomy: dict) -> dict:
    """One possible instruction-tuning shape: situation -> mistake + lesson."""
    cause = taxonomy["root_causes"].get(entry["root_cause"], "")
    answer = [f"Likely mistake: {entry['title']}.", f"Root cause ({entry['root_cause']}): {cause}"]
    answer.append(f"Rule: {entry['lesson']}")
    if entry.get("check"):
        answer.append(f"Check before acting: {entry['check']}")
    return {
        "id": entry["id"],
        "license": LICENSE_ID,
        "messages": [
            {"role": "system", "content": SFT_SYSTEM},
            {"role": "user", "content": entry["situation"]},
            {"role": "assistant", "content": "\n".join(answer)},
        ],
    }


def write_build(entries: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index = build_index(entries)
    (out_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    usable = [e for e in index["entries"] if e["status"] not in ("deprecated", "disputed")]
    with (out_dir / "dataset.jsonl").open("w", encoding="utf-8") as fh:
        for e in index["entries"]:
            fh.write(json.dumps({**e, "license": LICENSE_ID}, ensure_ascii=False) + "\n")
    with (out_dir / "sft.jsonl").open("w", encoding="utf-8") as fh:
        for e in usable:
            fh.write(json.dumps(to_sft(e, index["taxonomy"]), ensure_ascii=False) + "\n")
    site = ROOT / "site" / "index.html"
    if site.exists():
        (out_dir / "index.html").write_text(site.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"built {out_dir}: {len(entries)} entries, {len(usable)} training examples")


def sync_package(entries: list[dict], check_only: bool) -> bool:
    """The MCP server ships a copy of the schema, taxonomy and index so it works offline."""
    wanted = {
        "entry.schema.json": SCHEMA_PATH.read_text(encoding="utf-8"),
        "taxonomy.json": TAXONOMY_PATH.read_text(encoding="utf-8"),
    }
    stale = []
    for name, content in wanted.items():
        target = PACKAGE_DATA / name
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            stale.append(name)
            if not check_only:
                PACKAGE_DATA.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
    bundled = PACKAGE_DATA / "bundled_index.json"
    current_ids = sorted(e["id"] for e in entries)
    try:
        bundled_ids = sorted(e["id"] for e in json.loads(bundled.read_text(encoding="utf-8"))["entries"])
        bundled_entries = sorted(json.loads(bundled.read_text(encoding="utf-8"))["entries"], key=lambda e: e["id"])
    except (OSError, ValueError, KeyError):
        bundled_ids, bundled_entries = None, None
    if bundled_ids != current_ids or bundled_entries != sorted(entries, key=lambda e: e["id"]):
        stale.append("bundled_index.json")
        if not check_only:
            bundled.write_text(json.dumps(build_index(entries), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if stale:
        verb = "stale" if check_only else "updated"
        print(f"package data {verb}: {', '.join(stale)}")
    return not stale


# ---------------------------------------------------------------------------
# Submission (issue body) checks
# ---------------------------------------------------------------------------

_YAML_FENCE = re.compile(r"```ya?ml\s*\n(.*?)\n```", re.S)


def check_issue_body(body: str) -> tuple[bool, str]:
    """Validate a submitted entry from an issue body. Returns (ok, markdown_report)."""
    if FEEDBACK_MARKER in body:
        return True, "Thanks — feedback noted. A maintainer will fold it into the entry's counts."
    blocks = _YAML_FENCE.findall(body)
    if not blocks:
        return False, "No ```yaml block found. Paste the entry inside a ```yaml fenced block."
    try:
        entry = yaml.safe_load(blocks[0])
    except yaml.YAMLError as exc:
        return False, f"The YAML block does not parse:\n\n```\n{exc}\n```"
    if not isinstance(entry, dict):
        return False, "The YAML block must be a mapping of fields."
    entry = normalize(entry)
    # Maintainers assign these at merge; fill placeholders so the rest can be checked.
    entry.setdefault("id", "OOPS-9999")
    entry.setdefault("status", "reviewed")
    entry.setdefault("created", dt.date.today().isoformat())

    validator = Draft202012Validator(load_schema(), format_checker=FormatChecker())
    problems = [f"- `{'.'.join(map(str, e.path)) or 'entry'}`: {e.message}" for e in validator.iter_errors(entry)]
    lint = lint_entry(entry)
    problems += [f"- {i}" for i in lint if i.level == "error"]
    notes = [f"- {i}" for i in lint if i.level == "warning"]

    lines = []
    if problems:
        lines += ["### Automated check: changes needed", "", *problems]
        _, reds = redact_entry(entry)
        if reds:
            lines += ["", "Detected private data was **not** auto-removed here; please edit the issue to remove it."]
    else:
        lines += ["### Automated check: passed", "", "Schema and safety checks passed. A maintainer will review it."]
    if notes:
        lines += ["", "Notes:", *notes]
    lines += ["", f"_Checked by tools/oops_validate.py. Accepted entries are published under {LICENSE_ID}._"]
    return not problems, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", metavar="DIR", type=Path)
    ap.add_argument("--sync-package", action="store_true")
    ap.add_argument("--check-sync", action="store_true")
    ap.add_argument("--issue-body", metavar="FILE", type=Path)
    ap.add_argument("--report", metavar="FILE", type=Path, help="with --issue-body: also write the report here")
    ap.add_argument("--print-yaml", metavar="ID", help="print an entry re-serialized (formatting check)")
    args = ap.parse_args(argv)

    if args.issue_body:
        ok, report = check_issue_body(args.issue_body.read_text(encoding="utf-8"))
        print(report)
        if args.report:
            args.report.write_text(report + "\n", encoding="utf-8")
        return 0 if ok else 1

    entries, errors, warnings = validate_entries(ENTRIES_DIR)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\n{len(errors)} error(s) in {len(entries)} entries")
        return 1
    print(f"ok: {len(entries)} entries valid")

    if args.print_yaml:
        match = [e for e in entries if e["id"] == args.print_yaml]
        print(entry_to_yaml(match[0]) if match else f"no entry {args.print_yaml}")
    if args.build:
        write_build(entries, args.build)
    if args.sync_package or args.check_sync:
        in_sync = sync_package(entries, check_only=args.check_sync)
        if args.check_sync and not in_sync:
            print("run: python tools/oops_validate.py --sync-package")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
