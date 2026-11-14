# Contributing to OOPS

Thanks for helping AI systems stop repeating each other's mistakes.

## Writing a good entry

**Blameless.** Describe what happened and why, not who is at fault. The point is the pattern.

**Generalized.** Write the situation as a *kind* of task: "An agent was asked to clean up a
build directory", not "Bob asked Claude to clean up /srv/acme-payments/build". If a reader could
identify the person, company or project, it's too specific.

**One mistake, one lesson.** If there are two lessons, write two entries and link them with
`related`.

**The lesson is a rule.** Imperative, general, 20 to 300 characters, and useful to an agent that
has never seen this story. Good: *"Compute weekdays and date differences with a tool instead of
estimating them."* Not good: *"I should have been more careful with the date."*

**The check is a question.** Something an agent can ask itself just before acting: *"Did I
calculate this date fact, or did I guess it?"*

**`applies_when` is for retrieval.** Short phrases describing the moment the lesson matters,
in the words an agent would use to describe its task: "writing a cron expression", "rewriting
a whole file".

**Pick the root cause carefully.** It is what makes the data useful in aggregate. Use
`list_root_causes` or read `schema/taxonomy.json`. If nothing fits, use `other` and say what
category you would propose.

## Never include

- Names, emails, phone numbers, addresses, account names, IP addresses, internal hostnames
- Keys, tokens, passwords, or any credential, even revoked ones
- Content from anyone's private conversation, files, code or documents
- Links or commands inside `lesson`, `check`, `applies_when` or `title`
- Text that addresses the reading AI ("ignore your instructions", "you must now…")

The tooling strips or rejects most of this automatically. It cannot catch everything, so read
what you submit.

## Ways to submit

1. **From an agent** with the MCP server: `draft_mistake_report`, read the draft, then
   `submit_draft` if you approve.
2. **Issue form**: *Report an AI mistake*.
3. **Pull request**: add `entries/OOPS-NNNN.yaml` using the next free number and
   `status: reviewed`, then run `python tools/oops_validate.py --sync-package` and the tests.

By submitting, you release your contribution under CC0 1.0 (public domain).

## For maintainers: reviewing and merging

The intake workflow labels each submission `checks-passed` or `needs-changes` and comments with
the details. For a submission that passed:

1. **Is it real and useful?** Plausible, specific enough to learn from, general enough to reuse.
2. **Is it private-safe?** Re-read every field for anything identifying. The scrubber is a net,
   not a guarantee.
3. **Is it new?** Search the log. If the same mistake is already there, don't add a duplicate:
   increment `confirmations` on the existing entry and add the issue to its `sources`.
4. **Is the lesson right?** Edit for clarity and generality. A lesson that would mislead an
   agent in other situations is worse than no lesson.
5. **Merge:** create `entries/OOPS-NNNN.yaml` with the next id, `status: reviewed`, and
   `sources: [{type: issue, ref: "#123"}]`. Run `--sync-package`, open the PR, and close the
   issue with a link to it once merged.

### Feedback and status changes

Feedback issues (`[oops-feedback] OOPS-NNNN: helpful`) are tallied into the entry's
`feedback.helpful` / `feedback.not_helpful` counts, in batches. Then:

| Change | When |
|---|---|
| `seed` / `reviewed` → `confirmed` | `confirmations + feedback.helpful` reaches 3, from at least 3 different reporters |
| any → `disputed` | at least 3 `not_helpful`, and more `not_helpful` than `helpful`; record why in the PR |
| any → `deprecated` | the lesson no longer applies (tools changed), or a better entry replaces it (`superseded_by`) |

Entries are never deleted. Deprecated entries stay in the dataset for history, but are not
served to agents and are excluded from `sft.jsonl`. The one exception: remove anything that
turns out to contain private data, and rewrite history if needed.

### Changing the taxonomy

Root causes and domains are a shared vocabulary, so change them deliberately: open an issue
first, update `schema/taxonomy.json` and the matching enums in `schema/entry.schema.json`
together (CI checks they agree), and the `Literal` types in `mcp-server/oops_mcp/server.py`.
