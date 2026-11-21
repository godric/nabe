import os
from pathlib import Path

IFACE = os.getenv("IFACE", "eth0")
LISTEN_HOST = os.getenv("LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8097"))

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
# Pings, mDNS and NetBIOS rounds; with 0 they only run at start and when asked from the page
PROBE_INTERVAL = int(os.getenv("PROBE_INTERVAL", "300"))
RETENTION_DAYS = float(os.getenv("RETENTION_DAYS", "7"))
# Probing re-confirms whoever answers, so a device counts as online until a probe round misses it
ONLINE_FOR = (PROBE_INTERVAL or 3600) + 2 * POLL_INTERVAL

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "devices.json"
LAYOUT_FILE = DATA_DIR / "layout.json"
