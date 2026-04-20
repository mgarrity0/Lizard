import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

// Tauri expects a fixed port and needs HMR to work on that port.
export default defineConfig(async () => ({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // Tauri watches src-tauri itself; ignore the Python sidecar venv.
      ignored: ["**/src-tauri/**", "**/geometry/.venv/**", "**/geometry/__pycache__/**"],
    },
  },
}));
