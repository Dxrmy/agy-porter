#!/usr/bin/env bash
set -e

TARGET="$HOME/.gemini/config/plugins/agy-porter"
PARENT_DIR="$(dirname "$TARGET")"

mkdir -p "$PARENT_DIR"

if [ -d "$TARGET/.git" ]; then
    echo "[agy-porter] Updating existing installation..."
    git -C "$TARGET" pull --quiet
else
    if [ -d "$TARGET" ]; then
        rm -rf "$TARGET"
    fi
    echo "[agy-porter] Installing agy-porter into $TARGET..."
    git clone --quiet https://github.com/Dxrmy/agy-porter.git "$TARGET"
fi

echo "[agy-porter] Successfully installed!"
echo "You can now use /export and /import in Antigravity Desktop and the agy CLI."
