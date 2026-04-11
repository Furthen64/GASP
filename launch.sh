#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found on PATH." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in .venv"
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

has_xcb_cursor_lib() {
  if command -v ldconfig >/dev/null 2>&1; then
    ldconfig -p 2>/dev/null | grep -q "libxcb-cursor.so.0"
    return $?
  fi

  local lib_dir
  for lib_dir in /usr/lib /usr/lib64 /lib /lib64 /usr/lib/x86_64-linux-gnu; do
    if [ -e "$lib_dir/libxcb-cursor.so.0" ] || [ -e "$lib_dir/libxcb-cursor.so.0.0.0" ]; then
      return 0
    fi
  done

  return 1
}

if [ -z "${QT_QPA_PLATFORM:-}" ] && [ "${DISPLAY:-}" != "" ]; then
  if ! has_xcb_cursor_lib; then
    if [ "${WAYLAND_DISPLAY:-}" != "" ]; then
      export QT_QPA_PLATFORM=wayland
      echo "Notice: libxcb-cursor0 was not found; using Qt Wayland backend instead."
    else
      cat >&2 <<'EOF'
Error: Qt's xcb backend is available but cannot initialize without libxcb-cursor0.
Install it, then retry:
  sudo apt-get update && sudo apt-get install -y libxcb-cursor0

Alternative: run with QT_QPA_PLATFORM=wayland if your desktop session supports Wayland.
EOF
      exit 1
    fi
  fi
fi

exec python -m gasp.main
