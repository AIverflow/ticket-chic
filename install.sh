#!/bin/sh
# Install the ticket system in a project, or update it. Run it from the ticketing repo:
#   ./install.sh <project-dir>
# First run: .tickets/ becomes a clone of this repo (branch `core` = the system), with its own branch `main`
# for the project's tickets and config. Next runs: fetch `core` and merge it into `main`.
set -e
src=$(cd "$(dirname "$0")" && pwd)
[ -n "$1" ] && [ -d "$1" ] || { echo "usage: $0 <project-dir>"; exit 1; }
proj=$(cd "$1" && pwd)
dst="$proj/.tickets"
if [ ! -e "$dst" ]; then
  git clone -q -b core "$src" "$dst"
  git -C "$dst" checkout -q -b main
  python3 - "$dst" "$(basename "$proj")" <<'PY'
import json, sys
json.dump({'title': sys.argv[2], 'id_prefix': 'T'}, open(sys.argv[1] + '/config.json', 'w'), indent=2)
PY
  git -C "$dst" add config.json
  git -C "$dst" commit -q -m "Project config"
  echo "installed $dst (branch main; the system is on branch core)"
else
  git -C "$dst" rev-parse --git-dir >/dev/null 2>&1 || { echo "$dst exists but is not a git repo"; exit 1; }
  git -C "$dst" fetch -q origin core:core
  git -C "$dst" merge -q --no-edit core
  echo "updated $dst from core"
fi
if git -C "$proj" rev-parse >/dev/null 2>&1; then
  hooks=$(cd "$proj" && git rev-parse --git-path hooks)   # honors core.hooksPath and worktrees
  case $hooks in /*) ;; *) hooks="$proj/$hooks" ;; esac
  mkdir -p "$hooks"
  hook="$hooks/post-commit"
  sub=$(git -C "$proj" rev-parse --show-prefix)            # project folder inside the repo, "" at the root
  if [ -e "$hook" ] && ! grep -q '^# ticketing-hook' "$hook"; then
    echo "hook not installed: $hook exists and is not ours (nothing changed)."
    echo "  Add this line to it: [ -f \"$proj/.tickets/tickets.py\" ] && python3 \"$proj/.tickets/tickets.py\" commit-hook"
  else
    esc=$(printf '%s' "$sub" | sed 's/[|&\\]/\\&/g')   # a folder name with | & or \ must not break sed
    sed "s|^sub=.*|sub=\"$esc\"|" "$src/hooks/post-commit" > "$hook"
    chmod 755 "$hook"
    echo "installed $hook"
  fi
  if ! git -C "$proj" check-ignore -q .tickets; then
    f="$proj/.gitignore"
    { [ ! -s "$f" ] || [ -z "$(tail -c1 "$f")" ] || echo; echo ".tickets/"; } >> "$f"
    echo "added .tickets/ to $f"
  fi
else
  echo "not a git repo: hook not installed (run this script again once it is one)"
fi
python3 "$dst/tickets.py" board
