import json

import pytest

from nabe import config, store

MAC = "aa:bb:cc:00:00:01"


@pytest.fixture(autouse=True)
def empty_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_FILE", tmp_path / "devices.json")
    monkeypatch.setattr(config, "LAYOUT_FILE", tmp_path / "layout.json")
    monkeypatch.setattr(store, "devices", {})
    monkeypatch.setattr(store, "layout", {"groups": []})
    monkeypatch.setattr(store, "reverse_dns", {"192.0.2.15": "printer.home"}.get)


def test_update_merges_by_mac_and_saves():
    store.update(
        [
            {"dst": "192.0.2.12", "lladdr": "AA:BB:CC:00:00:01", "state": ["REACHABLE"]},
            {"dst": "fe80::1", "lladdr": MAC, "state": ["STALE"], "router": None},
            {"dst": "192.0.2.13", "state": ["INCOMPLETE"]},
            {"dst": "192.0.2.14", "lladdr": "aa:bb:cc:00:00:02", "state": ["FAILED"]},
        ],
        now=1000,
    )

    assert list(store.devices) == [MAC]
    assert store.devices[MAC]["router"] is True
    assert set(store.devices[MAC]["addresses"]) == {"192.0.2.12", "fe80::1"}
    assert json.loads(config.STATE_FILE.read_text()) == store.devices


def test_stale_entries_dont_count_as_seen_and_old_ones_expire():
    store.update([{"dst": "192.0.2.12", "lladdr": MAC, "state": ["REACHABLE"]}], now=1000)
    store.update([{"dst": "192.0.2.12", "lladdr": MAC, "state": ["STALE"]}], now=2000)
    assert store.devices[MAC]["addresses"]["192.0.2.12"]["last_seen"] == 1000

    store.update([], now=1000 + config.RETENTION_DAYS * 86400 + 1)
    assert store.devices == {}


def test_snapshot():
    store.update(
        [
            {"dst": "fd12:3456:789a::12", "lladdr": MAC, "state": ["REACHABLE"]},
            {"dst": "192.0.2.12", "lladdr": MAC, "state": ["REACHABLE"]},
        ],
        now=1000,
    )
    store.set_names(
        {"192.0.2.12": {"host": "ipad.local.", "services": {"iPad"}, "types": {"_ssh._tcp"}}},
        {"192.0.2.12": "IPAD"},
        {"192.0.2.12": MAC},
        None,
    )
    store.save_layout(
        {"groups": [{"id": "g", "name": " Tablets ", "members": [MAC.upper()]}, {"id": "x", "members": []}]},
    )

    snap = store.snapshot(now=1010)
    dev = snap["devices"][0]
    assert snap["groups"] == [{"id": "g", "name": "Tablets", "members": [MAC]}]
    assert (dev["name"], dev["host"], dev["services"], dev["online"]) == ("ipad", "ipad", ["iPad"], True)
    assert dev["netbios"] == "IPAD"
    assert (dev["seen_via"], dev["service_types"]) == (["NetBIOS", "mDNS"], ["_ssh._tcp"])
    assert dev["random_mac"] is True
    assert [a["kind"] for a in dev["addresses"]] == ["ipv4", "ula"]
    assert store.snapshot(now=1000 + config.ONLINE_FOR + 1)["devices"][0]["online"] is False


def test_readable_host_prefers_a_service_over_an_opaque_id():
    assert store.readable_host("2ecc3cf8e3d44f2b947cdb5d678245f0", ["Home"]) == "Home"
    assert store.readable_host("Apple-TV-4K", ["Apple TV 4K"]) == "Apple-TV-4K"
    assert store.readable_host(None, []) is None


def test_names_expire_like_addresses_and_the_latest_host_wins():
    store.update([{"dst": "192.0.2.12", "lladdr": MAC, "state": ["REACHABLE"]}], now=1000)
    by_addr = store.macs_by_address()
    store.set_names(
        {"192.0.2.12": {"host": "old.local.", "services": {"Old"}, "types": set()}},
        {},
        by_addr,
        None,
        1000,
    )
    store.set_names(
        {"192.0.2.12": {"host": "new.local.", "services": {"New"}, "types": set()}},
        {},
        by_addr,
        None,
        2000,
    )

    dev = store.snapshot(now=2010)["devices"][0]
    assert (dev["host"], dev["services"]) == ("new", ["New", "Old"])

    # The address keeps being confirmed, "old" and "Old" are past the retention period
    store.update(
        [{"dst": "192.0.2.12", "lladdr": MAC, "state": ["REACHABLE"]}],
        now=1500 + config.RETENTION_DAYS * 86400,
    )
    dev = store.snapshot()["devices"][0]
    assert (dev["host"], dev["services"], dev["seen_via"]) == ("new", ["New"], ["mDNS"])


def test_load_reads_both_files():
    config.STATE_FILE.write_text(json.dumps({MAC: {"router": False, "addresses": {}, "names": {"host:ipad": 1}}}))
    config.LAYOUT_FILE.write_text(json.dumps({"groups": [{"id": "g", "name": "", "members": [MAC]}]}))

    store.load()

    assert store.devices[MAC]["names"] == {"host:ipad": 1}
    assert store.layout["groups"][0]["id"] == "g"


def test_netbios_names_devices_without_mdns_and_unnamed_sort_last():
    other = "aa:bb:cc:00:00:02"
    third = "aa:bb:cc:00:00:03"
    store.update(
        [
            {"dst": "192.0.2.12", "lladdr": MAC, "state": ["REACHABLE"]},
            {"dst": "192.0.2.13", "lladdr": other, "state": ["REACHABLE"]},
            {"dst": "192.0.2.14", "lladdr": third, "state": ["REACHABLE"]},
        ],
        now=1000,
    )
    store.set_names(
        {"192.0.2.13": {"host": "zebra.local.", "services": set(), "types": set()}},
        {"192.0.2.14": "ALPHA-PC"},
        store.macs_by_address(),
        None,
    )

    assert [d["name"] for d in store.snapshot(now=1010)["devices"]] == ["ALPHA-PC", "zebra", None]


def test_reverse_dns_names_and_tags_the_device():
    store.update([{"dst": "192.0.2.15", "lladdr": MAC, "state": ["REACHABLE"]}], now=1000)
    store.set_reverse_dns(store.macs_by_address())

    dev = store.snapshot(now=1010)["devices"][0]
    assert (dev["name"], dev["seen_via"]) == ("printer.home", ["rDNS"])
