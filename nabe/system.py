"""The host side: its neighbor table and addresses (iproute2), and pings to make the LAN show up in that table."""

import ipaddress
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor

from nabe import config

ULA = ipaddress.ip_network("fc00::/7")
# Beyond that the IPv4 sweep would take too long, the neighbor table alone is used
MAX_SWEEP = 1024


def ip_json(*args):
    out = subprocess.run(["ip", "-j", *args], capture_output=True, text=True, check=True).stdout  # noqa: S603, S607
    return json.loads(out or "[]")


def kind(addr):
    ip = ipaddress.ip_address(addr)
    if ip.version == 4:  # noqa: PLR2004
        return "ipv4"
    if ip.is_link_local:
        return "link-local"
    return "ula" if ip in ULA else "global"


def neighbors():
    return ip_json("neigh", "show", "dev", config.IFACE)


def own_addresses():
    """The host's MAC and non-temporary addresses on the interface, as its neighbors see it."""
    mac, addrs, subnets = None, [], []
    for link in ip_json("addr", "show", "dev", config.IFACE):
        mac = link.get("address")
        for a in link.get("addr_info", []):
            if a.get("temporary"):
                continue
            addrs.append(a["local"])
            if a["family"] == "inet":
                subnets.append(ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False))
    return mac, addrs, subnets


def ping(*args):
    subprocess.run(["ping", *args], capture_output=True, check=False)  # noqa: S603, S607


def probe():
    """All-nodes ping from each IPv6 source, so hosts answer from their matching addresses, and an IPv4 sweep."""
    _, addrs, subnets = own_addresses()
    all_nodes = f"ff02::1%{config.IFACE}"
    for addr in addrs:
        if kind(addr) in {"global", "ula"}:
            ping("-6", "-c", "2", "-w", "3", "-I", addr, all_nodes)
    ping("-6", "-c", "2", "-w", "3", all_nodes)

    targets = [str(h) for net in subnets if net.num_addresses <= MAX_SWEEP for h in net.hosts() if str(h) not in addrs]
    with ThreadPoolExecutor(64) as pool:
        list(pool.map(lambda t: ping("-c", "1", "-W", "1", t), targets))
