#!/usr/bin/env python3
"""Build the MikroTik address-list VPN from public IPv4 ranges.

Sources (in priority order):
  cloudflare - https://www.cloudflare.com/ips-v4
  google     - https://www.gstatic.com/ipranges/goog.txt
  meta       - prefixes announced by Meta ASNs (RIPEstat)
  chatgpt    - OpenAI ASN prefixes + current IPs of ChatGPT hosts
  claude     - Anthropic documented ranges + ASN prefixes + current IPs
               of Claude hosts

Files written into lists/:
  <source>.txt - plain IPv4 CIDR list of one source
  vpn.txt      - combined list without duplicates
  vpn.rsc      - RouterOS script that syncs /ip firewall address-list VPN

A source that fails to download keeps its previous <source>.txt, so a
temporary outage never empties the list. The script exits with code 1 if
any source failed, after writing everything it could.
"""
import ipaddress
import json
import pathlib
import re
import socket
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

ADDRESS_LIST = "VPN"
COMMENT_PREFIX = "proxy_rules: "
STALE_COMMENT = COMMENT_PREFIX + "stale"

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "lists"
USER_AGENT = "proxy-rules-updater"
RIPESTAT_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"


@dataclass
class Source:
    name: str          # file name in lists/
    label: str         # comment on RouterOS entries
    urls: list[str] = field(default_factory=list)   # plain-text CIDR lists
    asns: list[int] = field(default_factory=list)   # announced prefixes
    docs: list[str] = field(default_factory=list)   # Markdown pages with CIDRs
    hosts: list[str] = field(default_factory=list)  # resolved to /32


# Order matters: a network already covered by an earlier source is not
# repeated in vpn.rsc (ChatGPT hosts are usually inside Cloudflare ranges).
SOURCES = [
    Source("cloudflare", "Cloudflare", urls=["https://www.cloudflare.com/ips-v4"]),
    Source("google", "Google", urls=["https://www.gstatic.com/ipranges/goog.txt"]),
    Source("meta", "Meta", asns=[32934, 63293, 54115]),
    Source(
        "chatgpt",
        "ChatGPT",
        asns=[401864],
        hosts=[
            "chatgpt.com",
            "ab.chatgpt.com",
            "chat.openai.com",
            "ios.chat.openai.com",
            "android.chat.openai.com",
            "openai.com",
            "api.openai.com",
            "auth.openai.com",
            "platform.openai.com",
            "cdn.oaistatic.com",
            "files.oaiusercontent.com",
            "sora.com",
            "chatgpt.livekit.cloud",
        ],
    ),
    Source(
        "claude",
        "Claude",
        docs=["https://platform.claude.com/docs/en/api/ip-addresses.md"],
        asns=[399358, 400243, 401551],
        hosts=[
            "claude.ai",
            "claude.com",
            "code.claude.com",
            "platform.claude.com",
            "anthropic.com",
            "api.anthropic.com",
            "console.anthropic.com",
            "a-cdn.anthropic.com",
            "claudeusercontent.com",
        ],
    ),
]

Network = ipaddress.IPv4Network


def http_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_ipv4(lines) -> set[Network]:
    nets = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if net.version == 4:
            nets.add(net)
    return nets


def asn_prefixes(asn: int) -> set[Network]:
    query = urllib.parse.urlencode({"resource": f"AS{asn}", "sourceapp": USER_AGENT})
    data = json.loads(http_get(f"{RIPESTAT_URL}?{query}"))
    if data.get("status") != "ok":
        raise RuntimeError(f"RIPEstat AS{asn}: status {data.get('status')!r}")
    return parse_ipv4(p["prefix"] for p in data["data"]["prefixes"])


IPV4_CIDR = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}\b")
PHASED_OUT = re.compile(r"^#+\s.*phased out", re.IGNORECASE | re.MULTILINE)


def doc_prefixes(url: str) -> set[Network]:
    # Inbound and outbound ranges; everything after "Phased out" is no longer used.
    text = http_get(url)
    match = PHASED_OUT.search(text)
    current = text[: match.start()] if match else text
    nets = parse_ipv4(IPV4_CIDR.findall(current))
    if not nets:
        raise RuntimeError(f"no IPv4 ranges in {url}")
    return nets


def resolve(host: str) -> set[Network]:
    infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    return {ipaddress.ip_network(info[4][0]) for info in infos}


def fetch(source: Source) -> list[Network]:
    nets: set[Network] = set()
    for url in source.urls:
        nets |= parse_ipv4(http_get(url).splitlines())
    for url in source.docs:
        nets |= doc_prefixes(url)
    for asn in source.asns:
        nets |= asn_prefixes(asn)
    for host in source.hosts:
        nets |= resolve(host)
    return list(ipaddress.collapse_addresses(nets))


def load_previous(path: pathlib.Path) -> list[Network]:
    if not path.exists():
        return []
    return list(ipaddress.collapse_addresses(parse_ipv4(path.read_text().splitlines())))


def ros_address(net: Network) -> str:
    # RouterOS stores single hosts without /32; match that for [find address=...].
    return str(net.network_address) if net.prefixlen == 32 else str(net)


def render_rsc(entries: list[tuple[Network, str]]) -> str:
    al = "/ip firewall address-list"
    lines = [
        "# Generated by scripts/update_ip_lists.py - do not edit by hand.",
        f"# Syncs address-list {ADDRESS_LIST}: entries with comment prefix "
        f"\"{COMMENT_PREFIX}\" are owned by this script, other entries are kept.",
        "# Old entries are marked stale first and removed only at the end,",
        "# so the list is never empty while the import runs.",
        f'{al} set [find where list="{ADDRESS_LIST}" comment~"^{COMMENT_PREFIX}"] '
        f'comment="{STALE_COMMENT}"',
    ]
    for net, label in entries:
        addr = ros_address(net)
        comment = COMMENT_PREFIX + label
        lines.append(
            f':do {{ {al} add list={ADDRESS_LIST} address={addr} comment="{comment}" }} '
            f'on-error={{ {al} set [find list={ADDRESS_LIST} address={addr} '
            f'comment="{STALE_COMMENT}"] comment="{comment}" }}'
        )
    lines.append(f'{al} remove [find where list="{ADDRESS_LIST}" comment="{STALE_COMMENT}"]')
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    failed = []
    combined: list[tuple[Network, str]] = []

    for source in SOURCES:
        path = OUT_DIR / f"{source.name}.txt"
        try:
            nets = fetch(source)
            if not nets:
                raise RuntimeError("no IPv4 ranges found")
            path.write_text("".join(f"{n}\n" for n in nets), encoding="utf-8")
            print(f"{source.name}: {len(nets)} IPv4 ranges")
        except Exception as exc:  # network, HTTP, DNS or parse errors
            failed.append(source.name)
            nets = load_previous(path)
            print(f"{source.name}: update failed ({exc}); keeping previous "
                  f"{len(nets)} ranges", file=sys.stderr)

        added = 0
        for net in nets:
            if any(net.subnet_of(prev) for prev, _ in combined):
                continue
            combined.append((net, source.label))
            added += 1
        print(f"{source.name}: {added} new entries in {ADDRESS_LIST}")

    if not combined:
        print("nothing to write", file=sys.stderr)
        return 1

    (OUT_DIR / "vpn.txt").write_text(
        "".join(f"{n}\n" for n in sorted(n for n, _ in combined)), encoding="utf-8")
    (OUT_DIR / "vpn.rsc").write_text(render_rsc(combined), encoding="utf-8")
    print(f"{ADDRESS_LIST}: {len(combined)} entries total")

    if failed:
        print(f"failed sources: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
