import socket
import struct

from nabe import mdns


def record(name, rtype, rdata):
    return mdns.encode_name(name) + struct.pack("!HHIH", rtype, 1, 120, len(rdata)) + rdata


def message(*records):
    return struct.pack("!6H", 0, 0x8400, 0, len(records), 0, 0) + b"".join(records)


def test_parse_records():
    msg = message(
        record("ipad.local.", mdns.A, socket.inet_pton(socket.AF_INET, "192.0.2.12")),
        record("ipad.local.", mdns.AAAA, socket.inet_pton(socket.AF_INET6, "fd12:3456:789a::12")),
        record("12.2.0.192.in-addr.arpa.", mdns.PTR, mdns.encode_name("ipad.local.")),
        record("Den._googlecast._tcp.local.", mdns.SRV, struct.pack("!3H", 0, 0, 8009) + mdns.encode_name("g.local.")),
        record("Den._googlecast._tcp.local.", mdns.TXT, b"\x0cfn=Den speak"),
    )

    assert mdns.parse(msg) == [
        ("ipad.local.", mdns.A, "192.0.2.12"),
        ("ipad.local.", mdns.AAAA, "fd12:3456:789a::12"),
        ("12.2.0.192.in-addr.arpa.", mdns.PTR, "ipad.local."),
        ("Den._googlecast._tcp.local.", mdns.SRV, "g.local."),
        ("Den._googlecast._tcp.local.", mdns.TXT, ["fn=Den speak"]),
    ]


def test_parse_follows_compression_pointers():
    # The PTR target points back at the "local." of the question name
    msg = struct.pack("!6H", 0, 0x8400, 1, 1, 0, 0) + mdns.encode_name("_x._tcp.local.") + struct.pack("!HH", 12, 1)
    msg += b"\xc0\x0c" + struct.pack("!HHIH", mdns.PTR, 1, 120, 6) + b"\x03box\xc0\x14"

    assert mdns.parse(msg) == [("_x._tcp.local.", mdns.PTR, "box.local.")]


def test_query_round_trips_through_parse_header():
    msg = mdns.query([("a.local.", mdns.PTR), ("b.local.", mdns.ANY)])

    assert struct.unpack("!6H", msg[:12]) == (0, 0, 2, 0, 0, 0)
    assert mdns.read_name(msg, 12) == ("a.local.", 21)


def test_clean_label():
    assert mdns.clean_label("06BBBE2CE704@Apple TV 4K") == "Apple TV 4K"
    assert mdns.clean_label("70-35-60-63.1 Apple TV 4K") == "Apple TV 4K"
    assert mdns.clean_label("Living\\032Room") == "Living Room"
    assert mdns.clean_label("fd37da3e-3444-5d9c-0f58-d50166360d4d") is None
    assert mdns.clean_label("2ecc3cf8e3d44f2b947cdb5d678245f0") is None


def test_ptr_address():
    assert mdns.ptr_address("12.2.0.192.in-addr.arpa.") == "192.0.2.12"
    reverse = socket.inet_pton(socket.AF_INET6, "fd12:3456:789a::1").hex()[::-1]
    assert mdns.ptr_address(".".join(reverse) + ".ip6.arpa.") == "fd12:3456:789a::1"
    assert mdns.ptr_address("nope.in-addr.arpa.") is None


def test_names_joins_hosts_and_services():
    found = mdns.names(
        [
            ("12.2.0.192.in-addr.arpa.", mdns.PTR, "ipad.local."),
            ("g.local.", mdns.A, "192.0.2.20"),
            ("abc._googlecast._tcp.local.", mdns.SRV, "g.local."),
            ("abc._googlecast._tcp.local.", mdns.TXT, ["id=1", "fn=Kitchen"]),
            ("lonely.local.", mdns.SRV, "nowhere.local."),
        ],
    )

    assert found == {
        "192.0.2.12": {"host": "ipad.local.", "services": set(), "types": set()},
        "192.0.2.20": {"host": "g.local.", "services": {"abc", "Kitchen"}, "types": {"_googlecast._tcp"}},
    }
