#!/usr/bin/env bash
set -o errexit

echo "=== Build: $(python --version 2>&1) ==="

PYVER="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PYVER" = "3.14" ]; then
  echo "ERROR: Python 3.14 is not supported. In Render Dashboard set Environment variable:"
  echo "  PYTHON_VERSION = 3.12.8"
  echo "Then redeploy."
  exit 1
fi

pip install --upgrade pip
pip install -r requirements.txt
echo "=== Build finished ==="
