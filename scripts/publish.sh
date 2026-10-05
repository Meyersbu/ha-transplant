#!/usr/bin/env bash
# Publish this repository to GitHub with the GitHub CLI.
#
#   ./scripts/publish.sh <github-username>
#
# Requires: git, gh (https://cli.github.com) logged in via `gh auth login`.
# Creates a PUBLIC repository <github-username>/ha-transplant, pushes main,
# sets topics (required by the HACS validation) and enables Discussions.
set -euo pipefail

OWNER="${1:?Usage: ./scripts/publish.sh <github-username>}"
REPO="ha-transplant"
cd "$(dirname "$0")/.."

command -v git >/dev/null || { echo "git is not installed" >&2; exit 1; }
command -v gh >/dev/null || { echo "GitHub CLI missing: brew install gh" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run 'gh auth login' first" >&2; exit 1; }

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "$OWNER/$REPO already exists. Aborting so nothing is overwritten." >&2
  exit 1
fi

# Replace the placeholder owner in manifest, README, templates.
# perl -pi works the same on macOS and Linux.
grep -rl "christophmeyer" --exclude-dir=node_modules --exclude-dir=.git --exclude=publish.sh . \
  | xargs perl -pi -e "s/christophmeyer/$OWNER/g"

if [ ! -d .git ]; then
  git init -q -b main
fi
git add -A
git commit -q -m "Transplant v0.1.0: replace a device without breaking anything" || true

gh repo create "$OWNER/$REPO" \
  --public \
  --source . \
  --remote origin \
  --push \
  --description "Replace a broken device in Home Assistant without breaking anything – preview, apply, undo."

gh repo edit "$OWNER/$REPO" \
  --enable-discussions \
  --enable-issues \
  --add-topic home-assistant \
  --add-topic hacs \
  --add-topic home-automation \
  --add-topic smart-home \
  --add-topic homeassistant-custom-component \
  --add-topic hacs-integration

echo
echo "Published: https://github.com/$OWNER/$REPO"
echo "Next: wait for the CI and Validate workflows to pass:"
echo "  gh run watch --repo $OWNER/$REPO"
echo "Then release when you have tested it on a test instance:"
echo "  git tag v0.1.0 && git push origin v0.1.0"
