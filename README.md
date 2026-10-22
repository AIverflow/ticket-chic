# ticketing

A small, personal ticket system for any project: markdown files with a frontmatter, a static HTML board, a git hook that finishes tickets from commit subjects. One Python file, standard library only.

```
.tickets/
  T12-strobe-grid.md        open ticket (frontmatter + free text)
  done/T11-fix-seek.md      finished ticket
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
python3 .tickets/tickets.py new "Fix the seek bug" -d 2 -s S
python3 .tickets/tickets.py set T3 ready
python3 .tickets/tickets.py list         # or: list ready
python3 .tickets/tickets.py show T3
python3 .tickets/tickets.py board        # then open .tickets/board.html
git commit -m "Fix seek on resume (T3)"   # the hook moves T3 to done/
```

## Ticket format
```
---
title: Fix the seek bug
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
`done` must stay in `statuses`. The board shows statuses in the listed order.

## Tests
```bash
python3 -m unittest discover -s tests
```
