import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mcp-server"))

from oops_mcp.store import Index, load_entries_dir  # noqa: E402

IDX = Index(load_entries_dir(ROOT / "entries"))


def top(query, **kw):
    hits = IDX.search(query, **kw)
    return hits[0][1]["id"] if hits else None


def test_natural_queries_find_the_right_lesson():
    cases = {
        "tell the user the tests pass": "OOPS-0001",
        "pip install a library for parsing pdfs": "OOPS-0002",
        "who is the current CEO of the company": "OOPS-0003",
        "rewrite a large config file": "OOPS-0004",
        "delete the build directory in a cleanup script": "OOPS-0005",
        "summarize this web page for me": "OOPS-0006",
        "schedule a cron job for 9am": "OOPS-0007",
        "fix a small bug in one function": "OOPS-0008",
        "request failed again, retry": "OOPS-0009",
        "the user says my total is wrong": "OOPS-0010",
        "what day of the week is March 3": "OOPS-0011",
        "import the sdk server class": "OOPS-0013",
    }
    misses = {q: (top(q), want) for q, want in cases.items() if top(q) != want}
    assert not misses, misses


def test_filters():
    hits = IDX.search("", root_cause="sycophancy")
    assert [e["id"] for _, e in hits] == ["OOPS-0010"]
    assert all(e["domain"] == "coding" for _, e in IDX.search("file", domain="coding"))


def test_status_and_feedback_affect_rank():
    a = {"id": "OOPS-1000", "status": "seed", "title": "Widget mistake one happened",
         "lesson": "Check the widget before shipping it out.", "domain": "coding", "root_cause": "other"}
    b = {**a, "id": "OOPS-1001", "status": "confirmed", "feedback": {"helpful": 9, "not_helpful": 0}}
    c = {**a, "id": "OOPS-1002", "status": "deprecated"}
    d = {**a, "id": "OOPS-1003", "status": "disputed"}
    idx = Index([a, b, c, d])
    ids = [e["id"] for _, e in idx.search("widget")]
    assert ids == ["OOPS-1001", "OOPS-1000"]
    assert "OOPS-1003" in [e["id"] for _, e in idx.search("widget", include_disputed=True)]
