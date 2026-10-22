# Module: worktrees

Applies only when `.tickets/config.json` has `"worktrees": true`. For parallel tickets, one worktree each. Where the work happens, commits and merging: `WORKFLOW.md`.
Ticket files are not in worktrees (`.tickets/` is its own git repo, ignored by the app repo), so whoever starts the work pastes the ticket text into the worker's prompt and gives the absolute path of `.tickets/`.

## Setup per ticket
`git worktree add <worktree_dir>/<ID> -b <ID> <base>`
- `worktree_dir` is in `config.json` (a full path). If it is missing, **ask Dave** before creating the first worktree, then write it in `config.json`. Never pick a folder yourself (Dave may choose `/tmp` if he wants; that is his call).
- `<base>` = `main`, or the previous ticket's branch when tickets are stacked.
- Branch already exists: use `<ID>-v2`. Keep the old one only if it was NOT merged into `main`; a merged one is deleted (see `WORKFLOW.md`).
- Work only in `<worktree_dir>/<ID>`.

## Shared git rules (all workers)
- All worktrees share one repo. Workers (implementer, reviewer) never use `git stash`, `checkout`, `switch`, `restore`, `reset` or `clean`: they reach other tickets' work. To look at old code: `git show <commit>:<path>`.
- Only the orchestrator (or, when `roles` is off, the agent doing the work) creates and merges branches and commits. It adds files by name, never `git add -A`.
- Run heavy tests one at a time (`nice -n 10`). Parallel browsers or builds overload the machine.

## Cleanup
The orchestrator (or the agent doing the work, when `roles` is off) does it, right after the ticket's branch is merged: `git worktree remove <worktree_dir>/<ID>` (no `--force`; if git refuses, keep it and say so). Then the branch is deleted (see `WORKFLOW.md`).
A worktree left over from an earlier run: remove it only if `git -C <path> status` shows nothing uncommitted.
