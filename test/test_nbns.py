import struct

from nabe import nbns


def response(transaction_id, *entries):
    rdata = bytes([len(entries)]) + b"".join(
        name.ljust(15).encode() + bytes([suffix]) + struct.pack("!H", flags) for name, suffix, flags in entries
    )
    header = struct.pack("!6H", transaction_id, 0x8400, 0, 1, 0, 0)
    return header + nbns.WILDCARD + struct.pack("!HHIH", nbns.NBSTAT, 1, 0, len(rdata)) + rdata


def test_query_encodes_the_wildcard_name():
    msg = nbns.query(7)

    assert struct.unpack("!6H", msg[:12]) == (7, 0, 1, 0, 0, 0)
    assert msg[12:46] == b"\x20CK" + b"A" * 30 + b"\0"
    assert msg[-4:] == struct.pack("!HH", nbns.NBSTAT, 1)


def test_parse_status_picks_the_unique_host_name():
    msg = response(
        7,
        ("WORKGROUP", 0x00, nbns.GROUP),  # the workgroup, a group name
        ("OFFICE-PC", 0x03, 0),  # messenger service
        ("OFFICE-PC", 0x20, 0),
    )

    assert nbns.parse_status(msg) == "OFFICE-PC"


def test_parse_status_without_a_host_name():
    assert nbns.parse_status(response(7, ("WORKGROUP", 0x00, nbns.GROUP))) is None
    assert nbns.parse_status(response(7)) is None
