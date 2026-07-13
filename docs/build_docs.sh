#!/usr/bin/env bash
# Build ABI documentation in both English and Chinese.
#
# Usage:
#   bash docs/build_docs.sh              # build both languages
#   bash docs/build_docs.sh en           # English only
#   bash docs/build_docs.sh zh           # Chinese only
#
# Output:
#   docs/_build/en/   — English HTML
#   docs/_build/zh/   — Chinese HTML
#   docs/_build/      — Landing page (index.html)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/_build"
LANDING="$SCRIPT_DIR/index.html"

# Existing autodoc diagnostics remain visible and are capped so documentation
# debt cannot grow silently. Lower these budgets whenever warnings are fixed.
EN_DIAGNOSTIC_BUDGET=6
ZH_DIAGNOSTIC_BUDGET=17

build_lang() {
    local lang="$1"
    local budget log_file diagnostic_count build_status
    if [ "$lang" = "en" ]; then
        budget="$EN_DIAGNOSTIC_BUDGET"
    else
        budget="$ZH_DIAGNOSTIC_BUDGET"
    fi
    log_file="$(mktemp)"
    echo "==> Building $lang docs..."
    set +e
    sphinx-build --keep-going -E -j auto -b html \
        -c "$SCRIPT_DIR/$lang" \
        "$SCRIPT_DIR/$lang" \
        "$BUILD_DIR/$lang" 2>&1 | tee "$log_file"
    build_status="${PIPESTATUS[0]}"
    set -e
    if [ "$build_status" -ne 0 ]; then
        rm -f "$log_file"
        return "$build_status"
    fi
    diagnostic_count="$(grep -Ec 'WARNING:|ERROR:' "$log_file" || true)"
    if grep -q 'ERROR:' "$log_file"; then
        echo "Documentation build contains Sphinx errors ($lang)" >&2
        rm -f "$log_file"
        return 1
    fi
    if [ "$diagnostic_count" -gt "$budget" ]; then
        echo "Documentation diagnostics increased: $diagnostic_count > $budget ($lang)" >&2
        rm -f "$log_file"
        return 1
    fi
    rm -f "$log_file"
    echo "    diagnostics: $diagnostic_count/$budget (must not increase)"
    echo "    $lang build complete → $BUILD_DIR/$lang"
}

# Copy landing page
mkdir -p "$BUILD_DIR"
cp "$LANDING" "$BUILD_DIR/index.html"

# Copy static assets to build root for landing page
if [ -d "$SCRIPT_DIR/_static" ]; then
    mkdir -p "$BUILD_DIR/_static"
    cp -r "$SCRIPT_DIR/_static"/* "$BUILD_DIR/_static/"
fi

case "${1:-all}" in
    en)
        build_lang en
        ;;
    zh)
        build_lang zh
        ;;
    all)
        build_lang en
        build_lang zh
        ;;
    *)
        echo "Usage: bash docs/build_docs.sh [all|en|zh]" >&2
        exit 2
        ;;
esac

echo "==> Docs built → $BUILD_DIR"
echo "    Landing: $BUILD_DIR/index.html"
echo "    English: $BUILD_DIR/en/index.html"
echo "    Chinese: $BUILD_DIR/zh/index.html"
