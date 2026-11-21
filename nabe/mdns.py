"""Hostnames and service names from mDNS (Bonjour): reverse lookups of known addresses, then service browsing."""

import contextlib
import ipaddress
import re
import select
import socket
import struct
import time

from nabe import config

A, PTR, TXT, AAAA, SRV, ANY = 1, 12, 16, 28, 33, 255
SERVICES = "_services._dns-sd._udp.local."
GROUPS = (("224.0.0.251", 5353), ("ff02::fb", 5353))
# Questions per query, so packets stay well under the MTU
CHUNK = 8
COMPRESSION = 0xC0


def encode_name(name):
    return b"".join(bytes([len(label)]) + label.encode() for label in name.rstrip(".").split(".")) + b"\0"


def query(questions):
    msg = struct.pack("!6H", 0, 0, len(questions), 0, 0, 0)
    return msg + b"".join(encode_name(n) + struct.pack("!HH", t, 1) for n, t in questions)


def read_name(msg, off):
    labels, end = [], None
    while True:
        length = msg[off]
        if length >= COMPRESSION:
            end = end or off + 2
            off = ((length & ~COMPRESSION) << 8) | msg[off + 1]
        elif length == 0:
            return ".".join(labels) + ".", end or off + 1
        else:
            labels.append(msg[off + 1 : off + 1 + length].decode(errors="replace"))
            off += 1 + length


def read_txt(rdata):
    strings, i = [], 0
    while i < len(rdata):
        strings.append(rdata[i + 1 : i + 1 + rdata[i]].decode(errors="replace"))
        i += 1 + rdata[i]
    return strings


def parse(msg):
    """Every record of a DNS message as (name, type, value): A/AAAA address, PTR/SRV target name, TXT strings."""
    qd, an, ns, ar = struct.unpack("!4H", msg[4:12])
    off = 12
    for _ in range(qd):
        off = read_name(msg, off)[1] + 4
    records = []
    for _ in range(an + ns + ar):
        name, off = read_name(msg, off)
        rtype, _, _, rdlen = struct.unpack("!HHIH", msg[off : off + 10])
        off += 10
        rdata = msg[off : off + rdlen]
        if rtype == A:
            records.append((name, rtype, socket.inet_ntop(socket.AF_INET, rdata)))
        elif rtype == AAAA:
            records.append((name, rtype, socket.inet_ntop(socket.AF_INET6, rdata)))
        elif rtype == PTR:
            records.append((name, rtype, read_name(msg, off)[0]))
        elif rtype == SRV:
            records.append((name, rtype, read_name(msg, off + 6)[0]))
        elif rtype == TXT:
            records.append((name, rtype, read_txt(rdata)))
        off += rdlen
    return records


def ask(questions, wait=1.5):
    """Ask from an ephemeral port, so responders answer directly instead of multicasting (legacy unicast)."""
    ifindex = socket.if_nametoindex(config.IFACE)
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s4,
        socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s6,
    ):
        s4.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, ifindex)
        s6.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
        for i in range(0, len(questions), CHUNK):
            msg = query(questions[i : i + CHUNK])
            for sock, dest in ((s4, GROUPS[0]), (s6, (*GROUPS[1], 0, ifindex))):
                with contextlib.suppress(OSError):  # no address in that family
                    sock.sendto(msg, dest)
        records = []
        deadline = time.monotonic() + wait
        while (left := deadline - time.monotonic()) > 0:
            for sock in select.select([s4, s6], [], [], left)[0]:
                with contextlib.suppress(OSError, IndexError, struct.error):  # malformed or truncated answer
                    records += parse(sock.recv(9000))
    return records


def clean_label(label):
    """A readable service name, or None for the opaque ones (UUIDs, hex IDs)."""
    label = label.replace("\\032", " ").split("@", 1)[-1]  # AirPlay: "<MAC>@<name>"
    label = re.sub(r"^\d+-\d+-\d+-\d+\.\d+ ", "", label)  # Apple companion link prefix
    return None if re.fullmatch(r"[0-9a-fA-F-]{12,}", label) else label


def ptr_address(name):
    labels = name.split(".")
    try:
        if name.endswith(".in-addr.arpa."):
            return str(ipaddress.ip_address(".".join(reversed(labels[:4]))))
        nibbles = list(reversed(labels[:32]))
        return str(ipaddress.ip_address(":".join("".join(nibbles[i : i + 4]) for i in range(0, 32, 4))))
    except ValueError:
        return None


def names(records):
    """{address: {"host", "services", "types"}} from the records of a scan: the hostname, the readable names of the
    services it announces and their types (_airplay._tcp, ...)."""
    found = {}
    for name, rtype, value in records:
        if rtype in {A, AAAA}:
            found.setdefault(value, {})["host"] = name
        elif rtype == PTR and name.endswith((".in-addr.arpa.", ".ip6.arpa.")) and (addr := ptr_address(name)):
            found.setdefault(addr, {})["host"] = value
    txt = {n: v for n, t, v in records if t == TXT}
    services, types = {}, {}  # hostname -> service display names, service types
    for instance, target in ((n, v) for n, t, v in records if t == SRV):
        label, _, stype = instance.partition("._")
        types.setdefault(target, set()).add("_" + stype.removesuffix(".local."))
        # Google devices put their friendly name in TXT fn=, others in the instance name
        fn = next((s[3:] for s in txt.get(instance, []) if s.startswith("fn=")), None)
        if label := clean_label(fn or label):
            services.setdefault(target, set()).add(label)
    for info in found.values():
        info["services"] = services.get(info.get("host"), set())
        info["types"] = types.get(info.get("host"), set())
    return {a: i for a, i in found.items() if i.get("host")}


def scan(addrs):
    records = ask([(ipaddress.ip_address(a).reverse_pointer + ".", PTR) for a in addrs] + [(SERVICES, PTR)])
    types = sorted({v for n, t, v in records if t == PTR and n == SERVICES})
    records += ask([(t, PTR) for t in types])
    records += ask([(v, ANY) for n, t, v in records if t == PTR and n in types])  # SRV/TXT/A of each instance
    return names(records)
