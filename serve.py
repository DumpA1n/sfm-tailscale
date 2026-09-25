#!/usr/bin/env python3
"""Serve the subscription config with a Tailscale endpoint patched in.

SFM subscribes to http://127.0.0.1:PORT/ as a remote profile. Every request
fetches the upstream subscription, patches it, validates it with
`sing-box check`, and returns it; on any failure the response is 502 and SFM
keeps its current profile.

`?log=info` overrides the subscription's log level; without an auth key the
endpoint prints its login URL at info level.

SFM's own container is never read or written: macOS denies background
processes access to another app's group container.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL_FILE = os.path.join(HERE, "subscription.url")
AUTH_KEY_FILE = os.path.join(HERE, "auth-key.txt")
LISTEN = ("127.0.0.1", 18080)
SINGBOX_PATHS = ("/opt/homebrew/bin/sing-box", "/usr/local/bin/sing-box")

TS_TAG = "ts-ep"
TS_DNS_TAG = "DNS-TS"
TS_SUFFIX = "ts.net"
# CGNAT range Tailscale assigns IPv4 node addresses from. The tailnet's IPv6
# prefix is omitted: the subscription gives the TUN an IPv4 address only.
TS_CIDR = "100.64.0.0/10"


def endpoint():
    ep = {
        "type": "tailscale",
        "tag": TS_TAG,
        # Relative to SFM's working directory, so the node identity survives
        # profile updates.
        "state_directory": "tailscale",
    }
    if os.path.exists(AUTH_KEY_FILE):
        with open(AUTH_KEY_FILE) as f:
            key = f.read().strip()
        if key:
            ep["auth_key"] = key
    return ep


def patch(cfg):
    cfg.setdefault("endpoints", []).append(endpoint())

    dns = cfg.setdefault("dns", {})
    dns.setdefault("servers", []).append({
        "type": "tailscale",
        "tag": TS_DNS_TAG,
        "endpoint": TS_TAG,
        "accept_default_resolvers": False,
    })
    # First, so MagicDNS names resolve to real tailnet addresses instead of
    # fake IPs from the subscription's fakeip catch-all.
    dns["rules"] = [{
        "domain_suffix": [TS_SUFFIX],
        "action": "route",
        "server": TS_DNS_TAG,
    }] + dns.get("rules", [])

    route = cfg.setdefault("route", {})
    # First, so the subscription's ip_is_private / UDP-443 reject rules never
    # see tailnet traffic.
    route["rules"] = [{
        "ip_cidr": [TS_CIDR],
        "action": "route",
        "outbound": TS_TAG,
    }] + route.get("rules", [])

    # An excluded tailnet range bypasses the TUN and never reaches the endpoint.
    for inbound in cfg.get("inbounds", []):
        if inbound.get("type") == "tun" and "route_exclude_address" in inbound:
            inbound["route_exclude_address"] = [
                a for a in inbound["route_exclude_address"] if a != TS_CIDR]
    return cfg


def check(body):
    singbox = next((p for p in SINGBOX_PATHS if os.access(p, os.X_OK)), None)
    if singbox is None:
        raise RuntimeError("sing-box CLI not found; brew install sing-box")
    with tempfile.NamedTemporaryFile(suffix=".json") as f:
        f.write(body)
        f.flush()
        r = subprocess.run([singbox, "check", "-c", f.name],
                           capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"sing-box check failed: {r.stderr.strip()}")


def build(user_agent, log_level):
    with open(URL_FILE) as f:
        url = f.read().strip()
    # Providers pick the config dialect by User-Agent, so SFM's is passed on.
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        cfg = json.load(resp)
    if log_level:
        cfg.setdefault("log", {})["level"] = log_level
    body = json.dumps(patch(cfg), ensure_ascii=False, indent=2).encode()
    check(body)
    return body


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            body = build(self.headers.get("User-Agent", "sing-box"),
                         query.get("log", [None])[0])
        except Exception as e:
            self.log_message("build failed: %s", e)
            self.send_error(502, "upstream or patch failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    if not os.path.exists(URL_FILE):
        sys.exit(f"missing {URL_FILE}; run install.sh")
    http.server.ThreadingHTTPServer(LISTEN, Handler).serve_forever()


if __name__ == "__main__":
    main()
