#!/bin/sh
# Install the ticket system in a project, or update it. Run it from the ticket-chic repo:
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
  # .tickets must be a repo root itself: a plain folder inside the app's repo would pass a bare rev-parse
  top=$(git -C "$dst" rev-parse --show-toplevel 2>/dev/null || true)
  [ -n "$top" ] && [ "$(cd "$top" && pwd -P)" = "$(cd "$dst" && pwd -P)" ] || { echo "$dst exists but is not a ticket repo (nothing changed)"; exit 1; }
  [ "$(git -C "$dst" symbolic-ref --short -q HEAD || true)" = main ] || { echo "check out main in $dst first (nothing changed)"; exit 1; }
  git -C "$dst" fetch -q "$src" core:core
  git -C "$dst" merge -q --no-edit core
  echo "updated $dst from core"
fi
if git -C "$proj" rev-parse >/dev/null 2>&1; then
  hooks=$(cd "$proj" && git rev-parse --git-path hooks)   # honors core.hooksPath and worktrees
  case $hooks in /*) ;; *) hooks="$proj/$hooks" ;; esac
  mkdir -p "$hooks"
  hook="$hooks/post-commit"
  sub=$(git -C "$proj" rev-parse --show-prefix)            # project folder inside the repo, "" at the root
  case $sub in *"
"*) echo "folder name with a newline is not supported: $sub"; exit 1 ;; esac
  sq() { printf '%s' "$1" | sed "s/'/'\\\\''/g"; }        # for single quotes: ' becomes '\''
  # sub is written single-quoted; sed also needs | (delimiter), & and \ escaped
  esc=$(sq "$sub" | sed 's/[|&\\]/\\&/g')
  new=$(sed "s|^sub=.*|sub='$esc'|" "$src/hooks/post-commit")
  old=$(grep '^sub=' "$hook" 2>/dev/null || true)
  if [ -e "$hook" ] && ! grep -q '^# ticketing-hook' "$hook"; then
    echo "hook not installed: $hook exists and is not ours (nothing changed)."
    echo "  Add this line to it: t='$(sq "$proj/.tickets/tickets.py")'; [ -f \"\$t\" ] && python3 \"\$t\" commit-hook"
  elif [ -n "$old" ] && [ "$old" != "sub='$(sq "$sub")'" ] && [ "$old" != "sub=\"$sub\"" ]; then   # second form: older hooks
    other=${old#sub=}; other=${other#?}; other=${other%?}
    echo "hook not changed: $hook already serves the ticket folder '${other:-.}' of this git repo."
    echo "  Only one ticket folder per git repo is supported."
  else
    printf '%s\n' "$new" > "$hook"
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
