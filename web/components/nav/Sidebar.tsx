"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { OnsIcon, GlobeMark } from "@/components/ui/icons";

type NavItem =
  | { kind: "section"; label: string }
  | { kind: "link"; href: string; label: string; icon: string };

const NAV: NavItem[] = [
  { kind: "section", label: "Life" },
  { kind: "link", href: "/",        label: "Home",         icon: "home" },
  { kind: "link", href: "/habits",  label: "Habits",       icon: "habits" },
  { kind: "link", href: "/fitness", label: "Fitness",      icon: "fitness" },
  { kind: "link", href: "/reading", label: "Reading",      icon: "reading" },
  { kind: "link", href: "/goals",   label: "Goals",        icon: "goals" },
  { kind: "link", href: "/checkin", label: "Check-in",     icon: "checkin" },
  { kind: "section", label: "Entertainment" },
  { kind: "link", href: "/music",   label: "Music",        icon: "music" },
  { kind: "link", href: "/kglw",    label: "King Gizzard", icon: "kglw" },
  { kind: "link", href: "/shows",   label: "Shows",        icon: "shows" },
  { kind: "link", href: "/sports",  label: "Sports",       icon: "sports" },
  { kind: "section", label: "Edge" },
  { kind: "link", href: "/cfb",     label: "CFB Betting",  icon: "cfb" },
];

export function Sidebar() {
  const path = usePathname();

  return (
    <aside
      className="w-[232px] shrink-0 bg-canvas-2 flex flex-col overflow-hidden"
      style={{ borderRight: "1px solid #e6e3dc", padding: "24px 0 16px" }}
    >
      {/* Brand mark */}
      <div className="px-[22px] pb-[18px] mb-[10px] flex gap-[11px] items-center">
        <div className="text-green">
          <GlobeMark size={34} stroke="#1d5536" sw={1.5} />
        </div>
        <div>
          <div
            className="font-serif font-bold text-green"
            style={{ fontSize: 19, letterSpacing: "0.5px" }}
          >
            ONS
          </div>
          <div
            className="font-mono uppercase text-faint"
            style={{ fontSize: 7.5, letterSpacing: "1.3px" }}
          >
            Operating Narcisystem
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-[13px] overflow-y-auto ons-scroll">
        {NAV.map((item, i) => {
          if (item.kind === "section") {
            return (
              <div
                key={i}
                className="font-mono uppercase text-faint"
                style={{
                  fontSize: 8.5,
                  letterSpacing: "1.8px",
                  padding: "15px 9px 6px",
                }}
              >
                {item.label}
              </div>
            );
          }

          const active =
            item.href === "/"
              ? path === "/"
              : path.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className="ons-tap flex items-center gap-[11px] mb-px no-underline"
              style={{
                width: "100%",
                textAlign: "left",
                padding: "8px 10px",
                borderRadius: 7,
                fontSize: 13,
                color: active ? "#1d5536" : "#232a22",
                background: active ? "#fbfaf5" : "transparent",
                fontWeight: active ? 600 : 400,
                boxShadow: active ? "inset 2px 0 0 #1d5536" : "none",
                textDecoration: "none",
              }}
            >
              <span
                className="flex"
                style={{ color: active ? "#1d5536" : "#736e5f" }}
              >
                <OnsIcon name={item.icon} size={17} stroke={1.5} />
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div
        className="font-mono flex justify-between text-faint"
        style={{
          padding: "12px 22px 0",
          borderTop: "1px solid #e6e3dc",
          fontSize: 8.5,
          letterSpacing: "1px",
        }}
      >
        <span>v3 walk-forward</span>
        <span className="text-green">● live</span>
      </div>
    </aside>
  );
}
