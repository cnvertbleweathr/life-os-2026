"use client";

/**
 * Phone navigation (< 768px; hidden on desktop by globals.css).
 *
 * Bottom tab bar for the pages used on the go — Home, Habits, Check-in,
 * Capture — plus "More", which opens a sheet with the full menu (same NAV
 * as the desktop sidebar, so the two can't drift apart).
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { OnsIcon } from "@/components/ui/icons";
import { NAV, isActive } from "@/components/nav/Sidebar";

const TABS = [
  { href: "/",        label: "Home",     icon: "home" },
  { href: "/habits",  label: "Habits",   icon: "habits" },
  { href: "/checkin", label: "Check-in", icon: "checkin" },
  { href: "/capture", label: "Capture",  icon: "inbox" },
];

const GREEN = "#1d5536";
const MUTED = "#736e5f";

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
        style={{ background: "rgba(35,42,34,0.35)" }}
        onClick={() => setOpen(false)}
      >
        <nav
          aria-label="All pages"
          onClick={(e) => e.stopPropagation()}
          className="bg-canvas-2"
          style={{
            borderTopLeftRadius: 14, borderTopRightRadius: 14,
            padding: "10px 14px calc(78px + env(safe-area-inset-bottom))",
            maxHeight: "80dvh", overflowY: "auto",
          }}
        >
          <div className="mx-auto mb-2" style={{ width: 36, height: 4, borderRadius: 4, background: "#d9d4c8" }} />
          {NAV.map((item, i) =>
            item.kind === "section" ? (
              <div key={i} className="font-mono uppercase text-faint"
                   style={{ fontSize: 9, letterSpacing: "1.8px", padding: "14px 8px 6px" }}>
                {item.label}
              </div>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 no-underline"
                style={{
                  padding: "12px 10px", borderRadius: 8, fontSize: 15,
                  color: isActive(path, item.href) ? GREEN : "#232a22",
                  fontWeight: isActive(path, item.href) ? 600 : 400,
                  background: isActive(path, item.href) ? "#fbfaf5" : "transparent",
                }}
              >
                <span style={{ color: isActive(path, item.href) ? GREEN : MUTED, display: "flex" }}>
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
        className="ons-tabbar fixed bottom-0 inset-x-0 z-50 bg-surface"
        style={{
          borderTop: "1px solid #e6e3dc",
          paddingBottom: "env(safe-area-inset-bottom)",
          boxShadow: "0 -4px 16px rgba(35,42,34,0.06)",
        }}
      >
        {TABS.map((t) => {
          const on = isActive(path, t.href) && !open;
          return (
            <Link key={t.href} href={t.href} aria-current={on ? "page" : undefined}
                  className="flex-1 flex flex-col items-center no-underline" style={tabStyle(on)}>
              <OnsIcon name={t.icon} size={21} stroke={on ? 1.9 : 1.5} />
              <span>{t.label}</span>
            </Link>
          );
        })}
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="flex-1 flex flex-col items-center border-none bg-transparent cursor-pointer"
          style={tabStyle(open || !onTab)}
        >
          <svg width={21} height={21} viewBox="0 0 24 24" fill="none" stroke="currentColor"
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
    gap: 3, padding: "8px 0 7px", minHeight: 54,
    color: on ? GREEN : MUTED,
    fontSize: 10.5, fontWeight: on ? 600 : 500, letterSpacing: "0.2px",
  };
}
