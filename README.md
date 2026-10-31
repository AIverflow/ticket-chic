# Ticket-Chic

A minimal ticket system for your projects and the AI agents working on them. It needs only git and Python, no packages.

- **Minimal.** One Python file (about 490 lines, standard library only).
- **Plain files.** One markdown file per ticket in `.tickets/`. Read, grep and diff them like code.
- **A real board.** `board.html` is a static page with filters, search and the full text of each ticket. No server.
- **Commits close tickets.** End a commit subject with `(T12)` and a git hook moves T12 to `done/`.
- **Made for agents.** Each ticket has a difficulty and a size. Modules give agents roles and worktree rules.

# Part 1: Quick guide

## Install
1. From the ticket-chic folder run `./install.sh /path/to/project`.
2. Answer 3 questions (Enter takes the default; without a terminal it uses the defaults): the board title, whether to use git worktrees for parallel tickets (and their folder, as a full path), and whether to install the git hook.
3. Add one line to the project's `AGENTS.md`: "Before any ticket, read `.tickets/WORKFLOW.md`."

Run `install.sh` again later to update. Your tickets and config stay.

## Four ways to work
**A list of small fixes.** Say "do T3, T4, T5". This is `chain` mode, the default. The agent does them one after another, one commit each; the hook closes each ticket. You test in the project folder, on the project's `main`, after the series.

**One big or delicate ticket.** Say "do T12 in validate mode". The agent works on a branch and commits without the ID, so T12 stays open. A reviewer checks. You test in the folder and branch the agent reports. You say OK; the agent merges with `(T12)`, which closes it.

**Several tickets in parallel.** Needs `"worktrees": true` and a `worktree_dir` in `config.json` (install can set both). Say "do T7, T8, T9 in parallel". Each ticket gets its own worktree in `<worktree_dir>/<ID>`. You test each one in the folder and branch the agent reports.

**Add a ticket.** Say "add a ticket: fix the export bug, difficulty 2". The agent runs `tickets.py new`.

## Switching things
- Mode: say it in your request, or set `"mode": "chain"` or `"validate"` in `.tickets/config.json`.
- Roles and worktrees: edit `.tickets/config.json`, e.g. `{"roles": false, "worktrees": true}`.
- Tiers to models: tell the agent, e.g. "light = Haiku, standard = Sonnet, strong = Opus". If you do not, it asks.

## Commands
```bash
python3 .tickets/tickets.py new "Fix the export bug" -d 2 -s S
python3 .tickets/tickets.py set T3 ready
python3 .tickets/tickets.py list         # or: list ready
python3 .tickets/tickets.py board        # then open .tickets/board.html
git commit -m "Fix export on empty list (T3)"   # the hook moves T3 to done/
```
Also `show T3`, `done T3`, `sync`.

# Part 2: How it works

## Tickets and statuses
A ticket is a markdown file with a short frontmatter: `title`, `status`, `difficulty` (1 to 3: how smart the worker must be), `size` (S, M, L: how much work), `blocked_by` (optional). Statuses and details: [`WORKFLOW.md`](WORKFLOW.md).

## Commits and the hook
A commit whose subject ends with an ID in parentheses, like `Login: retry after timeout (T88)`, finishes that ticket: the hook moves it to `done/` with the commit hash. Partial work has no parentheses. See [`WORKFLOW.md`](WORKFLOW.md).

## Modes
`chain` for a list of small tickets, `validate` for a big or delicate one. You pick when you ask; otherwise `mode` in `config.json` decides. See [`WORKFLOW.md`](WORKFLOW.md).

## Where work happens
On the project's `main`, on a branch named after the ticket, or in a worktree per parallel ticket. See [`WORKFLOW.md`](WORKFLOW.md) and [`modules/worktrees.md`](modules/worktrees.md).

## Roles
Three roles: the orchestrator (the agent you talk to; it commits), the implementer (codes) and the reviewer (checks). Tickets ask for a tier (`light`, `standard`, `strong`), never a model. Set `"roles": false` and the agent you talk to does the work itself. See [`modules/roles.md`](modules/roles.md).

## Settings
`.tickets/config.json`. All keys are optional. Full detail: [`WORKFLOW.md`](WORKFLOW.md), Settings.
```json
{"title": "My project", "id_prefix": "T", "auto_commit": true, "roles": true,
 "worktrees": false, "worktree_dir": "/home/me/worktrees/app", "mode": "chain"}
```
| Key | Default | Meaning |
|---|---|---|
| `title` | project folder name | board title |
| `id_prefix` | `T` | ticket ID letters |
| `auto_commit` | `true` | commit `.tickets/` after every change |
| `roles` | `true` | agents follow `modules/roles.md` |
| `worktrees` | `false` | allow a worktree per parallel ticket |
| `worktree_dir` | none | full path of the worktree folder |
| `mode` | `chain` | `chain` or `validate` |

Statuses are configurable too: see [`WORKFLOW.md`](WORKFLOW.md), Status.

## Storage
`.tickets/` is its own git repo, separate from your project's (which ignores it). Its two branches are not your project's branches:
- **`core`**: the system (`tickets.py`, `WORKFLOW.md`, hook, modules). Changed only in this repo; `install.sh` updates it.
- **`main`**: your project's tickets and `config.json`. Tickets are committed here. This is not your project's `main`.

```
.tickets/
  T12-login-timeout.md      open ticket
  done/T11-fix-export.md    finished ticket
  board.html                generated board
  config.json               your settings
  WORKFLOW.md  tickets.py  hooks/  modules/   (the system, from core)
```

## Several machines or people (optional, lightly tested)
For a few people who sync often; not a team tracker. Off until you use it.
- Share `.tickets/` through its own remote, not `origin` (that is where ticket-chic came from): `git -C .tickets push -u <remote> main` once, then `python3 .tickets/tickets.py sync` commits, pulls and pushes.
- A second machine: `git clone <remote> /path/to/project/.tickets`, then `./install.sh /path/to/project`.
- One prefix per machine so numbers never clash: `"id_prefix": ["T", "L"]` in `config.json`, and `export TICKETS_PREFIX=L` on the second one.
- Anyone who can push can change `tickets.py`, which the hook runs: share only with people you trust.
