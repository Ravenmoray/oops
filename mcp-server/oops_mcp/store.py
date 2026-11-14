"""Loading, indexing and searching OOPS entries.

Depends only on PyYAML. Used by the MCP server and by tools/oops_validate.py.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

import yaml

DATA_DIR = Path(__file__).parent / "data"

STATUS_WEIGHT = {"confirmed": 1.3, "reviewed": 1.1, "seed": 1.0, "disputed": 0.6, "deprecated": 0.0}

# Field weights for retrieval. Advice and triggers matter most.
FIELD_WEIGHTS = {
    "title": 3.0,
    "lesson": 3.0,
    "applies_when": 3.0,
    "tags": 2.5,
    "check": 2.0,
    "root_cause": 2.0,
    "domain": 1.5,
    "situation": 1.5,
    "what_happened": 1.0,
    "fix": 0.75,
}

_STOP = set("""
a an and are as at be been but by can could did do does for from had has have how i if in into is it
its just me my of on or our should so than that the their them then there these they this to was we
were what when where which while who why will with would you your about after before also any
""".split())

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]|[a-z0-9]")


def _stem(word: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "edly", "ied", "ies", "ed", "es", "ly", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    words = _TOKEN.findall(text.lower())
    out: list[str] = []
    for w in words:
        # split compound tokens like "rm-rf" or "date-math" into parts as well
        parts = [w] + ([p for p in re.split(r"[\-.]", w) if p] if ("-" in w or "." in w) else [])
        for p in parts:
            if p not in _STOP and len(p) > 1:
                out.append(_stem(p))
    return out


def normalize(entry: dict) -> dict:
    """YAML turns bare dates into date objects and folded strings end in newlines; tidy both."""

    def fix(v):
        if isinstance(v, (_dt.date, _dt.datetime)):
            return v.isoformat()[:10]
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, list):
            return [fix(x) for x in v]
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        return v

    return {k: fix(v) for k, v in entry.items()}


def load_entry_file(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: top level must be a mapping")
    return normalize(data)


def load_entries_dir(entries_dir: Path) -> list[dict]:
    return [load_entry_file(p) for p in sorted(entries_dir.glob("*.yaml"))]


def load_json(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def entry_to_yaml(entry: dict) -> str:
    """Stable, human-friendly YAML for an entry."""

    class _Dumper(yaml.SafeDumper):
        pass

    def _str(dumper, value: str):
        style = "|" if "\n" in value else ">" if len(value) > 90 else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    _Dumper.add_representer(str, _str)
    return yaml.dump(entry, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=88)


class Index:
    """A small in-memory BM25-style index over entries. Fine into the tens of thousands."""

    def __init__(self, entries: Iterable[dict]):
        self.entries = {e["id"]: e for e in entries}
        self._docs: dict[str, dict[str, Counter]] = {}
        df: Counter = Counter()
        for eid, e in self.entries.items():
            fields: dict[str, Counter] = {}
            for f in FIELD_WEIGHTS:
                v = e.get(f)
                if isinstance(v, list):
                    v = " ".join(map(str, v))
                if v:
                    fields[f] = Counter(tokenize(str(v)))
            self._docs[eid] = fields
            df.update(set().union(*[set(c) for c in fields.values()]) if fields else set())
        n = max(len(self.entries), 1)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, entry_id: str) -> dict | None:
        return self.entries.get(entry_id.strip().upper())

    def search(
        self,
        query: str,
        *,
        domain: str | None = None,
        root_cause: str | None = None,
        limit: int = 5,
        include_disputed: bool = False,
    ) -> list[tuple[float, dict]]:
        terms = tokenize(query)
        results: list[tuple[float, dict]] = []
        for eid, e in self.entries.items():
            status = e.get("status", "seed")
            if status == "deprecated" or (status == "disputed" and not include_disputed):
                continue
            if domain and e.get("domain") != domain:
                continue
            if root_cause and e.get("root_cause") != root_cause:
                continue
            fields = self._docs[eid]
            score = 0.0
            for t in terms:
                idf = self._idf.get(t)
                if not idf:
                    continue
                for f, counts in fields.items():
                    tf = counts.get(t, 0)
                    if tf:
                        score += idf * FIELD_WEIGHTS[f] * (tf / (tf + 1.0))
            if not terms and (domain or root_cause):
                score = 1.0  # pure filter query
            if score <= 0:
                continue
            fb = e.get("feedback") or {}
            votes = max(0, int(e.get("confirmations", 0)) + int(fb.get("helpful", 0)) - int(fb.get("not_helpful", 0)))
            score *= STATUS_WEIGHT.get(status, 1.0) * (1 + 0.15 * math.log1p(votes))
            results.append((score, e))
        results.sort(key=lambda r: (-r[0], r[1]["id"]))
        return results[: max(1, min(limit, 25))]
