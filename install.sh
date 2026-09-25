#!/bin/sh
# Install the LaunchAgent serving the patched subscription. Idempotent.
#
#   ./install.sh [subscription-url]
#
# Without an argument, the URL is taken from SFM's remote profile "sakura".
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
LABEL=com.ddd.sfm-tailscale
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
SFM_DB="$HOME/Library/Group Containers/P8XK3KHB48.io.nekohasekai.sfamt/settings.db"
UID_NUM=$(id -u)

if [ -n "$1" ]; then
    url=$1
else
    url=$(sqlite3 "file:$SFM_DB?mode=ro" \
        "SELECT remoteURL FROM profiles WHERE name = 'sakura' AND type = 2")
fi
[ -n "$url" ] || { echo "未取得订阅地址。用法: ./install.sh <subscription-url>" >&2; exit 1; }
( umask 077 && printf '%s\n' "$url" > "$HERE/subscription.url" )

mkdir -p "$(dirname "$AGENT")"
sed -e "s|@@ROOT@@|$HERE|g" "$HERE/launchagents/$LABEL.plist" > "$AGENT"

# bootout returns before launchd has finished unloading the label, and
# bootstrapping into that window fails with "Input/output error".
if launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1; then
    launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
    waited=0
    while launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 && [ "$waited" -lt 40 ]; do
        sleep 0.25
        waited=$((waited + 1))
    done
fi
launchctl bootstrap "gui/$UID_NUM" "$AGENT"
echo "已安装 $LABEL: http://127.0.0.1:18080/"
