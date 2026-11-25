#!/usr/bin/env bash
# Collect sanitized metadata from this node and push nodes/<node>.json to GitHub.
# GitHub Actions will then aggregate all nodes and regenerate README.md + docs/inventory.md.
#
# Optional environment variables:
#   NODE_NAME   Logical node name (defaults to `hostname`)
#   NODE_ROLE   Short role label (e.g., "Media Server", "Core Services", "Game & Backup Server")
#   GIT_BRANCH  Target branch (defaults to "main")

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_NAME="${NODE_NAME:-$(hostname)}"
NODE_ROLE="${NODE_ROLE:-}"
GIT_BRANCH="${GIT_BRANCH:-main}"

cd "$REPO_DIR"

# Sync latest main before collecting
git fetch origin "$GIT_BRANCH"
git pull --rebase --autostash origin "$GIT_BRANCH"

# Collect node snapshot (zero secrets, allowlist-based)
if [[ -n "$NODE_ROLE" ]]; then
  python3 scripts/collect_node.py --node-name "$NODE_NAME" --role "$NODE_ROLE"
else
  python3 scripts/collect_node.py --node-name "$NODE_NAME"
fi

# Exit cleanly if nothing changed
if git diff --quiet -- nodes/ && [[ -z "$(git ls-files --others --exclude-standard -- nodes/)" ]]; then
  echo "No changes detected for node '${NODE_NAME}'. Skipping commit."
  exit 0
fi

git add nodes/
git commit -m "chore(nodes): update ${NODE_NAME} snapshot"

# Retry push in case another node or GitHub Actions pushed concurrently
for attempt in 1 2 3; do
  if git push origin "$GIT_BRANCH"; then
    echo "Pushed snapshot for '${NODE_NAME}'."
    exit 0
  fi
  echo "Push failed (attempt ${attempt}/3), rebasing and retrying..."
  sleep $((attempt * 5))
  git pull --rebase origin "$GIT_BRANCH"
done

echo "Failed to push snapshot after 3 attempts." >&2
exit 1
