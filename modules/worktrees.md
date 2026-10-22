# Module: worktrees

Optional. One branch per ticket, usually with its own git worktree, so several tickets can run in parallel without touching each other. Some tickets use only a branch (no worktree): the branch rules below apply the same way, skip the worktree lines.
Ticket files are not in worktrees (`.tickets/` is its own git repo, ignored by the app repo), so whoever starts the work pastes the ticket text into the worker's prompt and gives the absolute path of `.tickets/`.

## Setup per ticket
`git worktree add /tmp/wt/<ID> -b <ID> <base>`
- `<base>` = `main`, or the previous ticket's branch when tickets are stacked.
- Branch already exists: use `<ID>-v2`. Keep the old one only if it was NOT merged into `main`; a merged one is deleted (see Merging).
- Work only in `/tmp/wt/<ID>`.

## Shared git rules (all workers)
- All worktrees share one repo. Never use `git stash`, `checkout`, `restore`, `reset` or `clean`: they reach other tickets' work. To look at old code: `git show <commit>:<path>`.
- Never `git add -A`: add the files by name.
- Run heavy tests one at a time (`nice -n 10`). Parallel browsers or builds overload the machine.

## Cleanup
- After the commit: `git worktree remove /tmp/wt/<ID>` (no `--force`; if git refuses, keep it and say so).
- Remove worktrees older than 48 h only if sure they hold nothing uncommitted.
- The branch stays until merged, then it is deleted (see Merging).

## Merging
- **Never squash.** Merge with a fast-forward or a merge commit, so git can see the branch is contained in `main` (a squash leaves the branch looking unmerged and in conflict forever).
- Right after a merge into `main`: remove its worktree (if any), then `git branch -d <ID>` (git refuses if it is not really merged: then keep it and say so). Stacked tickets: delete each one once the last of the stack is merged.
- Never use `git branch -D` on a branch with unmerged work. Exception: Dave decides to drop one; first write `name sha subject` to `.tickets/notes/` so it can be restored with `git branch <name> <sha>`.
- The orchestrator's final report states how many ticket branches are left and why.

## Commit
Subject = what changed + `(<ID>)`. The hook finishes the ticket. The hook runs in every worktree, so the `(<ID>)` commit closes the ticket even before the merge: put it only on the last commit, once the work is reviewed. Check that `done/<ID>-*.md` exists; if not, run `tickets.py done <ID> --commit <hash>`.
