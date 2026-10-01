import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getNetwork, addNetDevice, editNetDevice, deleteNetDevice, startScan, getScan, getSystem, getServer, getServerHistory, getStorage, listFiles, newFolder, renameFile, deleteFile, emptyTrash, downloadUrl, uploadFile, getPrinters, createPrinter, updatePrinter, reorderPrinters, deletePrinter, testPrinter } from "./api";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Cpu,
  ArrowDownToLine, ArrowUpFromLine, Box, Camera, Clock, CloudUpload, Globe, Monitor, Radar, Router, Search, Smartphone, Database, Download, File as FileIcon, Folder, FolderPlus, GripVertical, HeartPulse, HardDrive, LayoutDashboard, Loader2, Menu, Network, Package,
  Pencil, Plug, Plus, Printer, Server, Settings, ShieldCheck, Thermometer, Trash2, Wifi, X, Zap
} from "lucide-react";
import "./index.css";

const APP_VERSION = "v0.3";

// Shown only when the backend's /api/printers can't be reached.
const DEMO_PRINTERS = [
  { id: "demo-1", name: "Printer 01", model: "Klipper", state: "printing", job: "TTRC_RaceWing_v4.gcode", progress: 72, eta: "1h 24m", nozzle: 214, bed: 58, layer: "118 / 164" },
  { id: "demo-2", name: "Printer 02", model: "OctoPrint", state: "idle", job: null, progress: 0, eta: "—", nozzle: 31, bed: 29, layer: "—" },
  { id: "demo-3", name: "Printer 03", model: "Klipper", state: "complete", job: "NASCAR_Display_Base.gcode", progress: 100, eta: "Complete", nozzle: 29, bed: 27, layer: "142 / 142" },
  { id: "demo-4", name: "Printer 04", model: "Klipper", state: "offline", job: null, progress: 0, eta: "—", nozzle: 0, bed: 0, layer: "—" },
];

const PAGE_TITLES = {
  dashboard: "Operations Dashboard",
  printers: "Print Farm",
  server: "Server",
  storage: "Storage",
  network: "Network",
  services: "Services",
  settings: "Settings",
};

// Keys match the backend's printer_type values.
const PRINTER_TYPES = {
  moonraker: { label: "Klipper (Moonraker)", short: "Klipper", defaultPort: 7125 },
  octoprint: { label: "OctoPrint", short: "OctoPrint", defaultPort: 80 },
  bambu: { label: "Bambu Lab", short: "Bambu Lab", defaultPort: 8883 },
};
// Types whose secret (API key / access code) the backend keeps if the field is left blank on edit
const SECRET_LABEL = { octoprint: "API key", bambu: "Access code" };

function formatEta(seconds) {
  const s = Number(seconds) || 0;
  if (s <= 0) return "—";
  // Round to whole minutes first so 30h 59.6m shows as 31h 0m, not 30h 60m
  const total = Math.round(s / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

// The backend may name fields slightly differently; map whatever comes back
// onto the shape the cards expect.
function normalizeState(raw, online) {
  const s = String(raw ?? "").toLowerCase();
  if (s === "printing") return "printing";
  if (s === "paused" || s === "pausing") return "paused";
  if (["complete", "completed", "finished", "done"].includes(s)) return "complete";
  if (["offline", "error", "disconnected", "shutdown"].includes(s)) return "offline";
  if (online === false) return "offline";
  return "idle";
}

function normalizePrinter(p) {
  const type = String(p.printer_type ?? p.type ?? "").toLowerCase();
  const progress = Number(p.progress ?? 0) || 0;
  return {
    id: p.id,
    name: p.name || `Printer ${p.id}`,
    type,
    model: p.model ?? PRINTER_TYPES[type]?.short ?? (type || "Printer"),
    address: p.base_url ?? null,
    serial: p.serial ?? null,
    state: normalizeState(p.state, p.connected),
    job: p.job ?? null,
    progress: Math.round(progress),
    eta: p.state === "complete" ? "Complete" : formatEta(p.eta_seconds),
    nozzle: p.nozzle ?? 0,
    nozzleTarget: p.nozzle_target ?? 0,
    bed: p.bed ?? 0,
    bedTarget: p.bed_target ?? 0,
    firmware: p.firmware ?? null,
    error: p.error ?? null,
  };
}

const DOT_TONES = {
  good: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.55)]",
  warn: "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,.45)]",
  bad: "bg-red-400 shadow-[0_0_10px_rgba(248,113,113,.45)]",
  off: "bg-slate-600",
};
function StatusDot({ good = true, tone }) {
  return <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${DOT_TONES[tone ?? (good ? "good" : "bad")]}`} />;
}

// Alerts are worked out from data the dashboard already has; "bad" sorts first.
function buildAlerts({ apiError, usingDemo, printerError, printers, system }) {
  const list = [];
  if (apiError) list.push({ tone: "bad", text: "Can't reach the dashboard backend" });
  if (usingDemo) list.push({ tone: "bad", text: `Printer status unavailable (${printerError})` });
  if (!usingDemo) for (const p of printers) if (p.state === "offline") list.push({ tone: "warn", text: `${p.name} is offline` });
  if (system && !apiError) {
    const t = system.temperature_c;
    if (t != null && t >= 85) list.push({ tone: "bad", text: `Server is overheating (${t}°C)` });
    else if (t != null && t >= 75) list.push({ tone: "warn", text: `Server is running hot (${t}°C)` });
    if (system.storage_percent >= 90) list.push({ tone: system.storage_percent >= 97 ? "bad" : "warn", text: `Main drive is ${Math.round(system.storage_percent)}% full` });
    if (system.memory_percent >= 92) list.push({ tone: "warn", text: `Memory is ${Math.round(system.memory_percent)}% used` });
    if (system.database && !system.database.ok) list.push({ tone: "bad", text: "Printer database error" });
    if (system.network?.internet_up === false) list.push({ tone: "bad", text: "Internet is down" });
    for (const name of system.network?.offline_devices ?? []) list.push({ tone: "warn", text: `${name} is not responding` });
  }
  return list.sort((a, b) => (a.tone === "bad" ? 0 : 1) - (b.tone === "bad" ? 0 : 1));
}

function alertSummary(alerts) {
  if (!alerts.length) return { tone: "good", text: "All systems nominal" };
  const bad = alerts.some(a => a.tone === "bad");
  return { tone: bad ? "bad" : "warn", text: alerts.length === 1 ? alerts[0].text : `${alerts.length} alerts` };
}

// "Updated 4s ago", ticking on its own so the whole dashboard doesn't re-render every second
function UpdatedAgo({ at }) {
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t); }, []);
  if (!at) return <>Waiting for data</>;
  const s = Math.max(0, Math.round((Date.now() - at) / 1000));
  return <>Updated {s < 5 ? "just now" : s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`}</>;
}

function Metric({ icon: Icon, label, value, sub, progress }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500">
        <Icon size={15} /> {label}
      </div>
      <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
      {progress !== undefined && (
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/6">
          <div className="h-full rounded-full bg-violet-500" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}

function PrinterCard({ printer, onSelect }) {
  const styles = {
    printing: ["PRINTING", "text-violet-300", "border-violet-500/30", "bg-violet-500/8"],
    paused: ["PAUSED", "text-amber-300", "border-amber-500/25", "bg-amber-500/6"],
    idle: ["IDLE", "text-sky-300", "border-sky-500/20", "bg-sky-500/6"],
    complete: ["COMPLETE", "text-emerald-300", "border-emerald-500/20", "bg-emerald-500/6"],
    offline: ["OFFLINE", "text-red-300", "border-red-500/20", "bg-red-500/6"],
  };
  const [label, text, border, bg] = styles[printer.state] ?? styles.idle;

  return (
    <button onClick={() => onSelect(printer)} className={`group min-w-0 text-left rounded-2xl border ${border} ${bg} p-4 transition hover:-translate-y-0.5 hover:border-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400`}>
      <div className="truncate text-sm font-semibold text-white" title={printer.name}>{printer.name}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="truncate text-xs text-slate-500">{PRINTER_TYPES[printer.type]?.short ?? printer.model}</span>
        <span className={`flex shrink-0 items-center gap-1.5 text-[9px] font-bold tracking-widest ${text}`}>
          <StatusDot good={printer.state !== "offline"} /> {label}
        </span>
      </div>

      <div className="mt-4">
        <div className="flex justify-between text-xs">
          <span className="truncate pr-3 text-slate-400" title={printer.job || undefined}>{printer.job || "No active job"}</span>
          <span className="font-semibold text-white">{printer.progress}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/6">
          <div className={`h-full rounded-full ${printer.state === "printing" ? "bg-violet-500" : "bg-slate-600"}`} style={{ width: `${printer.progress}%` }} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-1.5 whitespace-nowrap border-t border-white/6 pt-3 text-xs">
        <div><div className="text-slate-600">Nozzle</div><div className="mt-1 font-medium text-slate-300">{printer.nozzle ? `${Math.round(printer.nozzle)}°C` : "—"}</div></div>
        <div><div className="text-slate-600">Bed</div><div className="mt-1 font-medium text-slate-300">{printer.bed ? `${Math.round(printer.bed)}°C` : "—"}</div></div>
        <div><div className="text-slate-600">ETA</div><div className="mt-1 font-medium text-slate-300">{printer.eta}</div></div>
      </div>
      <div className="mt-3 flex items-center justify-end gap-1 text-xs text-slate-600 group-hover:text-slate-300">
        Details <ChevronRight size={14} />
      </div>
    </button>
  );
}

function Sidebar({ page, setPage, open, setOpen, usingDemo, summary }) {
  const items = [
    ["Dashboard", LayoutDashboard, "dashboard"],
    ["Print Farm", Printer, "printers"],
    ["Server", Server, "server"],
    ["Storage", HardDrive, "storage"],
    ["Network", Network, "network"],
    ["Services", Activity, "services"],
    ["Settings", Settings, "settings"],
  ];
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/7 bg-[#0b0e15] transition-transform lg:static lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-20 items-center justify-between px-5">
          <div>
            <div className="text-lg font-black tracking-tight text-white">TEAM TACTICAL <span className="text-violet-400">RC</span></div>
            <div className="mt-0.5 text-[9px] font-bold uppercase tracking-[.28em] text-slate-600">Home Lab / Print Farm</div>
          </div>
          <button className="lg:hidden text-slate-500" onClick={() => setOpen(false)} aria-label="Close menu"><X size={20} /></button>
        </div>
        <nav className="flex-1 px-3 py-3">
          {items.map(([label, Icon, key]) => (
            <button key={key} onClick={() => { setPage(key); setOpen(false); }} className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${page === key ? "bg-violet-500/12 text-white" : "text-slate-500 hover:bg-white/4 hover:text-slate-300"}`}>
              <Icon size={18} className={page === key ? "text-violet-400" : ""} />
              {label}
            </button>
          ))}
        </nav>
        <div className="m-3 rounded-xl border border-white/6 bg-white/[.025] p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300"><StatusDot tone={summary.tone} /> <span className="truncate">{summary.text}</span></div>
          <div className="mt-2 text-[10px] text-slate-600">Dashboard {APP_VERSION}{usingDemo ? " • Demo printers" : " • Live data"}</div>
        </div>
      </aside>
    </>
  );
}

function useEscape(handler) {
  useEffect(() => {
    const onKey = e => { if (e.key === "Escape") handler(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handler]);
}

function DetailPanel({ printer, close, onRemoved, onEdit, isDemo }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState("");
  useEscape(close);

  const runTest = async () => {
    setTesting(true); setTestResult(null); setError("");
    try {
      const r = await testPrinter(printer.id);
      onRemoved();
      const ok = r?.ok ?? r?.success ?? r?.connected ?? true;
      setTestResult({ ok, message: r?.message || r?.detail || (ok ? "Printer responded." : "Printer did not respond.") });
    } catch (e) {
      setTestResult({ ok: false, message: e.message });
    } finally { setTesting(false); }
  };

  const remove = async () => {
    setRemoving(true); setError("");
    try { await deletePrinter(printer.id); onRemoved(); close(); }
    catch (e) { setError(e.message); setRemoving(false); setConfirmRemove(false); }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-white/10 bg-[#0d1018] p-6 shadow-2xl">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-violet-400">Printer detail</div>
          <h2 className="mt-1 text-xl font-semibold text-white">{printer.name}</h2>
          {printer.address && <div className="mt-1 text-xs text-slate-500">{printer.address}</div>}
        </div>
        <button onClick={close} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Close"><X size={20} /></button>
      </div>
      <div className="mt-8 rounded-2xl border border-white/8 bg-[#11151f] p-5">
        <div className="text-sm text-slate-400">Current job</div>
        <div className="mt-2 font-medium text-white">{printer.job || "No active print"}</div>
        <div className="mt-5 text-4xl font-bold text-white">{printer.progress}%</div>
        <div className="mt-2 h-2 rounded-full bg-white/6"><div className="h-full rounded-full bg-violet-500" style={{ width: `${printer.progress}%` }} /></div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <Metric icon={Thermometer} label="Nozzle" value={printer.nozzle ? `${printer.nozzle}°C` : "—"} sub={printer.nozzleTarget ? `Target ${printer.nozzleTarget}°C` : undefined} />
          <Metric icon={Thermometer} label="Bed" value={printer.bed ? `${printer.bed}°C` : "—"} sub={printer.bedTarget ? `Target ${printer.bedTarget}°C` : undefined} />
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-white/8 bg-[#11151f] p-5">
        <div className="text-xs uppercase tracking-wider text-slate-600">Connection</div>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-300"><StatusDot good={printer.state !== "offline"} /> {printer.state === "offline" ? "Offline" : "Connected"}</div>
        {printer.firmware && <div className="mt-3 text-xs text-slate-600">Firmware {printer.firmware}</div>}
        {printer.state === "offline" && printer.error && <div className="mt-3 break-words text-xs text-red-300/80">{printer.error}</div>}
        {printer.eta && printer.eta !== "—" && <div className="mt-3 text-xs text-slate-600">Time left {printer.eta}</div>}
      </div>

      {isDemo ? (
        <p className="mt-4 text-xs text-slate-600">This is a demo printer. Add a real printer from the Print Farm page to test or remove it.</p>
      ) : (
        <div className="mt-4 space-y-3">
          <button onClick={() => onEdit(printer)} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06]">
            <Pencil size={16} /> Edit printer
          </button>
          <button onClick={runTest} disabled={testing} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06] disabled:opacity-50">
            {testing ? <Loader2 size={16} className="animate-spin" /> : <Plug size={16} />} {testing ? "Testing…" : "Test connection"}
          </button>
          {testResult && (
            <div className={`rounded-xl border px-4 py-3 text-xs ${testResult.ok ? "border-emerald-500/20 bg-emerald-500/6 text-emerald-300" : "border-red-500/20 bg-red-500/6 text-red-300"}`}>{testResult.message}</div>
          )}
          {confirmRemove ? (
            <div className="rounded-xl border border-red-500/20 bg-red-500/6 p-4">
              <div className="text-sm text-red-200">Remove {printer.name} from the dashboard?</div>
              <div className="mt-3 flex gap-2">
                <button onClick={remove} disabled={removing} className="flex-1 rounded-lg bg-red-500/80 px-3 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50">{removing ? "Removing…" : "Remove printer"}</button>
                <button onClick={() => setConfirmRemove(false)} className="flex-1 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Keep it</button>
              </div>
            </div>
          ) : (
            <button onClick={() => setConfirmRemove(true)} className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm text-slate-500 hover:bg-red-500/6 hover:text-red-300">
              <Trash2 size={16} /> Remove printer
            </button>
          )}
          {error && <div className="text-xs text-red-300">{error}</div>}
        </div>
      )}
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-400">{label}</span>
      <div className="mt-1.5">{children}</div>
      {hint && <span className="mt-1 block text-[11px] text-slate-600">{hint}</span>}
    </label>
  );
}

// Printer cards on the Dashboard and Print Farm pages. Never more columns than
// printers (max 5 on wide screens), so a small farm gets larger, centered cards.
// Layout rules live in .printer-grid in index.css.
function PrinterGrid({ count, children }) {
  const cols = max => Math.max(1, Math.min(count, max));
  return <div className="printer-grid" style={{ "--cols-sm": cols(2), "--cols-lg": cols(3), "--cols-xl": cols(5) }}>{children}</div>;
}

const inputClass = "w-full rounded-lg border border-white/10 bg-[#0b0e15] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-violet-400 focus:outline-none";

// Split a saved base_url back into the form's host + port fields. A URL with no
// port (e.g. the Neptune's "http://192.168.1.155") shows 80/443 so saving it
// again doesn't swap in the connection type's default port.
function splitAddress(url) {
  const m = String(url ?? "").match(/^(https?|mqtts):\/\/([^/:]+)(?::(\d+))?/);
  if (!m) return { host: String(url ?? ""), port: "" };
  const [, scheme, host, port] = m;
  return { host: scheme === "https" ? `https://${host}` : host, port: port ?? { https: "443", mqtts: "8883" }[scheme] ?? "80" };
}

// `initial` pre-fills a new printer, e.g. one found by the Network page's scan
function PrinterFormModal({ printer, initial, onClose, onSaved }) {
  const editing = !!printer;
  const [form, setForm] = useState(() => editing
    ? { name: printer.name, type: PRINTER_TYPES[printer.type] ? printer.type : "moonraker", ...splitAddress(printer.address), api_key: "", serial: printer.serial ?? "" }
    : { name: initial?.name ?? "", type: initial?.type ?? "moonraker", host: initial?.host ?? "", port: initial?.port ? String(initial.port) : "", api_key: "", serial: initial?.serial ?? "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = key => e => setForm(f => ({ ...f, [key]: e.target.value }));
  const defaultPort = PRINTER_TYPES[form.type].defaultPort;
  useEscape(onClose);

  const save = async () => {
    if (!form.name.trim()) return setError("Give the printer a name.");
    if (!form.host.trim()) return setError("Enter the printer's IP address or hostname.");
    const bambu = form.type === "bambu";
    if (bambu && !form.serial.trim()) return setError("Enter the printer's serial number. It's on the printer screen under device info, or in Bambu Studio's Device tab.");
    const needsKey = SECRET_LABEL[form.type] && !(editing && printer.type === form.type);
    if (needsKey && !form.api_key.trim()) return setError(bambu
      ? "Enter the printer's access code. It's on the printer screen in the network (WLAN) settings."
      : "OctoPrint needs an API key. Find it in OctoPrint under Settings → Application Keys.");
    setSaving(true); setError("");
    // Backend wants printer_type + base_url, e.g. "http://192.168.1.50:7125".
    // Bambu printers are reached over MQTT, so their address is "mqtts://IP:8883".
    let base = form.host.trim().replace(/\/+$/, "");
    if (bambu) base = `mqtts://${base.replace(/^[a-z]+:\/\//, "")}`;
    const hostPart = base.replace(/^[a-z]+:\/\//, "");
    const hasPort = /:\d+$/.test(hostPart);
    if (!hasPort) base = `${base}:${Number(form.port) || defaultPort}`;
    const payload = {
      name: form.name.trim(),
      printer_type: form.type,
      base_url: base,
    };
    if (SECRET_LABEL[form.type] && form.api_key.trim()) payload.api_key = form.api_key.trim();
    if (bambu) payload.serial = form.serial.trim();
    try { await (editing ? updatePrinter(printer.id, payload) : createPrinter(payload)); onSaved(); onClose(); }
    catch (e) {
      const msg = typeof e.message === "string" && e.message !== "[object Object]" ? e.message : "The server rejected this printer. Check the uvicorn terminal for details.";
      setError(msg);
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="printer-form-title" className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0d1018] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 id="printer-form-title" className="text-lg font-semibold text-white">{editing ? "Edit printer" : "Add printer"}</h2>
          <button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Close"><X size={20} /></button>
        </div>
        <div className="mt-5 space-y-4">
          <Field label="Name">
            <input autoFocus className={inputClass} placeholder="Printer 05" value={form.name} onChange={set("name")} />
          </Field>
          <Field label="Connection type">
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(PRINTER_TYPES).map(([key, t]) => (
                <button key={key} type="button" onClick={() => setForm(f => ({ ...f, type: key }))} className={`rounded-lg border px-2 py-2 text-[13px] leading-tight transition ${form.type === key ? "border-violet-400 bg-violet-500/12 text-white" : "border-white/10 text-slate-400 hover:border-white/20"}`}>{t.label}</button>
              ))}
            </div>
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <Field label="IP address or hostname"><input className={inputClass} placeholder="192.168.1.50" value={form.host} onChange={set("host")} /></Field>
            </div>
            <Field label="Port"><input className={inputClass} inputMode="numeric" placeholder={String(defaultPort)} value={form.port} onChange={set("port")} /></Field>
          </div>
          {form.type === "bambu" && (
            <Field label="Serial number" hint="On the printer screen under device info, or in Bambu Studio's Device tab.">
              <input className={`${inputClass} uppercase`} autoComplete="off" spellCheck={false} placeholder="01P00A000000000" value={form.serial} onChange={set("serial")} />
            </Field>
          )}
          {SECRET_LABEL[form.type] && (
            <Field label={SECRET_LABEL[form.type]} hint={editing && printer.type === form.type
              ? `Leave blank to keep the saved ${SECRET_LABEL[form.type].toLowerCase()}.`
              : form.type === "bambu" ? "8 characters, shown on the printer screen in the network (WLAN) settings." : "In OctoPrint: Settings → Application Keys."}>
              <input className={inputClass} type={form.type === "bambu" ? "password" : "text"} autoComplete="off" spellCheck={false} value={form.api_key} onChange={set("api_key")} />
            </Field>
          )}
          {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-white/5 hover:text-white">Cancel</button>
          <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-50">
            {saving && <Loader2 size={15} className="animate-spin" />} {saving ? "Saving…" : editing ? "Save changes" : "Add printer"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReorderRow({ printer, index, count, move, dragging, setDragging }) {
  const btn = "rounded-lg p-2 text-slate-400 hover:bg-white/6 hover:text-white disabled:opacity-25 disabled:hover:bg-transparent";
  // Pointer events (not HTML drag-and-drop) so dragging the grip also works on phones and tablets
  const onPointerDown = e => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); setDragging(index); };
  const onPointerMove = e => {
    if (dragging !== index) return;
    const row = document.elementFromPoint(e.clientX, e.clientY)?.closest("[data-reorder-index]");
    const to = row ? Number(row.dataset.reorderIndex) : index;
    if (to !== index) move(index, to);
  };
  const stop = () => setDragging(null);
  return (
    <li data-reorder-index={index} className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${dragging === index ? "border-violet-400/60 bg-violet-500/10" : "border-white/8 bg-[#11151f]"}`}>
      <span onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={stop} onPointerCancel={stop} className="shrink-0 cursor-grab touch-none p-1 text-slate-600 hover:text-slate-400 active:cursor-grabbing" aria-hidden="true"><GripVertical size={18} /></span>
      <span className="w-6 shrink-0 text-right text-xs tabular-nums text-slate-600">{index + 1}</span>
      <div className="min-w-0 flex-1 select-none">
        <div className="truncate text-sm font-medium text-white">{printer.name}</div>
        <div className="truncate text-xs text-slate-500">{printer.model}</div>
      </div>
      <button className={btn} onClick={() => move(index, index - 1)} disabled={index === 0} aria-label={`Move ${printer.name} up`}><ArrowUp size={16} /></button>
      <button className={btn} onClick={() => move(index, index + 1)} disabled={index === count - 1} aria-label={`Move ${printer.name} down`}><ArrowDown size={16} /></button>
    </li>
  );
}

function PrintFarmPage({ printers, usingDemo, printerError, onSelect, onAdd, onSaveOrder }) {
  // While reordering, keep our own list of ids so the 10s printer poll doesn't undo moves.
  const [order, setOrder] = useState(null);
  const [dragging, setDragging] = useState(null);
  const [savingOrder, setSavingOrder] = useState(false);
  const [orderError, setOrderError] = useState("");
  const reordering = order !== null;
  const byId = new Map(printers.map(p => [p.id, p]));
  const draft = reordering ? order.map(id => byId.get(id)).filter(Boolean) : printers;

  const move = (from, to) => {
    if (to < 0 || to >= order.length) return;
    setOrder(o => { const next = [...o]; const [id] = next.splice(from, 1); next.splice(to, 0, id); return next; });
    if (dragging === from) setDragging(to);
  };
  const saveOrder = async () => {
    setSavingOrder(true); setOrderError("");
    try { await onSaveOrder(draft.map(p => p.id)); setOrder(null); }
    catch (e) { setOrderError(e.message); }
    finally { setSavingOrder(false); }
  };

  return (
    <>
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Print Farm</h1>
          <p className="mt-2 text-sm text-slate-500">{usingDemo ? "Showing demo printers until the printer API responds." : `${printers.length} printer${printers.length === 1 ? "" : "s"} on the dashboard.`}</p>
        </div>
        {reordering ? (
          <div className="flex gap-2">
            <button onClick={() => { setOrder(null); setOrderError(""); }} className="rounded-xl px-4 py-2.5 text-sm text-slate-400 hover:bg-white/5 hover:text-white">Cancel</button>
            <button onClick={saveOrder} disabled={savingOrder} className="flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-50">
              {savingOrder && <Loader2 size={15} className="animate-spin" />} {savingOrder ? "Saving…" : "Save order"}
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            {!usingDemo && printers.length > 1 && (
              <button onClick={() => setOrder(printers.map(p => p.id))} className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06]">
                <ArrowUpDown size={16} /> Reorder
              </button>
            )}
            <button onClick={onAdd} className="flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-300">
              <Plus size={17} /> Add printer
            </button>
          </div>
        )}
      </div>

      {usingDemo && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/6 px-4 py-3 text-sm text-amber-200">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <div>Couldn't load printers from the backend ({printerError}). Make sure uvicorn is running on port 8000 from the v3 folder.</div>
        </div>
      )}

      {reordering ? (
        <div className="max-w-xl">
          <p className="mb-3 text-sm text-slate-500">Drag printers or use the arrows. This order is used on the Dashboard and Print Farm pages.</p>
          <ol className="space-y-2">
            {draft.map((p, i) => <ReorderRow key={p.id} printer={p} index={i} count={draft.length} move={move} dragging={dragging} setDragging={setDragging} />)}
          </ol>
          {orderError && <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{orderError}</div>}
        </div>
      ) : printers.length === 0 ? (
        <div className="flex min-h-[40vh] flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 text-center">
          <Printer className="text-violet-400" size={28} />
          <h2 className="mt-4 font-semibold text-white">No printers yet</h2>
          <p className="mt-1 max-w-xs text-sm text-slate-500">Add your first Klipper, OctoPrint or Bambu Lab printer to start tracking jobs here.</p>
          <button onClick={onAdd} className="mt-5 flex items-center gap-2 rounded-xl bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400"><Plus size={16} /> Add printer</button>
        </div>
      ) : (
        <PrinterGrid count={printers.length}>
          {printers.map(p => <PrinterCard key={p.id} printer={p} onSelect={onSelect} />)}
        </PrinterGrid>
      )}
    </>
  );
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatRate(bps) {
  const b = Number(bps) || 0;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB/s`;
  if (b >= 1e3) return `${(b / 1e3).toFixed(0)} KB/s`;
  return `${Math.round(b)} B/s`;
}

// Temperature bands for small ARM boards; most throttle around 85°C.
function tempStatus(c) {
  if (c == null) return null;
  if (c >= 75) return { label: "Hot", cls: "text-red-300", Icon: AlertTriangle };
  if (c >= 60) return { label: "Warm", cls: "text-amber-300", Icon: AlertTriangle };
  return { label: "Normal", cls: "text-emerald-300", Icon: ShieldCheck };
}

function Bar({ percent, warnAt = 80 }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  return (
    <div className="h-1.5 overflow-hidden rounded-full bg-white/6">
      <div className={`h-full rounded-full ${p >= warnAt ? "bg-amber-400" : "bg-violet-500"}`} style={{ width: `${p}%` }} />
    </div>
  );
}

function Card({ title, icon: Icon, sub, children, className = "" }) {
  return (
    <div className={`rounded-2xl border border-white/8 bg-[#11151f] p-5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-white">{title}</h2>
          {sub && <p className="mt-1 text-xs text-slate-600">{sub}</p>}
        </div>
        {Icon && <Icon className="shrink-0 text-violet-400" size={18} />}
      </div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/5 py-2 text-sm last:border-0">
      <span className="shrink-0 whitespace-nowrap text-slate-500">{label}</span>
      <span className="min-w-0 truncate text-right text-slate-200" title={typeof value === "string" ? value : undefined}>{value ?? "—"}</span>
    </div>
  );
}

// One measurement over the last hour. Hover (or touch) shows the value at that moment.
// bare: no card border/padding, for charts placed inside another card
function HistoryChart({ title, points, field, unit, max, empty, bare = false }) {
  const wrap = React.useRef(null);
  const [width, setWidth] = useState(300);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(120, e.contentRect.width)));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);

  const data = points.filter(p => p[field] != null);
  const H = 120, L = 34, R = 8, T = 8, B = 20;
  const values = data.map(p => p[field]);
  const top = max ?? Math.max(10, Math.ceil((Math.max(...values, 0) + 5) / 10) * 10);
  const bottom = max ? 0 : Math.max(0, Math.floor((Math.min(...values, top) - 5) / 10) * 10);
  const t0 = data[0]?.t, t1 = data[data.length - 1]?.t;
  const span = Math.max(1, (t1 ?? 0) - (t0 ?? 0));
  const x = t => L + ((t - t0) / span) * (width - L - R);
  const y = v => T + (1 - (v - bottom) / (top - bottom || 1)) * (H - T - B);
  const line = data.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p[field]).toFixed(1)}`).join("");
  const area = data.length > 1 ? `${line}L${x(t1).toFixed(1)},${H - B}L${x(t0).toFixed(1)},${H - B}Z` : "";
  const ticks = [bottom, (bottom + top) / 2, top];
  const latest = data[data.length - 1];
  const shown = hover ?? latest;
  const minutes = Math.round(span / 60);
  // Charts cover anything from an hour (Server) to 90 days (Storage)
  const ago = span >= 2 * 86400 ? `${Math.round(span / 86400)} days ago` : span >= 2 * 3600 ? `${Math.round(span / 3600)} hours ago` : minutes ? `${minutes} min ago` : "just now";
  const timeLabel = t => new Date(t * 1000).toLocaleString([], span >= 86400 ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" } : { hour: "numeric", minute: "2-digit", second: "2-digit" });

  const onMove = e => {
    if (data.length < 2) return;
    const box = e.currentTarget.getBoundingClientRect();
    const px = (e.touches?.[0]?.clientX ?? e.clientX) - box.left;
    const t = t0 + ((px - L) / (width - L - R)) * span;
    let best = data[0];
    for (const p of data) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
    setHover(best);
  };

  return (
    <div className={bare ? "" : "rounded-2xl border border-white/8 bg-[#11151f] p-5"}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <div className="text-right">
          <span className="text-lg font-semibold tabular-nums text-white">{shown ? `${shown[field]}${unit}` : "—"}</span>
          <div className="text-[11px] text-slate-600">{hover ? timeLabel(hover.t) : "Now"}</div>
        </div>
      </div>
      <div ref={wrap} className="relative mt-3">
        {data.length < 2 ? (
          <div className="flex h-[120px] items-center justify-center rounded-xl border border-dashed border-white/8 px-4 text-center text-xs text-slate-600">{empty ?? "Collecting data. The chart fills in over the next few minutes."}</div>
        ) : (
          <svg width={width} height={H} className="block touch-none select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)} onTouchMove={onMove} onTouchEnd={() => setHover(null)} role="img" aria-label={`${title}, from ${ago} to now, latest ${latest[field]}${unit}`}>
            {ticks.map(v => (
              <g key={v}>
                <line x1={L} x2={width - R} y1={y(v)} y2={y(v)} stroke="rgba(255,255,255,.06)" />
                <text x={L - 6} y={y(v) + 3.5} textAnchor="end" className="fill-slate-600 text-[10px] tabular-nums">{Math.round(v)}</text>
              </g>
            ))}
            <path d={area} fill="rgba(139,92,246,.12)" />
            <path d={line} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <text x={L} y={H - 4} className="fill-slate-600 text-[10px]">{ago}</text>
            <text x={width - R} y={H - 4} textAnchor="end" className="fill-slate-600 text-[10px]">now</text>
            {hover && (
              <g>
                <line x1={x(hover.t)} x2={x(hover.t)} y1={T} y2={H - B} stroke="rgba(255,255,255,.25)" />
                <circle cx={x(hover.t)} cy={y(hover[field])} r="4.5" fill="#a78bfa" stroke="#11151f" strokeWidth="2" />
              </g>
            )}
          </svg>
        )}
      </div>
    </div>
  );
}

function ServerPage() {
  const [info, setInfo] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const loadInfo = async () => {
      try { const d = await getServer(); if (active) { setInfo(d); setError(""); } }
      catch (e) { if (active) setError(e.message || "network error"); }
    };
    const loadHistory = async () => {
      try { const d = await getServerHistory(); if (active) setHistory(d.points ?? []); } catch { /* info poll reports errors */ }
    };
    loadInfo(); loadHistory();
    const a = setInterval(loadInfo, 3000), b = setInterval(loadHistory, 5000);
    return () => { active = false; clearInterval(a); clearInterval(b); };
  }, []);

  if (!info) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-slate-500">
        {error ? <span className="flex items-center gap-2 text-red-300"><AlertTriangle size={16} /> Couldn't reach the server API ({error}).</span> : <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Loading server details…</span>}
      </div>
    );
  }

  const { cpu, memory, network } = info;
  const status = tempStatus(info.temperature_c);
  const root = info.disks.find(d => d.mount === "/") ?? info.disks[0];

  return (
    <>
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="min-w-0">
          <h1 className="text-3xl font-bold tracking-tight text-white">Server</h1>
          <p className="mt-2 truncate text-sm text-slate-500">{info.hostname} · {info.os} · {info.arch}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          {error && <span className="rounded-full border border-red-500/20 bg-red-500/5 px-3 py-1.5 text-red-300">Connection lost, retrying</span>}
          <span className="flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[.03] px-3 py-1.5"><Clock size={13} /> Up {formatUptime(info.uptime_seconds)}</span>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={Cpu} label="CPU" value={`${Math.round(cpu.percent)}%`} sub={`Load ${cpu.load_avg.join(" / ")}`} progress={cpu.percent} />
        <Metric icon={Database} label="Memory" value={`${Math.round(memory.percent)}%`} sub={`${memory.used_gb} GB / ${memory.total_gb} GB`} progress={memory.percent} />
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Thermometer size={15} /> Temperature</div>
          <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{info.temperature_c != null ? `${info.temperature_c}°C` : "—"}</div>
          {status
            ? <div className={`mt-1 flex items-center gap-1 text-xs ${status.cls}`}><status.Icon size={12} /> {status.label}</div>
            : <div className="mt-1 text-xs text-slate-500">No sensor on this machine</div>}
        </div>
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Network size={15} /> Network</div>
          <div className="mt-3 flex items-center gap-4 text-white">
            <span className="flex items-center gap-1.5 text-lg font-semibold tabular-nums"><ArrowDownToLine size={16} className="text-slate-500" aria-label="Download" />{formatRate(network.rx_bps)}</span>
            <span className="flex items-center gap-1.5 text-lg font-semibold tabular-nums"><ArrowUpFromLine size={16} className="text-slate-500" aria-label="Upload" />{formatRate(network.tx_bps)}</span>
          </div>
          <div className="mt-1 truncate text-xs text-slate-500">{network.addresses.map(a => a.address).join(", ") || "No network address"}</div>
        </div>
      </section>

      <section className="mt-4 grid gap-4 md:grid-cols-3">
        <HistoryChart title="CPU usage" points={history} field="cpu" unit="%" max={100} />
        <HistoryChart title="Memory usage" points={history} field="memory" unit="%" max={100} />
        <HistoryChart title="Temperature" points={history} field="temp" unit="°C" empty={info.temperature_c == null ? "This machine doesn't report temperature. It will show up on the board." : undefined} />
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="CPU cores" icon={Cpu} sub={`${cpu.cores} cores${cpu.freq_mhz ? ` · ${(cpu.freq_mhz / 1000).toFixed(2)} GHz` : ""}${cpu.freq_max_mhz && cpu.freq_max_mhz !== cpu.freq_mhz ? ` (max ${(cpu.freq_max_mhz / 1000).toFixed(2)} GHz)` : ""}`}>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(96px,1fr))] gap-x-5 gap-y-3">
            {cpu.per_core.map((p, i) => (
              <div key={i}>
                <div className="mb-1 flex justify-between gap-2 whitespace-nowrap text-xs"><span className="text-slate-500">Core {i}</span><span className="tabular-nums text-slate-300">{Math.round(p)}%</span></div>
                <Bar percent={p} warnAt={101} />
              </div>
            ))}
          </div>
          <div className="mt-4 text-xs text-slate-600">Load average (1 / 5 / 15 min): <span className="text-slate-400">{cpu.load_avg.join(" / ")}</span></div>
        </Card>

        <Card title="Storage" icon={HardDrive} sub={root ? `${root.used_gb} GB of ${root.total_gb} GB used on the main drive` : undefined}>
          <div className="space-y-4">
            {info.disks.map(d => (
              <div key={d.mount}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                  <span className="truncate text-slate-200">{d.mount === "/" ? "Main drive (/)" : d.mount}</span>
                  <span className="shrink-0 text-xs tabular-nums text-slate-400">{d.used_gb} / {d.total_gb} GB · {Math.round(d.percent)}%</span>
                </div>
                <Bar percent={d.percent} warnAt={85} />
              </div>
            ))}
            <div className="text-xs text-slate-600">Swap: {memory.swap_used_gb} GB of {memory.swap_total_gb} GB used</div>
          </div>
        </Card>
      </section>

      <section className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card title="System" icon={Server}>
          <Row label="Hostname" value={info.hostname} />
          <Row label="Operating system" value={info.os} />
          <Row label="Kernel" value={info.kernel} />
          <Row label="Architecture" value={info.arch} />
          <Row label="Last boot" value={new Date(info.boot_time).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })} />
        </Card>
        <Card title="Network addresses" icon={Wifi} sub="Use these to reach the dashboard from other devices.">
          {network.addresses.length ? network.addresses.map(a => <Row key={a.interface + a.address} label={a.interface} value={a.address} />) : <div className="text-sm text-slate-500">No network address</div>}
        </Card>
        <Card title="Temperature sensors" icon={Thermometer} className="md:col-span-2 xl:col-span-1">
          {info.sensors.length ? info.sensors.map(t => <Row key={t.name} label={t.name} value={`${t.celsius}°C`} />) : <div className="text-sm text-slate-500">This machine doesn't report temperatures. On the board, each sensor (CPU cores, GPU, NVMe) will be listed here.</div>}
        </Card>
      </section>

      <section className="mt-4">
        <Card title="Dashboard service" icon={Activity}>
          <div className="grid gap-x-8 md:grid-cols-3">
            <Row label="Memory used" value={`${info.app.memory_mb} MB`} />
            <Row label="Python" value={info.python} />
            <Row label="Running since" value={new Date(info.app.started).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} />
          </div>
        </Card>
      </section>
    </>
  );
}

function formatBytes(b) {
  const n = Number(b) || 0;
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)} TB`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} KB`;
  return `${n} B`;
}

function driveLabel(mount) {
  return mount === "/" ? "Main drive" : mount.split("/").filter(Boolean).pop() || mount;
}

function DriveCard({ drive, holdsFiles }) {
  const h = drive.health ?? {};
  const failing = h.available && (h.passed === false || h.critical_warning > 0 || h.media_errors > 0);
  const worn = h.available && h.wear_percent >= 80;
  const badge = !h.available ? null
    : failing ? { text: "Needs attention", cls: "border-red-500/20 bg-red-500/6 text-red-300", Icon: AlertTriangle }
    : worn ? { text: "Wearing out", cls: "border-amber-500/20 bg-amber-500/6 text-amber-200", Icon: AlertTriangle }
    : { text: "Healthy", cls: "border-emerald-500/20 bg-emerald-500/6 text-emerald-300", Icon: ShieldCheck };
  return (
    <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-white" title={drive.mount}>{driveLabel(drive.mount)}</h3>
          <p className="mt-1 truncate text-xs text-slate-600">{drive.mount} · {drive.fstype}{h.model ? ` · ${h.model}` : ""}</p>
        </div>
        {badge && <span className={`flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 text-[11px] ${badge.cls}`}><badge.Icon size={12} /> {badge.text}</span>}
      </div>
      <div className="mt-4 flex items-baseline justify-between text-sm">
        <span className="text-xl font-semibold tabular-nums text-white">{Math.round(drive.percent)}%</span>
        <span className="text-xs tabular-nums text-slate-400">{drive.used_gb} of {drive.total_gb} GB used</span>
      </div>
      <div className="mt-2"><Bar percent={drive.percent} warnAt={85} /></div>
      {holdsFiles && <div className="mt-3 flex items-center gap-1.5 text-xs text-violet-300"><Folder size={13} /> TTRC Files is stored here</div>}
      <div className="mt-4 border-t border-white/6 pt-3">
        {h.available ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            {h.wear_percent != null && <div><div className="text-slate-600">Wear</div><div className="mt-0.5 text-slate-200">{h.wear_percent}% of rated life</div></div>}
            {h.temperature_c != null && <div><div className="text-slate-600">Temperature</div><div className="mt-0.5 text-slate-200">{h.temperature_c}°C</div></div>}
            {h.power_on_hours != null && <div><div className="text-slate-600">Powered on</div><div className="mt-0.5 text-slate-200">{h.power_on_hours >= 48 ? `${Math.round(h.power_on_hours / 24)} days` : `${h.power_on_hours} hours`}</div></div>}
            {h.written_tb != null && <div><div className="text-slate-600">Data written</div><div className="mt-0.5 text-slate-200">{h.written_tb} TB</div></div>}
            {h.media_errors > 0 && <div className="col-span-2 text-red-300">{h.media_errors} media errors reported. Back up this drive.</div>}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 text-xs text-slate-600"><HeartPulse size={13} /> {h.reason || "Health data unavailable"}</div>
        )}
      </div>
    </div>
  );
}

function FileBrowser({ filesInfo, onChanged }) {
  const [path, setPath] = useState("");
  const [listing, setListing] = useState(null);
  const [error, setError] = useState("");
  const [uploads, setUploads] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [renaming, setRenaming] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [confirmEmpty, setConfirmEmpty] = useState(false);
  const picker = React.useRef(null);

  const load = useCallback(async (p = path) => {
    try { setListing(await listFiles(p)); setError(""); }
    catch (e) { setError(e.message); }
  }, [path]);
  useEffect(() => { load(path); }, [path, load]);

  const run = async action => {
    setError("");
    try { await action(); await load(); onChanged(); }
    catch (e) { setError(e.message); }
  };

  const upload = async files => {
    const list = [...files];
    if (!list.length) return;
    const target = path;
    const ids = list.map((f, i) => `${Date.now()}-${i}-${f.name}`);
    setUploads(u => [...u, ...list.map((f, i) => ({ id: ids[i], name: f.name, size: f.size, progress: 0 }))]);
    for (let i = 0; i < list.length; i++) {
      const id = ids[i];
      try {
        await uploadFile(target, list[i], progress => setUploads(u => u.map(x => x.id === id ? { ...x, progress } : x)));
        setUploads(u => u.filter(x => x.id !== id));
      } catch (e) {
        setUploads(u => u.map(x => x.id === id ? { ...x, error: e.message } : x));
      }
    }
    await load(target); onChanged();
  };

  const items = listing?.items ?? [];
  const biggest = Math.max(1, ...items.map(i => i.size));
  const totalHere = items.reduce((n, i) => n + i.size, 0);
  const iconBtn = "rounded-lg p-2 text-slate-500 hover:bg-white/6 hover:text-white";

  return (
    <div
      className={`relative rounded-2xl border bg-[#11151f] p-5 transition-colors ${dragOver ? "border-violet-400/60" : "border-white/8"}`}
      onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragOver(true); } }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false); }}
      onDrop={e => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files); }}
    >
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h2 className="font-semibold text-white">TTRC Files</h2>
          <nav className="mt-1 flex flex-wrap items-center gap-1 text-xs" aria-label="Folder path">
            <button onClick={() => setPath("")} className={listing?.crumbs.length ? "text-violet-400 hover:text-violet-300" : "text-slate-400"}>All files</button>
            {listing?.crumbs.map((c, i) => (
              <React.Fragment key={c.path}>
                <ChevronRight size={12} className="text-slate-600" />
                <button onClick={() => setPath(c.path)} className={i === listing.crumbs.length - 1 ? "text-slate-400" : "text-violet-400 hover:text-violet-300"}>{c.name}</button>
              </React.Fragment>
            ))}
          </nav>
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setCreating(true); setNewName(""); }} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><FolderPlus size={16} /> New folder</button>
          <button onClick={() => picker.current?.click()} className="flex items-center gap-2 rounded-xl bg-violet-500 px-3 py-2 text-sm font-medium text-white hover:bg-violet-400"><CloudUpload size={16} /> Upload</button>
          <input ref={picker} type="file" multiple className="hidden" onChange={e => { upload(e.target.files); e.target.value = ""; }} />
        </div>
      </div>

      {error && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}

      {uploads.length > 0 && (
        <ul className="mt-4 space-y-2">
          {uploads.map(u => (
            <li key={u.id} className="rounded-xl border border-white/8 bg-white/[.02] px-3 py-2 text-xs">
              <div className="flex justify-between gap-3"><span className="truncate text-slate-300">{u.name}</span><span className={u.error ? "text-red-300" : "tabular-nums text-slate-500"}>{u.error ?? `${Math.round(u.progress * 100)}% of ${formatBytes(u.size)}`}</span></div>
              {!u.error && <div className="mt-1.5"><Bar percent={u.progress * 100} warnAt={101} /></div>}
              {u.error && <button onClick={() => setUploads(x => x.filter(y => y.id !== u.id))} className="mt-1 text-slate-500 hover:text-white">Dismiss</button>}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
        {creating && (
          <form className="flex items-center gap-2 border-b border-white/6 bg-white/[.02] px-3 py-2" onSubmit={e => { e.preventDefault(); run(async () => { await newFolder(path, newName); setCreating(false); }); }}>
            <Folder size={16} className="shrink-0 text-violet-400" />
            <input autoFocus className={`${inputClass} py-1.5`} placeholder="Folder name" value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === "Escape" && setCreating(false)} />
            <button type="submit" className="rounded-lg bg-violet-500 px-3 py-1.5 text-sm text-white hover:bg-violet-400">Create</button>
            <button type="button" onClick={() => setCreating(false)} className="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:bg-white/5">Cancel</button>
          </form>
        )}
        {listing && path && (
          <button onClick={() => setPath(listing.crumbs.length > 1 ? listing.crumbs[listing.crumbs.length - 2].path : "")} className="flex w-full items-center gap-3 border-b border-white/6 px-3 py-2.5 text-left text-sm text-slate-500 hover:bg-white/[.03]">
            <ArrowUp size={16} /> Up one folder
          </button>
        )}
        {!listing ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Loading…</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <CloudUpload className="text-violet-400" size={26} />
            <div className="mt-3 text-sm font-medium text-white">{path ? "This folder is empty" : "No files yet"}</div>
            <div className="mt-1 text-xs text-slate-500">Drag files here or use Upload.</div>
          </div>
        ) : (
          <ul>
            {items.map(it => (
              <li key={it.path} className="group flex items-center gap-3 border-b border-white/6 px-3 py-2.5 last:border-0 hover:bg-white/[.02]">
                {it.type === "folder" ? <Folder size={18} className="shrink-0 text-violet-400" /> : <FileIcon size={18} className="shrink-0 text-slate-500" />}
                <div className="min-w-0 flex-1">
                  {renaming?.path === it.path ? (
                    <form className="flex gap-2" onSubmit={e => { e.preventDefault(); run(async () => { await renameFile(it.path, renaming.name); setRenaming(null); }); }}>
                      <input autoFocus className={`${inputClass} py-1`} value={renaming.name} onChange={e => setRenaming(r => ({ ...r, name: e.target.value }))} onKeyDown={e => e.key === "Escape" && setRenaming(null)} />
                      <button type="submit" className="rounded-lg bg-violet-500 px-3 text-sm text-white hover:bg-violet-400">Save</button>
                    </form>
                  ) : it.type === "folder" ? (
                    <button onClick={() => setPath(it.path)} className="block max-w-full truncate text-left text-sm text-white hover:text-violet-300">{it.name}</button>
                  ) : (
                    <a href={downloadUrl(it.path)} className="block truncate text-sm text-slate-200 hover:text-violet-300" title={`Download ${it.name}`}>{it.name}</a>
                  )}
                  <div className="mt-0.5 text-[11px] text-slate-600">
                    {it.type === "folder" ? `${it.items} file${it.items === 1 ? "" : "s"} · ` : ""}{new Date(it.modified).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}
                  </div>
                </div>
                <div className="hidden w-28 shrink-0 sm:block">
                  <div className="text-right text-xs tabular-nums text-slate-400">{formatBytes(it.size)}</div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/6" title="Share of this folder's space"><div className="h-full rounded-full bg-violet-500/70" style={{ width: `${(it.size / biggest) * 100}%` }} /></div>
                </div>
                {confirmDelete === it.path ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={() => run(async () => { await deleteFile(it.path); setConfirmDelete(null); })} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-red-500">Move to trash</button>
                    <button onClick={() => setConfirmDelete(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                  </div>
                ) : (
                  <div className="flex shrink-0 items-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                    {it.type === "file" && <a href={downloadUrl(it.path)} className={iconBtn} aria-label={`Download ${it.name}`}><Download size={16} /></a>}
                    <button onClick={() => setRenaming({ path: it.path, name: it.name })} className={iconBtn} aria-label={`Rename ${it.name}`}><Pencil size={16} /></button>
                    <button onClick={() => setConfirmDelete(it.path)} className={`${iconBtn} hover:text-red-300`} aria-label={`Delete ${it.name}`}><Trash2 size={16} /></button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-3 flex flex-col justify-between gap-2 text-xs text-slate-600 sm:flex-row sm:items-center">
        <span>{items.length} item{items.length === 1 ? "" : "s"} · {formatBytes(totalHere)}{filesInfo ? ` · ${formatBytes(filesInfo.free)} free on the drive` : ""}</span>
        {filesInfo && (filesInfo.trash_count > 0 ? (
          confirmEmpty ? (
            <span className="flex items-center gap-2">
              <span className="text-red-300">Permanently delete {filesInfo.trash_count} item{filesInfo.trash_count === 1 ? "" : "s"}?</span>
              <button onClick={() => run(async () => { await emptyTrash(); setConfirmEmpty(false); })} className="rounded-lg bg-red-500/80 px-2.5 py-1 font-medium text-white hover:bg-red-500">Empty trash</button>
              <button onClick={() => setConfirmEmpty(false)} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/5">Cancel</button>
            </span>
          ) : (
            <button onClick={() => setConfirmEmpty(true)} className="flex items-center gap-1.5 text-slate-500 hover:text-red-300"><Trash2 size={13} /> Trash: {filesInfo.trash_count} item{filesInfo.trash_count === 1 ? "" : "s"} ({formatBytes(filesInfo.trash_size)}) · Empty</button>
          )
        ) : <span className="flex items-center gap-1.5"><Trash2 size={13} /> Trash is empty</span>)}
      </div>

      {dragOver && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-2xl bg-violet-500/10 backdrop-blur-[1px]">
          <div className="flex items-center gap-2 rounded-xl border border-violet-400/40 bg-[#11151f] px-4 py-3 text-sm text-violet-200"><CloudUpload size={18} /> Drop to upload to {listing?.crumbs.at(-1)?.name ?? "All files"}</div>
        </div>
      )}
    </div>
  );
}

function StoragePage() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [trendMount, setTrendMount] = useState("/");

  const load = useCallback(async () => {
    try { setInfo(await getStorage()); setError(""); }
    catch (e) { setError(e.message || "network error"); }
  }, []);
  useEffect(() => {
    load();
    // Folder sizes are worked out on each call, so refresh this page less often than the Server tab
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  if (!info) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-slate-500">
        {error ? <span className="flex items-center gap-2 text-red-300"><AlertTriangle size={16} /> Couldn't reach the storage API ({error}).</span> : <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Loading storage…</span>}
      </div>
    );
  }

  const trend = (info.history[trendMount] ?? []).map(p => ({ t: p.t, used: p.used }));
  const mounts = info.drives.map(d => d.mount);

  return (
    <>
      <div className="mb-7">
        <h1 className="text-3xl font-bold tracking-tight text-white">Storage</h1>
        <p className="mt-2 text-sm text-slate-500">Drive health and the shared TTRC Files folder.</p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {info.drives.map(d => <DriveCard key={d.mount} drive={d} holdsFiles={d.mount === info.files.drive} />)}
      </section>

      <section className="mt-4">
        <HistoryChart
          title={`${driveLabel(trendMount)} usage (GB)`}
          points={trend}
          field="used"
          unit=" GB"
          empty={`Usage is recorded every ${info.history_every_minutes} minutes and kept for 90 days. The trend fills in over the next few hours.`}
        />
        {mounts.length > 1 && (
          <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Choose drive">
            {mounts.map(m => (
              <button key={m} onClick={() => setTrendMount(m)} className={`rounded-lg border px-3 py-1.5 text-xs ${trendMount === m ? "border-violet-400 bg-violet-500/12 text-white" : "border-white/10 text-slate-400 hover:border-white/20"}`}>{driveLabel(m)}</button>
            ))}
          </div>
        )}
      </section>

      <section className="mt-4">
        <FileBrowser filesInfo={info.files} onChanged={load} />
        <p className="mt-2 text-xs text-slate-600">Stored in <span className="text-slate-500">{info.files.root}</span>. Deleted items go to the trash until you empty it.</p>
      </section>
    </>
  );
}

const DEVICE_KINDS = {
  router: ["Router", Router], printer: ["Printer", Printer], computer: ["Computer", Monitor], server: ["Server", Server],
  nas: ["NAS / storage", HardDrive], camera: ["Camera", Camera], phone: ["Phone / tablet", Smartphone], other: ["Other", Box],
};

// 24 one-hour blocks, oldest on the left. Each block shows how many checks succeeded.
function UptimeBar({ hours, label }) {
  const now = new Date();
  return (
    <div className="flex h-5 gap-[2px]" role="img" aria-label={label}>
      {hours.map((v, i) => {
        const at = new Date(now.getTime() - (hours.length - 1 - i) * 3600e3);
        const cls = v == null ? "bg-white/8" : v >= 0.99 ? "bg-emerald-400/80" : v >= 0.9 ? "bg-amber-400/80" : "bg-red-400/80";
        return <div key={i} className={`flex-1 rounded-[2px] ${cls}`} title={`${at.toLocaleTimeString([], { hour: "numeric" })}: ${v == null ? "no data" : `${Math.round(v * 100)}% up`}`} />;
      })}
    </div>
  );
}

function DeviceForm({ device, onSave, onCancel }) {
  const [f, setF] = useState({ name: device?.name ?? "", host: device?.host ?? "", kind: device?.kind ?? "other", port: device?.port ? String(device.port) : "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const set = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  const submit = async e => {
    e.preventDefault();
    if (!f.name.trim() || !f.host.trim()) return setError("Give it a name and an IP address or hostname.");
    setSaving(true); setError("");
    try { await onSave({ name: f.name.trim(), host: f.host.trim(), kind: f.kind, port: f.port ? Number(f.port) : null }); }
    catch (err) { setError(err.message); setSaving(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-3 border-b border-white/6 bg-white/[.02] p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><input autoFocus className={inputClass} placeholder="Shop camera" value={f.name} onChange={set("name")} /></Field>
        <Field label="IP address or hostname"><input className={inputClass} placeholder="192.168.1.40" value={f.host} onChange={set("host")} /></Field>
        <Field label="Type">
          <select className={inputClass} value={f.kind} onChange={set("kind")}>{Object.entries(DEVICE_KINDS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}</select>
        </Field>
        <Field label="Port (optional)" hint="Leave blank to use ping. Enter a port for devices that ignore ping.">
          <input className={inputClass} inputMode="numeric" placeholder="Ping" value={f.port} onChange={set("port")} />
        </Field>
      </div>
      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:bg-white/5">Cancel</button>
        <button type="submit" disabled={saving} className="rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-50">{saving ? "Saving…" : device ? "Save" : "Add device"}</button>
      </div>
    </form>
  );
}

function DeviceMonitor({ devices, checkEvery, onChanged }) {
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const up = devices.filter(d => d.up).length;
  const iconBtn = "rounded-lg p-2 text-slate-500 hover:bg-white/6 hover:text-white";
  return (
    <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
      <div className="flex items-start justify-between gap-3">
        <div><h2 className="font-semibold text-white">Device monitor</h2><p className="mt-1 text-xs text-slate-600">{devices.length ? `${up} of ${devices.length} responding · checked every ${checkEvery / 60} min · last 24 hours` : "Add devices to watch"}</p></div>
        {!adding && <button onClick={() => { setAdding(true); setEditing(null); }} className="flex shrink-0 items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><Plus size={16} /> Add device</button>}
      </div>
      <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
        {adding && <DeviceForm onCancel={() => setAdding(false)} onSave={async d => { await addNetDevice(d); setAdding(false); onChanged(); }} />}
        {devices.length === 0 && !adding && <div className="py-10 text-center text-sm text-slate-500">No devices yet. Add one, or use Scan network below to find them.</div>}
        {devices.map(d => {
          const [kindLabel, KindIcon] = DEVICE_KINDS[d.kind] ?? DEVICE_KINDS.other;
          if (editing === d.id) return <DeviceForm key={d.id} device={d} onCancel={() => setEditing(null)} onSave={async x => { await editNetDevice(d.id, x); setEditing(null); onChanged(); }} />;
          return (
            <div key={d.id} className="group grid items-center gap-x-4 gap-y-2 border-b border-white/6 px-3 py-3 last:border-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_auto]">
              <div className="flex min-w-0 items-center gap-3">
                <StatusDot tone={d.up == null ? "off" : d.up ? "good" : "bad"} />
                <KindIcon size={17} className="shrink-0 text-slate-500" aria-label={kindLabel} />
                <div className="min-w-0">
                  <div className="truncate text-sm text-white">{d.name}</div>
                  <div className="truncate text-[11px] text-slate-600">{d.host}{d.port ? `:${d.port}` : ""} · {d.up == null ? "Checking…" : d.up ? `${d.ms} ms` : "Not responding"}</div>
                </div>
              </div>
              <div className="min-w-0">
                <UptimeBar hours={d.hours} label={`${d.name} uptime, last 24 hours`} />
                <div className="mt-1 text-[11px] text-slate-600">{d.uptime_24h == null ? "No data yet" : `${d.uptime_24h}% up`}</div>
              </div>
              {confirm === d.id ? (
                <div className="flex items-center gap-1">
                  <button onClick={async () => { await deleteNetDevice(d.id); setConfirm(null); onChanged(); }} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-red-500">Remove</button>
                  <button onClick={() => setConfirm(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                </div>
              ) : (
                <div className="flex items-center justify-end sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                  <button onClick={() => { setEditing(d.id); setAdding(false); }} className={iconBtn} aria-label={`Edit ${d.name}`}><Pencil size={16} /></button>
                  <button onClick={() => setConfirm(d.id)} className={`${iconBtn} hover:text-red-300`} aria-label={`Remove ${d.name}`}><Trash2 size={16} /></button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InterfaceCard({ iface }) {
  const mbps = (field) => iface.history.map(p => ({ t: p.t, v: +(p[field] * 8 / 1e6).toFixed(2) }));
  return (
    <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-semibold text-white">{iface.type === "Wi-Fi" ? <Wifi size={16} className="text-violet-400" /> : <Network size={16} className="text-violet-400" />} {iface.type} <span className="text-xs font-normal text-slate-500">({iface.name})</span></h3>
          <p className="mt-1 truncate text-xs text-slate-600">{iface.ipv4 ?? "No IPv4 address"}{iface.mac ? ` · ${iface.mac}` : ""}{iface.speed_mbps ? ` · ${iface.speed_mbps >= 1000 ? `${iface.speed_mbps / 1000} Gbps` : `${iface.speed_mbps} Mbps`} link` : ""}</p>
        </div>
        <div className="shrink-0 text-right text-xs text-slate-500">
          <div>Today</div>
          <div className="mt-0.5 tabular-nums text-slate-300"><ArrowDownToLine size={11} className="inline" /> {formatBytes(iface.today_rx)} · <ArrowUpFromLine size={11} className="inline" /> {formatBytes(iface.today_tx)}</div>
        </div>
      </div>
      <div className="mt-5 grid gap-6 md:grid-cols-2">
        <HistoryChart bare title="Download (Mbps)" points={mbps("rx")} field="v" unit=" Mbps" />
        <HistoryChart bare title="Upload (Mbps)" points={mbps("tx")} field="v" unit=" Mbps" />
      </div>
    </div>
  );
}

function Discovery({ printers, devices, onAddPrinter, onMonitored }) {
  const [scan, setScan] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [printersOnly, setPrintersOnly] = useState(false);
  const [added, setAdded] = useState({});

  const poll = useCallback(async () => { try { setScan(await getScan()); } catch (e) { setError(e.message); } }, []);
  useEffect(() => { poll(); }, [poll]);
  useEffect(() => {
    if (!scan?.running) return;
    const t = setInterval(poll, 1000);
    return () => clearInterval(t);
  }, [scan?.running, poll]);

  const run = async () => { setError(""); try { setScan(await startScan()); } catch (e) { setError(e.message); } };

  // What's already on the dashboard, from live data, so adding something updates this list immediately
  const onDashboard = useMemo(() => {
    const m = {};
    for (const p of printers) { const h = String(p.address ?? "").replace(/^[a-z]+:\/\//, "").split(/[:/]/)[0]; if (h) m[h] = `Printer: ${p.name}`; }
    for (const d of devices) m[d.host] ??= `Monitored: ${d.name}`;
    return m;
  }, [printers, devices]);

  const results = (scan?.results ?? []).filter(r =>
    (!printersOnly || r.printer) &&
    (!query || [r.ip, r.hostname, r.vendor, r.label].some(v => String(v ?? "").toLowerCase().includes(query.toLowerCase()))));
  const printerCount = (scan?.results ?? []).filter(r => r.printer).length;

  const monitor = async r => {
    const name = r.label && !["This server"].includes(r.label) ? (r.hostname?.split(".")[0] || r.label) : (r.hostname?.split(".")[0] || r.vendor || r.ip);
    await addNetDevice({ name, host: r.ip, kind: r.printer ? "printer" : r.label === "Router" ? "router" : "other", port: null });
    setAdded(a => ({ ...a, [r.ip]: true })); onMonitored();
  };

  return (
    <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h2 className="font-semibold text-white">Device discovery</h2>
          <p className="mt-1 text-xs text-slate-600">
            {scan?.running ? `Scanning ${scan.subnet ?? "the network"}…`
              : scan?.finished ? `Found ${scan.results.length} devices on ${scan.subnet}${printerCount ? `, including ${printerCount} printer${printerCount === 1 ? "" : "s"}` : ""} · ${new Date(scan.finished).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
              : "Find everything on your network, including printers the dashboard can add."}
          </p>
        </div>
        <button onClick={run} disabled={scan?.running} className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2 text-sm font-medium text-white hover:bg-violet-400 disabled:opacity-60">
          {scan?.running ? <Loader2 size={16} className="animate-spin" /> : <Radar size={16} />} {scan?.running ? `Scanning ${scan.progress}%` : scan?.finished ? "Scan again" : "Scan network"}
        </button>
      </div>
      {scan?.running && <div className="mt-4"><Bar percent={scan.progress} warnAt={101} /></div>}
      {(error || scan?.error) && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error || scan.error}</div>}

      {scan?.results?.length > 0 && (
        <>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
              <input className={`${inputClass} pl-9`} placeholder="Filter by IP, name or manufacturer" value={query} onChange={e => setQuery(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-400"><input type="checkbox" className="accent-violet-500" checked={printersOnly} onChange={e => setPrintersOnly(e.target.checked)} /> Printers only</label>
          </div>
          <div className="mt-3 overflow-hidden rounded-xl border border-white/6">
            {results.length === 0 && <div className="py-8 text-center text-sm text-slate-500">Nothing matches that filter.</div>}
            {results.map(r => {
              const known = onDashboard[r.ip];
              return (
                <div key={r.ip} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-white/6 px-3 py-2.5 last:border-0">
                  <span className="w-28 shrink-0 font-mono text-xs tabular-nums text-slate-300">{r.ip}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm text-white">{r.hostname?.replace(/\.(home\.)?local$/, "") || r.vendor || "Unknown device"}</span>
                      {r.label && <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${r.printer ? "border-violet-400/30 bg-violet-500/10 text-violet-200" : "border-white/10 text-slate-400"}`}>{r.label}</span>}
                    </div>
                    <div className="truncate text-[11px] text-slate-600">{[r.hostname && r.vendor, r.mac, r.ms != null ? `${r.ms} ms` : "Ignores ping"].filter(Boolean).join(" · ")}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {known ? <span className="flex items-center gap-1.5 text-xs text-emerald-300"><StatusDot tone="good" /> {known}</span> : (
                      <>
                        {r.printer && <button onClick={() => onAddPrinter({ ...r.printer, name: r.hostname?.split(".")[0] ?? "" })} className="rounded-lg bg-violet-500 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-violet-400">Add printer</button>}
                        {added[r.ip] ? <span className="text-xs text-emerald-300">Monitoring</span> : <button onClick={() => monitor(r)} className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5">Monitor</button>}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function NetworkPage({ printers, onAddPrinter }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setInfo(await getNetwork()); setError(""); }
    catch (e) { setError(e.message || "network error"); }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  if (!info) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-slate-500">
        {error ? <span className="flex items-center gap-2 text-red-300"><AlertTriangle size={16} /> Couldn't reach the network API ({error}).</span> : <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Checking the network…</span>}
      </div>
    );
  }

  const { internet, devices, interfaces } = info;
  const devUp = devices.filter(d => d.up).length;
  const todayRx = interfaces.reduce((n, i) => n + i.today_rx, 0), todayTx = interfaces.reduce((n, i) => n + i.today_tx, 0);
  const inetTone = internet.up == null ? "off" : internet.up ? "good" : "bad";

  return (
    <>
      <div className="mb-7">
        <h1 className="text-3xl font-bold tracking-tight text-white">Network</h1>
        <p className="mt-2 text-sm text-slate-500">Internet, devices, connections and discovery{info.gateway ? ` · Router ${info.gateway}` : ""}</p>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Globe size={15} /> Internet</div>
          <div className="mt-3 flex items-center gap-2 text-2xl font-semibold tracking-tight text-white"><StatusDot tone={inetTone} /> {internet.up == null ? "Checking" : internet.up ? "Online" : "Offline"}</div>
          <div className="mt-1 text-xs text-slate-500">{internet.up ? `${internet.ms} ms response` : "No response from 1.1.1.1 or 8.8.8.8"}</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Search size={15} /> DNS &amp; public IP</div>
          <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{internet.dns_ok == null ? "—" : internet.dns_ok ? `${internet.dns_ms} ms` : "Failing"}</div>
          <div className="mt-1 truncate text-xs text-slate-500">Public IP {internet.public_ip ?? "unknown"}</div>
        </div>
        <Metric icon={Router} label="Devices" value={devices.length ? `${devUp} / ${devices.length}` : "—"} sub={devices.length ? (devUp === devices.length ? "All responding" : `${devices.length - devUp} not responding`) : "None monitored yet"} />
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Network size={15} /> Data today</div>
          <div className="mt-3 flex flex-wrap gap-x-4 text-lg font-semibold tabular-nums text-white">
            <span className="flex items-center gap-1.5"><ArrowDownToLine size={16} className="text-slate-500" aria-label="Downloaded" />{formatBytes(todayRx)}</span>
            <span className="flex items-center gap-1.5"><ArrowUpFromLine size={16} className="text-slate-500" aria-label="Uploaded" />{formatBytes(todayTx)}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">This server, since midnight</div>
        </div>
      </section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
          <div className="flex items-start justify-between gap-3">
            <div><h2 className="font-semibold text-white">Internet health</h2><p className="mt-1 text-xs text-slate-600">{internet.uptime_24h == null ? "Collecting data" : `${internet.uptime_24h}% up in the last 24 hours · ${internet.uptime_7d}% over 7 days`}</p></div>
            <Globe className="shrink-0 text-violet-400" size={18} />
          </div>
          <div className="mt-4"><UptimeBar hours={internet.hours} label="Internet uptime, last 24 hours" /></div>
          <div className="mt-1 flex justify-between text-[10px] text-slate-600"><span>24 hours ago</span><span>now</span></div>
          <div className="mt-4"><HistoryChart bare title="Response time (ms)" points={internet.history} field="ms" unit=" ms" empty="Checked every minute. The chart fills in over the next few minutes." /></div>
          <div className="mt-4">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-600">Outages (last 7 days)</div>
            {internet.outages.length ? (
              <ul className="mt-2 space-y-1.5">
                {internet.outages.map(o => (
                  <li key={o.start} className="flex justify-between gap-3 rounded-lg border border-red-500/15 bg-red-500/5 px-3 py-2 text-xs">
                    <span className="text-red-200">{new Date(o.start * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
                    <span className="text-slate-400">{o.end ? `${o.minutes} min` : `ongoing, ${o.minutes} min so far`}</span>
                  </li>
                ))}
              </ul>
            ) : <div className="mt-2 flex items-center gap-2 text-sm text-emerald-300"><ShieldCheck size={15} /> No outages recorded.</div>}
          </div>
        </div>
        <DeviceMonitor devices={devices} checkEvery={info.check_every} onChanged={load} />
      </section>

      <section className="mt-4 space-y-4">
        {interfaces.map(i => <InterfaceCard key={i.name} iface={i} />)}
      </section>

      <section className="mt-4">
        <Discovery printers={printers} devices={devices} onAddPrinter={onAddPrinter} onMonitored={load} />
      </section>
    </>
  );
}

function Dashboard() {
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState("dashboard");
  const [menu, setMenu] = useState(false);
  const [system, setSystem] = useState(null);
  const [apiError, setApiError] = useState(false);
  const [livePrinters, setLivePrinters] = useState(null);
  const [printerError, setPrinterError] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);

  const printersInFlight = React.useRef(false);
  const printersGen = React.useRef(0);
  // force: after an add/edit/reorder, start a fresh load even if a poll is running,
  // and discard that older poll's result so it can't show stale data.
  const loadPrinters = useCallback(async ({ force = false } = {}) => {
    if (printersInFlight.current && !force) return;
    const gen = ++printersGen.current;
    printersInFlight.current = true;
    try {
      const data = await getPrinters();
      if (gen !== printersGen.current) return;
      const list = Array.isArray(data) ? data : (data?.printers ?? []);
      setLivePrinters(list.map(normalizePrinter));
      setPrinterError("");
    } catch (e) {
      if (gen !== printersGen.current) return;
      setLivePrinters(null);
      setPrinterError(e.message || "network error");
    } finally {
      if (gen === printersGen.current) printersInFlight.current = false;
    }
  }, []);
  const refreshPrinters = useCallback(() => loadPrinters({ force: true }), [loadPrinters]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try { const data = await getSystem(); if (active) { setSystem(data); setApiError(false); setUpdatedAt(Date.now()); } }
      catch { if (active) setApiError(true); }
    };
    load();
    loadPrinters();
    // Printer checks can take a few seconds per printer, so poll them less often.
    const sysTimer = setInterval(load, 3000);
    const printerTimer = setInterval(() => loadPrinters(), 10000);
    return () => { active = false; clearInterval(sysTimer); clearInterval(printerTimer); };
  }, [loadPrinters]);

  const closeDetail = useCallback(() => setSelected(null), []);
  const selectedLive = selected ? (livePrinters?.find(p => p.id === selected.id) ?? selected) : null;
  const closeAdd = useCallback(() => setAdding(false), []);
  const closeEdit = useCallback(() => setEditing(null), []);
  const startEdit = useCallback(p => { setSelected(null); setEditing(p); }, []);
  const saveOrder = useCallback(async ids => {
    await reorderPrinters(ids);
    // Show the new order right away; the refresh fills in fresh printer status
    setLivePrinters(list => list && ids.map(id => list.find(p => p.id === id)).filter(Boolean));
    refreshPrinters();
  }, [refreshPrinters]);

  const usingDemo = livePrinters === null && !!printerError;
  const printers = livePrinters ?? (usingDemo ? DEMO_PRINTERS : []);

  const active = useMemo(() => printers.filter(p => p.state === "printing").length, [printers]);
  const online = useMemo(() => printers.filter(p => p.state !== "offline").length, [printers]);
  const alerts = useMemo(() => buildAlerts({ apiError, usingDemo, printerError, printers, system }), [apiError, usingDemo, printerError, printers, system]);
  const summary = alertSummary(alerts);
  const tempState = tempStatus(system?.temperature_c);
  const services = [
    { name: "Dashboard API", tone: apiError ? "bad" : system ? "good" : "off", status: apiError ? "Not responding" : system ? "Running" : "Connecting" },
    { name: "Database", tone: !system ? "off" : system.database?.ok ? "good" : "bad", status: !system ? "—" : system.database?.ok ? `${system.database.printers} printer${system.database.printers === 1 ? "" : "s"}` : "Error" },
    { name: "Printers", tone: usingDemo ? "bad" : online === printers.length ? "good" : "warn", status: usingDemo ? "Not responding" : `${online} of ${printers.length} online` },
    // Planned for the board; shown grey until they're actually installed and checked
    { name: "Docker", tone: "off", status: "Not set up" },
    { name: "Home Assistant", tone: "off", status: "Not set up" },
    { name: "Pi-hole", tone: "off", status: "Not set up" },
  ];

  const placeholder = !['dashboard', 'printers', 'server', 'storage', 'network'].includes(page);
  const title = PAGE_TITLES[page] ?? page;

  return (
    <div className="min-h-screen bg-[#090b12] text-slate-200">
      <div className="flex min-h-screen">
        <Sidebar page={page} setPage={setPage} open={menu} setOpen={setMenu} usingDemo={usingDemo} summary={summary} />
        <main className="min-w-0 flex-1">
          <header className="flex h-20 items-center justify-between border-b border-white/7 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button className="rounded-lg p-2 text-slate-500 hover:bg-white/5 lg:hidden" onClick={() => setMenu(true)} aria-label="Open menu"><Menu size={21} /></button>
              <div>
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="mt-0.5 text-xs text-slate-600">TTRC Home Lab</div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <button onClick={() => setPage("dashboard")} className={`hidden max-w-[16rem] items-center gap-2 rounded-full border px-3 py-1.5 sm:flex ${{ good: "border-emerald-500/15 bg-emerald-500/6 text-emerald-300", warn: "border-amber-500/20 bg-amber-500/6 text-amber-200", bad: "border-red-500/20 bg-red-500/6 text-red-300" }[summary.tone]}`}><StatusDot tone={summary.tone} /> <span className="truncate">{summary.tone === "good" ? "All systems online" : summary.text}</span></button>
              <div className={`rounded-full border px-3 py-1.5 ${apiError ? "border-red-500/20 bg-red-500/5 text-red-300" : "border-violet-500/15 bg-violet-500/5 text-violet-300"}`}>{apiError ? "API offline" : <UpdatedAgo at={updatedAt} />}</div>
            </div>
          </header>

          <div className="p-4 sm:p-6 lg:p-8">
            {page === "server" ? (
              <ServerPage />
            ) : page === "storage" ? (
              <StoragePage />
            ) : page === "network" ? (
              <NetworkPage printers={livePrinters ?? []} onAddPrinter={p => setAdding(p)} />
            ) : page === "printers" ? (
              <PrintFarmPage printers={printers} usingDemo={usingDemo} printerError={printerError} onSelect={setSelected} onAdd={() => setAdding(true)} onSaveOrder={saveOrder} />
            ) : placeholder ? (
              <div className="flex min-h-[60vh] items-center justify-center">
                <div className="text-center">
                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-white/8 bg-white/[.025] text-violet-400"><Package /></div>
                  <h1 className="mt-5 text-xl font-semibold text-white">{title} module</h1>
                  <p className="mt-2 max-w-sm text-sm text-slate-500">This section is scaffolded for the next build step.</p>
                </div>
              </div>
            ) : (
              <>
                <div className="mb-7">
                  <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
                    <div>
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.22em] text-violet-400"><Zap size={13} /> TTRC Operations</div>
                      <h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">Home Lab / Print Farm</h1>
                      <p className="mt-2 text-sm text-slate-500">One place to see what's happening across the shop.</p>
                    </div>
                  </div>
                </div>

                <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <Metric icon={Printer} label="Printers Online" value={`${online} / ${printers.length}`} sub={`${active} active print${active === 1 ? "" : "s"}`} />
                  <Metric icon={Cpu} label="CPU" value={system ? `${Math.round(system.cpu_percent)}%` : "—"} sub={system ? system.hostname : "Waiting for API"} />
                  <Metric icon={Database} label="Memory" value={system ? `${Math.round(system.memory_percent)}%` : "—"} sub={system ? `${system.memory_used_gb} GB / ${system.memory_total_gb} GB` : "Waiting for API"} progress={system?.memory_percent ?? 0} />
                  <Metric icon={HardDrive} label="Storage" value={system ? `${Math.round(system.storage_percent)}%` : "—"} sub={system ? `${system.storage_used_gb} GB / ${system.storage_total_gb} GB` : "Waiting for API"} progress={system?.storage_percent ?? 0} />
                </section>

                <section className="mt-8">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h2 className="font-semibold text-white">Print Farm</h2>
                      <p className="mt-1 text-xs text-slate-600">{usingDemo ? "Demo printers. The printer API isn't responding." : "Printers added on the Print Farm page."}</p>
                    </div>
                    <button onClick={() => setPage("printers")} className="flex items-center gap-1 text-xs font-medium text-violet-400 hover:text-violet-300">View all <ChevronRight size={14} /></button>
                  </div>
                  {printers.length === 0 ? (
                    <button onClick={() => { setPage("printers"); setAdding(true); }} className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-white/10 py-10 text-sm text-slate-500 hover:border-violet-400/40 hover:text-slate-300">
                      <Plus size={16} /> Add your first printer
                    </button>
                  ) : (
                    <PrinterGrid count={printers.length}>
                      {printers.map(p => <PrinterCard key={p.id} printer={p} onSelect={setSelected} />)}
                    </PrinterGrid>
                  )}
                </section>

                <section className="mt-8 grid gap-4 lg:grid-cols-3">
                  <div className="lg:col-span-2 rounded-2xl border border-white/8 bg-[#11151f] p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0"><h2 className="font-semibold text-white">Server Health</h2><p className="mt-1 truncate text-xs text-slate-600">{system ? `${system.hostname}${system.ip ? ` · ${system.ip}` : ""}` : "Waiting for API"}</p></div>
                      <button onClick={() => setPage("server")} className="flex shrink-0 items-center gap-1 text-xs font-medium text-violet-400 hover:text-violet-300">Details <ChevronRight size={14} /></button>
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl bg-white/[.025] p-4">
                        <div className="text-xs text-slate-600">Temperature</div>
                        <div className="mt-2 text-xl font-semibold text-white">{system?.temperature_c != null ? `${system.temperature_c}°C` : "N/A"}</div>
                        {tempState ? <div className={`mt-1 flex items-center gap-1 text-xs ${tempState.cls}`}><tempState.Icon size={12} /> {tempState.label}</div> : <div className="mt-1 text-xs text-slate-600">No sensor on this machine</div>}
                      </div>
                      <div className="rounded-xl bg-white/[.025] p-4">
                        <div className="text-xs text-slate-600">Uptime</div>
                        <div className="mt-2 text-xl font-semibold text-white">{system ? formatUptime(system.uptime_seconds) : "—"}</div>
                        <div className="mt-1 text-xs text-slate-600">Since last restart</div>
                      </div>
                      <div className="rounded-xl bg-white/[.025] p-4">
                        <div className="text-xs text-slate-600">Network</div>
                        <div className="mt-2 flex flex-wrap gap-x-3 text-base font-semibold tabular-nums text-white">
                          <span className="flex items-center gap-1"><ArrowDownToLine size={14} className="text-slate-500" aria-label="Download" />{system ? formatRate(system.rx_bps) : "—"}</span>
                          <span className="flex items-center gap-1"><ArrowUpFromLine size={14} className="text-slate-500" aria-label="Upload" />{system ? formatRate(system.tx_bps) : "—"}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-1 text-xs text-slate-600"><Wifi size={12} /> {system?.ip ?? "No network address"}</div>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
                    <div className="flex items-center justify-between"><div><h2 className="font-semibold text-white">Services</h2><p className="mt-1 text-xs text-slate-600">Live checks</p></div><ShieldCheck className="text-violet-400" size={20} /></div>
                    <div className="mt-4 space-y-3">
                      {services.map(sv => (
                        <div key={sv.name} className="flex items-center justify-between gap-3 text-sm">
                          <span className={sv.tone === "off" ? "text-slate-600" : "text-slate-400"}>{sv.name}</span>
                          <span className="flex items-center gap-2 whitespace-nowrap text-xs text-slate-500"><StatusDot tone={sv.tone} />{sv.status}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="mt-4 rounded-2xl border border-white/8 bg-[#11151f] p-5">
                  <div className="flex items-center justify-between">
                    <div><h2 className="font-semibold text-white">Alerts</h2><p className="mt-1 text-xs text-slate-600">Printers, internet, monitored devices, server temperature, storage and memory</p></div>
                    <AlertTriangle className={alerts.length ? "text-amber-300" : "text-slate-600"} size={18} />
                  </div>
                  {alerts.length ? (
                    <ul className="mt-4 space-y-2">
                      {alerts.map(a => (
                        <li key={a.text} className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 text-sm ${a.tone === "bad" ? "border-red-500/20 bg-red-500/6 text-red-200" : "border-amber-500/20 bg-amber-500/6 text-amber-100"}`}>
                          <StatusDot tone={a.tone} /> {a.text}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mt-4 flex items-center gap-2 text-sm text-emerald-300"><ShieldCheck size={16} /> No active alerts. Everything is running normally.</div>
                  )}
                </section>
              </>
            )}
          </div>
        </main>
      </div>
      {selectedLive && <DetailPanel printer={selectedLive} isDemo={usingDemo} close={closeDetail} onRemoved={refreshPrinters} onEdit={startEdit} />}
      {adding && <PrinterFormModal initial={typeof adding === "object" ? adding : undefined} onClose={closeAdd} onSaved={refreshPrinters} />}
      {editing && <PrinterFormModal printer={editing} onClose={closeEdit} onSaved={refreshPrinters} />}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<Dashboard />);
