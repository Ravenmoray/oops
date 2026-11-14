"""The GitHub issue form and the CI intake check must agree with each other."""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import oops_validate  # noqa: E402

FORM = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/mistake-report.yml").read_text())


def template() -> str:
    return next(b for b in FORM["body"] if b.get("id") == "entry")["attributes"]["value"]


def as_issue_body(entry_yaml: str) -> str:
    # This is how GitHub renders an issue form with `render: yaml` into the issue body.
    return (f"### Entry\n\n```yaml\n{entry_yaml}\n```\n\n### Before submitting\n\n"
            "- [X] It contains no personal data, secrets, or private content.\n- [X] I release this entry under CC0 1.0.")


def test_template_parses_and_uses_valid_enums():
    data = yaml.safe_load(template())
    schema = oops_validate.load_schema()["properties"]
    for field in ("domain", "severity", "root_cause", "detected_by"):
        assert data[field] in schema[field]["enum"], field


def test_filled_form_passes_intake():
    filled = template().replace("Past-tense description of what went wrong", "Quoted a stale API flag from memory") \
                       .replace("[example-tag]", "[cli, flags]")
    ok, report = oops_validate.check_issue_body(as_issue_body(filled))
    assert ok, report


def test_form_submission_with_private_data_is_flagged():
    filled = template().replace("The kind of task and setting, in general terms.",
                                "Helping jane.doe@example.com debug her server at 192.168.1.20.")
    ok, report = oops_validate.check_issue_body(as_issue_body(filled))
    assert not ok and "redacted" in report
