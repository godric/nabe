"""Windows (and Samba) names over NetBIOS: a node status query to each IPv4 address, answered with its name table."""

import contextlib
import select
import socket
import struct
import time

PORT = 137
NBSTAT = 0x21
GROUP = 0x8000
# Name suffixes: 0x00 workstation, 0x20 file server
HOST_SUFFIXES = {0x00, 0x20}
# "*" in NetBIOS first-level encoding: each nibble as a letter from "A", padded to 16 bytes with NULs
WILDCARD = b"\x20" + b"".join(bytes([0x41 + (c >> 4), 0x41 + (c & 0xF)]) for c in b"*" + b"\0" * 15) + b"\0"
ENTRY = 18


def query(transaction_id):
    return struct.pack("!6H", transaction_id, 0, 1, 0, 0, 0) + WILDCARD + struct.pack("!HH", NBSTAT, 1)


def parse_status(msg):
    """The machine's own name from a node status response, or None."""
    off = 12 + len(WILDCARD)
    rtype, _, _, _ = struct.unpack("!HHIH", msg[off : off + 10])
    if rtype != NBSTAT:
        return None
    count = msg[off + 10]
    for i in range(count):
        entry = msg[off + 11 + i * ENTRY : off + 11 + (i + 1) * ENTRY]
        name, suffix, flags = entry[:15], entry[15], struct.unpack("!H", entry[16:18])[0]
        if suffix in HOST_SUFFIXES and not flags & GROUP:
            return name.decode(errors="replace").strip() or None
    return None


def scan(addrs, wait=1.5):
    """{address: name} for the IPv4 addresses that answer."""
    ids = {}
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for i, addr in enumerate(a for a in addrs if ":" not in a):
            ids[addr] = i + 1
            with contextlib.suppress(OSError):  # unreachable address
                sock.sendto(query(i + 1), (addr, PORT))
        deadline = time.monotonic() + wait
        while (left := deadline - time.monotonic()) > 0:
            if not select.select([sock], [], [], left)[0]:
                break
            with contextlib.suppress(OSError, IndexError, struct.error):  # malformed or truncated answer
                msg, (addr, _) = sock.recvfrom(2048)
                if ids.get(addr) == struct.unpack("!H", msg[:2])[0] and (name := parse_status(msg)):
                    found[addr] = name
    return found
