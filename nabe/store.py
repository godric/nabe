"""What's been seen, by MAC, and the groups edited in the page. Both are kept as JSON in the data directory."""

import copy
import ipaddress
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from nabe import config, mdns
from nabe.system import kind

# Neighbor states confirmed lately; STALE entries linger for hours after a device leaves
ACTIVE = {"REACHABLE", "DELAY", "PROBE", "PERMANENT", "SELF"}
ORDER = {"ipv4": 0, "global": 1, "ula": 2, "link-local": 3}

lock = threading.Lock()
# mac -> {"router", "addresses": {addr: {"first_seen", "last_seen", "state"}}, "names": {"<kind>:<value>": last_seen}}
# Name kinds, each expiring like addresses do: host (mDNS), netbios, rdns, service (mDNS service names), type (mDNS
# service types) and via (the protocols it answered)
devices = {}
layout = {"groups": []}  # [{"id", "name", "members": [mac]}], devices in none stand alone
# Probe rounds: the page shows when the last one ran and can ask for one now
probe_status = {"last": None, "running": False}
probe_requested = threading.Event()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def load():
    if config.STATE_FILE.exists():
        devices.update(json.loads(config.STATE_FILE.read_text()))
    if config.LAYOUT_FILE.exists():
        layout["groups"] = json.loads(config.LAYOUT_FILE.read_text()).get("groups", [])


def note(dev, name_kind, value, now):
    dev.setdefault("names", {})[f"{name_kind}:{value}"] = now


def named(dev, name_kind):
    """A device's values of one kind, most recently seen first."""
    found = [(t, k.partition(":")[2]) for k, t in dev.get("names", {}).items() if k.startswith(name_kind + ":")]
    return [v for _, v in sorted(found, reverse=True)]


def update(entries, now=None):
    """Merge `ip neigh` entries in, forget addresses and names not seen for the retention period, save."""
    now = now or time.time()
    with lock:
        for e in entries:
            if "lladdr" not in e or "FAILED" in e.get("state", []):
                continue
            dev = devices.setdefault(e["lladdr"].lower(), {"router": False, "addresses": {}})
            dev["router"] |= "router" in e
            seen = dev["addresses"].setdefault(e["dst"], {"first_seen": now, "last_seen": now})
            seen["state"] = e.get("state", ["?"])[0]
            if seen["state"] in ACTIVE:
                seen["last_seen"] = now
        cutoff = now - config.RETENTION_DAYS * 86400
        for mac in list(devices):
            addrs = devices[mac]["addresses"]
            for a in [a for a, s in addrs.items() if s["last_seen"] < cutoff]:
                del addrs[a]
            names = devices[mac].get("names", {})
            for k in [k for k, t in names.items() if t < cutoff]:
                del names[k]
            if not addrs:
                del devices[mac]
        write_json(config.STATE_FILE, devices)


def macs_by_address():
    with lock:
        return {a: m for m, d in devices.items() for a in d["addresses"] if kind(a) != "link-local"}


def set_names(found, netbios, by_addr, self_mac, now=None):
    """Record what the mDNS and NetBIOS scans found, and the host's own name: containers announce theirs on its
    addresses too."""
    now = now or time.time()
    with lock:
        for addr, info in found.items():
            if (dev := devices.get(by_addr.get(addr, ""))) is None:
                continue
            note(dev, "host", info["host"].removesuffix(".").removesuffix(".local"), now)
            note(dev, "via", "mDNS", now)
            for label in info["services"]:
                note(dev, "service", label, now)
            for stype in info["types"]:
                note(dev, "type", stype, now)
        for addr, name in netbios.items():
            if (dev := devices.get(by_addr.get(addr, ""))) is not None:
                note(dev, "netbios", name, now)
                note(dev, "via", "NetBIOS", now)
        if (dev := devices.get(self_mac)) is not None:
            note(dev, "host", socket.gethostname(), now)
        write_json(config.STATE_FILE, devices)


def save_layout(new):
    """Replace the groups edited in the page, keeping only well-formed ones."""
    groups = [
        {"id": str(g["id"]), "name": str(g.get("name", "")).strip(), "members": [str(m).lower() for m in g["members"]]}
        for g in new["groups"]
        if g.get("members")
    ]
    with lock:
        layout["groups"] = groups
        write_json(config.LAYOUT_FILE, layout)


def reverse_dns(addr):
    try:
        return socket.gethostbyaddr(addr)[0]
    except OSError:
        return None


def set_reverse_dns(by_addr, now=None):
    """Reverse DNS for every routable address, kept per device; done in the probe round as lookups can be slow."""
    now = now or time.time()
    with ThreadPoolExecutor(16) as pool:
        names = dict(zip(by_addr, pool.map(reverse_dns, by_addr), strict=True))
    found = {}  # mac -> its first address's name
    for addr, mac in by_addr.items():
        if names[addr]:
            found.setdefault(mac, names[addr])
    with lock:
        for mac, name in found.items():
            if mac in devices:
                note(devices[mac], "rdns", name, now)
                note(devices[mac], "via", "rDNS", now)


def readable_host(host, services):
    """The mDNS hostname, or the shortest service name when the hostname is an opaque ID (Google, Home Assistant)."""
    if host and mdns.clean_label(host) is None:
        return min(filter(None, map(mdns.clean_label, services)), key=len, default=host)
    return host


def snapshot(now=None):
    now = now or time.time()
    with lock:
        items = copy.deepcopy(devices)
        groups = copy.deepcopy(layout["groups"])
    result = []
    for mac, dev in items.items():
        addrs = sorted(
            ({"address": a, "kind": kind(a), **s} for a, s in dev["addresses"].items()),
            key=lambda x: (ORDER[x["kind"]], ipaddress.ip_address(x["address"])),
        )
        last_seen = max(x["last_seen"] for x in addrs)
        is_self = any(x["state"] == "SELF" for x in addrs)
        hosts, netbios_names, rdns_names = (named(dev, k) for k in ("host", "netbios", "rdns"))
        # The latest of each names the device; the host goes by its own name, not its containers'
        host = socket.gethostname() if is_self and hosts else next(iter(hosts), None)
        netbios, rdns = (next(iter(n), None) for n in (netbios_names, rdns_names))
        services = sorted(named(dev, "service"))
        name = readable_host(host, services) or netbios or rdns
        result.append(
            {
                "mac": mac,
                "name": name,
                "host": host,
                "netbios": netbios,
                "rdns": rdns,
                # Every name still kept, most recent first
                "hosts": hosts,
                "netbios_names": netbios_names,
                "rdns_names": rdns_names,
                "services": services,
                "service_types": sorted(named(dev, "type")),
                # The ways it answered: mDNS, NetBIOS, reverse DNS
                "seen_via": sorted(named(dev, "via")),
                # Locally administered bit: a randomized "private" MAC (phones, tablets, laptops)
                "random_mac": bool(int(mac.split(":")[0], 16) & 2),
                "router": dev["router"],
                "self": is_self,
                "last_seen": last_seen,
                "online": now - last_seen < config.ONLINE_FOR,
                "addresses": addrs,
            },
        )
    result.sort(key=lambda d: (d["name"] is None, (d["name"] or "").casefold(), d["mac"]))
    return {"devices": result, "groups": groups, "probe": dict(probe_status), "probe_interval": config.PROBE_INTERVAL}
