// Date helpers for ONS pages. Everything is a Denver calendar date as "YYYY-MM-DD"; formatting happens in UTC
// on a noon timestamp so a date never shifts across a timezone boundary.

export const TZ = "America/Denver";
export const DAY = 86_400_000;

export const isoDenver = (d: Date) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
export const fromIso = (iso: string) => { const [y, m, d] = iso.slice(0, 10).split("-").map(Number); return new Date(Date.UTC(y, m - 1, d, 12)); };
export const addDays = (iso: string, n: number) => new Date(fromIso(iso).getTime() + n * DAY).toISOString().slice(0, 10);
export const daysBetween = (a: string, b: string) => Math.round((fromIso(b).getTime() - fromIso(a).getTime()) / DAY);
export const fmt = (iso: string, o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-US", { timeZone: "UTC", ...o }).format(fromIso(iso));
export const short = (iso: string) => fmt(iso, { month: "short", day: "numeric" });
export const plural = (n: number, one: string, many = one + "s") => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
export const join = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/** Day of the year, days left and the fraction gone, for a Denver date. */
export function yearClock(today: string) {
  const y = +today.slice(0, 4);
  const daysInYear = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
  const dayOfYear = daysBetween(`${y}-01-01`, today) + 1;
  return { y, daysInYear, dayOfYear, daysLeft: daysInYear - dayOfYear, frac: dayOfYear / daysInYear };
}

/** "Today", "Tomorrow", or "Sat, Nov 7". */
export const dayLabel = (iso: string, today: string) =>
  iso === today ? "Today" : iso === addDays(today, 1) ? "Tomorrow" : fmt(iso, { weekday: "short", month: "short", day: "numeric" });

/** "7:30 pm" from a Denver-local "YYYY-MM-DDTHH:MM:SS". */
export function localTime(startLocal?: string | null) {
  if (!startLocal || !startLocal.includes("T")) return "";
  const [h, m] = startLocal.split("T")[1].split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
}

/** Decode HTML entities that arrive in scraped text ("Anita&#039;s"). */
export function decode(s: string) {
  return String(s ?? "").replace(/&(#\d+|#x[\da-f]+|amp|lt|gt|quot|apos|nbsp);/gi, (_, e: string) => {
    const k = e.toLowerCase();
    if (k[0] === "#") return String.fromCodePoint(k[1] === "x" ? parseInt(k.slice(2), 16) : parseInt(k.slice(1), 10));
    return ({ amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " } as Record<string, string>)[k];
  }).replace(/ /g, " ");
}
