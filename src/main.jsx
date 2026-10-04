import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getUpdates, checkUpdates, installUpdate, getHealth, getHotspot, joinWifi, getAuthStatus, setupLayerHound, login, logout, changePassword, getUsers, addUser, editUser, deleteUser, getKeys, addKey, deleteKey, getWifi, connectWifi, forgetWifi, getHistory, getHistoryStats, deleteHistoryJob, importHistory, getSettings, saveSettings, getAbout, clearHistory, restoreBackup, restartDashboard, getServices, addService, editService, deleteService, restartContainer, getNetwork, addNetDevice, editNetDevice, deleteNetDevice, startScan, getScan, getSystem, getServer, getServerHistory, getStorage, listFiles, newFolder, renameFile, deleteFile, emptyTrash, downloadUrl, uploadFile, getPrinters, createPrinter, updatePrinter, reorderPrinters, deletePrinter, testPrinter } from "./api";
import { createRoot } from "react-dom/client";
import {
  Activity, AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, ChevronRight, Cpu,
  ArrowDownToLine, ArrowUpFromLine, Ban, Box, Camera, Lock, CircleCheck, CircleX, Clock, ExternalLink, History as HistoryIcon, RotateCw, CloudUpload, Globe, Monitor, Radar, Router, Search, Smartphone, Database, Download, File as FileIcon, Folder, FolderPlus, GripVertical, HeartPulse, HardDrive, LayoutDashboard, Loader2, Menu, Network, Package,
  Pencil, Plug, Plus, Printer, Server, Settings, ShieldCheck, Thermometer, Trash2, Wifi, X, Zap, Eye, Fan, Moon, Sun, MessageSquareHeart, Send, KeyRound, LogIn, LogOut, UserRound, Users, Copy
} from "lucide-react";
import "./index.css";

const APP_VERSION = "v0.5.0";

// Display preferences from the Settings page. A plain object so helpers outside components can
// read it; the Dashboard re-renders the whole app whenever settings change.
const prefs = {
  farm_name: "My Print Farm", farm_description: "One place to see what's happening across your print farm.", accent: "electric",
  temp_unit: "C", time_format: "12", temp_warn: 75, temp_hot: 85, storage_warn: 90, storage_critical: 97, memory_warn: 92,
  alert_printers: true, alert_devices: true, alert_services: true, alert_internet: true,
  network_history_days: 7, storage_history_days: 90, data_usage_days: 90, guest_view: false, update_check: true,
  fan_mode: "auto", fan_quiet_temp: 45, fan_full_temp: 65, fan_min_percent: 30,
};

// Accent colors. The app's styles use Tailwind's violet shades, so switching accent swaps
// those CSS variables. Green, amber and red are left out: they mean good/warning/error here.
const ACCENTS = {
  // LayerHound's brand blue. 400 is the exact logo color; 500 is deeper so white button text stays readable
  electric: { label: "Electric blue", 200: "#B3E3FF", 300: "#66C8FF", 400: "#00A3FF", 500: "#007ACC" },
  violet: { label: "Violet", 200: "oklch(89.4% 0.057 293.283)", 300: "oklch(81.1% 0.111 293.571)", 400: "oklch(70.2% 0.183 293.541)", 500: "oklch(60.6% 0.25 292.717)" },
  indigo: { label: "Indigo", 200: "oklch(87% 0.065 274.039)", 300: "oklch(78.5% 0.115 274.713)", 400: "oklch(67.3% 0.182 276.935)", 500: "oklch(58.5% 0.233 277.117)" },
  blue: { label: "Blue", 200: "oklch(88.2% 0.059 254.128)", 300: "oklch(80.9% 0.105 251.813)", 400: "oklch(70.7% 0.165 254.624)", 500: "oklch(62.3% 0.214 259.815)" },
  fuchsia: { label: "Fuchsia", 200: "oklch(90.3% 0.076 319.62)", 300: "oklch(83.3% 0.145 321.434)", 400: "oklch(74% 0.238 322.16)", 500: "oklch(66.7% 0.295 322.15)" },
  pink: { label: "Pink", 200: "oklch(89.9% 0.061 343.231)", 300: "oklch(82.3% 0.12 346.018)", 400: "oklch(71.8% 0.202 349.761)", 500: "oklch(65.6% 0.241 354.308)" },
};

function applyPrefs(next) {
  Object.assign(prefs, next);
  const root = document.documentElement.style;
  const light = document.documentElement.classList.contains("lh-light");
  const accent = ACCENTS[prefs.accent] ?? ACCENTS.violet;
  for (const shade of [200, 300, 400, 500]) {
    // Light mode: the pale accent shades are hard to read on white, so text uses the deeper 500
    if (light) root.setProperty(`--color-violet-${shade}`, accent[Math.max(shade, 500)]);
    else if (prefs.accent === "violet" || !ACCENTS[prefs.accent]) root.removeProperty(`--color-violet-${shade}`);
    else root.setProperty(`--color-violet-${shade}`, accent[shade]);
  }
  // Product name first, then the customer's farm name
  document.title = prefs.farm_name ? `LayerHound · ${prefs.farm_name}` : "LayerHound";
}

const toUnit = c => c == null ? null : prefs.temp_unit === "F" ? Math.round((c * 9 / 5 + 32) * 10) / 10 : c;
const fromUnit = v => prefs.temp_unit === "F" ? Math.round((v - 32) * 5 / 9) : Math.round(v);
function fmtTemp(c, digits = 1) {
  if (c == null) return "—";
  const v = toUnit(c);
  return `${digits === 0 ? Math.round(v) : Math.round(v * 10) / 10}°${prefs.temp_unit}`;
}
const fmtDate = (d, opts) => new Date(d).toLocaleString([], { ...opts, hour12: prefs.time_format === "12" });

// Light or dark is chosen per device (each browser remembers its own), not for the whole farm.
// "system" follows the device's own light/dark setting.
const THEMES = [["dark", "Dark", Moon], ["light", "Light", Sun], ["system", "Match device", Monitor]];
function readTheme() { try { return localStorage.getItem("lh-theme") || "dark"; } catch { return "dark"; } }
const systemLight = () => window.matchMedia?.("(prefers-color-scheme: light)").matches;
function applyTheme(choice = readTheme()) {
  const light = choice === "light" || (choice === "system" && systemLight());
  document.documentElement.classList.toggle("lh-light", light);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", light ? "#f3f5f8" : "#090b12");
  applyPrefs({});
}
function setTheme(choice) {
  try { localStorage.setItem("lh-theme", choice); } catch { /* not saved, still applied */ }
  applyTheme(choice);
  window.dispatchEvent(new Event("lh-theme"));
}
window.matchMedia?.("(prefers-color-scheme: light)").addEventListener?.("change", () => { if (readTheme() === "system") applyTheme(); });

function useTheme() {
  const [theme, setLocal] = useState(readTheme);
  useEffect(() => { const on = () => setLocal(readTheme()); window.addEventListener("lh-theme", on); return () => window.removeEventListener("lh-theme", on); }, []);
  return [theme, setTheme];
}

// Three small buttons (dark / light / match device), used in the sidebar
function ThemeButtons() {
  const [theme, choose] = useTheme();
  return (
    <div className="flex rounded-lg border border-white/8 p-0.5" role="radiogroup" aria-label="Theme">
      {THEMES.map(([v, label, Icon]) => (
        <button key={v} type="button" role="radio" aria-checked={theme === v} title={label} aria-label={label} onClick={() => choose(v)}
          className={`rounded-md p-1.5 ${theme === v ? "bg-violet-500/15 text-violet-300" : "text-slate-500 hover:text-slate-300"}`}><Icon size={14} /></button>
      ))}
    </div>
  );
}

// Who is using the dashboard: { username, role: "admin" | "viewer", kind: "user" | "guest" | "key" }
const session = { user: null };
const isAdmin = () => session.user?.role === "admin";
function applySession(user) {
  session.user = user;
  // Viewers and guests only look; index.css hides controls marked data-admin
  document.documentElement.classList.toggle("lh-viewer", !!user && user.role !== "admin");
}

// Shown only when the backend's /api/printers can't be reached.
const DEMO_PRINTERS = [
  { id: "demo-1", name: "Printer 01", model: "Klipper", state: "printing", job: "Benchy_PLA_0.2mm.gcode", progress: 72, eta: "1h 24m", nozzle: 214, bed: 58, layer: "118 / 164" },
  { id: "demo-2", name: "Printer 02", model: "OctoPrint", state: "idle", job: null, progress: 0, eta: "—", nozzle: 31, bed: 29, layer: "—" },
  { id: "demo-3", name: "Printer 03", model: "Klipper", state: "complete", job: "NASCAR_Display_Base.gcode", progress: 100, eta: "Complete", nozzle: 29, bed: 27, layer: "142 / 142" },
  { id: "demo-4", name: "Printer 04", model: "Klipper", state: "offline", job: null, progress: 0, eta: "—", nozzle: 0, bed: 0, layer: "—" },
];

const PAGE_TITLES = {
  dashboard: "Operations Dashboard",
  printers: "Print Farm",
  history: "Print History",
  server: "Server",
  storage: "Storage",
  network: "Network",
  services: "Services",
  settings: "Settings",
  feedback: "Send Feedback",
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
    layer: p.layer ?? null,
    totalLayers: p.total_layers ?? null,
    hasThumbnail: !!p.has_thumbnail,
    hasCamera: !!p.has_camera,
    cameraUrl: p.camera_url ?? "",
  };
}

// The slicer's preview of the part being printed. The file name in the URL makes the
// browser fetch a fresh image when a new print starts.
function PartThumb({ printer, size = 40, className = "" }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [printer.job]);
  if (!printer.hasThumbnail || !printer.job || failed) return null;
  return <img src={`/api/printers/${printer.id}/thumbnail?f=${encodeURIComponent(printer.job)}`} alt="" width={size} height={size} onError={() => setFailed(true)}
    className={`shrink-0 rounded-lg bg-white/[.04] object-contain ${className}`} style={{ width: size, height: size }} />;
}

const layerText = p => p.totalLayers ? `Layer ${p.layer ?? "?"} / ${p.totalLayers}` : null;

// Camera view for the details panel: a fresh frame every 2 seconds while the panel is open
function CameraView({ printer }) {
  const [tick, setTick] = useState(0);
  const [paused, setPaused] = useState(false);
  const [state, setState] = useState("loading");
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setTick(n => n + 1), 2000);
    return () => clearInterval(t);
  }, [paused]);
  const src = `/api/printers/${printer.id}/camera?t=${tick}`;
  return (
    <div className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-600"><Camera size={14} /> Camera</div>
        <div className="flex items-center gap-1">
          {state === "ok" && <span className="mr-1 flex items-center gap-1.5 text-[11px] text-slate-500"><StatusDot tone={paused ? "off" : "good"} /> {paused ? "Paused" : "Live"}</span>}
          <button onClick={() => setPaused(v => !v)} className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/5 hover:text-white">{paused ? "Resume" : "Pause"}</button>
          <a href={src} target="_blank" rel="noopener noreferrer" className="rounded-lg p-1.5 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Open camera image in a new tab"><ExternalLink size={14} /></a>
        </div>
      </div>
      <div className="relative mt-3 aspect-video overflow-hidden rounded-xl bg-black/40">
        <img key={paused ? "p" : "l"} src={src} alt={`${printer.name} camera`} className={`h-full w-full object-contain ${state === "ok" ? "" : "opacity-0"}`}
          onLoad={() => setState("ok")} onError={() => setState("error")} />
        {state !== "ok" && (
          <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-slate-500">
            {state === "loading" ? <span className="flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Connecting to camera…</span> : "Camera unavailable right now. It will keep retrying."}
          </div>
        )}
      </div>
    </div>
  );
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
  if (!usingDemo && prefs.alert_printers) for (const p of printers) if (p.state === "offline") list.push({ tone: "warn", text: `${p.name} is offline` });
  if (system && !apiError) {
    const t = system.temperature_c;
    if (t != null && t >= prefs.temp_hot) list.push({ tone: "bad", text: `Server is overheating (${fmtTemp(t)})` });
    else if (t != null && t >= prefs.temp_warn) list.push({ tone: "warn", text: `Server is running hot (${fmtTemp(t)})` });
    if (system.storage_percent >= prefs.storage_warn) list.push({ tone: system.storage_percent >= prefs.storage_critical ? "bad" : "warn", text: `Main drive is ${Math.round(system.storage_percent)}% full` });
    if (system.memory_percent >= prefs.memory_warn) list.push({ tone: "warn", text: `Memory is ${Math.round(system.memory_percent)}% used` });
    if (system.database && !system.database.ok) list.push({ tone: "bad", text: "Printer database error" });
    if (prefs.alert_internet && system.network?.internet_up === false) list.push({ tone: "bad", text: "Internet is down" });
    if (prefs.alert_devices) for (const name of system.network?.offline_devices ?? []) list.push({ tone: "warn", text: `${name} is not responding` });
    if (prefs.alert_services) for (const sv of system.services?.services ?? []) if (sv.up === false) list.push({ tone: "warn", text: `${sv.name} is down` });
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
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
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

      <div className="mt-4 flex items-center gap-3">
        <PartThumb printer={printer} size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex justify-between text-xs">
            <span className="truncate pr-3 text-slate-400" title={printer.job || undefined}>{printer.job || "No active job"}</span>
            <span className="font-semibold text-white">{printer.progress}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/6">
            <div className={`h-full rounded-full ${printer.state === "printing" ? "bg-violet-500" : "bg-slate-600"}`} style={{ width: `${printer.progress}%` }} />
          </div>
          {layerText(printer) && <div className="mt-1.5 text-[11px] tabular-nums text-slate-500">{layerText(printer)}</div>}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-1.5 whitespace-nowrap border-t border-white/6 pt-3 text-xs">
        <div><div className="text-slate-600">Nozzle</div><div className="mt-1 font-medium text-slate-300">{printer.nozzle ? fmtTemp(printer.nozzle, 0) : "—"}</div></div>
        <div><div className="text-slate-600">Bed</div><div className="mt-1 font-medium text-slate-300">{printer.bed ? fmtTemp(printer.bed, 0) : "—"}</div></div>
        <div><div className="text-slate-600">ETA</div><div className="mt-1 font-medium text-slate-300">{printer.eta}</div></div>
      </div>
      <div className="mt-3 flex items-center justify-end gap-1 text-xs text-slate-600 group-hover:text-slate-300">
        Details <ChevronRight size={14} />
      </div>
    </button>
  );
}

// The LayerHound wordmark is fixed product branding; the farm name sits under it
function BrandMark() {
  return <div className="text-lg font-black uppercase leading-tight tracking-tight text-white">Layer<span className="text-violet-400">Hound</span></div>;
}

function Sidebar({ page, setPage, open, setOpen, usingDemo, summary, onSignOut, onSignIn }) {
  const items = [
    ["Dashboard", LayoutDashboard, "dashboard"],
    ["Print Farm", Printer, "printers"],
    ["History", HistoryIcon, "history"],
    ["Server", Server, "server"],
    ["Storage", HardDrive, "storage"],
    ["Network", Network, "network"],
    ["Services", Activity, "services"],
    ["Settings", Settings, "settings"],
    ["Send feedback", MessageSquareHeart, "feedback"],
  ];
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/60 lg:hidden" onClick={() => setOpen(false)} />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/7 bg-[var(--lh-input)] transition-transform lg:sticky lg:top-0 lg:h-screen lg:self-start lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex h-20 items-center justify-between px-5">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/brand/layerhound-mascot.png" alt="" className="h-11 w-11 shrink-0 object-contain" />
            <div className="min-w-0">
            <BrandMark />
            <div className="mt-0.5 truncate text-[11px] font-semibold text-slate-400" title={prefs.farm_name}>{prefs.farm_name}</div>
            </div>
          </div>
          <button className="lg:hidden text-slate-500" onClick={() => setOpen(false)} aria-label="Close menu"><X size={20} /></button>
        </div>
        <div className="flex items-center justify-between px-5 pb-1">
          <span className="text-[11px] text-slate-600">Theme</span>
          <ThemeButtons />
        </div>
        <nav className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {items.map(([label, Icon, key]) => (
            <button key={key} onClick={() => { setPage(key); setOpen(false); }} className={`mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${page === key ? "bg-violet-500/12 text-white" : "text-slate-500 hover:bg-white/4 hover:text-slate-300"}`}>
              <Icon size={18} className={page === key ? "text-violet-400" : ""} />
              {label}
            </button>
          ))}
        </nav>
        <div className="m-3 rounded-xl border border-white/6 bg-white/[.025] p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-slate-300"><StatusDot tone={summary.tone} /> <span className="truncate">{summary.text}</span></div>
          <div className="mt-2 text-[10px] text-slate-600">LayerHound {APP_VERSION}{usingDemo ? " • Demo printers" : " • Live data"}</div>
        </div>
        <AccountBadge onSignOut={onSignOut} onSignIn={onSignIn} />
      </aside>
    </>
  );
}

// Signed-in user at the bottom of the sidebar, with sign out (or sign in, for guests)
function AccountBadge({ onSignOut, onSignIn }) {
  const u = session.user;
  if (!u) return null;
  const guest = u.kind !== "user";
  return (
    <div className="mx-3 mb-3 flex items-center gap-3 rounded-xl px-3 py-2">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-500/15 text-violet-300"><UserRound size={16} /></div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-slate-200">{guest ? "Guest" : u.username}</div>
        <div className="text-[11px] text-slate-600">{u.role === "admin" ? "Admin" : "View only"}</div>
      </div>
      {guest
        ? <button onClick={onSignIn} className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-violet-300 hover:bg-white/5"><LogIn size={14} /> Sign in</button>
        : <button onClick={onSignOut} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Sign out" title="Sign out"><LogOut size={16} /></button>}
    </div>
  );
}

// Centered card used by the welcome and sign-in screens
function AuthShell({ title, sub, children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--lh-bg)] px-4 py-10 text-slate-200">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src="/brand/layerhound-mascot.png" alt="" className="h-20 w-20 object-contain" />
          <div className="mt-3 text-2xl"><BrandMark /></div>
          {title && <h1 className="mt-4 text-lg font-semibold text-white">{title}</h1>}
          {sub && <p className="mt-1 text-sm text-slate-500">{sub}</p>}
        </div>
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">{children}</div>
      </div>
    </div>
  );
}

function PasswordInput({ value, onChange, autoComplete, placeholder, id }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input id={id} className={`${inputClass} pr-10`} type={show ? "text" : "password"} value={value} onChange={e => onChange(e.target.value)} autoComplete={autoComplete} placeholder={placeholder} maxLength={200} />
      <button type="button" onClick={() => setShow(v => !v)} className="absolute inset-y-0 right-0 px-3 text-slate-500 hover:text-white" aria-label={show ? "Hide password" : "Show password"}><Eye size={16} /></button>
    </div>
  );
}

// First run: no accounts exist yet. Name the farm and create the admin account.
function WelcomeScreen({ farmName, onDone }) {
  const [f, setF] = useState({ farm_name: farmName && farmName !== "My Print Farm" ? farmName : "", username: "admin", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = k => v => setF(x => ({ ...x, [k]: v }));
  const submit = async e => {
    e.preventDefault(); setError("");
    if (f.password.length < 8) return setError("Passwords need at least 8 characters.");
    if (f.password !== f.confirm) return setError("The passwords don't match.");
    setBusy(true);
    try { await setupLayerHound({ farm_name: f.farm_name.trim() || "My Print Farm", username: f.username.trim(), password: f.password }); onDone(); }
    catch (err) { setError(err.message); setBusy(false); }
  };
  return (
    <AuthShell title="Welcome to LayerHound" sub="Two quick things and you're in.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Farm name" hint="Shown across the dashboard. You can change it later."><input className={inputClass} maxLength={40} placeholder="My Print Farm" value={f.farm_name} onChange={e => set("farm_name")(e.target.value)} autoFocus /></Field>
        <div className="border-t border-white/6 pt-4">
          <div className="mb-3 text-xs text-slate-500">Create the admin account. Admins can change everything; you can add view-only accounts later in Settings.</div>
          <div className="space-y-3">
            <Field label="Username"><input className={inputClass} maxLength={40} value={f.username} onChange={e => set("username")(e.target.value)} autoComplete="username" /></Field>
            <Field label="Password" hint="At least 8 characters."><PasswordInput value={f.password} onChange={set("password")} autoComplete="new-password" /></Field>
            <Field label="Type it again"><PasswordInput value={f.confirm} onChange={set("confirm")} autoComplete="new-password" /></Field>
          </div>
        </div>
        {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-sm text-red-200">{error}</div>}
        <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
          {busy && <Loader2 size={15} className="animate-spin" />} {busy ? "Setting up…" : "Finish setup"}
        </button>
      </form>
    </AuthShell>
  );
}

function LoginScreen({ farmName, onDone, onCancel }) {
  const [f, setF] = useState({ username: "", password: "", remember: true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [forgot, setForgot] = useState(false);
  const submit = async e => {
    e.preventDefault(); setError(""); setBusy(true);
    try { await login(f.username.trim(), f.password, f.remember); onDone(); }
    catch (err) { setError(err.message); setBusy(false); setF(x => ({ ...x, password: "" })); }
  };
  return (
    <AuthShell title={farmName} sub="Sign in to continue.">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Username"><input className={inputClass} maxLength={40} value={f.username} onChange={e => setF(x => ({ ...x, username: e.target.value }))} autoComplete="username" autoFocus /></Field>
        <Field label="Password"><PasswordInput value={f.password} onChange={v => setF(x => ({ ...x, password: v }))} autoComplete="current-password" /></Field>
        <label className="flex items-center gap-2 pt-1 text-sm text-slate-400">
          <input type="checkbox" checked={f.remember} onChange={e => setF(x => ({ ...x, remember: e.target.checked }))} className="accent-violet-500" /> Keep me signed in for 30 days
        </label>
        {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-sm text-red-200">{error}</div>}
        <button type="submit" disabled={busy || !f.username || !f.password} className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
          {busy && <Loader2 size={15} className="animate-spin" />} {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <div className="mt-4 border-t border-white/6 pt-3 text-center text-xs text-slate-500">
        {forgot
          ? <p>On the LayerHound board (over SSH, or with a keyboard and screen), run <code className="rounded bg-white/5 px-1.5 py-0.5 text-slate-300">layerhound reset-password</code></p>
          : <button onClick={() => setForgot(true)} className="hover:text-slate-300">Forgot your password?</button>}
        {onCancel && <div className="mt-2"><button onClick={onCancel} className="hover:text-slate-300">Back to the dashboard</button></div>}
      </div>
    </AuthShell>
  );
}

// Shown to a phone on the "LayerHound-Setup" hotspot: pick the home Wi-Fi, and on a new board
// also name the farm and create the admin account, all in one go
function HotspotScreen({ setupRequired, farmName, onDone }) {
  const [info, setInfo] = useState(null);
  const [net, setNet] = useState({ ssid: "", other: false, password: "" });
  const [acct, setAcct] = useState({ farm_name: farmName && farmName !== "My Print Farm" ? farmName : "", username: "admin", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [joining, setJoining] = useState(null);
  useEffect(() => { getHotspot().then(setInfo).catch(e => setError(e.message)); }, []);
  const chosen = info?.networks?.find(n => n.ssid === net.ssid);
  const needsPassword = net.other || (chosen?.secure && !chosen?.saved);
  const submit = async e => {
    e.preventDefault(); setError("");
    if (!net.ssid.trim()) return setError("Pick your Wi-Fi network.");
    if (needsPassword && net.other === false && !net.password) return setError("Enter the Wi-Fi password.");
    if (setupRequired) {
      if (acct.password.length < 8) return setError("The admin password needs at least 8 characters.");
      if (acct.password !== acct.confirm) return setError("The admin passwords don't match.");
    }
    setBusy(true);
    try {
      if (setupRequired) await setupLayerHound({ farm_name: acct.farm_name.trim() || "My Print Farm", username: acct.username.trim(), password: acct.password });
      setJoining(await joinWifi(net.ssid.trim(), net.password));
    } catch (err) { setError(err.message); setBusy(false); if (setupRequired) onDone(); }
  };
  if (joining) return (
    <AuthShell title={`Joining ${joining.network}…`}>
      <div className="space-y-3 text-sm text-slate-300">
        <p>LayerHound is switching to your Wi-Fi now, so this phone will drop off <span className="text-white">LayerHound-Setup</span>.</p>
        <ol className="list-decimal space-y-2 pl-5">
          <li>Connect this phone back to <span className="text-white">{joining.network}</span>.</li>
          <li>Open <a href={`http://${joining.hostname}`} className="font-medium text-violet-300">http://{joining.hostname}</a> and sign in.</li>
        </ol>
        <p className="text-xs text-slate-500">If the password was wrong, LayerHound-Setup comes back within a minute. Join it again to see what happened and try again.</p>
      </div>
    </AuthShell>
  );
  return (
    <AuthShell title="Connect LayerHound to your Wi-Fi" sub={setupRequired ? "Then name your farm and create the admin account." : "Pick the network LayerHound should use."}>
      <form onSubmit={submit} className="space-y-4">
        {info?.last_error && <div className="rounded-lg border border-amber-500/20 bg-amber-500/6 px-3 py-2 text-sm text-amber-100">{info.last_error} Check the password and try again.</div>}
        <div>
          <div className="mb-2 text-xs font-medium text-slate-400">Wi-Fi network</div>
          {!info ? <div className="flex items-center gap-2 py-2 text-sm text-slate-500"><Loader2 size={15} className="animate-spin" /> Loading networks…</div> : (
            <div className="max-h-56 space-y-1 overflow-y-auto">
              {(info.networks ?? []).map(n => (
                <label key={n.ssid} className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${net.ssid === n.ssid && !net.other ? "border-violet-400 bg-violet-500/10 text-white" : "border-white/8 text-slate-300 hover:bg-white/[.03]"}`}>
                  <input type="radio" name="ssid" className="sr-only" checked={net.ssid === n.ssid && !net.other} onChange={() => setNet({ ssid: n.ssid, other: false, password: "" })} />
                  <SignalBars signal={n.signal} />
                  <span className="min-w-0 flex-1 truncate">{n.ssid}</span>
                  {n.saved ? <span className="text-[11px] text-slate-500">Saved</span> : n.secure && <Lock size={13} className="text-slate-500" aria-label="Needs a password" />}
                </label>
              ))}
              <label className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${net.other ? "border-violet-400 bg-violet-500/10 text-white" : "border-white/8 text-slate-400 hover:bg-white/[.03]"}`}>
                <input type="radio" name="ssid" className="sr-only" checked={net.other} onChange={() => setNet({ ssid: "", other: true, password: "" })} />
                <Plus size={14} /> Other network (hidden or not listed)
              </label>
            </div>
          )}
        </div>
        {net.other && <Field label="Network name"><input className={inputClass} maxLength={64} value={net.ssid} onChange={e => setNet(x => ({ ...x, ssid: e.target.value }))} autoComplete="off" autoCapitalize="none" /></Field>}
        {(needsPassword || net.other) && <Field label="Wi-Fi password" hint={net.other ? "Leave blank if the network has no password." : undefined}><PasswordInput value={net.password} onChange={v => setNet(x => ({ ...x, password: v }))} autoComplete="off" /></Field>}
        {setupRequired && (
          <div className="space-y-3 border-t border-white/6 pt-4">
            <Field label="Farm name" hint="You can change it later."><input className={inputClass} maxLength={40} placeholder="My Print Farm" value={acct.farm_name} onChange={e => setAcct(x => ({ ...x, farm_name: e.target.value }))} /></Field>
            <div className="text-xs text-slate-500">Create the admin account. You'll use it to sign in once LayerHound is on your Wi-Fi.</div>
            <Field label="Username"><input className={inputClass} maxLength={40} value={acct.username} onChange={e => setAcct(x => ({ ...x, username: e.target.value }))} autoComplete="username" autoCapitalize="none" /></Field>
            <Field label="Password" hint="At least 8 characters."><PasswordInput value={acct.password} onChange={v => setAcct(x => ({ ...x, password: v }))} autoComplete="new-password" /></Field>
            <Field label="Type it again"><PasswordInput value={acct.confirm} onChange={v => setAcct(x => ({ ...x, confirm: v }))} autoComplete="new-password" /></Field>
          </div>
        )}
        {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-sm text-red-200">{error}</div>}
        <button type="submit" disabled={busy || !info} className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
          {busy && <Loader2 size={15} className="animate-spin" />} {busy ? "Connecting…" : setupRequired ? "Finish setup" : "Connect"}
        </button>
      </form>
    </AuthShell>
  );
}

// This page's own build: the hashed name of the main script it loaded (none in development)
const MY_BUILD = import.meta.env.DEV ? null : (document.querySelector('script[type="module"][src*="/assets/"]')?.getAttribute("src")?.split("/").pop() ?? null);
const UPDATE_CHECK_EVERY = 60000;

// After LayerHound is updated, an open tab is still running the old version until it reloads.
// Every minute (and when the window comes back into focus), compare with what the board serves.
function UpdateBanner() {
  const [newer, setNewer] = useState(false);
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if (!MY_BUILD) return;
    let stop = false;
    const check = async () => { try { const h = await getHealth(); if (!stop && h.build && h.build !== MY_BUILD) setNewer(true); } catch { /* board restarting; try again later */ } };
    const timer = setInterval(check, UPDATE_CHECK_EVERY);
    const onFocus = () => check();
    window.addEventListener("focus", onFocus);
    check();
    return () => { stop = true; clearInterval(timer); window.removeEventListener("focus", onFocus); };
  }, []);
  if (!newer || hidden) return null;
  return (
    <div role="status" className="fixed inset-x-0 top-0 z-[60] flex justify-center px-4 pt-3">
      <div className="flex max-w-full items-center gap-3 rounded-xl border border-violet-400/30 bg-[var(--lh-card)] px-4 py-2.5 text-sm shadow-lg shadow-black/30">
        <RotateCw size={16} className="shrink-0 text-violet-400" />
        <span className="text-slate-200">LayerHound has been updated. Reload to get the new version.</span>
        <button onClick={() => location.reload()} className="shrink-0 rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-medium text-[#fff] hover:bg-violet-400">Reload</button>
        <button onClick={() => setHidden(true)} className="shrink-0 rounded-lg p-1 text-slate-500 hover:text-white" aria-label="Not now"><X size={15} /></button>
      </div>
    </div>
  );
}

// Loads who is signed in, then shows the welcome screen, the sign-in screen or the dashboard
function App() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const check = useCallback(async () => {
    // The farm name and accent color come with the status, so the sign-in screen looks right too
    try { const s = await getAuthStatus(); applySession(s.user); applyPrefs({ farm_name: s.farm_name, accent: s.accent }); setStatus(s); setError(""); }
    catch (e) { setError(e.message || "Can't reach LayerHound"); }
  }, []);
  useEffect(() => { check(); }, [check]);
  useEffect(() => {
    // Any API call that finds the session gone (expired, signed out elsewhere) brings back the sign-in screen
    const onSignedOut = () => check();
    window.addEventListener("layerhound:signed-out", onSignedOut);
    return () => window.removeEventListener("layerhound:signed-out", onSignedOut);
  }, [check]);
  const signedIn = () => { setSigningIn(false); check(); };
  const signOut = async () => { try { await logout(); } catch { /* the cookie is cleared either way */ } check(); };

  if (!status) return (
    <AuthShell>
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-slate-400">
        {error ? <><CircleX size={16} className="text-red-300" /> {error}. <button onClick={check} className="text-violet-300 hover:text-violet-200">Try again</button></> : <><Loader2 size={16} className="animate-spin" /> Loading…</>}
      </div>
    </AuthShell>
  );
  // On the setup hotspot: Wi-Fi setup (plus the admin account on a new board). Once accounts exist, an admin signs in first.
  if (status.on_hotspot && (status.setup_required || status.user?.role === "admin") && !signingIn) return <HotspotScreen setupRequired={status.setup_required} farmName={status.farm_name} onDone={check} />;
  if (status.setup_required) return <WelcomeScreen farmName={status.farm_name} onDone={signedIn} />;
  if (!status.user || signingIn) return <LoginScreen farmName={status.farm_name} onDone={signedIn} onCancel={status.user ? () => setSigningIn(false) : null} />;
  // key: a different person signing in gets a fresh dashboard
  return <Dashboard key={`${status.user.kind}:${status.user.username}`} onSignOut={signOut} onSignIn={() => setSigningIn(true)} />;
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
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-white/10 bg-[var(--lh-sunken)] p-6 shadow-2xl">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-violet-400">Printer detail</div>
          <h2 className="mt-1 text-xl font-semibold text-white">{printer.name}</h2>
          {printer.address && <div className="mt-1 text-xs text-slate-500">{printer.address}</div>}
        </div>
        <button onClick={close} className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white" aria-label="Close"><X size={20} /></button>
      </div>
      <div className="mt-8 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
        <div className="flex items-start gap-4">
          <PartThumb printer={printer} size={96} className="p-1" />
          <div className="min-w-0">
            <div className="text-sm text-slate-400">Current job</div>
            <div className="mt-2 break-words font-medium text-white">{printer.job || "No active print"}</div>
            {layerText(printer) && <div className="mt-1 text-xs tabular-nums text-slate-500">{layerText(printer)}</div>}
          </div>
        </div>
        <div className="mt-5 text-4xl font-bold text-white">{printer.progress}%</div>
        <div className="mt-2 h-2 rounded-full bg-white/6"><div className="h-full rounded-full bg-violet-500" style={{ width: `${printer.progress}%` }} /></div>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <Metric icon={Thermometer} label="Nozzle" value={printer.nozzle ? fmtTemp(printer.nozzle) : "—"} sub={printer.nozzleTarget ? `Target ${fmtTemp(printer.nozzleTarget, 0)}` : undefined} />
          <Metric icon={Thermometer} label="Bed" value={printer.bed ? fmtTemp(printer.bed) : "—"} sub={printer.bedTarget ? `Target ${fmtTemp(printer.bedTarget, 0)}` : undefined} />
        </div>
      </div>
      {printer.hasCamera && !isDemo && <CameraView printer={printer} />}
      <div className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
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
          <button data-admin onClick={() => onEdit(printer)} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06]">
            <Pencil size={16} /> Edit printer
          </button>
          <button data-admin onClick={runTest} disabled={testing} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06] disabled:opacity-50">
            {testing ? <Loader2 size={16} className="animate-spin" /> : <Plug size={16} />} {testing ? "Testing…" : "Test connection"}
          </button>
          {testResult && (
            <div className={`rounded-xl border px-4 py-3 text-xs ${testResult.ok ? "border-emerald-500/20 bg-emerald-500/6 text-emerald-300" : "border-red-500/20 bg-red-500/6 text-red-300"}`}>{testResult.message}</div>
          )}
          {confirmRemove ? (
            <div className="rounded-xl border border-red-500/20 bg-red-500/6 p-4">
              <div className="text-sm text-red-200">Remove {printer.name} from the dashboard?</div>
              <div className="mt-3 flex gap-2">
                <button onClick={remove} disabled={removing} className="flex-1 rounded-lg bg-red-500/80 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-red-500 disabled:opacity-50">{removing ? "Removing…" : "Remove printer"}</button>
                <button onClick={() => setConfirmRemove(false)} className="flex-1 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-300 hover:bg-white/5">Keep it</button>
              </div>
            </div>
          ) : (
            <button data-admin onClick={() => setConfirmRemove(true)} className="flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm text-slate-500 hover:bg-red-500/6 hover:text-red-300">
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

const inputClass = "w-full rounded-lg border border-white/10 bg-[var(--lh-input)] px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-violet-400 focus:outline-none";

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
    ? { name: printer.name, type: PRINTER_TYPES[printer.type] ? printer.type : "moonraker", ...splitAddress(printer.address), api_key: "", serial: printer.serial ?? "", camera_url: printer.cameraUrl ?? "" }
    : { name: initial?.name ?? "", type: initial?.type ?? "moonraker", host: initial?.host ?? "", port: initial?.port ? String(initial.port) : "", api_key: "", serial: initial?.serial ?? "", camera_url: "" });
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
    // Blank clears a custom camera address (LayerHound then looks for one automatically)
    if (editing || form.camera_url.trim()) payload.camera_url = form.camera_url.trim();
    try { await (editing ? updatePrinter(printer.id, payload) : createPrinter(payload)); onSaved(); onClose(); }
    catch (e) {
      const msg = typeof e.message === "string" && e.message !== "[object Object]" ? e.message : "The server rejected this printer. Check the uvicorn terminal for details.";
      setError(msg);
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="printer-form-title" className="w-full max-w-md rounded-2xl border border-white/10 bg-[var(--lh-sunken)] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
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
          <Field label="Camera URL (optional)" hint={form.type === "bambu" ? "Leave blank: Bambu P1 and A1 cameras are found automatically." : "Leave blank to use the camera Klipper lists, if any. Or paste a snapshot or MJPEG stream address."}>
            <input className={inputClass} autoComplete="off" spellCheck={false} placeholder="http://192.168.1.50/webcam/?action=snapshot" value={form.camera_url} onChange={set("camera_url")} />
          </Field>
          {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-white/5 hover:text-white">Cancel</button>
          <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
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
    <li data-reorder-index={index} className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors ${dragging === index ? "border-violet-400/60 bg-violet-500/10" : "border-white/8 bg-[var(--lh-card)]"}`}>
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
            <button onClick={saveOrder} disabled={savingOrder} className="flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
              {savingOrder && <Loader2 size={15} className="animate-spin" />} {savingOrder ? "Saving…" : "Save order"}
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            {!usingDemo && printers.length > 1 && (
              <button data-admin onClick={() => setOrder(printers.map(p => p.id))} className="flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-4 py-2.5 text-sm font-medium text-slate-200 hover:bg-white/[.06]">
                <ArrowUpDown size={16} /> Reorder
              </button>
            )}
            <button data-admin onClick={onAdd} className="flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-300">
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
          <button data-admin onClick={onAdd} className="mt-5 flex items-center gap-2 rounded-xl bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400"><Plus size={16} /> Add printer</button>
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

// Uses the thresholds from Settings (defaults suit small ARM boards, which throttle around 85°C)
function tempStatus(c) {
  if (c == null) return null;
  if (c >= prefs.temp_hot) return { label: "Overheating", cls: "text-red-300", Icon: AlertTriangle };
  if (c >= prefs.temp_warn) return { label: "Running hot", cls: "text-amber-300", Icon: AlertTriangle };
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
    <div className={`rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5 ${className}`}>
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
  const timeLabel = t => fmtDate(t * 1000, span >= 86400 ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" } : { hour: "numeric", minute: "2-digit", second: "2-digit" });

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
    <div className={bare ? "" : "rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5"}>
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
                <line x1={L} x2={width - R} y1={y(v)} y2={y(v)} style={{ stroke: "var(--lh-grid)" }} />
                <text x={L - 6} y={y(v) + 3.5} textAnchor="end" className="fill-slate-600 text-[10px] tabular-nums">{Math.round(v)}</text>
              </g>
            ))}
            <path d={area} style={{ fill: "color-mix(in oklab, var(--color-violet-500) 12%, transparent)" }} />
            <path d={line} fill="none" style={{ stroke: "var(--color-violet-400)" }} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <text x={L} y={H - 4} className="fill-slate-600 text-[10px]">{ago}</text>
            <text x={width - R} y={H - 4} textAnchor="end" className="fill-slate-600 text-[10px]">now</text>
            {hover && (
              <g>
                <line x1={x(hover.t)} x2={x(hover.t)} y1={T} y2={H - B} style={{ stroke: "var(--lh-grid-strong)" }} />
                <circle cx={x(hover.t)} cy={y(hover[field])} r="4.5" style={{ fill: "var(--color-violet-400)", stroke: "var(--lh-card)" }} strokeWidth="2" />
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
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Thermometer size={15} /> Temperature</div>
          <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{info.temperature_c != null ? fmtTemp(info.temperature_c) : "—"}</div>
          {status
            ? <div className={`mt-1 flex items-center gap-1 text-xs ${status.cls}`}><status.Icon size={12} /> {status.label}</div>
            : <div className="mt-1 text-xs text-slate-500">No sensor on this machine</div>}
          {info.fan?.available && <div className="mt-2 flex items-center gap-1.5 border-t border-white/6 pt-2 text-xs text-slate-400"><Fan size={13} className={info.fan.percent ? "animate-spin [animation-duration:2s]" : ""} /> Fan {info.fan.percent ?? "—"}% · {!info.fan.controlled ? "not controlled" : info.fan.mode === "full" ? "full speed" : "auto"}</div>}
        </div>
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
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
        <HistoryChart title="Temperature" points={history.map(p => ({ ...p, temp: toUnit(p.temp) }))} field="temp" unit={`°${prefs.temp_unit}`} empty={info.temperature_c == null ? "This machine doesn't report temperature. It will show up on the board." : undefined} />
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
          <Row label="Last boot" value={fmtDate(info.boot_time, { dateStyle: "medium", timeStyle: "short" })} />
        </Card>
        <Card title="Network addresses" icon={Wifi} sub="Use these to reach the dashboard from other devices.">
          {network.addresses.length ? network.addresses.map(a => <Row key={a.interface + a.address} label={a.interface} value={a.address} />) : <div className="text-sm text-slate-500">No network address</div>}
        </Card>
        <Card title="Temperature sensors" icon={Thermometer} className="md:col-span-2 xl:col-span-1">
          {info.sensors.length ? info.sensors.map(t => <Row key={t.name} label={t.name} value={fmtTemp(t.celsius)} />) : <div className="text-sm text-slate-500">This machine doesn't report temperatures. On the board, each sensor (CPU cores, GPU, NVMe) will be listed here.</div>}
        </Card>
      </section>

      <section className="mt-4">
        <Card title="Dashboard service" icon={Activity}>
          <div className="grid gap-x-8 md:grid-cols-3">
            <Row label="Memory used" value={`${info.app.memory_mb} MB`} />
            <Row label="Python" value={info.python} />
            <Row label="Running since" value={fmtDate(info.app.started, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} />
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
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
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
      {holdsFiles && <div className="mt-3 flex items-center gap-1.5 text-xs text-violet-300"><Folder size={13} /> LayerHound Files is stored here</div>}
      <div className="mt-4 border-t border-white/6 pt-3">
        {h.available ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            {h.wear_percent != null && <div><div className="text-slate-600">Wear</div><div className="mt-0.5 text-slate-200">{h.wear_percent}% of rated life</div></div>}
            {h.temperature_c != null && <div><div className="text-slate-600">Temperature</div><div className="mt-0.5 text-slate-200">{fmtTemp(h.temperature_c, 0)}</div></div>}
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
      className={`relative rounded-2xl border bg-[var(--lh-card)] p-5 transition-colors ${dragOver ? "border-violet-400/60" : "border-white/8"}`}
      onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragOver(true); } }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false); }}
      onDrop={e => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files); }}
    >
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0">
          <h2 className="font-semibold text-white">LayerHound Files</h2>
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
          <button data-admin onClick={() => { setCreating(true); setNewName(""); }} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><FolderPlus size={16} /> New folder</button>
          <button data-admin onClick={() => picker.current?.click()} className="flex items-center gap-2 rounded-xl bg-violet-500 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400"><CloudUpload size={16} /> Upload</button>
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
            <button type="submit" className="rounded-lg bg-violet-500 px-3 py-1.5 text-sm text-[#fff] hover:bg-violet-400">Create</button>
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
                      <button type="submit" className="rounded-lg bg-violet-500 px-3 text-sm text-[#fff] hover:bg-violet-400">Save</button>
                    </form>
                  ) : it.type === "folder" ? (
                    <button onClick={() => setPath(it.path)} className="block max-w-full truncate text-left text-sm text-white hover:text-violet-300">{it.name}</button>
                  ) : (
                    <a href={downloadUrl(it.path)} className="block truncate text-sm text-slate-200 hover:text-violet-300" title={`Download ${it.name}`}>{it.name}</a>
                  )}
                  <div className="mt-0.5 text-[11px] text-slate-600">
                    {it.type === "folder" ? `${it.items} file${it.items === 1 ? "" : "s"} · ` : ""}{fmtDate(it.modified, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}
                  </div>
                </div>
                <div className="hidden w-28 shrink-0 sm:block">
                  <div className="text-right text-xs tabular-nums text-slate-400">{formatBytes(it.size)}</div>
                  <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/6" title="Share of this folder's space"><div className="h-full rounded-full bg-violet-500/70" style={{ width: `${(it.size / biggest) * 100}%` }} /></div>
                </div>
                {confirmDelete === it.path ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <button onClick={() => run(async () => { await deleteFile(it.path); setConfirmDelete(null); })} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-red-500">Move to trash</button>
                    <button onClick={() => setConfirmDelete(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                  </div>
                ) : (
                  <div className="flex shrink-0 items-center opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                    {it.type === "file" && <a href={downloadUrl(it.path)} className={iconBtn} aria-label={`Download ${it.name}`}><Download size={16} /></a>}
                    <button data-admin onClick={() => setRenaming({ path: it.path, name: it.name })} className={iconBtn} aria-label={`Rename ${it.name}`}><Pencil size={16} /></button>
                    <button data-admin onClick={() => setConfirmDelete(it.path)} className={`${iconBtn} hover:text-red-300`} aria-label={`Delete ${it.name}`}><Trash2 size={16} /></button>
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
              <button onClick={() => run(async () => { await emptyTrash(); setConfirmEmpty(false); })} className="rounded-lg bg-red-500/80 px-2.5 py-1 font-medium text-[#fff] hover:bg-red-500">Empty trash</button>
              <button onClick={() => setConfirmEmpty(false)} className="rounded-lg px-2 py-1 text-slate-400 hover:bg-white/5">Cancel</button>
            </span>
          ) : (
            <button data-admin onClick={() => setConfirmEmpty(true)} className="flex items-center gap-1.5 text-slate-500 hover:text-red-300"><Trash2 size={13} /> Trash: {filesInfo.trash_count} item{filesInfo.trash_count === 1 ? "" : "s"} ({formatBytes(filesInfo.trash_size)}) · Empty</button>
          )
        ) : <span className="flex items-center gap-1.5"><Trash2 size={13} /> Trash is empty</span>)}
      </div>

      {dragOver && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-2xl bg-violet-500/10 backdrop-blur-[1px]">
          <div className="flex items-center gap-2 rounded-xl border border-violet-400/40 bg-[var(--lh-card)] px-4 py-3 text-sm text-violet-200"><CloudUpload size={18} /> Drop to upload to {listing?.crumbs.at(-1)?.name ?? "All files"}</div>
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
        <p className="mt-2 text-sm text-slate-500">Drive health and the shared LayerHound Files folder.</p>
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
        return <div key={i} className={`flex-1 rounded-[2px] ${cls}`} title={`${fmtDate(at, { hour: "numeric" })}: ${v == null ? "no data" : `${Math.round(v * 100)}% up`}`} />;
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
        <button type="submit" disabled={saving} className="rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{saving ? "Saving…" : device ? "Save" : "Add device"}</button>
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
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div><h2 className="font-semibold text-white">Device monitor</h2><p className="mt-1 text-xs text-slate-600">{devices.length ? `${up} of ${devices.length} responding · checked every ${checkEvery / 60} min · last 24 hours` : "Add devices to watch"}</p></div>
        {!adding && <button data-admin onClick={() => { setAdding(true); setEditing(null); }} className="flex shrink-0 items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><Plus size={16} /> Add device</button>}
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
                  <button onClick={async () => { await deleteNetDevice(d.id); setConfirm(null); onChanged(); }} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-red-500">Remove</button>
                  <button onClick={() => setConfirm(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                </div>
              ) : (
                <div className="flex items-center justify-end sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                  <button data-admin onClick={() => { setEditing(d.id); setAdding(false); }} className={iconBtn} aria-label={`Edit ${d.name}`}><Pencil size={16} /></button>
                  <button data-admin onClick={() => setConfirm(d.id)} className={`${iconBtn} hover:text-red-300`} aria-label={`Remove ${d.name}`}><Trash2 size={16} /></button>
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
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
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
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h2 className="font-semibold text-white">Device discovery</h2>
          <p className="mt-1 text-xs text-slate-600">
            {scan?.running ? `Scanning ${scan.subnet ?? "the network"}…`
              : scan?.finished ? `Found ${scan.results.length} devices on ${scan.subnet}${printerCount ? `, including ${printerCount} printer${printerCount === 1 ? "" : "s"}` : ""} · ${fmtDate(scan.finished, { hour: "numeric", minute: "2-digit" })}`
              : "Find everything on your network, including printers the dashboard can add."}
          </p>
        </div>
        <button data-admin onClick={run} disabled={scan?.running} className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-60">
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
                        {r.printer && <button onClick={() => onAddPrinter({ ...r.printer, name: r.hostname?.split(".")[0] ?? "" })} className="rounded-lg bg-violet-500 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-violet-400">Add printer</button>}
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

function SignalBars({ signal }) {
  const bars = signal >= 75 ? 4 : signal >= 50 ? 3 : signal >= 30 ? 2 : 1;
  return (
    <span className="inline-flex items-end gap-[2px]" role="img" aria-label={`Signal ${signal}%`} title={`Signal ${signal}%`}>
      {[1, 2, 3, 4].map(b => <span key={b} className={`w-[3px] rounded-sm ${b <= bars ? "bg-violet-400" : "bg-white/12"}`} style={{ height: 3 + b * 3 }} />)}
    </span>
  );
}

// Wi-Fi settings for the board: see networks, join one, forget one. No terminal needed.
function WifiCard() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);
  const [scanning, setScanning] = useState(false);
  // Once connected, show just the summary; the network list opens on request
  const [showList, setShowList] = useState(null);
  const load = useCallback(async (rescan = false) => {
    try { setInfo(await getWifi(rescan)); setError(""); } catch (e) { setError(e.message); }
  }, []);
  const expanded = showList ?? !info?.wifi?.connected;
  useEffect(() => { load(); const t = setInterval(() => load(), 30000); return () => clearInterval(t); }, [load]);

  const rescan = async () => { setScanning(true); await load(true); setScanning(false); };
  const join = async net => {
    setBusy(net.ssid); setMsg(null);
    try {
      const r = await connectWifi(net.ssid, password);
      setMsg({ ok: `Connected to ${r.network}${r.ip ? ` (${r.ip})` : ""}. If this page stops responding, reopen http://layerhound.local.` });
      setOpen(null); setPassword(""); setShowList(null);
    } catch (e) { setMsg({ error: e.message }); }
    finally { setBusy(null); load(); }
  };
  const forget = async net => {
    setBusy(net.ssid); setMsg(null);
    try { await forgetWifi(net.ssid); setMsg({ ok: `Forgot ${net.ssid}.` }); setOpen(null); }
    catch (e) { setMsg({ error: e.message }); }
    finally { setBusy(null); load(); }
  };

  return (
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-white">Wi-Fi</h2>
          <p className="mt-1 text-xs text-slate-600">How this LayerHound box connects to your network</p>
        </div>
        {info?.available && (
          <div className="flex gap-2">
            {expanded && (
              <button onClick={rescan} disabled={scanning} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06] disabled:opacity-50">
                {scanning ? <Loader2 size={15} className="animate-spin" /> : <RotateCw size={15} />} Scan
              </button>
            )}
            {info.wifi.connected && (
              <button onClick={() => { setShowList(!expanded); setOpen(null); setMsg(null); }} className="rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]">
                {expanded ? "Hide networks" : "Change network"}
              </button>
            )}
          </div>
        )}
      </div>
      {error && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
      {!info ? <div className="mt-4 flex items-center gap-2 text-sm text-slate-500"><Loader2 size={15} className="animate-spin" /> Checking Wi-Fi…</div>
        : !info.available ? <div className="mt-4 rounded-xl border border-dashed border-white/10 px-4 py-5 text-sm text-slate-500">{info.reason}</div>
        : (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-white/[.025] px-4 py-3">
              <div className="flex items-center gap-2 text-xs text-slate-500"><Network size={14} /> Ethernet</div>
              <div className="mt-1 flex items-center gap-2 text-sm text-white"><StatusDot tone={info.ethernet.connected ? "good" : "off"} /> {info.ethernet.connected ? `Connected · ${info.ethernet.ip ?? ""}` : info.ethernet.present ? "Not plugged in" : "None"}</div>
            </div>
            <div className="rounded-xl bg-white/[.025] px-4 py-3">
              <div className="flex items-center gap-2 text-xs text-slate-500"><Wifi size={14} /> Wi-Fi</div>
              <div className="mt-1 flex items-center gap-2 truncate text-sm text-white"><StatusDot tone={info.wifi.connected ? "good" : "off"} /> {info.wifi.connected ? `${info.wifi.network} · ${info.wifi.ip ?? ""}` : "Not connected"}</div>
            </div>
          </div>
          {info.ethernet.connected && info.wifi.connected && <p className="mt-2 text-xs text-slate-600">Both are connected; the board prefers Ethernet while it's plugged in. You can unplug the cable and it will keep running on Wi-Fi.</p>}
          {msg && <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${msg.error ? "border-red-500/20 bg-red-500/6 text-red-300" : "border-emerald-500/20 bg-emerald-500/6 text-emerald-200"}`}>{msg.error ?? msg.ok}</div>}
          {expanded && (<>
          <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
            {info.networks.length === 0 && <div className="py-8 text-center text-sm text-slate-500">No Wi-Fi networks found. Try Scan.</div>}
            {info.networks.map(n => (
              <div key={n.ssid} className="border-b border-white/6 last:border-0">
                <button onClick={() => { setOpen(open === n.ssid ? null : n.ssid); setPassword(""); setMsg(null); }} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-white/[.02]">
                  <SignalBars signal={n.signal} />
                  <span className="min-w-0 flex-1 truncate text-sm text-white">{n.ssid}</span>
                  {n.band && <span className="text-[11px] text-slate-600">{n.band}</span>}
                  {n.in_use ? <span className="rounded-full border border-emerald-500/20 bg-emerald-500/6 px-2 py-0.5 text-[10px] text-emerald-300">Connected</span>
                    : n.saved ? <span className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-slate-400">Saved</span> : null}
                  {n.secure && <Lock size={13} className="text-slate-500" aria-label="Password protected" />}
                </button>
                {open === n.ssid && (
                  <div className="flex flex-wrap items-center gap-2 bg-white/[.02] px-3 pb-3 pt-1">
                    {n.enterprise ? <span className="text-xs text-slate-500">This network uses a company login (802.1X), which isn't supported yet.</span> : (
                      <>
                        {!n.in_use && n.secure && !n.saved && (
                          <input autoFocus type="password" autoComplete="off" className={`${inputClass} max-w-xs`} placeholder="Wi-Fi password" value={password}
                            onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key === "Enter" && password && join(n)} />
                        )}
                        {!n.in_use && (
                          <button onClick={() => join(n)} disabled={busy === n.ssid || (n.secure && !n.saved && !password)} className="flex items-center gap-2 rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
                            {busy === n.ssid && <Loader2 size={14} className="animate-spin" />} {busy === n.ssid ? "Connecting… (up to 30s)" : "Connect"}
                          </button>
                        )}
                        {n.saved && (
                          <button onClick={() => forget(n)} disabled={busy === n.ssid} className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:bg-red-500/6 hover:text-red-300 disabled:opacity-50">Forget network</button>
                        )}
                        {n.in_use && !n.saved && <span className="text-xs text-slate-500">Connected.</span>}
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-600">If a new network doesn't work (wrong password, out of range), the board goes back to the network it was on. Power saving is turned off automatically for a steadier connection.</p>
          </>)}
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
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Globe size={15} /> Internet</div>
          <div className="mt-3 flex items-center gap-2 text-2xl font-semibold tracking-tight text-white"><StatusDot tone={inetTone} /> {internet.up == null ? "Checking" : internet.up ? "Online" : "Offline"}</div>
          <div className="mt-1 text-xs text-slate-500">{internet.up ? `${internet.ms} ms response` : "No response from 1.1.1.1 or 8.8.8.8"}</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Search size={15} /> DNS &amp; public IP</div>
          <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{internet.dns_ok == null ? "—" : internet.dns_ok ? `${internet.dns_ms} ms` : "Failing"}</div>
          <div className="mt-1 truncate text-xs text-slate-500">Public IP {internet.public_ip ?? "unknown"}</div>
        </div>
        <Metric icon={Router} label="Devices" value={devices.length ? `${devUp} / ${devices.length}` : "—"} sub={devices.length ? (devUp === devices.length ? "All responding" : `${devices.length - devUp} not responding`) : "None monitored yet"} />
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><Network size={15} /> Data today</div>
          <div className="mt-3 flex flex-wrap gap-x-4 text-lg font-semibold tabular-nums text-white">
            <span className="flex items-center gap-1.5"><ArrowDownToLine size={16} className="text-slate-500" aria-label="Downloaded" />{formatBytes(todayRx)}</span>
            <span className="flex items-center gap-1.5"><ArrowUpFromLine size={16} className="text-slate-500" aria-label="Uploaded" />{formatBytes(todayTx)}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">This server, since midnight</div>
        </div>
      </section>

      <section data-admin className="mt-4"><WifiCard /></section>

      <section className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
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
                    <span className="text-red-200">{fmtDate(o.start * 1000, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
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

const INTEGRATIONS = {
  none: { label: "None", token: null },
  homeassistant: { label: "Home Assistant", token: "Long-lived access token", hint: "In Home Assistant: your profile → Security → Long-lived access tokens → Create token." },
  pihole: { label: "Pi-hole", token: "Password or API token", hint: "Pi-hole v6: your web password or an app password (Settings → Web interface / API). Pi-hole v5: the API token (Settings → API). Leave blank if Pi-hole has no password." },
};

function ServiceIcon({ url }) {
  // Show the service's own favicon; fall back to a globe if it doesn't have one
  const [failed, setFailed] = useState(false);
  let src = null;
  try { src = new URL("/favicon.ico", url).href; } catch { /* host:port checks have no favicon */ }
  if (!src || failed) return <Globe size={20} className="text-slate-500" />;
  return <img src={src} alt="" className="h-5 w-5 rounded" onError={() => setFailed(true)} />;
}

function ServiceForm({ service, onSave, onCancel }) {
  const [f, setF] = useState({ name: service?.name ?? "", url: service?.url ?? "", integration: service?.integration ?? "none", token: "" });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const set = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  const integ = INTEGRATIONS[f.integration];
  const keeping = service?.has_token && service.integration === f.integration;
  const submit = async e => {
    e.preventDefault();
    if (!f.name.trim() || !f.url.trim()) return setError("Give it a name and an address.");
    if (f.integration === "homeassistant" && !f.token.trim() && !keeping) return setError("Home Assistant needs a long-lived access token.");
    setSaving(true); setError("");
    try { await onSave({ name: f.name.trim(), url: f.url.trim(), integration: f.integration, token: f.token.trim() || null }); }
    catch (err) { setError(err.message); setSaving(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-3 border-b border-white/6 bg-white/[.02] p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><input autoFocus className={inputClass} placeholder="Home Assistant" value={f.name} onChange={set("name")} /></Field>
        <Field label="Address" hint="A web address, or host:port to just check that a port is open."><input className={inputClass} placeholder="http://192.168.1.20:8123" value={f.url} onChange={set("url")} /></Field>
        <Field label="Extra stats">
          <select className={inputClass} value={f.integration} onChange={set("integration")}>{Object.entries(INTEGRATIONS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select>
        </Field>
        {integ.token && (
          <Field label={integ.token} hint={keeping ? "Leave blank to keep the saved token." : integ.hint}>
            <input className={inputClass} type="password" autoComplete="off" spellCheck={false} value={f.token} onChange={set("token")} />
          </Field>
        )}
      </div>
      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:bg-white/5">Cancel</button>
        <button type="submit" disabled={saving} className="rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{saving ? "Saving…" : service ? "Save" : "Add service"}</button>
      </div>
    </form>
  );
}

function IntegrationStats({ s }) {
  if (s.integration === "none") return null;
  if (!s.stats) return <div className="mt-1 text-[11px] text-slate-600">Loading {INTEGRATIONS[s.integration].label} stats…</div>;
  if (!s.stats.ok) return <div className="mt-1 text-[11px] text-amber-300">{INTEGRATIONS[s.integration].label}: {s.stats.error}</div>;
  const d = s.stats.data;
  const chips = s.integration === "homeassistant"
    ? [`Version ${d.version}`, `${d.entities} entities`, d.unavailable ? `${d.unavailable} unavailable` : null]
    : [`${(d.queries_today ?? 0).toLocaleString()} queries today`, `${d.percent_blocked}% blocked`, `${(d.blocklist ?? 0).toLocaleString()} domains on blocklist`, d.enabled === false ? "Blocking disabled" : null];
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {chips.filter(Boolean).map(c => <span key={c} className={`rounded-full border px-2 py-0.5 text-[10px] ${/unavailable|disabled/.test(c) ? "border-amber-500/20 text-amber-200" : "border-white/10 text-slate-400"}`}>{c}</span>)}
    </div>
  );
}

function DockerCard({ docker, onRestarted }) {
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const restart = async c => {
    setBusy(c.id); setError("");
    try { await restartContainer(c.id); setConfirm(null); onRestarted(); }
    catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };
  const running = docker.containers?.filter(c => c.state === "running").length ?? 0;
  return (
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div><h2 className="font-semibold text-white">Docker containers</h2><p className="mt-1 text-xs text-slate-600">{docker.available ? `${running} of ${docker.containers.length} running` : "Not available"}</p></div>
        <Box className="shrink-0 text-violet-400" size={18} />
      </div>
      {!docker.available ? (
        <div className="mt-4 rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-slate-500">
          {docker.reason}. Once Docker is installed on the board, your containers show up here automatically.
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
          {error && <div className="border-b border-white/6 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}
          {docker.containers.length === 0 && <div className="py-8 text-center text-sm text-slate-500">No containers yet.</div>}
          {docker.containers.map(c => (
            <div key={c.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-white/6 px-3 py-2.5 last:border-0">
              <StatusDot tone={c.state === "running" ? "good" : c.state === "restarting" ? "warn" : "off"} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-white">{c.name}</div>
                <div className="truncate text-[11px] text-slate-600">{c.image} · {c.status}{c.ports.length ? ` · ports ${c.ports.join(", ")}` : ""}</div>
              </div>
              {c.state === "running" && <div className="text-right text-xs tabular-nums text-slate-400">{c.cpu_percent ?? "—"}% CPU · {formatBytes(c.memory_bytes)}</div>}
              {confirm === c.id ? (
                <div className="flex items-center gap-1">
                  <button data-admin onClick={() => restart(c)} disabled={busy === c.id} className="rounded-lg bg-amber-500/80 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-amber-500 disabled:opacity-50">{busy === c.id ? "Working…" : `${c.state === "running" ? "Restart" : "Start"} ${c.name}`}</button>
                  <button onClick={() => setConfirm(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                </div>
              ) : (
                <button data-admin onClick={() => setConfirm(c.id)} className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5"><RotateCw size={13} /> {c.state === "running" ? "Restart" : "Start"}</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ServicesPage({ printers }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const load = useCallback(async () => {
    try { setInfo(await getServices()); setError(""); }
    catch (e) { setError(e.message || "network error"); }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  if (!info) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-sm text-slate-500">
        {error ? <span className="flex items-center gap-2 text-red-300"><AlertTriangle size={16} /> Couldn't reach the services API ({error}).</span> : <span className="flex items-center gap-2"><Loader2 size={16} className="animate-spin" /> Checking services…</span>}
      </div>
    );
  }

  const svcs = info.services;
  const up = svcs.filter(s => s.up).length;
  const host = u => { try { return new URL(/^https?:/i.test(u) ? u : `http://${u}`).hostname; } catch { return u; } };
  const have = new Set(svcs.map(s => host(s.url)));
  // Klipper printers serve Fluidd/Mainsail on port 80; offer them as one-click quick links
  const suggestions = printers.filter(p => p.type === "moonraker" && p.address && !have.has(host(p.address)))
    .map(p => ({ name: `${p.name} web UI`, url: `http://${host(p.address)}` }));
  const iconBtn = "rounded-lg p-2 text-slate-500 hover:bg-white/6 hover:text-white";

  return (
    <>
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Services</h1>
          <p className="mt-2 text-sm text-slate-500">{svcs.length ? `${up} of ${svcs.length} services up` : "Your home lab's web apps, in one place"}{info.docker.available ? ` · ${info.docker.containers.filter(c => c.state === "running").length} containers running` : ""}</p>
        </div>
        <button data-admin onClick={() => { setAdding(true); setEditing(null); }} className="flex items-center justify-center gap-2 rounded-xl bg-violet-500 px-4 py-2.5 text-sm font-medium text-[#fff] hover:bg-violet-400"><Plus size={17} /> Add service</button>
      </div>

      {svcs.length > 0 && (
        <section className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-3">
          {svcs.map(s => (
            <a key={s.id} href={s.open_url} target="_blank" rel="noopener noreferrer" className="group rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4 transition hover:-translate-y-0.5 hover:border-violet-400/40">
              <div className="flex items-center justify-between"><ServiceIcon url={s.open_url} /><StatusDot tone={s.up == null ? "off" : s.up ? "good" : "bad"} /></div>
              <div className="mt-3 truncate text-sm font-medium text-white">{s.name}</div>
              <div className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-slate-600">{s.up ? `${s.ms} ms` : s.up === false ? "Down" : "Checking…"} <ExternalLink size={11} className="opacity-0 group-hover:opacity-100" /></div>
            </a>
          ))}
        </section>
      )}

      {suggestions.length > 0 && (
        <div data-admin className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-600">Suggested:</span>
          {suggestions.map(sg => (
            <button data-admin key={sg.url} onClick={async () => { await addService({ ...sg, integration: "none" }); load(); }} className="flex items-center gap-1 rounded-full border border-white/10 px-2.5 py-1 text-slate-300 hover:border-violet-400/40 hover:text-white"><Plus size={12} /> {sg.name}</button>
          ))}
        </div>
      )}

      <section className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
        <div><h2 className="font-semibold text-white">Health checks</h2><p className="mt-1 text-xs text-slate-600">Checked every {info.check_every / 60} min · last 24 hours · a service that stops answering shows up in Alerts</p></div>
        <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
          {adding && <ServiceForm onCancel={() => setAdding(false)} onSave={async x => { await addService(x); setAdding(false); load(); }} />}
          {svcs.length === 0 && !adding && (
            <div className="py-10 text-center">
              <Globe className="mx-auto text-violet-400" size={24} />
              <div className="mt-3 text-sm font-medium text-white">No services yet</div>
              <div className="mt-1 text-xs text-slate-500">Add Home Assistant, Pi-hole, your router's admin page, or any web app.</div>
            </div>
          )}
          {svcs.map(s => editing === s.id
            ? <ServiceForm key={s.id} service={s} onCancel={() => setEditing(null)} onSave={async x => { await editService(s.id, x); setEditing(null); load(); }} />
            : (
              <div key={s.id} className="group grid items-center gap-x-4 gap-y-2 border-b border-white/6 px-3 py-3 last:border-0 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="mt-1.5"><StatusDot tone={s.up == null ? "off" : s.up ? "good" : "bad"} /></span>
                  <div className="min-w-0">
                    <a href={s.open_url} target="_blank" rel="noopener noreferrer" className="truncate text-sm text-white hover:text-violet-300">{s.name}</a>
                    <div className="truncate text-[11px] text-slate-600">{s.url} · {s.up == null ? "Checking…" : s.up ? `${s.ms} ms` : s.error || "Down"}{s.check === "tcp" ? " · port check" : ""}</div>
                    <IntegrationStats s={s} />
                  </div>
                </div>
                <div className="min-w-0">
                  <UptimeBar hours={s.hours} label={`${s.name} uptime, last 24 hours`} />
                  <div className="mt-1 text-[11px] text-slate-600">{s.uptime_24h == null ? "No data yet" : `${s.uptime_24h}% up`}</div>
                </div>
                {confirm === s.id ? (
                  <div className="flex items-center gap-1">
                    <button onClick={async () => { await deleteService(s.id); setConfirm(null); load(); }} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-red-500">Remove</button>
                    <button onClick={() => setConfirm(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                  </div>
                ) : (
                  <div className="flex items-center justify-end sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100">
                    <button data-admin onClick={() => { setEditing(s.id); setAdding(false); }} className={iconBtn} aria-label={`Edit ${s.name}`}><Pencil size={16} /></button>
                    <button data-admin onClick={() => setConfirm(s.id)} className={`${iconBtn} hover:text-red-300`} aria-label={`Remove ${s.name}`}><Trash2 size={16} /></button>
                  </div>
                )}
              </div>
            ))}
        </div>
      </section>

      {/* Hidden unless Docker is on this machine (most LayerHound boards don't have it) */}
      {(info.docker.available || info.docker.installed) && <section className="mt-4"><DockerCard docker={info.docker} onRestarted={load} /></section>}
    </>
  );
}

function Section({ title, sub, children, footer }) {
  return (
    <section className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <h2 className="font-semibold text-white">{title}</h2>
      {sub && <p className="mt-1 text-xs text-slate-600">{sub}</p>}
      <div className="mt-5">{children}</div>
      {footer && <div className="mt-5 flex flex-wrap items-center justify-end gap-3 border-t border-white/6 pt-4">{footer}</div>}
    </section>
  );
}

function Segmented({ value, options, onChange, label }) {
  return (
    <div className="inline-flex rounded-lg border border-white/10 p-0.5" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)} className={`rounded-md px-3 py-1.5 text-sm ${value === v ? "bg-violet-500/20 text-white" : "text-slate-400 hover:text-white"}`}>{text}</button>
      ))}
    </div>
  );
}

function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-2">
      <span><span className="block text-sm text-slate-200">{label}</span>{hint && <span className="block text-xs text-slate-600">{hint}</span>}</span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input type="checkbox" className="peer sr-only" checked={checked} onChange={e => onChange(e.target.checked)} />
        <span className="h-5 w-9 rounded-full bg-white/10 transition peer-checked:bg-violet-500 peer-focus-visible:ring-2 peer-focus-visible:ring-violet-300" />
        <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-[#fff] shadow transition peer-checked:translate-x-4" />
      </span>
    </label>
  );
}

// Save a group of settings; shows "Saved" or the server's error next to the button
function useSaver(onSaved) {
  const [status, setStatus] = useState(null);
  const save = async changes => {
    setStatus({ busy: true });
    try { onSaved(await saveSettings(changes)); setStatus({ ok: "Saved" }); setTimeout(() => setStatus(null), 2500); }
    catch (e) { setStatus({ error: e.message }); }
  };
  const note = status?.error ? <span className="text-xs text-red-300">{status.error}</span> : status?.ok ? <span className="text-xs text-emerald-300">{status.ok}</span> : null;
  return [save, status?.busy, note];
}

function BrandingSection({ onSaved }) {
  const [f, setF] = useState(() => ({ farm_name: prefs.farm_name, farm_description: prefs.farm_description, accent: prefs.accent, temp_unit: prefs.temp_unit, time_format: prefs.time_format }));
  const [save, busy, note] = useSaver(onSaved);
  const set = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  return (
    <Section title="Farm & display" sub="Your farm's name, plus colors and units used across the dashboard."
      footer={<>{note}<button onClick={() => save(f)} disabled={busy} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{busy ? "Saving…" : "Save"}</button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Farm name" hint="Shown under the LayerHound logo, as the main heading, and in the browser tab."><input className={inputClass} maxLength={40} placeholder="My Print Farm" value={f.farm_name} onChange={set("farm_name")} /></Field>
        <Field label="Description" hint="Shown under the main heading. Leave blank to hide."><input className={inputClass} maxLength={120} value={f.farm_description} onChange={set("farm_description")} /></Field>
      </div>
      <div className="mt-5 grid gap-5 sm:grid-cols-3">
        <div>
          <div className="text-xs font-medium text-slate-400">Accent color</div>
          <div className="mt-2 flex gap-2" role="radiogroup" aria-label="Accent color">
            {Object.entries(ACCENTS).map(([k, a]) => (
              <button key={k} type="button" role="radio" aria-checked={f.accent === k} aria-label={a.label} title={a.label} onClick={() => setF(x => ({ ...x, accent: k }))}
                className={`h-8 w-8 rounded-full ring-offset-2 ring-offset-[var(--lh-card)] ${f.accent === k ? "ring-2 ring-white" : "hover:ring-2 hover:ring-white/30"}`} style={{ background: a[500] }} />
            ))}
          </div>
        </div>
        <div><div className="text-xs font-medium text-slate-400">Temperature</div><div className="mt-2"><Segmented label="Temperature unit" value={f.temp_unit} onChange={v => setF(x => ({ ...x, temp_unit: v }))} options={[["C", "°C"], ["F", "°F"]]} /></div></div>
        <div><div className="text-xs font-medium text-slate-400">Time</div><div className="mt-2"><Segmented label="Time format" value={f.time_format} onChange={v => setF(x => ({ ...x, time_format: v }))} options={[["12", "3:45 PM"], ["24", "15:45"]]} /></div></div>
      </div>
    </Section>
  );
}

function AlertsSection({ onSaved }) {
  const [f, setF] = useState(() => ({ temp_warn: toUnit(prefs.temp_warn), temp_hot: toUnit(prefs.temp_hot), storage_warn: prefs.storage_warn, storage_critical: prefs.storage_critical, memory_warn: prefs.memory_warn, alert_printers: prefs.alert_printers, alert_devices: prefs.alert_devices, alert_services: prefs.alert_services, alert_internet: prefs.alert_internet }));
  const [save, busy, note] = useSaver(onSaved);
  const num = k => e => setF(x => ({ ...x, [k]: e.target.value === "" ? "" : Number(e.target.value) }));
  const unit = `°${prefs.temp_unit}`;
  const submit = () => save({ ...f, temp_warn: fromUnit(f.temp_warn), temp_hot: fromUnit(f.temp_hot) });
  const NumberField = ({ k, label, suffix }) => (
    <Field label={label}><div className="flex items-center gap-2"><input type="number" className={`${inputClass} w-24`} value={f[k]} onChange={num(k)} /><span className="text-sm text-slate-500">{suffix}</span></div></Field>
  );
  return (
    <Section title="Alerts" sub="When alerts appear in the header, sidebar and Alerts list."
      footer={<>{note}<button onClick={submit} disabled={busy} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{busy ? "Saving…" : "Save"}</button></>}>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {NumberField({ k: "temp_warn", label: "Server running hot at", suffix: unit })}
        {NumberField({ k: "temp_hot", label: "Server overheating at", suffix: unit })}
        {NumberField({ k: "memory_warn", label: "Memory warning at", suffix: "% used" })}
        {NumberField({ k: "storage_warn", label: "Main drive warning at", suffix: "% full" })}
        {NumberField({ k: "storage_critical", label: "Main drive critical at", suffix: "% full" })}
      </div>
      <div className="mt-4 divide-y divide-white/6 border-t border-white/6 pt-2">
        <Toggle label="Printers offline" checked={f.alert_printers} onChange={v => setF(x => ({ ...x, alert_printers: v }))} />
        <Toggle label="Monitored devices not responding" hint="From the Network page's device monitor." checked={f.alert_devices} onChange={v => setF(x => ({ ...x, alert_devices: v }))} />
        <Toggle label="Services down" hint="From the Services page." checked={f.alert_services} onChange={v => setF(x => ({ ...x, alert_services: v }))} />
        <Toggle label="Internet down" checked={f.alert_internet} onChange={v => setF(x => ({ ...x, alert_internet: v }))} />
      </div>
    </Section>
  );
}

// Case fan speed (backend/fan.py). Shown when this machine has a speed-controlled fan.
function FanSection({ onSaved }) {
  const [fan, setFan] = useState(null);
  const [f, setF] = useState(() => ({ fan_mode: prefs.fan_mode, fan_quiet_temp: toUnit(prefs.fan_quiet_temp), fan_full_temp: toUnit(prefs.fan_full_temp), fan_min_percent: prefs.fan_min_percent }));
  const [save, busy, note] = useSaver(onSaved);
  useEffect(() => { getServer().then(s => setFan(s.fan)).catch(() => setFan({ available: false })); }, []);
  if (!fan?.available) return null;
  const unit = `°${prefs.temp_unit}`;
  const num = k => e => setF(x => ({ ...x, [k]: e.target.value === "" ? "" : Number(e.target.value) }));
  const submit = () => save({ ...f, fan_quiet_temp: fromUnit(f.fan_quiet_temp), fan_full_temp: fromUnit(f.fan_full_temp) });
  return (
    <Section title={<span className="flex items-center gap-2"><Fan size={16} className="text-violet-400" /> Cooling fan</span>} sub={`Now ${fan.percent ?? "—"}%${fan.temp_c != null ? ` at ${fmtTemp(fan.temp_c, 0)}` : ""}. If LayerHound stops, the fan goes to full speed.`}
      footer={<>{note}<button onClick={submit} disabled={busy || !fan.controlled} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{busy ? "Saving…" : "Save"}</button></>}>
      {!fan.controlled && <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/6 px-3 py-2 text-sm text-amber-100">LayerHound doesn't have permission to set the fan speed yet, so it runs at full speed. Run the board setup again (deploy) to fix this.</div>}
      <Segmented label="Fan mode" value={f.fan_mode} onChange={v => setF(x => ({ ...x, fan_mode: v }))} options={[["auto", "Automatic"], ["full", "Always full speed"]]} />
      {f.fan_mode === "auto" && (
        <>
          <p className="mt-3 text-xs text-slate-500">Runs at the minimum speed while the chip is cool, then speeds up evenly to full speed.</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <Field label="Quiet up to"><div className="flex items-center gap-2"><input type="number" className={`${inputClass} w-24`} value={f.fan_quiet_temp} onChange={num("fan_quiet_temp")} /><span className="text-sm text-slate-500">{unit}</span></div></Field>
            <Field label="Full speed at"><div className="flex items-center gap-2"><input type="number" className={`${inputClass} w-24`} value={f.fan_full_temp} onChange={num("fan_full_temp")} /><span className="text-sm text-slate-500">{unit}</span></div></Field>
            <Field label="Minimum speed" hint="Some small fans stop below about 25%."><div className="flex items-center gap-2"><input type="number" className={`${inputClass} w-24`} value={f.fan_min_percent} onChange={num("fan_min_percent")} /><span className="text-sm text-slate-500">%</span></div></Field>
          </div>
        </>
      )}
    </Section>
  );
}

function DataSection({ onSaved, onRestored }) {
  const [f, setF] = useState(() => ({ network_history_days: prefs.network_history_days ?? 7, storage_history_days: prefs.storage_history_days ?? 90, data_usage_days: prefs.data_usage_days ?? 90 }));
  const [save, busy, note] = useSaver(onSaved);
  const [confirmClear, setConfirmClear] = useState(null);
  const [cleared, setCleared] = useState("");
  const [secrets, setSecrets] = useState(true);
  const [restore, setRestore] = useState(null);
  const [restoreMsg, setRestoreMsg] = useState(null);
  const picker = React.useRef(null);
  const days = (k, opts) => (
    <select className={inputClass} value={f[k]} onChange={e => setF(x => ({ ...x, [k]: Number(e.target.value) }))}>
      {opts.map(d => <option key={d} value={d}>{d === 1 ? "1 day" : d >= 365 ? "1 year" : `${d} days`}</option>)}
    </select>
  );
  const histories = [["network", "Uptime history", "Internet, devices and services"], ["storage", "Storage trend", "Drive usage over time"], ["usage", "Data usage", "Daily download/upload totals"]];

  const pickFile = async e => {
    const file = e.target.files?.[0]; e.target.value = "";
    if (!file) return;
    setRestoreMsg(null);
    try {
      const data = JSON.parse(await file.text());
      if (!["layerhound", "ttrc-dashboard"].includes(data.app)) throw Error("This file isn't a LayerHound backup.");
      setRestore({ name: file.name, data });
    } catch (err) { setRestoreMsg({ error: err.message.startsWith("This file") ? err.message : "Couldn't read that file. Choose a backup .json from this dashboard." }); }
  };
  const doRestore = async () => {
    try {
      const r = await restoreBackup(restore.data);
      setRestore(null); onRestored();
      setRestoreMsg({ ok: `Restored ${r.printers} printers, ${r.devices} devices and ${r.services} services.${r.secrets_missing ? " This backup had no access codes or tokens; re-enter them by editing each printer or service." : ""}` });
    } catch (err) { setRestoreMsg({ error: err.message }); }
  };

  return (
    <Section title="Data & backups" sub="How long history is kept, and backups of your setup.">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Uptime history">{days("network_history_days", [1, 3, 7, 14, 30, 90])}</Field>
        <Field label="Storage trend">{days("storage_history_days", [7, 30, 90, 180, 365])}</Field>
        <Field label="Data usage">{days("data_usage_days", [7, 30, 90, 180, 365])}</Field>
      </div>
      <div className="mt-3 flex items-center justify-end gap-3">{note}<button onClick={() => save(f)} disabled={busy} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{busy ? "Saving…" : "Save"}</button></div>

      <div className="mt-5 border-t border-white/6 pt-4">
        <div className="text-sm font-medium text-white">Clear history</div>
        <div className="mt-2 divide-y divide-white/6">
          {histories.map(([k, label, hint]) => (
            <div key={k} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <span><span className="block text-sm text-slate-200">{label}</span><span className="block text-xs text-slate-600">{hint}</span></span>
              {confirmClear === k ? (
                <span className="flex items-center gap-2">
                  <button onClick={async () => { await clearHistory(k); setConfirmClear(null); setCleared(k); setTimeout(() => setCleared(""), 2500); }} className="rounded-lg bg-red-500/80 px-3 py-1.5 text-xs font-medium text-[#fff] hover:bg-red-500">Clear {label.toLowerCase()}</button>
                  <button onClick={() => setConfirmClear(null)} className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
                </span>
              ) : cleared === k ? <span className="text-xs text-emerald-300">Cleared</span> : (
                <button onClick={() => setConfirmClear(k)} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-300 hover:border-red-500/30 hover:text-red-300">Clear</button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 border-t border-white/6 pt-4">
        <div className="text-sm font-medium text-white">Backup</div>
        <p className="mt-1 text-xs text-slate-600">Printers, monitored devices, services and settings. History and LayerHound Files aren't included.</p>
        <div className="mt-3 flex flex-wrap items-center gap-4">
          <a href={`/api/settings/backup?secrets=${secrets}`} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><Download size={15} /> Download backup</a>
          <label className="flex items-center gap-2 text-sm text-slate-400"><input type="checkbox" className="accent-violet-500" checked={secrets} onChange={e => setSecrets(e.target.checked)} /> Include access codes and tokens</label>
        </div>
        {secrets && <p className="mt-2 text-xs text-amber-200/80">Keep this file private: it contains your printer access codes and service tokens.</p>}

        <div className="mt-4 text-sm font-medium text-white">Restore</div>
        {restore ? (
          <div className="mt-2 rounded-xl border border-amber-500/20 bg-amber-500/6 p-4 text-sm">
            <div className="text-amber-100">Restore <span className="font-medium">{restore.name}</span>?</div>
            <div className="mt-1 text-xs text-slate-400">From {restore.data.created ? fmtDate(restore.data.created, { dateStyle: "medium", timeStyle: "short" }) : "an unknown date"} · {restore.data.printers?.length ?? 0} printers · {restore.data.net_devices?.length ?? 0} devices · {restore.data.services?.length ?? 0} services{restore.data.includes_secrets === false ? " · no access codes or tokens" : ""}</div>
            <div className="mt-2 text-xs text-amber-200/80">This replaces your current printers, devices, services and settings.</div>
            <div className="mt-3 flex gap-2">
              <button onClick={doRestore} className="rounded-lg bg-amber-500/80 px-3 py-1.5 text-xs font-medium text-[#fff] hover:bg-amber-500">Replace and restore</button>
              <button onClick={() => setRestore(null)} className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:bg-white/5">Cancel</button>
            </div>
          </div>
        ) : (
          <div className="mt-2"><button onClick={() => picker.current?.click()} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06]"><CloudUpload size={15} /> Choose backup file</button></div>
        )}
        <input ref={picker} type="file" accept="application/json,.json" className="hidden" onChange={pickFile} />
        {restoreMsg && <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${restoreMsg.error ? "border-red-500/20 bg-red-500/6 text-red-300" : "border-emerald-500/20 bg-emerald-500/6 text-emerald-200"}`}>{restoreMsg.error ?? restoreMsg.ok}</div>}
      </div>
    </Section>
  );
}

const UPDATE_PHASES = { downloading: "Downloading", verifying: "Checking the signature", installing: "Installing", restarting: "Restarting LayerHound" };

// Settings: is there a newer LayerHound, and one-click install (backend/updates.py, updater.py)
function UpdatesSection({ onSaved }) {
  const [u, setU] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [offline, setOffline] = useState(false);
  const load = useCallback(async () => {
    try { setU(await getUpdates()); setOffline(false); } catch { setOffline(true); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const job = u?.job;
  const working = job && UPDATE_PHASES[job.phase];
  // While an update runs, keep checking; LayerHound restarts partway through
  useEffect(() => { if (!working) return; const t = setInterval(load, 3000); return () => clearInterval(t); }, [working, load]);
  const run = async (what, fn) => { setBusy(what); setError(""); try { await fn(); await load(); } catch (e) { setError(e.message); } setBusy(""); };
  const toggle = async v => { try { onSaved(await saveSettings({ update_check: v })); load(); } catch (e) { setError(e.message); } };
  if (!u) return null;
  const latest = u.latest;
  return (
    <Section title={<span className="flex items-center gap-2"><Download size={16} className="text-violet-400" /> Updates</span>}
      sub={`You're on LayerHound v${u.current}.${u.checked_at ? ` Last checked ${fmtDate(u.checked_at * 1000, { dateStyle: "medium", timeStyle: "short" })}.` : ""}`}>
      {working ? (
        <div className="flex items-center gap-3 rounded-xl border border-violet-400/25 bg-violet-500/8 px-4 py-3 text-sm text-slate-200">
          <Loader2 size={16} className="shrink-0 animate-spin text-violet-400" />
          <span>{offline ? "LayerHound is restarting…" : `${UPDATE_PHASES[job.phase]} v${job.version}…`} This takes a minute or two. The database was backed up, and if the new version doesn't start, the previous one comes back by itself.</span>
        </div>
      ) : u.available ? (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/6 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium text-white">LayerHound v{latest.version} is available</div>
              {latest.published && <div className="text-xs text-slate-500">Released {fmtDate(latest.published, { dateStyle: "medium" })}</div>}
            </div>
            {u.can_install && !confirm && <button onClick={() => setConfirm(true)} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400">Update now</button>}
          </div>
          {latest.notes && <div className="mt-3 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg bg-black/10 p-3 text-sm text-slate-300">{latest.notes}</div>}
          {u.reason && <p className="mt-3 text-xs text-amber-200">{u.reason}</p>}
          {confirm && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-slate-300">
              LayerHound will restart, so the dashboard is unavailable for a minute or two. Printers keep printing.
              <button onClick={() => { setConfirm(false); run("install", installUpdate); }} disabled={!!busy} className="rounded-lg bg-violet-500 px-3 py-1.5 text-xs font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">Update to v{latest.version}</button>
              <button onClick={() => setConfirm(false)} className="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:bg-white/5">Not now</button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-slate-300">{u.error ? <><AlertTriangle size={15} className="text-amber-300" /> {u.error}</> : <><CircleCheck size={15} className="text-emerald-300" /> {u.checked_at ? "LayerHound is up to date." : "Not checked yet."}</>}</div>
      )}
      {job?.phase === "done" && !working && <p className="mt-3 text-xs text-emerald-300">Updated from v{job.from_version} to v{job.version} {job.finished ? fmtDate(job.finished * 1000, { dateStyle: "medium", timeStyle: "short" }) : ""}.</p>}
      {job?.phase === "failed" && <p className="mt-3 text-xs text-red-300">The update to v{job.version} didn't work: {job.error}{job.rolled_back ? ` LayerHound is back on v${job.from_version}.` : ""}</p>}
      {error && <p className="mt-3 text-xs text-red-300">{error}</p>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/6 pt-3">
        <div className="min-w-0 flex-1"><Toggle checked={u.auto_check} onChange={toggle} label="Check for updates once a day" hint="Asks GitHub for the latest LayerHound release. Installing always needs an admin." /></div>
        <button onClick={() => run("check", checkUpdates)} disabled={!!busy || !!working} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06] disabled:opacity-50">
          {busy === "check" ? <Loader2 size={14} className="animate-spin" /> : <RotateCw size={14} />} Check now
        </button>
      </div>
    </Section>
  );
}

function AboutSection() {
  const [about, setAbout] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { getAbout().then(setAbout).catch(() => {}); }, []);
  const restart = async () => {
    try { await restartDashboard(); setMsg("Restarting. The page reconnects in a few seconds."); setConfirm(false); }
    catch (e) { setMsg(e.message); }
  };
  return (
    <Section title="About & maintenance">
      {!about ? <div className="text-sm text-slate-500">Loading…</div> : (
        <>
          <Row label="Version" value={`${about.version}`} />
          <Row label="Running since" value={fmtDate(about.started, { dateStyle: "medium", timeStyle: "short" })} />
          <Row label="Memory used" value={`${about.memory_mb} MB`} />
          <Row label="Database" value={`${about.database}${about.database_bytes != null ? ` (${formatBytes(about.database_bytes)})` : ""}`} />
          <Row label="Files folder" value={about.files_folder} />
          <Row label="Python" value={about.python} />
          <Row label="System" value={about.platform} />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {confirm ? (
              <>
                <button onClick={restart} className="rounded-lg bg-amber-500/80 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-amber-500">Restart now</button>
                <button onClick={() => setConfirm(false)} className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:bg-white/5">Cancel</button>
              </>
            ) : (
              <button data-admin onClick={() => setConfirm(true)} disabled={!about.can_restart} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06] disabled:cursor-not-allowed disabled:opacity-40"><RotateCw size={15} /> Restart dashboard</button>
            )}
            {!about.can_restart && <span className="text-xs text-slate-600">{about.restart_note}</span>}
            {msg && <span className="text-xs text-slate-400">{msg}</span>}
          </div>
        </>
      )}
    </Section>
  );
}

function AppearanceSection() {
  const [theme, choose] = useTheme();
  return (
    <Section title="Appearance" sub="Saved on this device only, so each screen can have its own.">
      <Segmented label="Theme" value={theme} onChange={choose} options={THEMES.map(([v, label]) => [v, label])} />
    </Section>
  );
}

function AccountSection() {
  const [f, setF] = useState({ current: "", next: "", confirm: "" });
  const [status, setStatus] = useState(null);
  const submit = async e => {
    e.preventDefault();
    if (f.next.length < 8) return setStatus({ error: "Passwords need at least 8 characters." });
    if (f.next !== f.confirm) return setStatus({ error: "The new passwords don't match." });
    setStatus({ busy: true });
    try { await changePassword(f.current, f.next); setF({ current: "", next: "", confirm: "" }); setStatus({ ok: "Password changed. Other devices were signed out." }); }
    catch (err) { setStatus({ error: err.message }); }
  };
  return (
    <Section title="Your account" sub={`Signed in as ${session.user.username} (${session.user.role === "admin" ? "admin" : "view only"}).`}>
      <form onSubmit={submit}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Current password"><PasswordInput value={f.current} onChange={v => setF(x => ({ ...x, current: v }))} autoComplete="current-password" /></Field>
          <Field label="New password"><PasswordInput value={f.next} onChange={v => setF(x => ({ ...x, next: v }))} autoComplete="new-password" /></Field>
          <Field label="Type it again"><PasswordInput value={f.confirm} onChange={v => setF(x => ({ ...x, confirm: v }))} autoComplete="new-password" /></Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
          {status?.error && <span className="text-xs text-red-300">{status.error}</span>}
          {status?.ok && <span className="text-xs text-emerald-300">{status.ok}</span>}
          <button type="submit" disabled={status?.busy || !f.current || !f.next} className="rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">{status?.busy ? "Saving…" : "Change password"}</button>
        </div>
      </form>
    </Section>
  );
}

const ROLE_LABEL = { admin: "Admin", viewer: "View only" };

function UserRow({ u, onChanged, onError }) {
  const [mode, setMode] = useState(null); // "password" | "remove"
  const [pw, setPw] = useState("");
  const me = u.username.toLowerCase() === session.user.username?.toLowerCase();
  const run = async fn => { try { await fn(); setMode(null); setPw(""); onChanged(); } catch (e) { onError(e.message); } };
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/5 text-slate-400"><UserRound size={15} /></div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm text-white">{u.username}{me && <span className="ml-2 text-xs text-slate-500">(you)</span>}</div>
          <div className="text-xs text-slate-600">{u.last_login ? `Last signed in ${fmtDate(u.last_login * 1000, { dateStyle: "medium", timeStyle: "short" })}` : "Never signed in"}</div>
        </div>
        <select aria-label={`Role for ${u.username}`} value={u.role} onChange={e => run(() => editUser(u.id, { role: e.target.value }))} className="rounded-lg border border-white/10 bg-[var(--lh-input)] px-2 py-1.5 text-xs text-slate-200">
          <option value="admin">Admin</option><option value="viewer">View only</option>
        </select>
        {!me && <button onClick={() => setMode(mode === "password" ? null : "password")} className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-300 hover:bg-white/5">Set password</button>}
        {!me && <button onClick={() => setMode("remove")} className="rounded-lg p-1.5 text-slate-500 hover:bg-red-500/6 hover:text-red-300" aria-label={`Remove ${u.username}`}><Trash2 size={15} /></button>}
      </div>
      {mode === "password" && (
        <form onSubmit={e => { e.preventDefault(); run(() => editUser(u.id, { password: pw })); }} className="mt-3 flex gap-2 pl-11">
          <div className="flex-1"><PasswordInput value={pw} onChange={setPw} autoComplete="new-password" placeholder="New password (8+ characters)" /></div>
          <button type="submit" disabled={pw.length < 8} className="rounded-lg bg-violet-500 px-3 text-sm text-[#fff] hover:bg-violet-400 disabled:opacity-50">Save</button>
        </form>
      )}
      {mode === "remove" && (
        <div className="mt-3 flex flex-wrap items-center gap-2 pl-11 text-sm text-slate-300">
          Remove {u.username}? They'll be signed out right away.
          <button onClick={() => run(() => deleteUser(u.id))} className="rounded-lg bg-red-500/80 px-2.5 py-1.5 text-xs font-medium text-[#fff] hover:bg-red-500">Remove</button>
          <button onClick={() => setMode(null)} className="rounded-lg px-2.5 py-1.5 text-xs text-slate-400 hover:bg-white/5">Keep</button>
        </div>
      )}
    </li>
  );
}

// Admins: who can sign in, access keys for devices, and guest viewing on the local network
function AccessSection({ onSaved }) {
  const [users, setUsers] = useState(null);
  const [keys, setKeys] = useState(null);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(null);
  const [keyName, setKeyName] = useState("");
  const [newKey, setNewKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [guest, setGuest] = useState(!!prefs.guest_view);
  const load = useCallback(async () => {
    try { setUsers((await getUsers()).users); setKeys((await getKeys()).keys); } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const toggleGuest = async v => {
    setGuest(v);
    try { onSaved(await saveSettings({ guest_view: v })); } catch (e) { setGuest(!v); setError(e.message); }
  };
  const submitUser = async e => {
    e.preventDefault(); setError("");
    try { await addUser(adding); setAdding(null); load(); } catch (err) { setError(err.message); }
  };
  const createKey = async e => {
    e.preventDefault(); setError("");
    try { setNewKey(await addKey(keyName.trim())); setKeyName(""); setCopied(false); load(); } catch (err) { setError(err.message); }
  };
  const copy = async () => { try { await navigator.clipboard.writeText(newKey.key); setCopied(true); } catch { /* select it by hand */ } };
  return (
    <Section title={<span className="flex items-center gap-2"><ShieldCheck size={16} className="text-violet-400" /> Login & users</span>} sub="Who can see and change this dashboard.">
      <Toggle checked={guest} onChange={toggleGuest} label="Let anyone on my network view without signing in"
        hint="Handy for a shop wall screen. Viewing only: changes still need an admin. Devices outside your local network always need to sign in." />

      <div className="mt-5 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium text-slate-300"><Users size={15} /> Accounts</h3>
        {!adding && <button onClick={() => setAdding({ username: "", password: "", role: "viewer" })} className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-white/5"><Plus size={14} /> Add account</button>}
      </div>
      {adding && (
        <form onSubmit={submitUser} className="mt-3 grid gap-3 rounded-xl border border-white/8 bg-white/[.02] p-3 sm:grid-cols-[1fr_1fr_auto_auto] sm:items-end">
          <Field label="Username"><input className={inputClass} maxLength={40} value={adding.username} onChange={e => setAdding(x => ({ ...x, username: e.target.value }))} autoComplete="off" autoFocus /></Field>
          <Field label="Password"><PasswordInput value={adding.password} onChange={v => setAdding(x => ({ ...x, password: v }))} autoComplete="new-password" placeholder="8+ characters" /></Field>
          <Field label="Access"><select value={adding.role} onChange={e => setAdding(x => ({ ...x, role: e.target.value }))} className={inputClass}><option value="viewer">View only</option><option value="admin">Admin</option></select></Field>
          <div className="flex gap-2">
            <button type="button" onClick={() => setAdding(null)} className="rounded-lg px-3 py-2 text-sm text-slate-400 hover:bg-white/5">Cancel</button>
            <button type="submit" disabled={!adding.username || adding.password.length < 8} className="rounded-lg bg-violet-500 px-3 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">Add</button>
          </div>
        </form>
      )}
      <ul className="mt-1 divide-y divide-white/6">
        {users?.map(u => <UserRow key={u.id} u={u} onChanged={load} onError={setError} />)}
      </ul>

      <div className="mt-5 border-t border-white/6 pt-5">
        <h3 className="flex items-center gap-2 text-sm font-medium text-slate-300"><KeyRound size={15} /> Access keys</h3>
        <p className="mt-1 text-xs text-slate-600">For devices that read LayerHound without signing in, like an LED status bar. Keys can only view, never change anything.</p>
        <form onSubmit={createKey} className="mt-3 flex gap-2">
          <input className={inputClass} maxLength={60} placeholder="Device name, e.g. LED bar" value={keyName} onChange={e => setKeyName(e.target.value)} />
          <button type="submit" disabled={!keyName.trim()} className="shrink-0 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06] disabled:opacity-50">Create key</button>
        </form>
        {newKey && (
          <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/6 p-3 text-sm">
            <div className="text-emerald-200">Key for {newKey.name}. Copy it now: it won't be shown again.</div>
            <div className="mt-2 flex items-center gap-2">
              <code className="min-w-0 flex-1 select-all break-all rounded-lg bg-black/30 px-2 py-1.5 text-xs text-white">{newKey.key}</code>
              <button onClick={copy} className="flex shrink-0 items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-slate-200 hover:bg-white/5"><Copy size={13} /> {copied ? "Copied" : "Copy"}</button>
              <button onClick={() => setNewKey(null)} className="shrink-0 rounded-lg p-1.5 text-slate-500 hover:text-white" aria-label="Done"><X size={15} /></button>
            </div>
          </div>
        )}
        {keys?.length > 0 && (
          <ul className="mt-3 divide-y divide-white/6">
            {keys.map(k => (
              <li key={k.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-white">{k.name} <span className="ml-1 font-mono text-xs text-slate-600">{k.prefix}…</span></div>
                  <div className="text-xs text-slate-600">{k.last_used ? `Last used ${fmtDate(k.last_used * 1000, { dateStyle: "medium", timeStyle: "short" })}` : "Not used yet"}</div>
                </div>
                <button onClick={async () => { try { await deleteKey(k.id); load(); } catch (e) { setError(e.message); } }} className="rounded-lg px-2.5 py-1.5 text-xs text-slate-400 hover:bg-red-500/6 hover:text-red-300">Revoke</button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {error && <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-sm text-red-200">{error}</div>}
    </Section>
  );
}

function SettingsPage({ onSaved, onRestored }) {
  return (
    <>
      <div className="mb-7">
        <h1 className="text-3xl font-bold tracking-tight text-white">Settings</h1>
        <p className="mt-2 text-sm text-slate-500">{isAdmin() ? "Branding, alerts, accounts, data and maintenance." : "Your account. Other settings can be changed by an admin."}</p>
      </div>
      <div className="space-y-4">
        {isAdmin() && <>
          <BrandingSection onSaved={onSaved} />
          <AppearanceSection />
          <AlertsSection onSaved={onSaved} />
          <FanSection onSaved={onSaved} />
          <AccessSection onSaved={onSaved} />
          <DataSection onSaved={onSaved} onRestored={onRestored} />
        </>}
        {/* Everyone can pick their theme; admins see it right under Farm & display */}
        {!isAdmin() && <AppearanceSection />}
        {session.user?.kind === "user" && <AccountSection />}
        {isAdmin() && <UpdatesSection onSaved={onSaved} />}
        <AboutSection />
      </div>
    </>
  );
}

// Feedback goes to Team Tactical RC's Google Form, sent straight from this browser when the person
// presses Send. Nothing is sent otherwise. To point it at a different form: open the form's
// "Get pre-filled link", fill every box, and copy the form id and each entry number from that link.
const FEEDBACK_FORM = {
  id: "1FAIpQLSeX2TuPXg0FvDs9kieZwtDx3mvu4ZDcI3JDz6EwDouX-OpOcw",
  fields: { type: "entry.1143753026", message: "entry.871400439", email: "entry.1984542148", version: "entry.550025366", details: "entry.963760724" },
};
// Must match the form's multiple-choice options exactly
const FEEDBACK_TYPES = [["idea", "Idea or feature request"], ["problem", "Something isn't working"], ["question", "Question"], ["other", "Other"]];

function browserName() {
  const ua = navigator.userAgent;
  const name = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${name} on ${os}` : name;
}

function FeedbackPage({ printers }) {
  const [type, setType] = useState("idea");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [includeDetails, setIncludeDetails] = useState(true);
  const [server, setServer] = useState(null);
  const [state, setState] = useState(null); // null | "sending" | "sent" | {error}
  useEffect(() => { getServer().then(setServer).catch(() => {}); }, []);
  const counts = printers.reduce((acc, p) => ({ ...acc, [p.model || p.type]: (acc[p.model || p.type] || 0) + 1 }), {});
  const details = [
    server ? `${server.os} (${server.arch})` : null,
    printers.length ? `${printers.length} printer${printers.length === 1 ? "" : "s"}: ${Object.entries(counts).map(([k, n]) => `${k} ×${n}`).join(", ")}` : "No printers yet",
    browserName(),
  ].filter(Boolean).join(" · ");
  const version = APP_VERSION.replace(/^v/, "");
  const send = async e => {
    e.preventDefault();
    if (!message.trim()) return;
    setState("sending");
    const f = FEEDBACK_FORM.fields;
    const body = new URLSearchParams({ [f.type]: FEEDBACK_TYPES.find(([k]) => k === type)[1], [f.message]: message.trim(), [f.email]: email.trim(), [f.version]: version, [f.details]: includeDetails ? details : "" });
    try {
      // Google doesn't let other sites read its reply, so a sent message can't be confirmed beyond reaching Google
      await fetch(`https://docs.google.com/forms/d/e/${FEEDBACK_FORM.id}/formResponse`, { method: "POST", mode: "no-cors", body });
      setState("sent"); setMessage("");
    } catch { setState({ error: "Couldn't reach Google Forms. Check this device's internet connection and try again." }); }
  };
  return (
    <>
      <div className="mb-7">
        <h1 className="text-3xl font-bold tracking-tight text-white">Send feedback</h1>
        <p className="mt-2 text-sm text-slate-500">Ideas, problems, questions: it all helps make LayerHound better. It goes straight to Team Tactical RC.</p>
      </div>
      <div className="max-w-2xl">
        {!FEEDBACK_FORM ? (
          <Section title="Not set up yet"><p className="text-sm text-slate-400">The feedback form hasn't been connected in this version of LayerHound.</p></Section>
        ) : state === "sent" ? (
          <Section title={<span className="flex items-center gap-2"><CircleCheck size={17} className="text-emerald-300" /> Thank you!</span>}>
            <p className="text-sm text-slate-300">Your feedback was sent to Team Tactical RC.{email.trim() ? " If a reply is needed, it will go to " + email.trim() + "." : ""}</p>
            <button onClick={() => setState(null)} className="mt-4 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 hover:bg-white/5">Send more feedback</button>
          </Section>
        ) : (
          <form onSubmit={send}>
            <Section title="What's on your mind?" footer={<>
              {state?.error && <span className="text-xs text-red-300">{state.error}</span>}
              <button type="submit" disabled={state === "sending" || !message.trim()} className="flex items-center gap-2 rounded-lg bg-violet-500 px-4 py-2 text-sm font-medium text-[#fff] hover:bg-violet-400 disabled:opacity-50">
                {state === "sending" ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} {state === "sending" ? "Sending…" : "Send"}
              </button>
            </>}>
              <Segmented label="Kind of feedback" value={type} onChange={setType} options={FEEDBACK_TYPES.map(([k, label]) => [k, k === "idea" ? "Idea" : k === "problem" ? "Problem" : label])} />
              <div className="mt-4 space-y-4">
                <Field label={type === "problem" ? "What happened, and what did you expect?" : type === "idea" ? "What would you like LayerHound to do?" : "Your feedback"}>
                  <textarea className={`${inputClass} min-h-[9rem] resize-y`} maxLength={4000} value={message} onChange={e => setMessage(e.target.value)} required />
                </Field>
                <Field label="Your email (optional)" hint="Only if you'd like a reply."><input type="email" className={inputClass} maxLength={200} value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" /></Field>
              </div>
              <div className="mt-4 rounded-xl border border-white/8 bg-white/[.02] p-3 text-xs">
                <Toggle checked={includeDetails} onChange={setIncludeDetails} label="Include system details" hint="Helps track down problems. No names, addresses or passwords." />
                <div className="mt-1 text-slate-500">Sent with your message: <span className="text-slate-300">LayerHound {version}{includeDetails ? ` · ${details}` : ""}</span></div>
              </div>
              <p className="mt-3 text-xs text-slate-600">Sent through Google Forms. Nothing is sent unless you press Send.</p>
            </Section>
          </form>
        )}
      </div>
    </>
  );
}

function formatDuration(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
  return h ? `${h}h ${m}m` : `${m}m`;
}
const formatFilament = mm => mm == null ? "—" : mm >= 1e6 ? `${(mm / 1e6).toFixed(2)} km` : `${(mm / 1000).toFixed(1)} m`;

const JOB_STATUS = {
  completed: { label: "Completed", cls: "border-emerald-500/20 bg-emerald-500/6 text-emerald-300", Icon: CircleCheck },
  failed: { label: "Failed", cls: "border-red-500/20 bg-red-500/6 text-red-300", Icon: CircleX },
  cancelled: { label: "Cancelled", cls: "border-white/10 bg-white/[.03] text-slate-400", Icon: Ban },
  interrupted: { label: "Interrupted", cls: "border-amber-500/20 bg-amber-500/6 text-amber-200", Icon: AlertTriangle },
  printing: { label: "Printing", cls: "border-violet-400/30 bg-violet-500/10 text-violet-200", Icon: Loader2 },
};

// Hours printed per day. Hover (or touch) a bar to see the day's total.
function DailyBars({ days }) {
  const wrap = React.useRef(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(200, e.contentRect.width)));
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, []);
  const H = 140, L = 30, B = 20, T = 8;
  const max = Math.max(1, ...days.map(d => d.hours));
  const top = Math.ceil(max / 4) * 4 || 4;
  const step = (width - L) / days.length, bw = Math.max(1, step - (step > 6 ? 2 : 1));
  const y = v => T + (1 - v / top) * (H - T - B);
  const shown = hover ?? null;
  const label = d => new Date(`${d}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
  const onMove = e => {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.touches?.[0]?.clientX ?? e.clientX) - box.left - L) / step);
    setHover(days[Math.max(0, Math.min(days.length - 1, i))]);
  };
  return (
    <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">Hours printed per day</h3>
        <div className="text-right">
          <span className="text-lg font-semibold tabular-nums text-white">{shown ? `${shown.hours.toFixed(1)} h` : `${days.reduce((n, d) => n + d.hours, 0).toFixed(0)} h`}</span>
          <div className="text-[11px] text-slate-600">{shown ? label(shown.day) : `Last ${days.length} days`}</div>
        </div>
      </div>
      <div ref={wrap} className="mt-3">
        <svg width={width} height={H} className="block touch-none select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)} onTouchMove={onMove} onTouchEnd={() => setHover(null)} role="img" aria-label={`Hours printed per day over the last ${days.length} days`}>
          {[0, top / 2, top].map(v => (
            <g key={v}>
              <line x1={L} x2={width} y1={y(v)} y2={y(v)} style={{ stroke: "var(--lh-grid)" }} />
              <text x={L - 6} y={y(v) + 3.5} textAnchor="end" className="fill-slate-600 text-[10px] tabular-nums">{v}</text>
            </g>
          ))}
          {days.map((d, i) => d.hours > 0 && (
            <rect key={d.day} x={L + i * step} y={y(d.hours)} width={bw} height={Math.max(1, y(0) - y(d.hours))} rx={Math.min(3, bw / 2)}
              style={{ fill: hover?.day === d.day ? "var(--color-violet-300)" : "var(--color-violet-500)" }} />
          ))}
          <text x={L} y={H - 4} className="fill-slate-600 text-[10px]">{label(days[0].day)}</text>
          <text x={width} y={H - 4} textAnchor="end" className="fill-slate-600 text-[10px]">Today</text>
        </svg>
      </div>
    </div>
  );
}

function HistoryPage({ printers }) {
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState(null);
  const [filter, setFilter] = useState({ printer_id: "", status: "", q: "" });
  const [error, setError] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");
  const [confirm, setConfirm] = useState(null);
  const PAGE = 50;

  const loadStats = useCallback(async () => {
    try { setStats(await getHistoryStats(days)); setError(""); } catch (e) { setError(e.message); }
  }, [days]);
  const loadJobs = useCallback(async (more = false) => {
    try {
      const offset = more ? (jobs?.jobs.length ?? 0) : 0;
      const r = await getHistory({ days, ...filter, limit: PAGE, offset });
      setJobs(prev => more && prev ? { total: r.total, jobs: [...prev.jobs, ...r.jobs] } : r);
    } catch (e) { setError(e.message); }
  }, [days, filter, jobs]);
  useEffect(() => { loadStats(); }, [loadStats]);
  // Reload the list when the range or filters change (not when the list itself changes)
  useEffect(() => { loadJobs(); }, [days, filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setInterval(() => { loadStats(); }, 30000); return () => clearInterval(t); }, [loadStats]);

  const sync = async () => {
    setSyncing(true); setSyncMsg("");
    try {
      const r = await importHistory();
      const added = Object.values(r.printers).reduce((n, x) => n + (x.added || 0), 0);
      const failed = Object.entries(r.printers).filter(([, x]) => x.error).map(([n]) => n);
      setSyncMsg(`${added ? `Added ${added} print${added === 1 ? "" : "s"}` : "Already up to date"}${failed.length ? `. Couldn't reach ${failed.join(", ")}` : ""}.`);
      loadStats(); loadJobs();
    } catch (e) { setSyncMsg(e.message); } finally { setSyncing(false); }
  };
  const remove = async id => {
    try { await deleteHistoryJob(id); setConfirm(null); loadStats(); loadJobs(); } catch (e) { setError(e.message); }
  };

  const t = stats?.totals;
  const hasBambu = printers.some(p => p.type === "bambu");
  // Printers with no prints in this range still get a row, so none look forgotten
  const rows = stats ? [...stats.printers, ...printers.filter(p => !stats.printers.some(x => x.printer_id === p.id))
    .map(p => ({ printer_id: p.id, printer: p.name, current: 1, jobs: 0, success_rate: null, seconds: 0, filament_mm: null, last_started: null, none: true }))] : [];
  const compactInput = inputClass.replace("w-full ", "");
  const set = k => e => setFilter(f => ({ ...f, [k]: e.target.value }));
  const ranges = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [0, "All time"]];

  return (
    <>
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Print History</h1>
          <p className="mt-2 text-sm text-slate-500">Every print across your farm. Klipper printers' own history is imported automatically.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Time range" value={days} onChange={setDays} options={ranges} />
          <button data-admin onClick={sync} disabled={syncing} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[.03] px-3 py-2 text-sm text-slate-200 hover:bg-white/[.06] disabled:opacity-50">
            {syncing ? <Loader2 size={15} className="animate-spin" /> : <RotateCw size={15} />} Sync from printers
          </button>
        </div>
      </div>
      {syncMsg && <div className="mb-4 rounded-lg border border-white/10 bg-white/[.03] px-3 py-2 text-xs text-slate-300">{syncMsg}</div>}
      {error && <div className="mb-4 rounded-lg border border-red-500/20 bg-red-500/6 px-3 py-2 text-xs text-red-300">{error}</div>}

      {!stats ? (
        <div className="flex min-h-[30vh] items-center justify-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Loading history…</div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric icon={Printer} label="Prints" value={t.jobs.toLocaleString()} sub={t.active ? `${t.active} printing now` : days ? `In the last ${days} days` : "All time"} />
            <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-4">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-500"><CircleCheck size={15} /> Success rate</div>
              <div className="mt-3 text-2xl font-semibold tracking-tight text-white">{t.success_rate == null ? "—" : `${t.success_rate}%`}</div>
              <div className="mt-1 text-xs text-slate-500">{t.completed} completed · {t.failed} failed · {t.cancelled} cancelled</div>
            </div>
            <Metric icon={Clock} label="Hours printed" value={Math.round((t.seconds || 0) / 3600).toLocaleString()} sub={t.jobs ? `Average ${formatDuration((t.seconds || 0) / t.jobs)} per print` : "No prints yet"} />
            <Metric icon={Package} label="Filament used" value={formatFilament(t.filament_mm || 0)} sub={hasBambu ? "Klipper printers only; Bambu doesn't report it" : "By length"} />
          </section>

          <section className="mt-4"><DailyBars days={stats.daily} /></section>

          <section className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
            <h2 className="font-semibold text-white">By printer</h2>
            <p className="mt-1 text-xs text-slate-600">Click a printer to see only its prints below.</p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead><tr className="border-b border-white/6 text-left text-xs text-slate-500">
                  <th className="pb-2 font-medium">Printer</th><th className="pb-2 text-right font-medium">Prints</th><th className="pb-2 pl-6 font-medium">Success rate</th>
                  <th className="pb-2 text-right font-medium">Hours</th><th className="pb-2 text-right font-medium">Filament</th><th className="pb-2 text-right font-medium">Last print</th>
                </tr></thead>
                <tbody>
                  {rows.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-slate-500">No prints in this time range.</td></tr>}
                  {rows.map(p => (
                    <tr key={p.printer_id} onClick={() => setFilter(f => ({ ...f, printer_id: String(p.printer_id) }))} className={`cursor-pointer border-b border-white/6 last:border-0 hover:bg-white/[.02] ${String(p.printer_id) === filter.printer_id ? "bg-violet-500/8" : ""}`}>
                      <td className="py-2.5 text-white">{p.printer}{!p.current && <span className="ml-2 text-xs text-slate-600">(removed)</span>}{p.none && <span className="ml-2 text-xs text-slate-600">No prints recorded yet</span>}</td>
                      <td className="py-2.5 text-right tabular-nums text-slate-300">{p.jobs}</td>
                      <td className="py-2.5 pl-6">
                        {p.success_rate == null ? <span className="text-slate-600">—</span> : (
                          <div className="flex items-center gap-2"><div className="w-24"><Bar percent={p.success_rate} warnAt={101} /></div><span className="tabular-nums text-slate-300">{p.success_rate}%</span></div>
                        )}
                      </td>
                      <td className="py-2.5 text-right tabular-nums text-slate-300">{Math.round((p.seconds || 0) / 3600).toLocaleString()}</td>
                      <td className="py-2.5 text-right tabular-nums text-slate-300">{p.filament_mm ? formatFilament(p.filament_mm) : "—"}</td>
                      <td className="py-2.5 text-right text-slate-400">{p.last_started ? fmtDate(p.last_started * 1000, { month: "short", day: "numeric" }) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <section className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
        <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
          <div><h2 className="font-semibold text-white">Prints</h2><p className="mt-1 text-xs text-slate-600">{jobs ? `${jobs.total.toLocaleString()} matching` : "Loading…"}</p></div>
          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600" />
              <input className={`${compactInput} w-56 pl-9`} placeholder="Search file names" value={filter.q} onChange={set("q")} />
            </div>
            <select className={`${compactInput} w-44`} value={filter.printer_id} onChange={set("printer_id")} aria-label="Printer">
              <option value="">All printers</option>
              {rows.map(p => <option key={p.printer_id} value={p.printer_id}>{p.printer}</option>)}
            </select>
            <select className={`${compactInput} w-36`} value={filter.status} onChange={set("status")} aria-label="Status">
              <option value="">Any status</option>
              {Object.entries(JOB_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-4 overflow-hidden rounded-xl border border-white/6">
          {jobs?.jobs.length === 0 && <div className="py-10 text-center text-sm text-slate-500">No prints match these filters.</div>}
          {jobs?.jobs.map(j => {
            const st = JOB_STATUS[j.status] ?? JOB_STATUS.interrupted;
            return (
              <div key={j.id} className="group flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-white/6 px-3 py-2.5 last:border-0">
                <span className={`flex w-28 shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] ${st.cls}`}><st.Icon size={12} className={j.status === "printing" ? "animate-spin" : ""} /> {st.label}</span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-white" title={j.file}>{j.file || "Unknown file"}</div>
                  <div className="truncate text-[11px] text-slate-600">{j.printer} · {fmtDate(j.started_at * 1000, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}{j.source === "printer" ? " · from printer" : ""}</div>
                </div>
                <div className="w-20 text-right text-xs tabular-nums text-slate-300">{formatDuration(j.duration)}</div>
                <div className="hidden w-20 text-right text-xs tabular-nums text-slate-500 sm:block">{j.filament_mm ? formatFilament(j.filament_mm) : ""}</div>
                <div className="w-24 text-right">
                  {j.status === "printing" ? null : confirm === j.id ? (
                    <span className="flex items-center justify-end gap-1">
                      <button onClick={() => remove(j.id)} className="rounded-lg bg-red-500/80 px-2 py-1 text-xs text-[#fff] hover:bg-red-500">Delete</button>
                      <button onClick={() => setConfirm(null)} className="rounded-lg px-1.5 py-1 text-xs text-slate-400 hover:bg-white/5">Keep</button>
                    </span>
                  ) : (
                    <button data-admin onClick={() => setConfirm(j.id)} className="rounded-lg p-1.5 text-slate-600 opacity-100 hover:bg-white/6 hover:text-red-300 sm:opacity-0 sm:group-hover:opacity-100" aria-label={`Delete ${j.file} from history`}><Trash2 size={15} /></button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        {jobs && jobs.jobs.length < jobs.total && (
          <div className="mt-3 flex justify-center"><button onClick={() => loadJobs(true)} className="rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 hover:bg-white/5">Show more ({(jobs.total - jobs.jobs.length).toLocaleString()} left)</button></div>
        )}
      </section>
    </>
  );
}

function Dashboard({ onSignOut, onSignIn }) {
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
  // Bumped whenever settings change, so the whole app re-renders with the new preferences
  const [, setPrefsVersion] = useState(0);
  const applySettings = useCallback(s => { applyPrefs(s); setPrefsVersion(v => v + 1); }, []);
  const reloadSettings = useCallback(async () => { try { applySettings(await getSettings()); } catch { /* keep defaults */ } }, [applySettings]);
  useEffect(() => { reloadSettings(); }, [reloadSettings]);

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
    ...(system?.services?.docker?.available ? [{ name: "Docker", tone: "good", status: `${system.services.docker.running} of ${system.services.docker.total} running` }] : []),
    // Services added on the Services page (first few; the page shows all of them)
    ...(system?.services?.services ?? []).slice(0, 5).map(sv => ({ name: sv.name, tone: sv.up == null ? "off" : sv.up ? "good" : "bad", status: sv.up == null ? "Checking" : sv.up ? "Up" : "Down" })),
  ];
  const extraServices = Math.max(0, (system?.services?.services?.length ?? 0) - 5);

  const placeholder = !['dashboard', 'printers', 'history', 'server', 'storage', 'network', 'services', 'settings', 'feedback'].includes(page);
  const title = PAGE_TITLES[page] ?? page;

  return (
    <div className="min-h-screen bg-[var(--lh-bg)] text-slate-200">
      <div className="flex min-h-screen">
        <Sidebar page={page} setPage={setPage} open={menu} setOpen={setMenu} usingDemo={usingDemo} summary={summary} onSignOut={onSignOut} onSignIn={onSignIn} />
        <main className="min-w-0 flex-1">
          <header className="flex h-20 items-center justify-between border-b border-white/7 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button className="rounded-lg p-2 text-slate-500 hover:bg-white/5 lg:hidden" onClick={() => setMenu(true)} aria-label="Open menu"><Menu size={21} /></button>
              <div>
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="mt-0.5 text-xs text-slate-600">{prefs.farm_name}</div>
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
            ) : page === "history" ? (
              <HistoryPage printers={livePrinters ?? []} />
            ) : page === "settings" ? (
              <SettingsPage onSaved={applySettings} onRestored={() => { reloadSettings(); refreshPrinters(); }} />
            ) : page === "services" ? (
              <ServicesPage printers={livePrinters ?? []} />
            ) : page === "feedback" ? (
              <FeedbackPage printers={livePrinters ?? []} />
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
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.22em] text-violet-400"><Zap size={13} /> Print farm operations</div>
                      <h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">{prefs.farm_name}</h1>
                      {prefs.farm_description && <p className="mt-2 text-sm text-slate-500">{prefs.farm_description}</p>}
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
                    <button data-admin onClick={() => { setPage("printers"); setAdding(true); }} className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-white/10 py-10 text-sm text-slate-500 hover:border-violet-400/40 hover:text-slate-300">
                      <Plus size={16} /> Add your first printer
                    </button>
                  ) : (
                    <PrinterGrid count={printers.length}>
                      {printers.map(p => <PrinterCard key={p.id} printer={p} onSelect={setSelected} />)}
                    </PrinterGrid>
                  )}
                </section>

                <section className="mt-8 grid gap-4 lg:grid-cols-3">
                  <div className="lg:col-span-2 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0"><h2 className="font-semibold text-white">Server Health</h2><p className="mt-1 truncate text-xs text-slate-600">{system ? `${system.hostname}${system.ip ? ` · ${system.ip}` : ""}` : "Waiting for API"}</p></div>
                      <button onClick={() => setPage("server")} className="flex shrink-0 items-center gap-1 text-xs font-medium text-violet-400 hover:text-violet-300">Details <ChevronRight size={14} /></button>
                    </div>
                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl bg-white/[.025] p-4">
                        <div className="text-xs text-slate-600">Temperature</div>
                        <div className="mt-2 text-xl font-semibold text-white">{system?.temperature_c != null ? fmtTemp(system.temperature_c) : "N/A"}</div>
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

                  <div className="rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
                    <div className="flex items-center justify-between"><div><h2 className="font-semibold text-white">Services</h2><p className="mt-1 text-xs text-slate-600">Live checks</p></div><button onClick={() => setPage("services")} className="flex items-center gap-1 text-xs font-medium text-violet-400 hover:text-violet-300">Manage <ChevronRight size={14} /></button></div>
                    <div className="mt-4 space-y-3">
                      {services.map(sv => (
                        <div key={sv.name} className="flex items-center justify-between gap-3 text-sm">
                          <span className={sv.tone === "off" ? "text-slate-600" : "text-slate-400"}>{sv.name}</span>
                          <span className="flex items-center gap-2 whitespace-nowrap text-xs text-slate-500"><StatusDot tone={sv.tone} />{sv.status}</span>
                        </div>
                      ))}
                      {extraServices > 0 && <button onClick={() => setPage("services")} className="text-xs text-slate-500 hover:text-slate-300">+ {extraServices} more on the Services page</button>}
                      {!system?.services?.services?.length && <button onClick={() => setPage("services")} className="text-xs text-violet-400 hover:text-violet-300">Add Home Assistant, Pi-hole and other services</button>}
                    </div>
                  </div>
                </section>

                <section className="mt-4 rounded-2xl border border-white/8 bg-[var(--lh-card)] p-5">
                  <div className="flex items-center justify-between">
                    <div><h2 className="font-semibold text-white">Alerts</h2><p className="mt-1 text-xs text-slate-600">Printers, internet, devices, services, server temperature, storage and memory</p></div>
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

applyTheme();
createRoot(document.getElementById("root")).render(<><UpdateBanner /><App /></>);
