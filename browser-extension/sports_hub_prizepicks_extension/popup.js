"use strict";

const statusEl = document.getElementById("status");
const detailsEl = document.getElementById("details");
const exportButton = document.getElementById("export");
const exportJsonButton = document.getElementById("exportJson");
const clearButton = document.getElementById("clear");
const sportsInput = document.getElementById("sports");

let capturedPayload = null;

function includedLookup(included) {
  const map = new Map();
  for (const item of included || []) {
    if (item?.type != null && item?.id != null) {
      map.set(`${item.type}:${item.id}`, item);
    }
  }
  return map;
}

function relationshipId(item, name) {
  const data = item?.relationships?.[name]?.data;
  return data && !Array.isArray(data) && data.id != null ? String(data.id) : "";
}

function findIncluded(map, id, types) {
  if (!id) return {};
  for (const type of types) {
    const item = map.get(`${type}:${id}`);
    if (item) return item;
  }
  return {};
}

function normalizeLeague(value) {
  return String(value || "").trim().toUpperCase();
}

function rowsFromPayload(payload) {
  const projections = Array.isArray(payload?.data) ? payload.data : [];
  const included = Array.isArray(payload?.included) ? payload.included : [];
  const lookup = includedLookup(included);

  return projections.map((projection) => {
    const a = projection.attributes || {};
    const playerId =
      relationshipId(projection, "new_player") ||
      relationshipId(projection, "player");
    const leagueId = relationshipId(projection, "league");
    const gameId = relationshipId(projection, "game");

    const player = findIncluded(
      lookup, playerId, ["new_player", "player", "players"]
    ).attributes || {};
    const league = findIncluded(
      lookup, leagueId, ["league", "leagues"]
    ).attributes || {};
    const game = findIncluded(
      lookup, gameId, ["game", "games"]
    ).attributes || {};

    return {
      projection_id: String(projection.id || ""),
      league: league.name || league.abbreviation || a.league || "",
      league_id: leagueId,
      player_name: player.name || a.name || a.player_name || "",
      player_id: playerId,
      team: player.team || player.team_name || a.team || "",
      position: player.position || a.position || "",
      stat_type: a.stat_type || "",
      line_score: a.line_score ?? "",
      projection_type: a.projection_type || "",
      odds_type: a.odds_type || "",
      start_time: a.start_time || game.start_time || "",
      game_description: game.description || a.description || "",
      description: a.description || "",
      is_live: a.is_live ?? "",
      status: a.status || "",
      board_time: a.board_time || "",
      updated_at: a.updated_at || "",
      flash_sale_line_score: a.flash_sale_line_score ?? "",
      discount_percentage: a.discount_percentage ?? "",
      source: "PrizePicks",
      captured_at_utc: new Date().toISOString()
    };
  });
}

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function toCsv(rows) {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const lines = [
    headers.map(csvEscape).join(","),
    ...rows.map(row => headers.map(h => csvEscape(row[h])).join(","))
  ];
  return lines.join("\r\n");
}

function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function downloadText(filename, text, mimeType) {
  const url = URL.createObjectURL(new Blob([text], { type: mimeType }));
  try {
    await chrome.downloads.download({
      url,
      filename,
      saveAs: true,
      conflictAction: "uniquify"
    });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
}

async function refreshStatus() {
  const stored = await chrome.storage.local.get([
    "latestPrizePicksPayload",
    "latestCapturedAt",
    "latestProjectionCount",
    "bridgeReady"
  ]);

  capturedPayload = stored.latestPrizePicksPayload || null;

  if (capturedPayload) {
    const count = stored.latestProjectionCount || capturedPayload.data?.length || 0;
    statusEl.textContent = `Board captured: ${count.toLocaleString()} projections`;
    detailsEl.textContent = stored.latestCapturedAt
      ? `Captured ${new Date(stored.latestCapturedAt).toLocaleString()}`
      : "";
    exportButton.disabled = false;
    exportJsonButton.disabled = false;
  } else {
    statusEl.textContent = stored.bridgeReady
      ? "Extension ready. Refresh PrizePicks."
      : "Open PrizePicks and refresh the page.";
    detailsEl.textContent = "No projection response has been captured yet.";
    exportButton.disabled = true;
    exportJsonButton.disabled = true;
  }
}

exportButton.addEventListener("click", async () => {
  if (!capturedPayload) return;

  let rows = rowsFromPayload(capturedPayload);
  const requested = sportsInput.value
    .split(",")
    .map(normalizeLeague)
    .filter(Boolean);

  if (requested.length) {
    const allowed = new Set(requested);
    rows = rows.filter(row => allowed.has(normalizeLeague(row.league)));
  }

  const seen = new Set();
  rows = rows.filter(row => {
    const key = row.projection_id;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  rows.sort((a, b) =>
    String(a.league).localeCompare(String(b.league)) ||
    String(a.start_time).localeCompare(String(b.start_time)) ||
    String(a.player_name).localeCompare(String(b.player_name)) ||
    String(a.stat_type).localeCompare(String(b.stat_type))
  );

  if (!rows.length) {
    statusEl.textContent = "No rows matched the selected sports.";
    detailsEl.textContent = "Clear the sports field to export every league.";
    return;
  }

  await downloadText(
    `prizepicks_pool_${timestamp()}.csv`,
    toCsv(rows),
    "text/csv;charset=utf-8"
  );

  statusEl.textContent = `Exported ${rows.length.toLocaleString()} projections`;
});

exportJsonButton.addEventListener("click", async () => {
  if (!capturedPayload) return;
  await downloadText(
    `prizepicks_raw_${timestamp()}.json`,
    JSON.stringify(capturedPayload, null, 2),
    "application/json;charset=utf-8"
  );
});

clearButton.addEventListener("click", async () => {
  await chrome.storage.local.remove([
    "latestPrizePicksPayload",
    "latestCaptureUrl",
    "latestCapturedAt",
    "latestProjectionCount"
  ]);
  capturedPayload = null;
  await refreshStatus();
});

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "CAPTURE_UPDATED") refreshStatus();
});

refreshStatus();
