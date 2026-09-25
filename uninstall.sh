#!/bin/sh
# Remove the LaunchAgent. The SFM profile and its Tailscale node state are left
# in place.
LABEL=com.ddd.sfm-tailscale
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "已移除 $LABEL"
