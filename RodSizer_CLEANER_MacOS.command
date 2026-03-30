#!/bin/bash
# =============================================================================
#  WARNING — RodSizer — Clear All Local History Data (Mac)
#  Double-click this file in Finder only if you want to delete local history.
# =============================================================================

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
RESULTS_DIR="$PROJECT_DIR/results"
UPLOADS_DIR="$PROJECT_DIR/uploads"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }
step()  { echo -e "\n${CYAN}──────────────────────────────────────────${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}──────────────────────────────────────────${NC}"; }

pause_and_exit() {
    echo ""
    echo "Press Enter to close..."
    read -r
    exit "$1"
}

ensure_dir() {
    local dir="$1"
    [ -d "$dir" ] || mkdir -p "$dir"
}

clear_dir_contents() {
    local dir="$1"
    ensure_dir "$dir"
    find "$dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

step "WARNING — Clear All Local History Data"

echo "This is a destructive cleanup action."
echo "It will permanently remove local runtime history, including:"
echo "  - uploaded files in uploads/"
echo "  - generated results in results/"
echo "  - folder analysis cache (.analysis_cache)"
echo "  - backend/server.log"
echo "  - Python __pycache__ files"
echo ""
echo "It will NOT delete your installed Python packages in backend/.venv."
echo ""
read -r -p "Type YES to permanently delete the local history data: " CONFIRM

if [ "$CONFIRM" != "YES" ]; then
    warn "Cleanup cancelled."
    pause_and_exit 0
fi

step "Stopping local server if needed"

if lsof -ti:8000 &>/dev/null; then
    warn "Port 8000 is in use. Stopping the running app first..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

step "Removing local history files"

clear_dir_contents "$RESULTS_DIR"
clear_dir_contents "$UPLOADS_DIR"

find "$PROJECT_DIR" -type d -name ".analysis_cache" -prune -exec rm -rf {} +
find "$PROJECT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PROJECT_DIR" -type f -name "*.pyc" -delete

if [ -f "$BACKEND_DIR/server.log" ]; then
    rm -f "$BACKEND_DIR/server.log"
fi

ensure_dir "$RESULTS_DIR"
ensure_dir "$UPLOADS_DIR"

info "Local history data has been cleared."
info "Your virtual environment and installed packages were kept intact."

echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Cleanup complete.${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"

pause_and_exit 0
