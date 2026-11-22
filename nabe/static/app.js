const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const ago = t => { const s = Date.now()/1000 - t; return s < 90 ? "now" : s < 5400 ? Math.round(s/60)+" min ago"
  : s < 172800 ? Math.round(s/3600)+" h ago" : Math.round(s/86400)+" d ago"; };
// The same, short, for the column after each address
const agoShort = t => ago(t).replace(/ (min|h|d) ago$/, (_, u) => u[0]);
const KIND = {global: "IPv6", ula: "ULA", "link-local": "link", ipv4: "IPv4"};
// Six dots: the handle cards are dragged by, so the rest of the card stays selectable
const GRIP = '<svg viewBox="0 0 10 16" width="10" height="16" aria-hidden="true">' +
  [3, 8, 13].flatMap(y => [3, 7].map(x => `<circle cx="${x}" cy="${y}" r="1.4"/>`)).join("") + "</svg>";
// A small button right after each MAC, address and name that copies it
// Power symbol: the Wake button on offline cards
const WAKE_ICON = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" ' +
  'stroke-width="1.6" stroke-linecap="round"><path d="M4.8 4a5.3 5.3 0 1 0 6.4 0"/><path d="M8 1.8v5.4"/></svg>';
const COPY_ICON = '<svg viewBox="0.5 0.5 15 15" width="12" height="12" aria-hidden="true" fill="none" stroke="currentColor" ' +
  'stroke-width="1.6"><rect x="5.5" y="5.5" width="8" height="8" rx="1.8"/><path d="M10.5 3.5v-.2A1.8 1.8 0 0 0 8.7 1.5H3.3A1.8 1.8 0 0 0 1.5 3.3v5.4a1.8 1.8 0 0 0 1.8 1.8h.2"/></svg>';
const copyButton = text => `<span class="copy-col"><button type="button" class="copy" data-copy="${esc(text)}" title="Copy" ` +
  `aria-label="Copy ${esc(text)}">${COPY_ICON}</button></span>`;
const newId = () => crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
let devices = [], groups = [], probe = {}, probeInterval = 0, busy = false;

// Saved groups, plus a group of its own for every device not in one
function allGroups() {
  const byMac = Object.fromEntries(devices.map(d => [d.mac, d]));
  const saved = groups.map(g => ({...g, devs: g.members.map(m => byMac[m]).filter(Boolean)})).filter(g => g.devs.length);
  const taken = new Set(saved.flatMap(g => g.members));
  const alone = devices.filter(d => !taken.has(d.mac)).map(d => ({id: "mac:" + d.mac, name: "", members: [d.mac], devs: [d]}));
  // Alphabetical, unnamed ones last
  return [...saved, ...alone].map(g => ({...g, title: g.name || g.devs.find(d => d.name)?.name || ""}))
    .sort((a, b) => !a.title - !b.title || a.title.localeCompare(b.title, undefined, {sensitivity: "base"}));
}

function cardHtml(d) {
  return `<div class="card ${d.online ? "on" : ""}" data-mac="${esc(d.mac)}">
    <div class="top"><span class="dot"></span><span class="name ${d.name ? "" : "unnamed"}">${esc(d.name || "Unknown")}</span>
      ${d.self ? '<span class="tag">this host</span>' : ""}${d.router ? '<span class="tag">router</span>' : ""}
      ${d.random_mac ? '<span class="tag" title="Locally administered (private) MAC">private MAC</span>' : ""}
      ${d.online ? "" : `<button type="button" class="wake" data-wake="${esc(d.mac)}"
        title="Wake: send a Wake-on-LAN magic packet to ${esc(d.mac)}" aria-label="Wake ${esc(d.mac)}">${WAKE_ICON}</button>`}
      <span class="handle" draggable="true" title="Drag into another group">${GRIP}</span></div>
    <div class="mac"><span class="value">${esc(d.mac)}</span>${copyButton(d.mac)}${
      // The dot says whether it's online; when it isn't, since when
      d.online ? "" : ` · ${ago(d.last_seen)}`}</div>
    ${d.seen_via.length ? `<div class="tags">${
      d.seen_via.map(p => `<span class="tag proto" title="Answered over ${esc(p)}">${esc(p)}</span>`).join("")}</div>` : ""}
    <ul>${d.addresses.map(a => `<li class="${Date.now()/1000 - a.last_seen > 600 ? "old" : ""}">
      <span class="${a.kind}">${KIND[a.kind]}</span>
      <span class="addr value" title="${esc(a.state)}">${esc(a.address)}</span>${copyButton(a.address)}
      <span class="seen" title="Last seen ${esc(new Date(a.last_seen * 1000).toLocaleString())}">${agoShort(a.last_seen)}</span></li>`).join("")}
    ${[...d.hosts.map(n => ["mDNS", n + ".local"]), ...d.netbios_names.map(n => ["NetBIOS", n]),
      ...d.rdns_names.map(n => ["rDNS", n]),
      // Names of the services it announces over mDNS
      ...d.services.map(n => ["Service", n])]
      .map(([label, n]) => `<li><span>${label}</span><span class="addr value">${esc(n)}</span>${copyButton(n)}<span class="seen"></span></li>`).join("")}
    ${d.service_types.length ? `<li><span>Types</span><span class="addr value">${
      // The types of the services it announces, as announced, each in a box with its own copy button
      d.service_types.map(t => `<span class="type">${esc(t)}${copyButton(t)}</span>`).join(" ")}</span><span class="seen"></span></li>` : ""}</ul>
    <div class="card-end">&#8203;</div>
  </div>`;
}

function render() {
  if (busy) return;
  const q = document.getElementById("filter").value.trim().toLowerCase();
  const match = d => [d.name, ...d.hosts, ...d.netbios_names, ...d.rdns_names, d.mac, ...d.services, ...d.seen_via,
    ...d.service_types, ...d.addresses.map(a => a.address)].join(" ").toLowerCase().includes(q);
  const shown = allGroups().filter(g => !q || g.title.toLowerCase().includes(q) || g.devs.some(match));
  document.getElementById("summary").textContent = `${devices.filter(d => d.online).length} online, ${devices.length} seen`;
  renderScan();
  document.getElementById("list").innerHTML = shown.map(g => `
    <section class="group ${g.devs.some(d => d.online) ? "on" : ""}" data-group="${esc(g.id)}">
      <div class="top"><span class="dot"></span>
        <span class="name ${g.title ? "" : "unnamed"}" data-rename="${esc(g.id)}" title="Click to rename">${esc(g.title || "Unknown")}</span></div>
      <div class="stack">${g.devs.map(cardHtml).join("")}</div>
    </section>`).join("");
}

function renderScan() {
  const every = probeInterval ? ` · every ${Math.round(probeInterval / 60)} min` : "";
  document.getElementById("scan").textContent =
    probe.running ? "Scanning…" : probe.last ? `Last scan ${ago(probe.last)}${every}` : "";
  document.getElementById("scan-now").disabled = !!probe.running;
}

async function save() {
  await fetch("api/layout", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify({groups})});
  await refresh();
}

async function refresh() {
  try {
    const r = await (await fetch("api/devices")).json();
    devices = r.devices;
    probe = r.probe;
    probeInterval = r.probe_interval;
    if (!busy) groups = r.groups;
    render();
  } catch (e) {}
}

// A device's own group only gets saved once it's renamed or joined
function savedGroup(id) {
  let g = groups.find(g => g.id === id);
  if (!g && id.startsWith("mac:")) groups.push(g = {id: newId(), name: "", members: [id.slice(4)]});
  return g;
}

// Renaming a group: Enter or leaving the field saves, Escape cancels, empty goes back to the device's name
document.addEventListener("click", e => {
  const el = e.target.closest("[data-rename]");
  if (!el || busy) return;
  const id = el.dataset.rename;
  const input = document.createElement("input");
  input.className = "name-edit";
  input.value = groups.find(g => g.id === id)?.name || "";
  input.placeholder = el.textContent;
  el.replaceWith(input);
  busy = true;
  input.focus();
  let done = false;
  const finish = async keep => {
    if (done) return;
    done = true;
    busy = false;
    const v = input.value.trim();
    if (keep && v !== (groups.find(g => g.id === id)?.name || "")) {
      savedGroup(id).name = v;
      await save();
    } else render();
  };
  input.addEventListener("keydown", e => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
  input.addEventListener("blur", () => finish(true));
});

// Moving devices between groups by drag and drop
let dragged = null;
const clearDrop = () => document.querySelectorAll(".drop").forEach(el => el.classList.remove("drop"));
const target = e => e.target.closest(".group") || e.target.closest("main");
document.addEventListener("dragstart", e => {
  const card = e.target.closest(".handle")?.closest(".card");
  if (!card || busy) return;
  dragged = card.dataset.mac;
  card.classList.add("dragging");
  e.dataTransfer.setData("text/plain", dragged);
  e.dataTransfer.effectAllowed = "move";
  // Drag the whole card, held where the handle was grabbed
  const box = card.getBoundingClientRect();
  e.dataTransfer.setDragImage(card, e.clientX - box.left, e.clientY - box.top);
});
document.addEventListener("dragend", () => { dragged = null; clearDrop(); render(); });
document.addEventListener("dragover", e => {
  const t = dragged && target(e);
  if (!t) return;
  e.preventDefault();
  clearDrop();
  if (t.classList.contains("group")) t.classList.add("drop");
});
document.addEventListener("drop", async e => {
  const t = dragged && target(e);
  if (!t) return;
  e.preventDefault();
  const mac = dragged;
  dragged = null;
  clearDrop();
  const id = t.classList.contains("group") ? t.dataset.group : null;
  const from = allGroups().find(g => g.members.includes(mac));
  if (id === from?.id || (!id && from?.members.length === 1)) return render();
  const into = id && savedGroup(id);
  groups.forEach(g => g.members = g.members.filter(m => m !== mac));
  if (into) into.members.push(mac);
  groups = groups.filter(g => g.members.length);
  await save();
});

// Copy buttons
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  // Pages served over plain HTTP have no clipboard API
  const area = Object.assign(document.createElement("textarea"), {value: text});
  document.body.append(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  return ok;
}
// A small bubble above a button, saying what it did
function bubble(el, text) {
  const box = el.getBoundingClientRect();
  const toast = Object.assign(document.createElement("div"), {className: "toast", textContent: text});
  toast.style.left = `${box.left + box.width / 2}px`;
  toast.style.top = `${box.top}px`;
  document.body.append(toast);
  setTimeout(() => toast.remove(), 1000);
}
document.addEventListener("click", async e => {
  const el = e.target.closest(".copy");
  if (el && await copyText(el.dataset.copy)) bubble(el, "Copied");
});

// Wake buttons, on offline cards: send the magic packet, nothing more; the card turns online if the device wakes
document.addEventListener("click", async e => {
  const el = e.target.closest("[data-wake]");
  if (!el || el.disabled) return;
  el.disabled = true;
  const r = await fetch("api/wake", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({mac: el.dataset.wake})}).catch(() => null);
  bubble(el, r?.ok ? "Sent" : "Failed");
  el.disabled = false;
});

// Scan now, then refresh quickly until the round is over
document.getElementById("scan-now").addEventListener("click", async () => {
  probe = {...probe, running: true};
  renderScan();
  await fetch("api/probe", {method: "POST"});
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000));
    await refresh();
    if (!probe.running) break;
  }
});

// Theme: auto follows the system, light and dark stick (per browser)
function setTheme(theme) {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  try { theme === "auto" ? localStorage.removeItem("theme") : localStorage.setItem("theme", theme); } catch (e) {}
  document.querySelectorAll(".theme button").forEach(b => b.setAttribute("aria-pressed", b.dataset.theme === theme));
}
document.querySelectorAll(".theme button").forEach(b => b.addEventListener("click", () => setTheme(b.dataset.theme)));
setTheme(document.documentElement.dataset.theme || "auto");

document.getElementById("filter").addEventListener("input", render);
refresh(); setInterval(refresh, 15000);
