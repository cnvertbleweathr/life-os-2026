"use client";

// The top bar of the L-frame: breadcrumb on the left, theme switch on the right.
// (The mockup's "Ask the system ⌘K" field waits for Ask ONS, ROADMAP A1; no fake search box here.)

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GlobeMark } from "@/components/ui/icons";
import { routeLabel } from "@/components/nav/Sidebar";
import { ThemeToggle } from "@/components/nav/ThemeToggle";

export function TopBar() {
  const path = usePathname();
  const { group, label } = routeLabel(path);

  return (
    <header className="ons-topbar flex items-center gap-3 bg-frame" style={{ padding: "0 12px 0 8px" }}>
      {/* Brand on phones, where the sidebar is hidden */}
      <Link href="/" className="md:hidden flex items-center gap-2 no-underline text-hue pl-2">
        <GlobeMark size={22} stroke="currentColor" sw={1.5} />
        <span className="font-semibold text-ink" style={{ fontSize: 15 }}>ONS</span>
      </Link>
      <nav aria-label="Breadcrumb" className="hidden md:block text-muted" style={{ fontSize: 13 }}>
        {group && <>{group} / </>}
        <span className="text-ink font-medium">{label}</span>
      </nav>
      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
      </div>
    </header>
  );
}
