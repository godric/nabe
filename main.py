#!/usr/bin/env python

import logging
import threading
import time
from http.server import ThreadingHTTPServer

from nabe import config, mdns, nbns, store, system
from nabe.server import Handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger("main")


def poll():
    mac, addrs, _ = system.own_addresses()
    store.update(system.neighbors() + [{"dst": a, "lladdr": mac, "state": ["SELF"]} for a in addrs])


def probe():
    system.probe()
    poll()
    by_addr = store.macs_by_address()
    store.set_names(mdns.scan(list(by_addr)), nbns.scan(list(by_addr)), by_addr, system.own_addresses()[0])
    store.set_reverse_dns(by_addr)


def run(fn):
    try:
        fn()
    except Exception:
        LOGGER.exception("%s failed, keeping what was there", fn.__name__)


def poll_rounds():
    while True:
        run(poll)
        time.sleep(config.POLL_INTERVAL)


def probe_rounds():
    """A probe round every PROBE_INTERVAL, or right away when the page asks for one (only then if it's 0)."""
    while True:
        store.probe_status["running"] = True
        run(probe)
        store.probe_status.update(running=False, last=time.time())
        store.probe_requested.wait(config.PROBE_INTERVAL or None)
        store.probe_requested.clear()


if __name__ == "__main__":
    store.load()
    threading.Thread(target=probe_rounds, daemon=True).start()
    threading.Thread(target=poll_rounds, daemon=True).start()
    LOGGER.info("Listening on %s:%d, watching %s", config.LISTEN_HOST, config.LISTEN_PORT, config.IFACE)
    ThreadingHTTPServer((config.LISTEN_HOST, config.LISTEN_PORT), Handler).serve_forever()
