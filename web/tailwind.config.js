/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // Registered as real Tailwind color tokens (not just CSS custom
        // properties) so opacity-modifier syntax like bg-green/70 works.
        // Without this, /NN suffixes silently compile to nothing.
        canvas:       "#f6f5f2",
        surface:      "#ffffff",
        sidebar:      "#1a2420",
        border:       "#e6e3dc",
        ink:          "#1a2420",
        muted:        "#6b7268",
        faint:        "#9a9d94",
        green: {
          DEFAULT: "#4a7c5f",
          light:   "#7ec8a0",
          bright:  "#3f6e52",
        },
        amber:        "#c08a2e",
        red:          "#b6493f",
      },
    },
  },
  plugins: [],
};
