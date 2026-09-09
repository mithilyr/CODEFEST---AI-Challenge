#!/usr/bin/env bash
# Rebuilds setup.exe from scripts/setup-windows/ into the project root.
# Requires Go (any platform - this cross-compiles to Windows, no Wine or
# Windows machine needed). Run after editing scripts/setup-windows/main.go.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/setup-windows"

go vet ./...
go test ./...

GOOS=windows GOARCH=amd64 CGO_ENABLED=0 \
  go build -ldflags="-s -w" -o ../../setup.exe .

echo "built setup.exe: $(cd ../.. && ls -la setup.exe)"
