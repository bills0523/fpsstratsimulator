import { simulatePayload } from "./browserSimulation.js";

self.addEventListener("message", (event) => {
  const { type, requestId, payload } = event.data || {};

  try {
    if (type === "ping") {
      self.postMessage({ requestId, result: { ok: true } });
      return;
    }

    if (type === "simulate") {
      const result = simulatePayload(payload);
      self.postMessage({ requestId, result });
      return;
    }

    self.postMessage({ requestId, error: `Unknown worker request type: ${type}` });
  } catch (error) {
    self.postMessage({ requestId, error: error?.message || "Simulation worker failed." });
  }
});
