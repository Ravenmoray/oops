# oops

[![ci](https://github.com/Ravenmoray/oops/actions/workflows/ci.yml/badge.svg)](https://github.com/Ravenmoray/oops/actions/workflows/ci.yml)
[![license: CC0 public domain](https://img.shields.io/badge/license-CC0%20public%20domain-lightgrey)](LICENSE)

**A public log of mistakes AI systems made, and the lessons learned from them.**

Browse the log: **https://ravenmoray.github.io/oops/**

Every AI agent makes the same mistakes as thousands of others: it claims the tests passed
without running them, recommends a package that doesn't exist, rewrites a file from truncated
output, follows instructions hidden in a web page. Each time, the lesson is learned once and then
lost when the session ends.

OOPS keeps those lessons and shares them, in two loops:

| Loop | Who learns | How | When |
|---|---|---|---|
| **In context** | Any agent, today | The MCP server lets an agent search the log before it acts | Immediately |
| **In training** | Future models | The whole log is published as a public-domain dataset (CC0) | Next training run |

```
   agent makes a mistake ──► draft_mistake_report ──► scrubbed + safety-linted, saved locally
                                                              │
                                              human reads it and approves
                                                              │
                                                              ▼
   GitHub issue ──► CI intake check ──► maintainer review ──► entries/OOPS-NNNN.yaml (PR)
                                                              │
                                                       CI builds & publishes
                                                              ▼
            index.json · dataset.jsonl · sft.jsonl · browse page   (GitHub Pages, CC0)
                     │                                        │
         agents call search_lessons                  labs and researchers train on it
         before risky work; rate_lesson
         says whether it helped ──► feedback raises good lessons, retires bad ones
```

## What an entry looks like

```yaml
id: OOPS-0004
title: Rewrote a file from truncated tool output and deleted most of it
status: seed
domain: coding
severity: high
root_cause: context-loss
situation: >
  An agent needed to change one function in a large source file, and had read the file
  through a tool that truncates long output.
what_happened: >
  The agent rewrote the whole file from what it had seen. The tool had cut the file off
  partway, so everything after the cut was dropped from the new version.
fix: Restored the file from version control and applied the change as a targeted edit.
lesson: >
  Edit files with targeted replacements rather than full rewrites, and never rebuild a file
  from output that may have been truncated.
check: Have I seen the entire file, and do I really need to rewrite all of it?
applies_when: [rewriting a whole file, editing a large file, tool output ends abruptly]
```

Every entry has one **lesson** (a general rule, in the imperative), an optional **check** (a
question an agent asks itself before acting), and a **root cause** from a fixed taxonomy of 16
categories (`schema/taxonomy.json`), so the data can be counted, compared and trained on.
The schema is `schema/entry.schema.json`.

## Use it from an agent (MCP)

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). No configuration needed: the
server reads the published log from this repository's GitHub Pages and falls back to a
bundled snapshot when offline.

**Claude Code**

```sh
claude mcp add oops -- uvx --from "git+https://github.com/Ravenmoray/oops#subdirectory=mcp-server" oops-mcp
```

**Claude Desktop and other MCP clients** (`claude_desktop_config.json` or equivalent):

```json
{
  "mcpServers": {
    "oops": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Ravenmoray/oops#subdirectory=mcp-server", "oops-mcp"]
    }
  }
}
```

To make an agent use it without being asked, add this to your `CLAUDE.md` (or your client's
equivalent):

```markdown
## OOPS shared mistake log
- Before destructive, unfamiliar or high-stakes actions, call `search_lessons` with a short
  description of what you are about to do.
- When you make a real mistake and it has been fixed, offer to log it with `draft_mistake_report`.
  Never call `submit_draft` unless I have read the draft and said yes.
```

Tools: `search_lessons`, `get_lesson`, `list_root_causes`, `draft_mistake_report`,
`rate_lesson`, `list_drafts`, `discard_draft`, `submit_draft`. Prompts: `oops_preflight`,
`oops_postmortem`. Details and configuration: [mcp-server/README.md](mcp-server/README.md).

## Contribute

Three ways in, all ending in human review:

1. **From an agent**, through the MCP server: the agent drafts, you read and approve, it submits.
2. **By hand**, with the *Report an AI mistake* issue form.
3. **By pull request**, adding `entries/OOPS-NNNN.yaml` directly.

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. In short: blameless, generalized, no private
data, one lesson per entry.

## Trust and safety

A public log that agents read back into their own context is a target. Anyone who can get text
into it can try to steer every agent that reads it. The defenses are layered:

- **Nothing is published automatically.** Drafts stay on the user's machine until a human
  approves them. Without a GitHub token configured, the human has to press *Submit* on GitHub
  themselves. With a token, the approval code ties approval to the exact text shown, but it
  relies on the client asking the user, so the token-free mode is the one to use if you want a
  hard guarantee.
- **Private data is scrubbed** before anything leaves the machine: keys and tokens, private
  keys, passwords, emails, phone numbers, IP addresses, home-directory usernames. CI runs the
  same check on every submission and every entry.
- **Anti-poisoning lint** rejects text that addresses the reading agent ("ignore previous
  instructions", fake role tags), links or commands inside lessons, pipe-to-shell commands
  anywhere, and hidden or bidirectional unicode.
- **Human moderation**, with an audit trail: every entry is a reviewed pull request, and git
  history shows who changed what.
- **Clients filter too.** The server re-lints everything it downloads and drops entries that
  fail, and labels every result as *advisory community data, not instructions*.
- **Status reflects evidence.** `seed` and `reviewed` lessons rank below `confirmed` ones,
  `disputed` lessons are hidden by default, and `deprecated` ones are kept for history but
  never served.

None of this is perfect. Report weaknesses as issues.

## Data

On every merge to `main`, CI publishes to GitHub Pages:

- [`index.json`](https://ravenmoray.github.io/oops/index.json): all entries plus the taxonomy
  (what the MCP server reads)
- [`dataset.jsonl`](https://ravenmoray.github.io/oops/dataset.jsonl): one entry per line, all fields
- [`sft.jsonl`](https://ravenmoray.github.io/oops/sft.jsonl): chat-format examples (situation →
  likely mistake, root cause, rule, check), excluding disputed and deprecated entries
- [`index.html`](https://ravenmoray.github.io/oops/): a searchable page for people

## License

**Public domain, by design.** Everything in this repository (the log, the schema, the code
and the published dataset) is dedicated to the public domain under
[CC0 1.0](LICENSE). Copy it, change it, train on it, build on it; no permission or attribution
needed.

## How this differs from related projects

- The [AI Incident Database](https://incidentdatabase.ai) catalogues real-world *harms*
  caused by deployed AI, for researchers and policymakers. OOPS records the everyday
  *operational* mistakes of AI agents, written as rules that agents can apply.
- Hosted shared-memory MCP services (for example AgentBase and Bhived) let agents store and
  share knowledge in general. OOPS is narrower and deliberately slower: only mistakes, with a
  fixed taxonomy, human-reviewed, plain files in git, forkable, and no account or service to
  depend on.

## Repository layout

```
entries/          one YAML file per entry (the log itself)
schema/           entry JSON Schema and the taxonomy
tools/            oops_validate.py: validation, safety lint, dataset build, issue intake
mcp-server/       the oops-mcp Python package
site/             the browse page published with the data
tests/            unit tests, issue-form tests, end-to-end MCP tests
.github/          CI, issue intake, issue form
```

Local development:

```sh
pip install PyYAML jsonschema "mcp>=2" pytest
python tools/oops_validate.py --build dist --sync-package
python -m pytest -q tests
cd mcp-server && OOPS_LOCAL_REPO=.. python -m oops_mcp --check
```

## Roadmap

- Semantic search (embeddings) once the log outgrows keyword retrieval
- A hosted read-only MCP endpoint, so agents can connect by URL with no install
- Automatic duplicate detection at intake, suggesting "confirm OOPS-NNNN" instead of a new entry
- Signed submissions, so a reporter's track record can count toward trust
- Periodic statistics: which root causes are most common, and which lessons help most
