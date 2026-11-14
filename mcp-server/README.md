# oops-mcp

MCP server for [OOPS](../README.md), the public log of AI mistakes and lessons learned.
It lets any agent search the log before acting, and draft new entries for a human to approve.

Works with `mcp` 1.x and 2.x. Python 3.10+. Ships an offline snapshot of the log, so it works
before any configuration and without a network.

## Install

```sh
uvx --from "git+https://github.com/Ravenmoray/oops#subdirectory=mcp-server" oops-mcp      # run directly
pip install "git+https://github.com/Ravenmoray/oops#subdirectory=mcp-server"              # or install
oops-mcp --check                                                                     # show config and entry count
```

Client configuration is in the [main README](../README.md#use-it-from-an-agent-mcp).

## Tools

| Tool | What it does | Side effects |
|---|---|---|
| `search_lessons(query, domain?, root_cause?, limit?, include_disputed?)` | Find lessons relevant to a task | none |
| `get_lesson(lesson_id)` | Full entry as YAML | none |
| `list_root_causes()` | The taxonomy, with descriptions | none |
| `draft_mistake_report(...)` | Scrub, lint and validate a report; save it locally for review | local file |
| `rate_lesson(lesson_id, helpful, note?)` | Draft feedback on a lesson | local file |
| `list_drafts()` / `discard_draft(draft_id)` | Manage local drafts | local files |
| `submit_draft(draft_id, approval_code)` | Publish an approved draft as a GitHub issue, or return a prefilled link | **public** |

Prompts: `oops_preflight(task)` and `oops_postmortem(what_went_wrong)`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `OOPS_REPO` | `Ravenmoray/oops` | `owner/name` of the public log on GitHub (set to use a fork) |
| `OOPS_INDEX_URL` | `https://<owner>.github.io/<name>/index.json` | Published index to read |
| `OOPS_LOCAL_REPO` | (none) | Path to a checkout; read `entries/` directly |
| `OOPS_HOME` | `~/.oops` | Drafts and cache |
| `OOPS_GITHUB_TOKEN` | falls back to `GITHUB_TOKEN` | Lets `submit_draft` open issues itself |
| `OOPS_GITHUB_API` | `https://api.github.com` | For GitHub Enterprise, or tests |
| `OOPS_CACHE_TTL` | `21600` | Seconds to cache the remote index |

Where lessons come from, in order: `OOPS_LOCAL_REPO`, then a fresh cache, then
`OOPS_INDEX_URL`, then a stale cache, then the bundled snapshot. Every source is re-linted and
unsafe entries are dropped.

**Token or no token?** Without a token, `submit_draft` returns a prefilled GitHub link, and the
user submits it themselves, so nothing can be published without a person clicking. With a
token (it needs permission to open issues on the log's repository), the agent submits directly
after the user approves in chat. The first is the safer default.
