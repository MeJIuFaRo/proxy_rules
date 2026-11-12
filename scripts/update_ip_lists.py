#!/usr/bin/env python3
"""Download IPv4 ranges the same way MikroTik scripts ip-updater-cloudflare
and ip-updater-google do, and save them as address lists.

For every source two files are written into lists/:
  <name>.txt  - plain CIDR list, one per line
  <name>.rsc  - RouterOS script that refreshes /ip firewall address-list

A source that fails to download or yields no valid IPv4 ranges is left
untouched, so a temporary outage never empties a list.
"""
import ipaddress
import pathlib
import sys
import urllib.request

SOURCES = [
    # (file name, address-list name, comment, url)
    ("cloudflare", "CLOUDFLARE", "Cloudflare IPv4", "https://www.cloudflare.com/ips-v4"),
    ("google", "GOOGLE", "Google IPv4", "https://www.gstatic.com/ipranges/goog.txt"),
]

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "lists"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "proxy-rules-updater"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ipv4(text: str) -> list[str]:
    nets = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if net.version == 4:
            nets.add(net)
    return [str(n) for n in sorted(nets)]


def render_rsc(list_name: str, comment: str, url: str, nets: list[str]) -> str:
    lines = [
        f"# Source: {url}",
        f'/ip firewall address-list remove [find list="{list_name}" comment="{comment}"]',
        "/ip firewall address-list",
    ]
    lines += [f'add list="{list_name}" address={n} comment="{comment}"' for n in nets]
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    failed = 0
    for name, list_name, comment, url in SOURCES:
        try:
            nets = parse_ipv4(fetch(url))
        except Exception as exc:  # network errors, HTTP errors
            print(f"{name}: download failed: {exc}", file=sys.stderr)
            failed += 1
            continue
        if not nets:
            print(f"{name}: no IPv4 ranges found, keeping previous list", file=sys.stderr)
            failed += 1
            continue
        (OUT_DIR / f"{name}.txt").write_text("\n".join(nets) + "\n", encoding="utf-8")
        (OUT_DIR / f"{name}.rsc").write_text(render_rsc(list_name, comment, url, nets), encoding="utf-8")
        print(f"{name}: {len(nets)} IPv4 ranges")
    return 1 if failed == len(SOURCES) else 0


if __name__ == "__main__":
    sys.exit(main())
