# Changelog

All notable changes to Nabe. Versions follow [Semantic Versioning](https://semver.org); each is published as
`ghcr.io/godric/nabe:<version>`.

## Unreleased

### Added

- When each address was last seen (5m, 4h, 3d), at the right of its line. The copy button now sits right after the
  value it copies, and columns are a little wider so a full IPv6 address stays on one line.

### Changed

- Nothing seen is hidden or renamed any more: every mDNS, NetBIOS and reverse DNS name still kept (not only the
  latest), service names as announced (IDs included, and Google's friendly name next to its instance name), and the
  names containers announce on the host's own addresses.
- mDNS service types are listed as announced on a "Types" line, each in a box with its own copy button
  (`_airplay._tcp`, `_sleep-proxy._udp`), instead of as tags with friendly names (AirPlay, ...) that left some types
  out. Tags are only for how a device answered (mDNS, NetBIOS, rDNS).
- Copy buttons are always shown, faint until hovered, instead of only when their line is hovered.
- A device's MAC line no longer says "online", which the green dot already shows; offline ones still say when they
  were last seen.

### Fixed

- Address labels (IPv4, IPv6, ...) sat slightly higher than the values next to them.

## 0.1.1 - 2026-11-21

### Added

- A copy button after each MAC, address and name, shown when its line is hovered.

### Changed

- Cards are dragged into groups by a grip at the end of their title row, so the rest of the card selects text
  normally.

### Fixed

- Long values (mDNS names, on narrow screens) wrap instead of pushing out of the card.
- Selecting a MAC no longer takes the online/last seen text with it.
- In Safari, a double-click in the blank after a value or a triple-click on a card's last line no longer selects
  into the next group.
- Links with a query string (`/?x=1`) returned 404.

## 0.1.0 - 2026-11-21

First release.

- Devices on the LAN by MAC, with every IPv4, global IPv6, ULA and link-local address seen for them, from the host's
  neighbor table and regular probes (IPv6 all-nodes ping, IPv4 sweep).
- Names from mDNS, NetBIOS and reverse DNS, the protocols each device answered and the services it announces.
- Devices grouped by dragging them together, groups renamed in the page.
- Addresses, names and services kept until unseen for 7 days.
- Scan now, light/dark/auto theme, home screen icons and web manifest.
- Multi-arch image (amd64, arm64) on GHCR.
