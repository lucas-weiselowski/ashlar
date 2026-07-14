#!/usr/bin/env bash
# ashlar — plugin installer.
#
# Registers this repo as a Claude Code marketplace and installs the ashlar
# plugin (skill + bin/ashlar CLI) from it.
#
# One-line install:
#   curl -fsSL https://raw.githubusercontent.com/lucas-weiselowski/ashlar/main/install.sh | bash
#
# Local clone:
#   ./install.sh

set -euo pipefail

REPO="lucas-weiselowski/ashlar"

if ! command -v claude >/dev/null 2>&1; then
  echo "ashlar: Claude Code CLI ('claude') not found on PATH." >&2
  echo "  Install: https://docs.claude.com/en/docs/claude-code" >&2
  exit 1
fi

# BASH_SOURCE is unset when bash is invoked from stdin (curl | bash). Guard
# on that directly instead of feeding an empty string to dirname, which
# returns "." (the caller's CWD) rather than "" and would wrongly treat any
# directory the user happens to be in as the repo.
here=""
if [ -n "${BASH_SOURCE[0]:-}" ]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here=""
fi
if [ -n "$here" ] && [ -f "$here/.claude-plugin/marketplace.json" ]; then
  source="$here"
else
  source="$REPO"
fi

echo "ashlar: adding marketplace ($source)..."
claude plugin marketplace add "$source"

echo "ashlar: installing plugin..."
claude plugin install ashlar@ashlar

if [ -n "$here" ]; then
  chmod +x "$here/bin/ashlar"
  echo "ashlar: standalone CLI at $here/bin/ashlar — add to PATH if you want it outside Claude Code:"
  echo "  export PATH=\"\$PATH:$here/bin\""
fi

echo "ashlar: done. Restart Claude Code (or start a new session) to pick up the skill."
echo "ashlar: once restarted, ask Claude to run 'ashlar doctor' to verify the install (ledger/cache status, hook wiring)."
