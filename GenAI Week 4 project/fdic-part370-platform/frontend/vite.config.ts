import { execSync } from "node:child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Stamp the build with the git commit + build time so any running instance
// (esp. a Replit deployment serving a prebuilt dist) reveals exactly which code
// it is. Prefer an explicit env override (e.g. a Replit Secret), then git, then
// "unknown" — never fail the build if git isn't available.
function buildSha(): string {
  if (process.env.VITE_BUILD_SHA) return process.env.VITE_BUILD_SHA;
  try {
    return execSync("git rev-parse --short HEAD").toString().trim();
  } catch {
    return "unknown";
  }
}

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  define: {
    __BUILD_SHA__: JSON.stringify(buildSha()),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
});
