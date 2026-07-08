const byId = (id) => document.getElementById(id);

async function loadLiveArchitecture() {
  const liveBadge = document.querySelector(".why-live");
  try {
    const [healthResponse, statsResponse, networkResponse] = await Promise.all([
      fetch("api/health", { cache: "no-store" }),
      fetch("api/stats", { cache: "no-store" }),
      fetch("api/network", { cache: "no-store" }),
    ]);
    if (!healthResponse.ok || !statsResponse.ok || !networkResponse.ok) throw new Error("live data unavailable");
    const [health, stats, network] = await Promise.all([
      healthResponse.json(),
      statsResponse.json(),
      networkResponse.json(),
    ]);
    byId("system-label").textContent = health.data_mode === "adb" ? "ADB LIVE" : "DEMO MODE";
    byId("live-state").textContent = health.status === "ok" ? "ONLINE" : "DEGRADED";
    byId("live-data-mode").textContent = health.database_driver || "Oracle AI Database";
    byId("live-dimension").textContent = Number(health.embedding_dimension) || 1536;
    byId("live-model").textContent = health.embedding_model || "cohere.embed-v4.0";
    byId("live-people").textContent = Number(stats.participants) || network.nodes?.length || 0;
    const edgeCount = network.edges?.length || 0;
    byId("live-note").textContent = `Oracle実測COSINE距離から ${edgeCount} 本のつながりを表示中`;
  } catch (_) {
    liveBadge.classList.add("warning");
    byId("system-label").textContent = "RECONNECTING";
    byId("live-state").textContent = "RETRYING";
    byId("live-note").textContent = "ライブ情報へ再接続しています";
  }
}

loadLiveArchitecture();
window.setInterval(loadLiveArchitecture, 15000);
