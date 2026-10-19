#!/usr/bin/env bash
# Install (or remove) the CyberAware defense overlay into an AIGoat checkout.
#
# Usage: scripts/install-overlay.sh [--uninstall] [AIGOAT_DIR]
#
#   AIGOAT_DIR defaults to ~/AIGoat. Safe to re-run: steps already applied are
#   skipped. Restart AIGoat afterwards (./scripts/stop.sh && ./scripts/start.sh).

set -euo pipefail

PINNED_COMMIT="bb3cd1bbd1e0"
PROFILE_NAME="cyberaware_profiles.yml"
STOCK_PROFILE_PATH='./config/defense_profiles.yml'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="install"
if [[ "${1:-}" == "--uninstall" ]]; then
  MODE="uninstall"; shift
elif [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0
fi
AIGOAT_DIR="${1:-$HOME/AIGoat}"

log()  { printf '[cyberaware] %s\n' "$*"; }
fail() { printf '[cyberaware] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$AIGOAT_DIR/app/defense/controls" ]] || fail "$AIGOAT_DIR does not look like an AIGoat checkout."
[[ -f "$AIGOAT_DIR/config/config.yml" ]] || fail "$AIGOAT_DIR/config/config.yml is missing."

PATCHES=("$REPO_ROOT"/patches/*.patch)
PKG_DST="$AIGOAT_DIR/app/defense/controls/cyberaware"
PROFILE_DST="$AIGOAT_DIR/config/$PROFILE_NAME"
CONFIG="$AIGOAT_DIR/config/config.yml"

is_applied() { git -C "$AIGOAT_DIR" apply --reverse --check "$1" >/dev/null 2>&1; }

set_profiles_path() {
  # Rewrites the single `profiles_path:` line under `defense:` in config.yml.
  local value="$1"
  grep -q '^  profiles_path:' "$CONFIG" || fail "No 'profiles_path:' line found in $CONFIG."
  sed -i.bak -E "s|^(  profiles_path:).*|\1 \"$value\"|" "$CONFIG"
  rm -f "$CONFIG.bak"
}

if [[ "$MODE" == "uninstall" ]]; then
  for (( i=${#PATCHES[@]}-1; i>=0; i-- )); do
    p="${PATCHES[$i]}"
    if is_applied "$p"; then
      git -C "$AIGOAT_DIR" apply --reverse "$p"; log "Reverted $(basename "$p")"
    fi
  done
  rm -rf "$PKG_DST" "$PROFILE_DST"
  set_profiles_path "$STOCK_PROFILE_PATH"
  log "Removed the overlay and restored the stock defense profiles."
  log "Restart AIGoat: cd $AIGOAT_DIR && ./scripts/stop.sh && ./scripts/start.sh"
  exit 0
fi

# 1. Check the AIGoat version the patches were written against.
head="$(git -C "$AIGOAT_DIR" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
if [[ "$head" != "$PINNED_COMMIT" ]]; then
  log "Warning: AIGoat is at $head, patches target $PINNED_COMMIT. Checking they still apply..."
fi

# 2. Verify every pending patch applies before changing anything.
for p in "${PATCHES[@]}"; do
  if ! is_applied "$p"; then
    git -C "$AIGOAT_DIR" apply --check "$p" \
      || fail "$(basename "$p") does not apply cleanly. Nothing was changed. Check out $PINNED_COMMIT and retry."
  fi
done

# 3. Copy the controls package (replaced on every run so updates land).
rm -rf "$PKG_DST"
cp -r "$REPO_ROOT/overlay/cyberaware" "$PKG_DST"
find "$PKG_DST" -name '__pycache__' -prune -exec rm -rf {} +
log "Installed controls package -> app/defense/controls/cyberaware/"

# 4. Apply the patches.
for p in "${PATCHES[@]}"; do
  if is_applied "$p"; then
    log "Already applied: $(basename "$p")"
  else
    git -C "$AIGOAT_DIR" apply "$p"; log "Applied $(basename "$p")"
  fi
done

# 5. Install our profile and point config.yml at it.
cp "$REPO_ROOT/overlay/config/$PROFILE_NAME" "$PROFILE_DST"
set_profiles_path "./config/$PROFILE_NAME"
log "Defense profiles -> config/$PROFILE_NAME"

log "Done. Restart AIGoat to load the overlay:"
log "  cd $AIGOAT_DIR && ./scripts/stop.sh && ./scripts/start.sh"
log "Audit log: $AIGOAT_DIR/logs/cyberaware-audit.jsonl"
