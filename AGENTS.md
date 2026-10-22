# ticketing: agent guide

Generic ticket system (see `README.md`). It is copied into other projects, so it must stay small and project-neutral.

- `tickets.py`: one file, Python standard library only. No dependency, no mention of any specific project, model, branch or worktree (those belong in `modules/`).
- This repo has one branch, `core`. Projects clone it into `.tickets/` and work on their own `main` branch; `install.sh <project>` installs or updates (fetch `core`, merge into `main`). Never make a change that would conflict with project tickets (`T<n>-*.md`) or `config.json`.
- `WORKFLOW.md` is the core rules only. Branch, worktree, role and model rules go in `modules/`.
- Never write to a project's `.tickets/` from here: each project has its own.
- Test: `python3 -m unittest discover -s tests` (must pass before a commit).
- Docs use plain words; the owner is called "Dave" in `WORKFLOW.md` and modules.
