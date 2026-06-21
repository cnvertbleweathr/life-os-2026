"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV = [
  { href: "/",        label: "Home",         icon: "⬛" },
  { section: "Life" },
  { href: "/habits",  label: "Habits",       icon: "✅" },
  { href: "/fitness", label: "Fitness",      icon: "🏃" },
  { href: "/reading", label: "Reading",      icon: "📖" },
  { href: "/goals",   label: "Goals",        icon: "🎯" },
  { href: "/checkin", label: "Check-in",     icon: "📋" },
  { section: "Entertainment" },
  { href: "/music",   label: "Music",        icon: "🎵" },
  { href: "/kglw",    label: "King Gizzard", icon: "🎸" },
  { href: "/shows",   label: "Shows",        icon: "🎟️" },
  { href: "/sports",  label: "Sports",       icon: "📺" },
  { section: "Edge" },
  { href: "/cfb",     label: "CFB Betting",  icon: "🏈" },
] as const;

export function Sidebar() {
  const path = usePathname();

  return (
    <aside className="w-[200px] shrink-0 bg-sidebar flex flex-col py-5 overflow-y-auto">
      <div className="px-3 pb-4 border-b border-white/8 mb-2">
        <p className="text-[13px] font-semibold tracking-wide text-white/85 px-1">
          ONS
        </p>
        <p className="text-[10px] text-white/30 px-1">Operating Narcisystem</p>
      </div>

      <nav className="flex-1">
        {NAV.map((item, i) => {
          if ("section" in item) {
            return (
              <div
                key={i}
                className="px-4 pt-3 pb-1 text-[10px] font-medium tracking-[1.5px] uppercase text-white/20"
              >
                {item.section}
              </div>
            );
          }

          const active =
            item.href === "/" ? path === "/" : path.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-2.5 px-4 py-[7px] text-[13px] transition-colors duration-100",
                active
                  ? "text-green-light bg-green/10 border-l-2 border-l-green pl-[14px]"
                  : "text-white/45 hover:bg-white/5 hover:text-white/75"
              )}
            >
              <span className="text-base leading-none">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 pt-4 border-t border-white/8">
        <span className="text-[10px] text-white/20">v3 walk-forward</span>
      </div>
    </aside>
  );
}
