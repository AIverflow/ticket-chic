# Ticket workflow

Core rules. They say nothing about branches, worktrees, agents or models. Those are optional modules (`modules/`).
Dave (the owner) reads the board, not the files: when you report, give each ticket as ID + one plain sentence.

## Files
Everything lives in `.tickets/`:
- `T<n>-<slug>.md`: one file per open ticket.
- `done/T<n>-<slug>.md`: finished tickets (same file, moved).
- `board.html`: the table Dave reads (status filters, search, details). Built by `tickets.py`, never edited.
- `config.json` (optional): board title, ID prefix, statuses.
- `WORKFLOW.md`, `tickets.py`, `hooks/`, `modules/`, `README.md`, `tests/`, `install.sh`: the system (git branch `core`). Don't edit them in a project: change them in the `ticket-chic` repo, then update.

`.tickets/` is its own git repo, independent of the project's. Its branch `main` holds this project's tickets and config (commit them there); branch `core` is the system and is only updated by `install.sh`. The project's repo ignores `.tickets/`.

## Ticket file
```
---
title: Short title
status: ready
difficulty: 2
size: M
blocked_by: T4, T7
created: 2026-10-15
---

## Do
What to change, where.

## Done when
Checks that prove it works.
```
Only `title` and `status` matter. Everything else is optional. Free text goes below the frontmatter.

## Status
| Status | Meaning |
|---|---|
| `open` | exists, not ready to start (idea, unclear) |
| `ready` | clear enough to start now |
| `doing` | someone works on it |
| `blocked` | waits for something outside the tickets (a decision, a service) |
| `parked` | on purpose not touched; waits for Dave |
| `done` | finished. The file is in `done/` |

- A `ready` or `open` ticket whose `blocked_by` tickets are not all done shows as **blocked** on the board. Nothing to edit: it becomes ready again when they are done.
- Statuses are configurable in `config.json` (`done` must stay).

## Two scores
Optional, independent. Judge each on its own question.

| Field | Question | 1 / S | 2 / M | 3 / L |
|---|---|---|---|---|
| `difficulty` 🟢🟡🔴 | How smart must the worker be? (judgment, risk of a subtle mistake) | Mechanical. The ticket text is enough | Careful. Read the surrounding code | Design or risky change. Strongest worker only |
| `size` | How much work? (steps, files, time) | Minutes, one file | About an hour, a few files | Hours or many files: consider splitting |

- They differ: a one-line fix of a subtle race is 🔴 + S. Renaming a function in 40 files is 🟢 + L.
- Unsure about difficulty: ask "what is the worst mistake a cheap worker could make, and would we notice?"
- 🔴 + L: split it first.

## Tool: `python3 .tickets/tickets.py <cmd>`
| Command | Does |
|---|---|
| `new "Title" [-d 1\|2\|3] [-s S\|M\|L] [-b T1,T2]` | creates the next ticket from a template |
| `list [<status>] [--all]` | prints open tickets (all with `--all`, one status with e.g. `list ready`) |
| `show T12` | prints one ticket file |
| `set T12 <status>` | changes status; `done` moves the file to `done/`, anything else moves it back |
| `done T12 [T13 …] [--commit <hash>]` | same as `set … done`, records the commit |
| `board` | rewrites `board.html` |
| `sync` | commits `.tickets/`, then pulls and pushes if `main` has a remote (see README, optional) |

**The hook finishes tickets.** A commit whose subject ends with ticket ID(s) in parentheses, e.g. `Login: retry after timeout (T88)` or `(T64, T67 to T71)`, moves them to `done/` with the commit hash and rebuilds the board.
So: **an ID in parentheses at the end of the subject means finished. Never use it for partial work** (write `T88 part 1` without parentheses).
An ID that matches no ticket changes nothing and prints `unknown ticket id`. The hook moves files inside `.tickets/` but does not commit them (unless config.json sets `auto_commit`, see README): commit them on `main` (in `.tickets/`) after your work commit.

## Rules for any agent
- Ticket files are the source of truth. Don't track work anywhere else.
- Change a status with the tool, not by moving files by hand.
- Never commit `.tickets/` into the app repo (it has its own git). Commit tickets inside `.tickets/`, on `main`.

## Optional modules
Already in `.tickets/modules/`; the project's `AGENTS.md` says which ones apply.
- [`modules/worktrees.md`](modules/worktrees.md): one branch + worktree per ticket, shared git rules.
- [`modules/roles.md`](modules/roles.md): orchestrator / implementer / reviewer, agent tiers, STOP rule.

## In the project
The project's `AGENTS.md` needs one line: "Before any ticket, read `.tickets/WORKFLOW.md`." Test commands, invariants and commit style stay in `AGENTS.md`, not here.
