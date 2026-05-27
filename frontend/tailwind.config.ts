import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0a0d12",
          panel: "#11161d",
          elev: "#161c25",
          border: "#1f2733",
        },
        ink: {
          DEFAULT: "#e5e9f0",
          mute: "#7b8597",
          dim: "#475063",
        },
        state: {
          normal: "#22c55e",
          alert: "#f59e0b",
          blackhole: "#ef4444",
          recover: "#3b82f6",
          offline: "#6b7280",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      keyframes: {
        pulseAlert: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
      animation: {
        "pulse-alert": "pulseAlert 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
