"use client";

/**
 * Phone navigation (< 768px; hidden on desktop by globals.css).
 *
 * Bottom tab bar for the pages used on the go (This week, Habits, Check-in,
 * Capture), plus "More", which opens a sheet with the full menu (same NAV
 * as the desktop sidebar, so the two can't drift apart). Flat: a 1px top
 * border and a 2px forest line over the active tab, no shadow.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { OnsIcon } from "@/components/ui/icons";
import { NAV, isActive } from "@/components/nav/Sidebar";

const TABS = [
  { href: "/",        label: "Week",     icon: "home" },
  { href: "/habits",  label: "Habits",   icon: "habits" },
  { href: "/checkin", label: "Check-in", icon: "checkin" },
  { href: "/capture", label: "Capture",  icon: "inbox" },
];

export function MobileNav() {
  const path = usePathname();
  const [open, setOpen] = useState(false);

  // Close the sheet after navigating, and on Escape.
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onTab = TABS.some((t) => isActive(path, t.href));

  return (
    <>
      <div
        className="ons-sheet fixed inset-0 z-40 flex-col justify-end"
        data-open={open}
        style={{ background: "color-mix(in srgb, var(--ink) 35%, transparent)" }}
        onClick={() => setOpen(false)}
      >
        <nav
          aria-label="All pages"
          onClick={(e) => e.stopPropagation()}
          className="bg-frame"
          style={{
            borderTopLeftRadius: 16, borderTopRightRadius: 16,
            padding: "10px 14px calc(78px + env(safe-area-inset-bottom))",
            maxHeight: "80dvh", overflowY: "auto",
          }}
        >
          <div className="mx-auto mb-2" style={{ width: 36, height: 4, borderRadius: 4, background: "var(--control)" }} />
          {NAV.map((item, i) =>
            item.kind === "section" ? (
              <div key={i} className="text-muted" style={{ fontSize: 13, padding: "14px 8px 6px" }}>
                {item.label}
              </div>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(path, item.href) ? "page" : undefined}
                className="flex items-center gap-3 no-underline"
                style={{
                  minHeight: 44, padding: "0 10px", borderRadius: 8, fontSize: 15,
                  color: isActive(path, item.href) ? "var(--ink)" : "var(--ink-2)",
                  fontWeight: isActive(path, item.href) ? 500 : 400,
                  background: isActive(path, item.href) ? "var(--active)" : "transparent",
                }}
              >
                <span style={{ display: "flex", color: isActive(path, item.href) ? "var(--hue)" : item.area ? `var(--${item.area}-mark)` : "var(--icon)" }}>
                  <OnsIcon name={item.icon} size={19} stroke={1.5} />
                </span>
                {item.label}
              </Link>
            )
          )}
        </nav>
      </div>

      <nav
        aria-label="Main"
        className="ons-tabbar fixed bottom-0 inset-x-0 z-50 bg-frame"
        style={{ borderTop: "1px solid var(--border)", paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {TABS.map((t) => {
          const on = isActive(path, t.href) && !open;
          return (
            <Link key={t.href} href={t.href} aria-current={on ? "page" : undefined}
                  className="flex-1 flex flex-col items-center justify-center no-underline" style={tabStyle(on)}>
              <OnsIcon name={t.icon} size={20} stroke={on ? 1.9 : 1.5} />
              <span>{t.label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="flex-1 flex flex-col items-center justify-center border-none bg-transparent cursor-pointer font-sans"
          style={tabStyle(open || !onTab)}
        >
          <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth={open || !onTab ? 1.9 : 1.5} strokeLinecap="round" aria-hidden="true">
            <line x1="5" y1="7" x2="19" y2="7" />
            <line x1="5" y1="12" x2="19" y2="12" />
            <line x1="5" y1="17" x2="19" y2="17" />
          </svg>
          <span>More</span>
        </button>
      </nav>
    </>
  );
}

function tabStyle(on: boolean): React.CSSProperties {
  return {
    gap: 3, minHeight: 58,
    color: on ? "var(--hue)" : "var(--muted)",
    boxShadow: on ? "inset 0 2px 0 var(--hue)" : undefined,
    fontSize: 12, fontWeight: on ? 600 : 400,
  };
}
