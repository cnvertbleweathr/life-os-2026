import type { Metadata, Viewport } from "next";
import { Sidebar } from "@/components/nav/Sidebar";
import { TopBar } from "@/components/nav/TopBar";
import { MobileNav } from "@/components/nav/MobileNav";
import { TopTicker } from "@/components/nav/TopTicker";
import "./globals.css";

export const metadata: Metadata = {
  title: "ONS — Operating Narcisystem",
  description: "Personal life-tracking dashboard and CFB analytics engine",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#edf1ee" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1210" },
  ],
};

// Runs before first paint: saved theme, else the OS setting. Keeps dark-mode users from a white flash.
const THEME_INIT = `(function(){try{var t=localStorage.getItem('ons-theme');if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme='light'}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="ons-shell overflow-hidden bg-frame text-ink font-sans antialiased">
        <div className="ons-app">
          <Sidebar />
          <TopBar />
          <main className="ons-sheet-main">
            <TopTicker />
            <div className="flex-1 overflow-y-auto ons-scroll">{children}</div>
          </main>
        </div>
        <MobileNav />
      </body>
    </html>
  );
}
