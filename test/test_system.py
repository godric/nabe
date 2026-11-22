import pytest

from nabe import system

SOURCE = bytes.fromhex("020000000001")


def test_magic_frame():
    frame = system.magic_frame(system.mac_bytes("AA:BB:CC:00:00:01"), SOURCE)

    assert frame[:6] == b"\xff" * 6  # To everyone on the link
    assert frame[6:12] == SOURCE
    assert frame[12:14] == b"\x08\x42"
    assert frame[14:] == b"\xff" * 6 + bytes.fromhex("aabbcc000001") * 16


@pytest.mark.parametrize("mac", ["aa:bb:cc:00:00", "aa:bb:cc:00:00:01:02", "aabbcc000001", "zz:bb:cc:00:00:01", 42])
def test_mac_bytes_needs_a_mac(mac):
    with pytest.raises(ValueError, match=str(mac)):
        system.mac_bytes(mac)
