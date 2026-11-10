"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { OnsIcon, GlobeMark } from "@/components/ui/icons";

type NavItem =
  | { kind: "section"; label: string }
  | { kind: "link"; href: string; label: string; icon: string; area?: string };

// Logbook Color groups (DESIGN.md → Layout). `area` colours the icon with that life area's mark.
export const NAV: NavItem[] = [
  { kind: "section", label: "Today" },
  { kind: "link", href: "/",        label: "This week",        icon: "home" },
  { kind: "link", href: "/habits",  label: "Habits",           icon: "habits",  area: "habit" },
  { kind: "link", href: "/checkin", label: "Check-in",         icon: "checkin", area: "check" },
  { kind: "link", href: "/capture", label: "Capture",          icon: "inbox",   area: "check" },
  { kind: "section", label: "Track" },
  { kind: "link", href: "/goals",   label: "Goals",            icon: "goals" },
  { kind: "link", href: "/fitness", label: "Fitness",          icon: "fitness", area: "run" },
  { kind: "link", href: "/reading", label: "Reading",          icon: "reading", area: "read" },
  { kind: "link", href: "/film",    label: "Film",             icon: "film",    area: "film" },
  { kind: "link", href: "/progeny", label: "Progeny",          icon: "progeny" },
  { kind: "section", label: "Degenerates Corner" },
  { kind: "link", href: "/cfb",     label: "College Football", icon: "cfb",     area: "edge" },
  { kind: "link", href: "/nba",     label: "NBA",              icon: "nba",     area: "edge" },
  { kind: "link", href: "/nhl",     label: "NHL",              icon: "nhl",     area: "edge" },
  { kind: "section", label: "Play" },
  { kind: "link", href: "/music",   label: "Music",            icon: "music" },
  { kind: "link", href: "/kglw",    label: "King Gizzard",     icon: "kglw" },
  { kind: "link", href: "/sports",  label: "Sports",           icon: "sports" },
];

/** Shared by the sidebar, top bar and phone nav so "active" means the same thing. */
export function isActive(path: string, href: string): boolean {
  return href === "/" ? path === "/" : path.startsWith(href);
}

/** The group and label for the current route, for the breadcrumb. */
export function routeLabel(path: string): { group: string; label: string } {
  let group = "";
  for (const item of NAV) {
    if (item.kind === "section") { group = item.label; continue; }
    if (isActive(path, item.href)) return { group, label: item.label };
  }
  return { group: "", label: "" };
}

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="ons-sidebar bg-frame flex flex-col overflow-hidden">
      <Link href="/" className="flex items-center gap-[10px] px-5 no-underline text-hue" style={{ height: 48, flex: "none" }}>
        <GlobeMark size={24} stroke="currentColor" sw={1.5} />
        <span className="font-semibold text-ink" style={{ fontSize: 15 }}>ONS</span>
      </Link>

      <nav aria-label="Main" className="flex-1 overflow-y-auto ons-scroll" style={{ padding: "4px 12px 16px" }}>
        {NAV.map((item, i) => {
          if (item.kind === "section") {
            return (
              <div key={i} className="text-muted" style={{ fontSize: 12, padding: "16px 10px 4px" }}>
                {item.label}
              </div>
            );
          }
          const active = isActive(path, item.href);
          const iconColor = active ? "var(--hue)" : item.area ? `var(--${item.area}-mark)` : "var(--icon)";
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className="flex items-center gap-[10px] no-underline hover:bg-[var(--hover)]"
              style={{
                height: 32,
                marginBottom: 2,
                padding: "0 10px",
                borderRadius: 6,
                fontSize: 14,
                color: active ? "var(--ink)" : "var(--ink-2)",
                background: active ? "var(--active)" : undefined,
                fontWeight: active ? 500 : 400,
              }}
            >
              <span className="flex" style={{ color: iconColor }}>
                <OnsIcon name={item.icon} size={16} stroke={1.5} />
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
