import { defineConfig } from "vite";

// Dev-only proxy so the browser can open one origin and reach both the static
// client and the FastAPI WebSocket gateway -- avoids a CORS/mixed-origin
// dance during local development. Production points VITE_WS_URL at the
// deployed Azure Container Apps backend instead (see .env.example).
export default defineConfig({
  build: {
    // The AudioWorklet module (capture-worklet.js) must be fetchable as a
    // real URL, not inlined as a data: URI -- some browsers restrict or
    // reject data: URLs for audioWorklet.addModule(), especially under CSP.
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
      "/health": "http://localhost:8000",
    },
  },
});
