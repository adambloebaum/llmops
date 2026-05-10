#!/usr/bin/env bash
# Install in-repo skills into Claude Code's discovery path.
#
# Symlinks every directory under ~/llmops/skills/ into ~/.claude/skills/
# so they're picked up by the Claude Code harness. Idempotent — re-running
# refreshes the symlinks. Existing non-symlink dirs at the target paths
# are NOT overwritten (script aborts with a warning).
#
# Why symlinks: edits in ~/llmops/skills/ are reflected immediately, no
# re-install needed. The skill content is version-controlled in the repo.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/skills"
DST="$HOME/.claude/skills"

if [[ ! -d "$SRC" ]]; then
  echo "[skip] $SRC does not exist — nothing to install."
  exit 0
fi

mkdir -p "$DST"

count=0
for skill in "$SRC"/*/; do
  [[ -d "$skill" ]] || continue
  name="$(basename "$skill")"
  target="$DST/$name"

  if [[ -e "$target" && ! -L "$target" ]]; then
    echo "[warn] $target exists and is not a symlink — skipping."
    echo "       Move or delete it first if you want the in-repo version."
    continue
  fi

  ln -sfn "$skill" "$target"
  echo "[ok]   linked $name -> $skill"
  count=$((count + 1))
done

echo
echo "Installed $count skill(s) into $DST."
echo "Restart Claude Code to pick up changes."
