/** @type {import('tailwindcss').Config} */
// Logbook Color (DESIGN.md). Every colour is a CSS variable defined twice in app/globals.css
// (light and dark on <html data-theme>), so one class works in both themes.
const v = (name) => `var(--${name})`;
const area = (k) => ({ DEFAULT: v(k), ink: v(`${k}-ink`), mark: v(`${k}-mark`) });

module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:  ["IBM Plex Sans", "system-ui", "sans-serif"],
        // No serif in Logbook Color: `font-serif` (titles and big figures on un-migrated pages) maps to Plex Sans.
        serif: ["IBM Plex Sans", "system-ui", "sans-serif"],
        mono:  ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        // ── Logbook Color system ──
        frame: v("frame"),
        sheet: v("sheet"),
        raised: v("raised"),
        active: v("active"),
        rule: v("rule"),
        control: v("control"),
        "ink-2": v("ink-2"),
        hue: { DEFAULT: v("hue"), soft: v("hue-soft"), ink: v("hue-ink") },
        neg: v("neg"),
        pos: v("pos"),
        ok: { DEFAULT: v("ok"), ink: v("ok-ink") },
        risk: { DEFAULT: v("risk"), ink: v("risk-ink") },
        off: { DEFAULT: v("off"), ink: v("off-ink") },
        none: { DEFAULT: v("none"), ink: v("none-ink") },
        // life areas: tint / ink / mark
        run: area("run"), lift: area("lift"), read: area("read"), habit: area("habit"),
        check: area("check"), plan: area("plan"), edge: area("edge"), wx: area("wx"),
        film: area("film"),

        // ── Almanac names, re-pointed so un-migrated pages follow the new system ──
        canvas:       v("raised"),
        "canvas-2":   v("frame"),
        surface:      v("sheet"),
        "surface-hi": v("hue-ink"),
        border:       v("border"),
        "border-2":   v("rule"),
        ink:          v("ink"),
        muted:        v("muted"),
        faint:        v("faint"),
        green: { DEFAULT: v("hue"), bright: v("hue"), soft: v("hue-soft"), light: v("hue") },
        amber:        v("warn"),
        red:          v("neg"),
        blue:         v("series2"),
      },
    },
  },
  plugins: [],
};
