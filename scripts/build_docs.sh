#!/usr/bin/env bash
# Builds the bilingual docs site into site/ — one Zensical build per language,
# assembled afterwards (measured 2026-09-23: building into a shared site_dir makes
# each build wipe the other language).
#
# Usage: bash scripts/build_docs.sh [--stamp]
#   --stamp  first write git revision dates into guide/ pages (CI only: it edits the
#            working copy, and it refuses a shallow clone).
set -euo pipefail
cd "$(dirname "$0")/.."

STAMP="${1:-}"
if [ "$STAMP" = "--stamp" ]; then
  uv run python scripts/stamp_revision_dates.py guide
fi

rm -rf .docs-build site
uv run --group docs zensical build --strict -f zensical.en.yml
uv run --group docs zensical build --strict -f zensical.pt.yml

mkdir -p site
cp -R .docs-build/en/. site/
cp -R .docs-build/pt site/pt

mkdir -p site/assets site/stylesheets site/pt/stylesheets
if [ -d assets/diagrams ]; then cp -R assets/diagrams site/assets/diagrams; fi
cp assets/site/night-shift.css site/stylesheets/night-shift.css
cp assets/site/night-shift.css site/pt/stylesheets/night-shift.css
if [ -f assets/site/social-preview.png ]; then mkdir -p site/assets/site && cp assets/site/social-preview.png site/assets/site/; fi
# The theme's language switcher fetches sitemap.xml beside each hreflang URL, and ours are
# per page (overrides/main.html): each page directory gets its language's sitemap, or
# every page view fires two 404s.
find site -name index.html -not -path 'site/pt/*' -not -path site/index.html \
  -exec dirname {} \; | while read -r page_dir; do cp site/sitemap.xml "$page_dir/"; done
find site/pt -name index.html -not -path site/pt/index.html \
  -exec dirname {} \; | while read -r page_dir; do cp site/pt/sitemap.xml "$page_dir/"; done
REQUIRE_DATES=""
if [ "$STAMP" = "--stamp" ]; then REQUIRE_DATES="--require-dates"; fi
uv run python scripts/check_built_site.py site guide $REQUIRE_DATES
