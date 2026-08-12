---
name: commit-message
description: Write a Conventional Commits-style commit message (subject + body) from a description of a code change.
---

# Commit Message

When asked to write a commit message from a description of a change, ALWAYS follow this structure:

1. **Type** — one of: feat, fix, docs, style, refactor, test, chore, perf.
2. **Scope** (optional) — the module/area affected, in parentheses.
3. **Subject** — imperative mood ("add", not "added"/"adds"), lowercase, no period, under 50 characters.
4. **Body** (blank line after subject) — explain WHAT changed and WHY (not how), wrapped at ~72 chars per line.
5. **Footer** (if relevant) — BREAKING CHANGE: ... or Refs #issue-number.

Format:
<type>(<scope>): <subject>

<body> <footer> 

Rules:

Subject line: imperative, lowercase, no trailing period, under 50 characters.
Never combine unrelated changes into one message — if the description covers multiple concerns, say so and suggest splitting into separate commits.
If no scope is clear from the description, omit the parentheses entirely.
Body is optional for trivial changes (e.g. typo fixes).