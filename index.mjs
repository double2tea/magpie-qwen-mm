import { startServer } from "./server.mjs";

let starting;
function ensureServer() {
  starting ||= startServer().then(server => {
    // CLI hosts can briefly own the port before the desktop host takes over.
    if (!server) {
      const timer = setTimeout(() => {
        starting = undefined;
        ensureServer().catch(error => console.error("[qwen-mm]", error.message));
      }, 1000);
      timer.unref();
    }
    return server;
  });
  return starting;
}

export default {
  id: "qwen-mm-settings",
  server: async () => {
    await ensureServer();
    return {};
  },
};
