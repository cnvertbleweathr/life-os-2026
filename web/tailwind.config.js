/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans:  ["Spline Sans", "system-ui", "sans-serif"],
        serif: ["Spectral", "Georgia", "serif"],
        mono:  ["Spline Sans Mono", "ui-monospace", "monospace"],
      },
      colors: {
        canvas:       "#f6f5f2",
        "canvas-2":   "#efebe1",
        surface:      "#fbfaf5",
        "surface-hi": "#ffffff",
        border:       "#e6e3dc",
        "border-2":   "#ebe5d8",
        ink:          "#232a22",
        muted:        "#736e5f",
        faint:        "#a39d8c",
        green: {
          DEFAULT: "#1d5536",
          bright:  "#2f6b43",
          soft:    "#e9efe7",
          light:   "#7ec8a0",
        },
        amber:        "#9a6a1e",
        red:          "#a8473a",
        blue:         "#3a5f7a",
      },
    },
  },
  plugins: [],
};
