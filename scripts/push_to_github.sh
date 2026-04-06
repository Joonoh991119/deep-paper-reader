#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# push_to_github.sh — Create repo and push Deep Paper Reader
#
# Usage:
#   export GITHUB_TOKEN="ghp_your_token_here"
#   bash scripts/push_to_github.sh
#
# Or with a specific org/user:
#   bash scripts/push_to_github.sh myusername
# ──────────────────────────────────────────────────────────────

set -euo pipefail

REPO_NAME="deep-paper-reader"
OWNER="${1:-}"  # Optional: GitHub username or org

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "❌ GITHUB_TOKEN not set."
    echo "   Get one at: https://github.com/settings/tokens"
    echo "   Required scopes: repo"
    echo ""
    echo "   export GITHUB_TOKEN='ghp_your_token_here'"
    echo "   bash scripts/push_to_github.sh [username]"
    exit 1
fi

# Get authenticated user if owner not specified
if [ -z "$OWNER" ]; then
    OWNER=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])")
    echo "📌 Using GitHub user: $OWNER"
fi

echo "🔧 Creating repo: $OWNER/$REPO_NAME"

# Create repo via GitHub API
HTTP_CODE=$(curl -s -o /tmp/gh_response.json -w "%{http_code}" \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Content-Type: application/json" \
    https://api.github.com/user/repos \
    -d "{
        \"name\": \"$REPO_NAME\",
        \"description\": \"Comprehension-driven scientific paper parsing & embedding pipeline for neuroscience\",
        \"private\": true,
        \"auto_init\": false
    }")

if [ "$HTTP_CODE" = "201" ]; then
    echo "✅ Repo created: https://github.com/$OWNER/$REPO_NAME"
elif [ "$HTTP_CODE" = "422" ]; then
    echo "⚠️  Repo already exists, will push to existing"
else
    echo "❌ Failed to create repo (HTTP $HTTP_CODE):"
    cat /tmp/gh_response.json
    exit 1
fi

# Set remote and push
REMOTE_URL="https://${GITHUB_TOKEN}@github.com/${OWNER}/${REPO_NAME}.git"

git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE_URL"

echo "📤 Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ Done! Repo: https://github.com/$OWNER/$REPO_NAME"
echo ""
echo "Next steps:"
echo "  1. Clone on your machine: git clone git@github.com:$OWNER/$REPO_NAME.git"
echo "  2. Install: pip install -e '.[all]'"
echo "  3. Set up Zotero: export ZOTERO_LIBRARY_ID=... ZOTERO_API_KEY=..."
echo "  4. Run: python -m src.pipeline paper.pdf"
