#!/usr/bin/env bash
# Sprint 10 pre-flight environment check.
#
# Runs a battery of go/no-go checks before the autonomous session starts
# real work. Any FAIL here means Phase 0 cannot complete — the session
# should stop and ask for human intervention via Slack DM.
#
# Exit code:
#   0 — all checks passed
#   1 — one or more critical checks failed
#
# Output format:
#   "[OK]    <check> — <detail>"
#   "[WARN]  <check> — <detail>"
#   "[FAIL]  <check> — <detail>"
#
# Checks (in order):
#   1. .env.master sourced
#   2. $OPENROUTER_API_KEY non-empty
#   3. Postgres 17 running (brew services)
#   4. pgvector extension available
#   5. Zotero MCP responds on :23120
#   6. Ollama responds on :11434
#   7. csnl-ontology Python module importable
#   8. gh CLI authenticated
#   9. ai-science-reading-tutor repo readable via gh
#  10. deep-paper-reader git status clean

set -u

BUNDLE_ENV="$HOME/Documents/Claude/Projects/_mcp-bundle/.env.master"
REPO_DIR="$HOME/deep-paper-reader"
ONTOLOGY_VENV="$HOME/Zotero/csnl-ontology/.venv/bin/python"
FAIL_COUNT=0
WARN_COUNT=0

status_ok()   { echo "[OK]    $1 — $2"; }
status_warn() { echo "[WARN]  $1 — $2"; WARN_COUNT=$((WARN_COUNT + 1)); }
status_fail() { echo "[FAIL]  $1 — $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

# 1 — .env.master sourced
if [ -f "$BUNDLE_ENV" ]; then
  # shellcheck disable=SC1090
  set -a && source "$BUNDLE_ENV" && set +a
  status_ok "env-master" "sourced from $BUNDLE_ENV"
else
  status_fail "env-master" "not found at $BUNDLE_ENV"
fi

# 2 — OPENROUTER_API_KEY
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  status_ok "openrouter-key" "set (length=${#OPENROUTER_API_KEY})"
else
  status_fail "openrouter-key" "OPENROUTER_API_KEY not set after sourcing env"
fi

# 3 — Postgres 17
if brew services list 2>/dev/null | grep -q 'postgresql@17.*started'; then
  status_ok "postgres-17" "running via brew services"
elif command -v psql >/dev/null 2>&1 && psql -l >/dev/null 2>&1; then
  status_ok "postgres-17" "reachable via psql -l (brew services state unknown)"
else
  status_fail "postgres-17" "not running. Try: brew services start postgresql@17"
fi

# 4 — pgvector
if psql -tAc "SELECT 1 FROM pg_available_extensions WHERE name='vector';" 2>/dev/null | grep -q 1; then
  status_ok "pgvector" "extension available"
else
  status_warn "pgvector" "extension not available. Install with: brew install pgvector && brew services restart postgresql@17"
fi

# 5 — Zotero MCP (:23120)
if curl -sf -o /dev/null -w "%{http_code}" http://127.0.0.1:23120/ 2>/dev/null | grep -qE "^(200|404|405)$"; then
  status_ok "zotero-mcp" "responding on 127.0.0.1:23120"
else
  status_fail "zotero-mcp" "not reachable on 127.0.0.1:23120. Start Zotero desktop and ensure HTTP server is enabled."
fi

# 6 — Ollama (:11434)
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  OLLAMA_MODELS=$(curl -sf http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(",".join(m["name"] for m in d.get("models",[])))' 2>/dev/null || echo "")
  if [ -n "$OLLAMA_MODELS" ]; then
    status_ok "ollama" "responding; models: $OLLAMA_MODELS"
  else
    status_ok "ollama" "responding (model list unavailable)"
  fi
else
  status_fail "ollama" "not reachable on 127.0.0.1:11434. Start with: ollama serve"
fi

# 7 — csnl-ontology import
if [ -x "$ONTOLOGY_VENV" ]; then
  if "$ONTOLOGY_VENV" -c "from csnl_ontology import rag_adapter" 2>/dev/null; then
    status_ok "csnl-ontology" "importable via $ONTOLOGY_VENV"
  else
    status_warn "csnl-ontology" "venv exists but rag_adapter import failed"
  fi
else
  status_warn "csnl-ontology" "venv Python not found at $ONTOLOGY_VENV"
fi

# 8 — gh CLI auth
if gh auth status 2>&1 | grep -q "Logged in to github.com"; then
  GH_USER=$(gh api user --jq .login 2>/dev/null || echo "unknown")
  status_ok "gh-cli" "authenticated as $GH_USER"
else
  status_fail "gh-cli" "not authenticated. Run: gh auth login"
fi

# 9 — ai-science-reading-tutor readable
if gh api repos/Joonoh991119/ai-science-reading-tutor --jq .name >/dev/null 2>&1; then
  status_ok "ai-reading-tutor-repo" "accessible via gh"
else
  status_warn "ai-reading-tutor-repo" "not accessible — check gh token scopes"
fi

# 10 — deep-paper-reader clean
if [ -d "$REPO_DIR/.git" ]; then
  if [ -z "$(cd "$REPO_DIR" && git status --porcelain 2>/dev/null)" ]; then
    BRANCH=$(cd "$REPO_DIR" && git branch --show-current 2>/dev/null)
    status_ok "deep-paper-reader" "clean working tree on branch '$BRANCH'"
  else
    status_warn "deep-paper-reader" "working tree has uncommitted changes"
  fi
else
  status_fail "deep-paper-reader" "$REPO_DIR is not a git repo"
fi

echo ""
echo "Summary: $FAIL_COUNT failures, $WARN_COUNT warnings."

if [ $FAIL_COUNT -gt 0 ]; then
  echo "Sprint 10 cannot proceed. Resolve FAILs before retrying."
  exit 1
fi

if [ $WARN_COUNT -gt 0 ]; then
  echo "Sprint 10 can proceed but some features may degrade."
fi

exit 0
