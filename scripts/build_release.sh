#!/usr/bin/env bash
# Build the frontend and package custom_components/transplant as transplant.zip
# (the file HACS downloads, see hacs.json "filename").
set -euo pipefail
cd "$(dirname "$0")/.."

npm ci --silent
npm run build

VERSION=$(python3 -c "import json;print(json.load(open('custom_components/transplant/manifest.json'))['version'])")
if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME#v}" != "$VERSION" ]]; then
  echo "Tag ${GITHUB_REF_NAME} does not match manifest version ${VERSION}" >&2
  exit 1
fi

mkdir -p dist
rm -f dist/transplant.zip
(cd custom_components/transplant && zip -qr ../../dist/transplant.zip . -x "__pycache__/*" "*/__pycache__/*")
echo "Built dist/transplant.zip for v${VERSION}"
