#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "Installing my-diary systemd user timer..."
echo "Project directory: $PROJECT_DIR"

mkdir -p "$SYSTEMD_USER_DIR"

# Template the service file with the actual project path
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    "$SCRIPT_DIR/my-diary.service" > "$SYSTEMD_USER_DIR/my-diary.service"
cp "$SCRIPT_DIR/my-diary.timer" "$SYSTEMD_USER_DIR/"

systemctl --user daemon-reload
systemctl --user enable my-diary.timer
systemctl --user start my-diary.timer

echo "Done! Timer status:"
systemctl --user status my-diary.timer --no-pager
