import type { Metadata } from "next";
import { Sidebar } from "@/components/nav/Sidebar";
import { LiveTrackerBanner } from "@/components/cfb/LiveTrackerBanner";
import "./globals.css";

export const metadata: Metadata = {
  title: "ONS — Operating Narcisystem",
  description: "Personal life-tracking dashboard and CFB analytics engine",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="flex h-screen overflow-hidden bg-canvas text-ink font-sans antialiased">
        <Sidebar />
        <main className="flex-1 overflow-y-auto ons-scroll flex flex-col">
          <LiveTrackerBanner />
          <div className="flex-1">{children}</div>
        </main>
      </body>
    </html>
  );
}
