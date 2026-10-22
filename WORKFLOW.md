# Ticket workflow

Core rules. Branch, worktree, agent and model rules are in the modules (`modules/`), switched on in `config.json` (see Settings).
Dave (the owner) reads the board, not the files. Every report gives each ticket as ID + one plain sentence, and the folder path and branch to test. The final report also says how many ticket branches are left and why.

## Settings
Before each ticket, read the switches in `.tickets/config.json`. A missing key means the default. Edit the file any time.

| Key | Default | Meaning |
|---|---|---|
| `auto_commit` | `true` | `tickets.py` commits `.tickets/` after every change (new, set, done, hook): `New: T12`, `T12: doing`, `Done: T12 (<hash>)`. If it cannot (not its own repo, rebase in progress) it warns and goes on. Never pushes. If off, commit the changes yourself on `main` in `.tickets/` |
| `roles` | `true` | follow `modules/roles.md` |
| `worktrees` | `false` | allow a worktree per parallel ticket; if true, follow `modules/worktrees.md` |
| `worktree_dir` | none | full path of the folder for worktrees (see `modules/worktrees.md`) |
| `mode` | `chain` | `chain` or `validate`: how work is committed and checked (see Modes) |

`tickets.py` uses `auto_commit` and the board settings, and only checks that `mode` is valid; the other keys are for agents.

## Files
Everything lives in `.tickets/`:
- `T<n>-<slug>.md`: one file per open ticket.
- `done/T<n>-<slug>.md`: finished tickets (same file, moved).
- `board.html`: the table Dave reads (status filters, search, details). Built by `tickets.py`, never edited.
- `notes/` (optional): saved info on dropped branches (see Where the work happens).
- `config.json` (optional): board title, ID prefix, statuses, the switches in Settings.
- `WORKFLOW.md`, `tickets.py`, `hooks/`, `modules/` and the other files from git branch `core`: the system. Don't edit them in a project: change them in the `ticket-chic` repo, then update.

`.tickets/` is its own git repo, independent of the project's. Its branch `main` (not the project's `main`) holds this project's tickets and config (commit them there); its branch `core` is the system and is only updated by `install.sh`. The project's repo ignores `.tickets/`.

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
Every key is optional (no title: the ID is shown; no status: `open`). Free text goes below the frontmatter.

## Status
| Status | Meaning |
|---|---|
| `open` | exists, not ready to start (idea, unclear) |
| `ready` | clear enough to start now |
| `doing` | someone works on it |
| `blocked` | waits for something outside the tickets (a decision, a service) |
| `parked` | on purpose not touched; waits for Dave |
| `done` | finished. The file is in `done/` |

- Easy to mix up: **open** = not ready (idea, unclear) · **ready** = clear, can start · **blocked** = waits for something.
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
| `sync` | commits `.tickets/`, then pulls and pushes if `main` in `.tickets/` has a remote (see README, optional) |

**The hook finishes tickets.** A commit whose subject ends with ticket ID(s) in parentheses, e.g. `Login: retry after timeout (T88)` or `(T64, T67 to T71)`, moves them to `done/` with the commit hash and rebuilds the board. It works in every worktree too, even before the merge.
So: **an ID in parentheses at the end of the subject means finished. Never use it for partial work** (write `T88 part 1` without parentheses).
An ID that matches no ticket changes nothing and prints `unknown ticket id`. After the closing commit, check that `done/<ID>-*.md` exists; if not, run `tickets.py done <ID> --commit <hash>`.

## Modes
Dave picks the mode when he asks for the work ("chain" / "validate"). When he says nothing, use `mode` from `config.json`. Small tickets may be grouped in one run. With parallel tickets the mode applies per ticket: merge into the project's `main` after the ticket's checks (chain) or after Dave's OK (validate).

**chain**: a list of small tickets done one after another. One commit per ticket, with its ID in parentheses (it closes the ticket). Review is optional, e.g. one review at the end of the series. Dave checks after the series.

**validate**: for a big or delicate ticket.
1. Commit your work as you go on the ticket's branch **without** `(T12)`, so nothing is lost uncommitted and the ticket stays open.
2. Review (an agent reviewer if `roles`, then Dave).
3. Only after Dave's OK, close it: merge with `git merge --no-ff -m "<what changed> (T12)"`, or make a final small commit with the ID. A fast-forward merge makes no commit, so it cannot close a ticket: use fast-forward only in chain.

## Where the work happens
| Work | Place |
|---|---|
| Small fix, one worker | directly on the project's `main` |
| Bigger or risky | a branch named `<ID>` |
| Several tickets in parallel | a worktree per ticket, only if `worktrees` is true (`modules/worktrees.md`) |

- Without worktrees, make the branch in the project folder with `git switch -c <ID>`; go back with `git switch main` to merge.
- Commit as soon as the checks pass: the orchestrator does it when `roles` is on, otherwise the agent doing the work. Never leave work uncommitted on a branch (or worktree) while waiting for a review or for Dave. The `(<ID>)` goes only on the closing commit (see Modes).
- **Never squash.** Merge with a fast-forward (chain only) or a merge commit, so git can see the branch is contained in the project's `main` (a squash leaves the branch looking unmerged and in conflict forever).
- Right after a merge into the project's `main`: `git branch -d <ID>` (remove its worktree first, see `modules/worktrees.md`) (git refuses if it is not really merged: then keep it and say so). Stacked tickets: delete each one once the last of the stack is merged.
- Never use `git branch -D` on a branch with unmerged work. Exception: Dave decides to drop one; first write `name sha subject` to `notes/` so it can be restored with `git branch <name> <sha>`.

## Rules for any agent
- Ticket files are the source of truth. Don't track work anywhere else.
- Change a status with the tool, not by moving files by hand. Set `doing` when work starts: the orchestrator if `roles` is on, otherwise the agent doing the work.
- Create a ticket with `tickets.py new` when Dave asks you to.
- Never commit `.tickets/` into the app repo (it has its own git). Commit tickets inside `.tickets/`, on its `main`.

## Modules
In `.tickets/modules/`; the switches in `config.json` say which ones apply.
- [`modules/worktrees.md`](modules/worktrees.md) (`worktrees`): setup, shared-repo git rules and cleanup for worktrees.
- [`modules/roles.md`](modules/roles.md) (`roles`): orchestrator / implementer / reviewer, agent tiers, STOP rule.

## In the project
The project's `AGENTS.md` needs one line: "Before any ticket, read `.tickets/WORKFLOW.md`." Test commands, invariants and commit style stay in `AGENTS.md`, not here.
