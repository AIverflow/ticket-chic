# Module: roles

Applies when `.tickets/config.json` has `"roles": true` (the default). For work split between several agents. Only the orchestrator talks to Dave and commits. Agents talk only with the orchestrator. **Find your role below and read only that section.** Any agent or model can run a role.
The mode (`chain` or `validate`, see `WORKFLOW.md`) decides when the reviewer runs. Where the work happens: `WORKFLOW.md`.

## Agent tiers
Tickets and prompts name a tier, never a model or a tool: **light** (small agent, small clear tickets) · **standard** (normal coding agent) · **strong** (hardest work, design, risky changes).
A ticket's `difficulty` suggests one: 1 → light, 2 → standard, 3 → strong. Dave maps tiers to real models when he starts the orchestrator; if he did not, the orchestrator asks.

## Orchestrator (main agent, in the chat)
You pick the work, start the agents, decide what reaches Dave. You run no tests.
1. Find the mode: Dave's words (chain / validate), else `mode` in `config.json`.
2. Pick a `ready` ticket (not blocked). One ticket per implementer run. Set it `doing`. Small tickets may be grouped in one run.
3. Give the implementer the ticket text.
4. When it reports done, commit its work (the implementer does not commit):
   - **chain**: commit with the ticket ID in parentheses at the end of the subject; the hook finishes the ticket. Review is optional: skip it, or start the reviewer once on the whole series at the end.
   - **validate**: commit without the ID, on the ticket's branch. Start the reviewer on those commits, in the background. On PASS show Dave the result and what to test, then wait. Only after Dave's OK: the final commit or merge with the ID.
5. On any problem from the reviewer: show Dave, then wait.
6. On STOP from any agent: leave the ticket as it is, add `Stopped: <reason>` at its top, set it `parked`, tell Dave. Don't restart it.
7. Report to Dave in 5 lines: what changed · what was tested · what was not · anything suspicious · folder path and branch to test.

## Implementer
You code one ticket. You never touch `.tickets/` and you do not commit.
1. **Check the ticket first.** If the code is clearly not what it describes (missing function, other behaviour, wrong file), do not code: reply `STOP: <what differs>` and say what you need.
2. Edit the files the ticket names, nothing else.
3. First pass on your own code: read your diff against the ticket's "Do" and "Done when". Fix what you see.
4. Run the project's build and the test that covers your change (see `AGENTS.md`). It must pass.
5. Report: what changed, tests run, what you could not check. Leave changes uncommitted for the orchestrator to commit.

## Reviewer
One broader pass on the changes you are given (uncommitted, or the ticket's commits in `validate` mode). No repeated reviews. You do not touch `.tickets/` and do not commit.
1. Read the ticket's "Do" and "Done when" and the diff.
2. Run the tests (see `AGENTS.md`). For UI changes, open the screenshots and describe what you see.
3. Fix small problems yourself, uncommitted (the orchestrator commits them).
4. Report: PASS or FAIL per "Done when" point, what you fixed, anything suspicious, what you did not check.
**STOP** instead of fixing when the problem is serious: wrong design, ticket does not match the code, or a large fix. One line with the reason.

## Stop rule
A STOP ends the ticket for this run. One implementer pass, one reviewer pass; if the reviewer still finds a serious problem, STOP. Nobody restarts a stopped ticket on their own.
