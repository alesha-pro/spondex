#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Building frontend..."
cd src/dashboard
npm ci
npm run build
cd ../..

echo "==> Building Python wheel..."
uv build

echo "==> Done. Checking static files in wheel..."
unzip -l dist/spondex-*.whl | grep static/ || echo "WARNING: no static files found in wheel!"
