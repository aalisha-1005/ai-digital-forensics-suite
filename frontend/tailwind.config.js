export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {
    fontFamily: { sans: ["Inter", "system-ui", "Segoe UI", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "Consolas", "monospace"] },
    colors: { ink: { 950: "#060b14", 900: "#0a1220", 850: "#0e1a2c", 800: "#13233a", 700: "#1c3352" }, cy: { 400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2" } },
  } },
  plugins: [],
};
