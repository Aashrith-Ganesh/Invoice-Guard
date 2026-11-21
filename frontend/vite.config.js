import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const { DEV_API_TARGET, VITE_API_BASE_URL } = loadEnv(mode, process.cwd(), ["DEV_", "VITE_"]);
  if (VITE_API_BASE_URL) {
    let origin;
    try { origin = new URL(VITE_API_BASE_URL); } catch { throw new Error("Set VITE_API_BASE_URL to an API origin."); }
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname);
    if ((origin.protocol !== "https:" && !(origin.protocol === "http:" && loopback))
      || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) {
      throw new Error("VITE_API_BASE_URL requires an HTTPS origin without a path or credentials.");
    }
  }
  return {
    base: "/app/",
    server: {
      host: "127.0.0.1",
      proxy: { "/api": { target: DEV_API_TARGET || "http://127.0.0.1:8000" } },
    },
  };
});
