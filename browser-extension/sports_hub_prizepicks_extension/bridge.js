(() => {
  "use strict";

  const SOURCE = "sports-hub-prizepicks-exporter";
  const URL_MATCH = /(?:api\.)?prizepicks\.com\/.*(?:projections|board|pickem)/i;

  function publish(payload, url) {
    try {
      if (!payload || typeof payload !== "object") return;
      const data = Array.isArray(payload.data) ? payload.data : null;
      if (!data || data.length === 0) return;

      window.postMessage({
        source: SOURCE,
        type: "PRIZEPICKS_PAYLOAD",
        url: String(url || ""),
        capturedAt: new Date().toISOString(),
        payload
      }, "*");
    } catch (_) {
      // Never interfere with the PrizePicks page.
    }
  }

  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const response = await originalFetch.apply(this, args);
    try {
      const requestUrl =
        typeof args[0] === "string" ? args[0] :
        args[0] && args[0].url ? args[0].url : "";

      if (URL_MATCH.test(requestUrl)) {
        response.clone().json()
          .then(payload => publish(payload, requestUrl))
          .catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__sportsHubUrl = String(url || "");
    return originalOpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function(...args) {
    try {
      this.addEventListener("load", function() {
        try {
          const url = this.__sportsHubUrl || this.responseURL || "";
          if (!URL_MATCH.test(url)) return;

          let payload;
          if (this.responseType === "json") {
            payload = this.response;
          } else if (!this.responseType || this.responseType === "text") {
            payload = JSON.parse(this.responseText);
          }
          publish(payload, url);
        } catch (_) {}
      });
    } catch (_) {}
    return originalSend.apply(this, args);
  };

  // Let the isolated content script know the bridge loaded.
  window.postMessage({
    source: SOURCE,
    type: "BRIDGE_READY",
    capturedAt: new Date().toISOString()
  }, "*");
})();
