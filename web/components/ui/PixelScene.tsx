"use client";

// A pixel-art title scene (DESIGN.md → Pixel Scenes). Place it in PageHead's `scene` slot.
// The canvas engine lives in lib/pixelScenes.js; this wrapper mounts it and passes data through
// data-* attributes, so changing a prop redraws without remounting.

import { useEffect, useRef } from "react";
import { mountScene } from "@/lib/pixelScenes";

export type Weather = "sun" | "partly" | "cloudy" | "wind" | "rain" | "snow";

export function PixelScene({
  scene,
  label,
  record,
  weather,
  temp,
  data,
}: {
  scene: "cfb" | "week" | "fitness" | "reading";
  /** What the scene shows, for screen readers. */
  label: string;
  /** CFB: the season record for the scoreboard, e.g. "17-11". */
  record?: string;
  /** This week: today's conditions and high. */
  weather?: Weather;
  temp?: number | string;
  /** Scene-specific values, passed as data-* attributes (e.g. { classes: 84, miles: 272 } for Fitness). */
  data?: Record<string, string | number | null | undefined>;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => (ref.current ? mountScene(ref.current) : undefined), []);

  return (
    <button
      ref={ref}
      type="button"
      className="ons-scene"
      data-scene={scene}
      data-record={record ?? ""}
      data-wx={weather ?? "sun"}
      data-temp={temp ?? ""}
      {...Object.fromEntries(Object.entries(data ?? {}).map(([k, v]) => [`data-${k}`, v ?? ""]))}
      aria-label={`Pause animation: ${label}`}
    >
      <canvas aria-hidden="true" />
    </button>
  );
}
