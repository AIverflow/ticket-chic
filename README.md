# Ticket-Chic

A minimal ticket system for your projects and the AI agents working on them. One script installs it; it needs only git and Python, no packages.

- **Minimal.** One Python file (about 350 lines, standard library only). An agent can read the whole system in a minute.
- **Plain files.** One markdown file per ticket in `.tickets/`, with a short frontmatter. You can read, grep and diff them like code.
- **A real board.** `board.html` is a static page with status filters, search and the full text of each ticket. Open it in a browser; no server.
- **Commits close tickets.** End a commit subject with `(T12)` and a git hook moves T12 to `done/` with the commit hash.
- **Made for agents.** Each ticket has a difficulty (which model is smart enough) and a size (how much work). Optional modules give agents roles and worktree rules.

```
.tickets/
  T12-login-timeout.md      open ticket (frontmatter + free text)
  done/T11-fix-export.md    finished ticket
  board.html                generated dashboard
  config.json               optional: title, ID prefix, statuses
  WORKFLOW.md  tickets.py  hooks/  modules/   (the system, from branch core)
```

## Branches
- This repo has one branch: **`core`** = the system (`tickets.py`, `WORKFLOW.md`, hook, modules, docs). Change the system here only.
- In each project, `.tickets/` is a **clone** of this repo with its own branch **`main`**: the project's tickets, plans and `config.json`. Work on `main`, never commit on `core` there.
- The project's own git repo ignores `.tickets/`.

## Install in a project, and update
```bash
./install.sh /path/to/project
```
- First run: clones `core` into `<project>/.tickets/`, creates `main` with a `config.json`, installs the git hook, adds `.tickets/` to the project's `.gitignore`.
- Next runs (update): fetches `core` and merges it into `main`. Your tickets and config stay.
- Then add one line to the project's `AGENTS.md`: "Before any ticket, read `.tickets/WORKFLOW.md`."

## Use
```bash
python3 .tickets/tickets.py new "Fix the export bug" -d 2 -s S
python3 .tickets/tickets.py set T3 ready
python3 .tickets/tickets.py list         # or: list ready
python3 .tickets/tickets.py show T3
python3 .tickets/tickets.py board        # then open .tickets/board.html
git commit -m "Fix export on empty list (T3)"   # the hook moves T3 to done/
```

## Ticket format
```
---
title: Fix the export bug
status: ready
difficulty: 2
size: S
blocked_by: T1, T2
---
```
No comments inside the block: each line is `key: value`.
- `status`: open · ready · doing · blocked · parked · done
- `difficulty`: 1 🟢 mechanical · 2 🟡 careful · 3 🔴 hard (how smart the worker must be)
- `size`: S minutes · M about an hour · L hours (how much work)
- `blocked_by`: optional; shows as blocked until they are done
Details in [`WORKFLOW.md`](WORKFLOW.md). Optional modules: [`worktrees`](modules/worktrees.md), [`roles`](modules/roles.md).

## Config (optional)
`.tickets/config.json`:
```json
{"title": "My project", "id_prefix": "T",
 "statuses": [["ready", "Ready", "#4ea1ff"], ["open", "Open", "#f0b429"], ["done", "Done", "#3fb950"]]}
```
`done` must stay in `statuses`; `blocked` is added before it if missing. The board shows statuses in the listed order.
`id_prefix` is letters only.

## Several machines or people (optional, lightly tested)
Off by default; nothing changes until you use it.
- Share `.tickets/` through its own git remote: `git -C .tickets push -u <remote> main` once, then `python3 .tickets/tickets.py sync` commits, pulls and pushes the tickets.
- Do not use `origin` as the shared remote: in `.tickets/`, `origin` is the ticket-chic repo it was installed from.
- A second machine joins: `git clone <remote> /path/to/project/.tickets`, then `./install.sh /path/to/project` to install the hook.
- One prefix per machine or person, so numbers never clash: `"id_prefix": ["T", "L"]` in `config.json`, and `export TICKETS_PREFIX=L` on the second one.
- `"auto_commit": true` in `config.json`: the hook also commits `.tickets/` after closing tickets.
- `set T12 doing` records `by: <git user.name>` in the ticket; the board shows it.
- Anyone who can push to the shared remote can change `tickets.py`, which the commit hook runs on every machine: only share with people you trust.
It works for a few people who sync often. It is not a team tracker.

## Tests
```bash
python3 -m unittest discover -s tests
```
