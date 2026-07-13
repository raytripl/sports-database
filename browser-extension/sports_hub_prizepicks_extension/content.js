(() => {
  "use strict";

  const SOURCE = "sports-hub-prizepicks-exporter";

  window.addEventListener("message", async (event) => {
    if (event.source !== window) return;
    const message = event.data;
    if (!message || message.source !== SOURCE) return;

    if (message.type === "BRIDGE_READY") {
      await chrome.storage.local.set({
        bridgeReady: true,
        bridgeReadyAt: message.capturedAt
      });
      return;
    }

    if (message.type !== "PRIZEPICKS_PAYLOAD") return;

    const projectionCount = Array.isArray(message.payload?.data)
      ? message.payload.data.length
      : 0;

    await chrome.storage.local.set({
      latestPrizePicksPayload: message.payload,
      latestCaptureUrl: message.url,
      latestCapturedAt: message.capturedAt,
      latestProjectionCount: projectionCount
    });

    chrome.runtime.sendMessage({
      type: "CAPTURE_UPDATED",
      projectionCount,
      capturedAt: message.capturedAt
    }).catch(() => {});
  });
})();
