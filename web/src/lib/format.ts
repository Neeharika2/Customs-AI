import type { ShipmentStatus } from "./api";

export function relativeTime(iso: string): string {
  const date = new Date(iso);
  const diff = (date.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(diff / 86400), "day");
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(date);
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}

export const STATUS_LABEL: Record<ShipmentStatus, string> = {
  DRAFT: "Draft",
  EXTRACTING: "Extracting",
  NEEDS_REVIEW: "Needs review",
  AWAITING_APPROVAL: "Awaiting approval",
  READY: "Ready",
  EXPORTED: "Exported",
};

export const STATUS_ORDER: ShipmentStatus[] = [
  "DRAFT",
  "EXTRACTING",
  "NEEDS_REVIEW",
  "AWAITING_APPROVAL",
  "READY",
  "EXPORTED",
];

export function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function num(value: unknown, digits = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n);
}
