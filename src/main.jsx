import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getSystem, getPrinters, createPrinter, updatePrinter, reorderPrinters, deletePrinter, testPrinter } from "./api";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, Archive, ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, CircleGauge, Cpu,
  Database, GripVertical, HardDrive, LayoutDashboard, Loader2, Menu, Network, Package,
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

const services = [
  ["Docker", "Running", true],
  ["FastAPI", "Running", true],
  ["SQLite", "Running", true],
  ["Printer Monitor", "Connected", true],
  ["Home Assistant", "Secondary node", true],
  ["Pi-hole", "Secondary node", true],
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
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
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

function StatusDot({ good = true }) {
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${good ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,.55)]" : "bg-red-400 shadow-[0_0_10px_rgba(248,113,113,.45)]"}`} />;
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
    <button onClick={() => onSelect(printer)} className={`group text-left rounded-2xl border ${border} ${bg} p-5 transition hover:-translate-y-0.5 hover:border-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-400`}>
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-white">{printer.name}</div>
          <div className="mt-1 text-xs text-slate-500">{printer.model}</div>
        </div>
        <div className={`flex shrink-0 items-center gap-2 text-[10px] font-bold tracking-widest ${text}`}>
          <StatusDot good={printer.state !== "offline"} /> {label}
        </div>
      </div>

      <div className="mt-5">
        <div className="flex justify-between text-xs">
          <span className="truncate pr-3 text-slate-400">{printer.job || "No active job"}</span>
          <span className="font-semibold text-white">{printer.progress}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/6">
          <div className={`h-full rounded-full ${printer.state === "printing" ? "bg-violet-500" : "bg-slate-600"}`} style={{ width: `${printer.progress}%` }} />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2 border-t border-white/6 pt-4 text-xs">
        <div><div className="text-slate-600">Nozzle</div><div className="mt-1 font-medium text-slate-300">{printer.nozzle ? `${printer.nozzle}°C` : "—"}</div></div>
        <div><div className="text-slate-600">Bed</div><div className="mt-1 font-medium text-slate-300">{printer.bed ? `${printer.bed}°C` : "—"}</div></div>
        <div><div className="text-slate-600">ETA</div><div className="mt-1 font-medium text-slate-300">{printer.eta}</div></div>
      </div>
      <div className="mt-4 flex items-center justify-end gap-1 text-xs text-slate-600 group-hover:text-slate-300">
        Details <ChevronRight size={14} />
      </div>
    </button>
  );
}

function Sidebar({ page, setPage, open, setOpen, usingDemo }) {
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
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300"><StatusDot good={!usingDemo} /> {usingDemo ? "Printer API not reachable" : "All systems nominal"}</div>
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

function PrinterFormModal({ printer, onClose, onSaved }) {
  const editing = !!printer;
  const [form, setForm] = useState(() => editing
    ? { name: printer.name, type: PRINTER_TYPES[printer.type] ? printer.type : "moonraker", ...splitAddress(printer.address), api_key: "", serial: printer.serial ?? "" }
    : { name: "", type: "moonraker", host: "", port: "", api_key: "", serial: "" });
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
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {printers.map(p => <PrinterCard key={p.id} printer={p} onSelect={onSelect} />)}
        </div>
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
      try { const data = await getSystem(); if (active) { setSystem(data); setApiError(false); } }
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

  const placeholder = page !== "dashboard" && page !== "printers";
  const title = PAGE_TITLES[page] ?? page;

  return (
    <div className="min-h-screen bg-[#090b12] text-slate-200">
      <div className="flex min-h-screen">
        <Sidebar page={page} setPage={setPage} open={menu} setOpen={setMenu} usingDemo={usingDemo} />
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
              <div className="hidden items-center gap-2 rounded-full border border-emerald-500/15 bg-emerald-500/6 px-3 py-1.5 text-emerald-300 sm:flex"><StatusDot /> System online</div>
              <div className={`rounded-full border px-3 py-1.5 ${apiError ? "border-red-500/20 bg-red-500/5 text-red-300" : "border-violet-500/15 bg-violet-500/5 text-violet-300"}`}>{apiError ? "API offline" : system ? "Live system data" : "Connecting..."}</div>
            </div>
          </header>

          <div className="p-4 sm:p-6 lg:p-8">
            {page === "printers" ? (
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
                    <div className="text-right text-xs text-slate-600">Updated just now</div>
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
                    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                      {printers.slice(0, 4).map(p => <PrinterCard key={p.id} printer={p} onSelect={setSelected} />)}
                    </div>
                  )}
                </section>

                <section className="mt-8 grid gap-4 lg:grid-cols-3">
                  <div className="lg:col-span-2 rounded-2xl border border-white/8 bg-[#11151f] p-5">
                    <div className="flex items-center justify-between">
                      <div><h2 className="font-semibold text-white">Server Health</h2><p className="mt-1 text-xs text-slate-600">Values are simulated until the ROCK 4D is online.</p></div>
                      <CircleGauge className="text-violet-400" size={20} />
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl bg-white/[.025] p-4"><div className="text-xs text-slate-600">Temperature</div><div className="mt-2 text-xl font-semibold text-white">{system?.temperature_c != null ? `${system.temperature_c}°C` : "N/A"}</div><div className="mt-1 text-xs text-emerald-400">{system?.temperature_c != null ? "Live reading" : "Sensor unavailable"}</div></div>
                      <div className="rounded-xl bg-white/[.025] p-4"><div className="text-xs text-slate-600">Uptime</div><div className="mt-2 text-xl font-semibold text-white">{system ? formatUptime(system.uptime_seconds) : "—"}</div><div className="mt-1 text-xs text-slate-600">{system ? "Live reading" : "Waiting for API"}</div></div>
                      <div className="rounded-xl bg-white/[.025] p-4"><div className="text-xs text-slate-600">Network</div><div className="mt-2 text-xl font-semibold text-white">1 Gbps</div><div className="mt-1 flex items-center gap-1 text-xs text-emerald-400"><Wifi size={12} /> Connected</div></div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/8 bg-[#11151f] p-5">
                    <div className="flex items-center justify-between"><div><h2 className="font-semibold text-white">Services</h2><p className="mt-1 text-xs text-slate-600">Planned stack</p></div><ShieldCheck className="text-emerald-400" size={20} /></div>
                    <div className="mt-4 space-y-3">
                      {services.map(([name, status, good]) => <div key={name} className="flex items-center justify-between text-sm"><span className="text-slate-400">{name}</span><span className="flex items-center gap-2 text-xs text-slate-500"><StatusDot good={good} />{status}</span></div>)}
                    </div>
                  </div>
                </section>

                <section className="mt-4 grid gap-4 sm:grid-cols-3">
                  <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4"><div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-600"><Archive size={15} /> Storage</div><div className="mt-3 text-sm font-medium text-white">TTRC Files</div><div className="mt-1 text-xs text-slate-600">NVMe storage • independent from iMac DAS</div></div>
                  <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4"><div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-600"><Network size={15} /> Network</div><div className="mt-3 text-sm font-medium text-white">Gigabit Ethernet</div><div className="mt-1 text-xs text-slate-600">Wi-Fi available as secondary path</div></div>
                  <div className="rounded-2xl border border-white/8 bg-[#11151f] p-4"><div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-600"><AlertTriangle size={15} /> Alerts</div><div className="mt-3 text-sm font-medium text-white">0 active alerts</div><div className="mt-1 text-xs text-slate-600">Alert system will be added later</div></div>
                </section>
              </>
            )}
          </div>
        </main>
      </div>
      {selectedLive && <DetailPanel printer={selectedLive} isDemo={usingDemo} close={closeDetail} onRemoved={refreshPrinters} onEdit={startEdit} />}
      {adding && <PrinterFormModal onClose={closeAdd} onSaved={refreshPrinters} />}
      {editing && <PrinterFormModal printer={editing} onClose={closeEdit} onSaved={refreshPrinters} />}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<Dashboard />);
