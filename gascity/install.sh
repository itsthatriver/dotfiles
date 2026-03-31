#!/usr/bin/env bash
#
# Verify gascity installation.

if command -v gc > /dev/null 2>&1; then
  echo "» gascity $(gc version 2>&1 | head -1)"
else
  echo "⚠ gascity (gc) not found on PATH after install"
fi
