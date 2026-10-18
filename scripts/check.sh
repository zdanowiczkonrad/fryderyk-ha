#!/usr/bin/env bash
# The one check command (AISDLC): lint, JSON validity, parser + Home Assistant tests.
# PHCC pins the Home Assistant version the tests run against; bump it deliberately.
set -euo pipefail
cd "$(dirname "$0")/.."
uvx ruff check custom_components tests fryderyk.py
uvx ruff format --check custom_components tests fryderyk.py
PHCC="${PHCC:-pytest-homeassistant-custom-component==0.13.316}"
uv run --no-project --python 3.13 --with "$PHCC" --with beautifulsoup4 pytest -q -p no:cacheprovider
python3 -m json.tool custom_components/fryderyk/manifest.json >/dev/null
for f in custom_components/fryderyk/strings.json custom_components/fryderyk/translations/*.json; do python3 -m json.tool "$f" >/dev/null; done
cmp -s custom_components/fryderyk/strings.json custom_components/fryderyk/translations/en.json || { echo "translations/en.json out of sync with strings.json"; exit 1; }
echo "checks: OK"
