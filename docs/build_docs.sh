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

# Suppress pre-existing docstring-formatting noise from autodoc.
# New docstring warnings SHOULD be caught in dev, but the bulk of the
# current ~75 warnings are pre-existing and not worth failing CI on.
export SPHINXOPTS="-j auto"

build_lang() {
    local lang="$1"
    echo "==> Building $lang docs..."
    sphinx-build -b html \
        -c "$SCRIPT_DIR/$lang" \
        "$SCRIPT_DIR/$lang" \
        "$BUILD_DIR/$lang" \
        2>&1 | tail -5
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
    all|*)
        build_lang en
        build_lang zh
        ;;
esac

echo "==> Docs built → $BUILD_DIR"
echo "    Landing: $BUILD_DIR/index.html"
echo "    English: $BUILD_DIR/en/index.html"
echo "    Chinese: $BUILD_DIR/zh/index.html"
