// Formatting helpers. Money is integer minor units (satang for THB).

const moneyFormatters = new Map<string, Intl.NumberFormat>();

export function formatMoney(minor: number | null | undefined, currency = "THB"): string {
  const key = currency;
  let fmt = moneyFormatters.get(key);
  if (!fmt) {
    fmt = new Intl.NumberFormat("th-TH", { style: "currency", currency, minimumFractionDigits: 2 });
    moneyFormatters.set(key, fmt);
  }
  return fmt.format((minor ?? 0) / 100);
}

/** Compact money for chart axes: ฿1.2K, ฿35K. */
export function formatMoneyCompact(minor: number): string {
  const value = minor / 100;
  if (Math.abs(value) >= 1000) {
    return `฿${new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value)}`;
  }
  return `฿${Math.round(value)}`;
}

/** Parse a user-entered baht amount ("120", "120.50") into minor units. */
export function parseMoney(input: string): number | null {
  const cleaned = input.replace(/[,\s฿]/g, "");
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const [whole, fraction = ""] = cleaned.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

export function minorToInput(minor: number): string {
  return (minor / 100).toFixed(2);
}

export function formatNumber(value: number | null | undefined, maximumFractionDigits = 2): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits }).format(value ?? 0);
}

export function formatQty(value: number | null | undefined, unit?: string | null): string {
  const n = value ?? 0;
  if (unit === "g" && Math.abs(n) >= 1000) return `${formatNumber(n / 1000, 2)} kg`;
  if (unit === "ml" && Math.abs(n) >= 1000) return `${formatNumber(n / 1000, 2)} L`;
  return `${formatNumber(n, 3)}${unit ? ` ${unit}` : ""}`;
}

export function formatPercentBps(bps: number): string {
  return `${formatNumber(bps / 100, 2)}%`;
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatDateTime(iso: string | null | undefined, timeZone = "Asia/Bangkok"): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(iso));
}

export function formatTime(iso: string | null | undefined, timeZone = "Asia/Bangkok"): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone }).format(new Date(iso));
}

export function formatDate(isoDate: string | null | undefined): string {
  if (!isoDate) return "—";
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export function formatShortDate(isoDate: string): string {
  const [y, m, d] = isoDate.slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

export function minutesSince(iso: string | null | undefined, now = Date.now()): number {
  if (!iso) return 0;
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60000));
}

/** Local calendar date (YYYY-MM-DD) in a time zone. */
export function localDate(timeZone = "Asia/Bangkok", offsetDays = 0): string {
  const date = new Date(Date.now() + offsetDays * 86400000);
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function humanize(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/** Convert a baht amount typed by the user (may be fractional, e.g. per gram)
 * into a minor-unit string with at most 4 decimals, avoiding float artefacts. */
export function bahtToMinorString(input: string): string | null {
  const value = Number(input.replace(/[,\s฿]/g, ""));
  if (!Number.isFinite(value) || value < 0) return null;
  return (Math.round(value * 1_000_000) / 10_000).toString();
}

/** Per-base-unit cost; gram/millilitre prices read better per kg/L. */
export function formatUnitCost(minor: number | null | undefined, unit?: string | null): string {
  if (minor === null || minor === undefined) return "—";
  if (unit === "g") return `${formatMoney(minor * 1000)}/kg`;
  if (unit === "ml") return `${formatMoney(minor * 1000)}/L`;
  return `${formatMoney(minor)}${unit ? `/${unit}` : ""}`;
}

/** "just now", "5 min ago", "3 hr ago", "2 days ago". */
export function formatRelativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  if (Math.abs(seconds) < 45) return "just now";
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) return rtf.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return rtf.format(hours, "hour");
  return rtf.format(Math.round(hours / 24), "day");
}
