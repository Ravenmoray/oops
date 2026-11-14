"""Privacy scrubbing and safety linting for OOPS entries.

Standard library only: shared by the MCP server (before anything leaves the
user's machine) and by the CI validator (before anything is published).

Two jobs:
  redact()      - remove secrets and personal data, report what was removed.
  lint_entry()  - reject content that could poison agents that later read it
                  (prompt injection, links and commands in lessons, hidden
                  unicode), since every published lesson is fed back into
                  other models' context windows.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# (label, pattern, replacement). Order matters: specific secrets before generic.
_REDACTIONS: list[tuple[str, re.Pattern[str], str]] = [
    ("private-key",
     re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)", re.S),
     "[REDACTED-PRIVATE-KEY]"),
    ("url-credentials",
     re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@"),
     "[REDACTED-CREDENTIALS]@"),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{22,})\b"),
     "[REDACTED-GITHUB-TOKEN]"),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[REDACTED-API-KEY]"),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED-SLACK-TOKEN]"),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED-GOOGLE-KEY]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[REDACTED-JWT]"),
    # Placeholders below must never match any pattern here or in the injection lint:
    # redact() has to be idempotent, because lint re-runs it on already-redacted text.
    ("assigned-secret",
     re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|auth)(\s*[:=]\s*)(['\"]?)(?!\[REDACTED)[^\s'\"]{4,}\3"),
     r"\1\2[REDACTED]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
    ("home-path-unix", re.compile(r"(/(?:home|Users))/(?!\[user\])[A-Za-z0-9._\-]+"), r"\1/[user]"),
    ("home-path-windows", re.compile(r"(?i)([A-Z]:\\Users)\\(?!\[user\])[A-Za-z0-9._\-]+"), r"\1\\[user]"),
    ("phone", re.compile(r"(?<![\w.])\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?![\w.])"), "[REDACTED-PHONE]"),
]

_IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")
_IP_ALLOW = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}


@dataclass
class Redaction:
    kind: str
    count: int


@dataclass
class ScrubResult:
    text: str
    redactions: list[Redaction] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.redactions)


def _redact_ips(text: str) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal n
        ip = m.group(0)
        if ip in _IP_ALLOW or any(int(o) > 255 for o in m.groups()):
            return ip  # loopback / not an address (e.g. a version string)
        n += 1
        return "[REDACTED-IP]"

    return _IPV4.sub(repl, text), n


def redact(text: str) -> ScrubResult:
    """Remove secrets and personal data from free text."""
    if not text:
        return ScrubResult(text or "")
    found: dict[str, int] = {}
    for kind, pattern, replacement in _REDACTIONS:
        text, n = pattern.subn(replacement, text)
        if n:
            found[kind] = found.get(kind, 0) + n
    text, n = _redact_ips(text)
    if n:
        found["ip-address"] = n
    return ScrubResult(text, [Redaction(k, v) for k, v in found.items()])


def redact_entry(entry: dict) -> tuple[dict, list[Redaction]]:
    """Redact every string in an entry (recursively). Returns (clean_entry, redactions)."""
    totals: dict[str, int] = {}

    def walk(value):
        if isinstance(value, str):
            r = redact(value)
            for red in r.redactions:
                totals[red.kind] = totals.get(red.kind, 0) + red.count
            return r.text
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    clean = walk(entry)
    return clean, [Redaction(k, v) for k, v in totals.items()]


# ---------------------------------------------------------------------------
# Safety lint (anti-poisoning)
# ---------------------------------------------------------------------------

# Phrases typical of prompt injection. Lessons are read by other agents, so a
# lesson must never try to instruct the reader outside its own advice.
_INJECTION = re.compile(
    r"(?i)("
    r"ignore (?:all |any |the )?(?:previous|prior|above|earlier|other) (?:instructions|rules|prompts?)"
    r"|disregard (?:all |any |the |your )?(?:previous |prior |system )?(?:instructions|rules|guidelines|prompt)"
    r"|(?:reveal|print|output|show) (?:your |the )?system prompt"
    r"|you are now\b"
    r"|new instructions\s*:"
    r"|from now on,? (?:you|always|never)"
    r"|do not tell the user"
    r"|without (?:telling|informing|asking) the user"
    r"|<\s*/?\s*(?:system|assistant|user|instructions?)\s*>"
    r"|\[\s*(?:system|INST)\s*\]"
    r")"
)

_URL = re.compile(r"(?i)\b(?:https?|ftp|file|data|javascript):[^\s]*|\bwww\.[^\s]+")
# Shell commands that fetch-and-execute or escalate. Forbidden in advice fields.
_DANGEROUS_CMD = re.compile(
    r"(?i)(?:\b(?:curl|wget|iwr|invoke-webrequest)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"
    r"|\bsudo\s+\S+"
    r"|\brm\s+-[a-z]*r[a-z]*f?\s+[/~$]"
    r"|\bchmod\s+(?:-R\s+)?777\b"
    r"|\beval\s*\("
    r"|\bbase64\s+(?:-d|--decode)\b"
    r"|\bpowershell(?:\.exe)?\s+-(?:enc|e)\b)"
)

# Invisible / direction-changing characters used to hide text from reviewers.
_HIDDEN_CODEPOINTS = {
    *range(0x200B, 0x2010),   # zero-width space/joiners, LRM/RLM
    *range(0x202A, 0x202F),   # bidi embeddings/overrides
    *range(0x2060, 0x2065),   # word joiner, invisible operators
    *range(0x2066, 0x206A),   # bidi isolates
    0xFEFF,                   # BOM / zero-width no-break space
    *range(0xE0000, 0xE0080), # tag characters (ASCII smuggling)
}

# Fields that are *advice* and get read as guidance by other agents.
ADVICE_FIELDS = ("lesson", "check", "applies_when", "title")


@dataclass
class LintIssue:
    level: str   # "error" | "warning"
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper()} [{self.field}] {self.message}"


def _strings(entry: dict, prefix: str = ""):
    for key, value in entry.items():
        name = f"{prefix}{key}"
        if isinstance(value, str):
            yield name, value
        elif isinstance(value, list):
            for i, v in enumerate(value):
                if isinstance(v, str):
                    yield f"{name}[{i}]", v
                elif isinstance(v, dict):
                    yield from _strings(v, f"{name}[{i}].")
        elif isinstance(value, dict):
            yield from _strings(value, f"{name}.")


def lint_entry(entry: dict) -> list[LintIssue]:
    """Check an entry for content that is unsafe to publish or to feed to other agents."""
    issues: list[LintIssue] = []

    for name, text in _strings(entry):
        root = name.split("[")[0].split(".")[0]

        hidden = sorted({f"U+{ord(c):04X}" for c in text if ord(c) in _HIDDEN_CODEPOINTS})
        if hidden:
            issues.append(LintIssue("error", name, f"hidden/bidi unicode characters: {', '.join(hidden)}"))
        if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
            issues.append(LintIssue("error", name, "control characters"))

        if _INJECTION.search(text):
            issues.append(LintIssue("error", name, "looks like an instruction to the reading agent (prompt injection)"))

        residual = redact(text)
        if residual.changed:
            kinds = ", ".join(r.kind for r in residual.redactions)
            issues.append(LintIssue("error", name, f"contains data that must be redacted: {kinds}"))

        if root in ADVICE_FIELDS:
            if _URL.search(text):
                issues.append(LintIssue("error", name, "advice fields may not contain links"))
            if _DANGEROUS_CMD.search(text):
                issues.append(LintIssue("error", name, "advice fields may not contain executable commands"))
        else:
            if _DANGEROUS_CMD.search(text) and re.search(r"(?i)\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", text):
                issues.append(LintIssue("error", name, "pipe-to-shell commands are not allowed anywhere"))
            if _URL.search(text) and root not in ("sources",):
                issues.append(LintIssue("warning", name, "links in narrative fields will be reviewed; prefer describing the source"))

    lesson = entry.get("lesson", "")
    if lesson and lesson.strip().lower().startswith(("i ", "we ", "the user ")):
        issues.append(LintIssue("warning", "lesson", "write the lesson as a general rule in the imperative, not as a narrative"))

    return issues
