import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          muted: "rgb(var(--ink-muted) / <alpha-value>)",
        },
        surface: "rgb(var(--surface) / <alpha-value>)",
        panel: "rgb(var(--panel) / <alpha-value>)",
        raised: "rgb(var(--raised) / <alpha-value>)",
        brand: {
          DEFAULT: "rgb(var(--brand) / <alpha-value>)",
          soft: "rgb(var(--brand-soft) / <alpha-value>)",
          2: "rgb(var(--brand-2) / <alpha-value>)",
        },
        accent: "rgb(var(--accent) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
      },
      borderRadius: { xl2: "1.25rem", xl3: "1.75rem" },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--brand) / 0.15), 0 8px 30px -8px rgb(var(--brand) / 0.35)",
        soft: "0 1px 2px rgb(0 0 0 / 0.04), 0 8px 24px -12px rgb(0 0 0 / 0.18)",
        panel: "0 1px 0 rgb(255 255 255 / 0.04) inset, 0 12px 40px -20px rgb(0 0 0 / 0.45)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(135deg, rgb(var(--brand)) 0%, rgb(var(--brand-2)) 100%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%, 100%": { transform: "scale(2.2)", opacity: "0" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
        "gradient-x": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.35s cubic-bezier(0.21, 1.02, 0.73, 1) both",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(0.66, 0, 0, 1) infinite",
        shimmer: "shimmer 1.6s linear infinite",
        float: "float 5s ease-in-out infinite",
        "gradient-x": "gradient-x 6s ease infinite",
      },
    },
  },
  plugins: [],
};

export default config;
