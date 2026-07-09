const towerState = {
  graph: null,
  semanticGraph: { nodes: [], edges: [] },
  standings: new Map(),
  selectedId: null,
  signature: "",
  labelFrame: null,
  rotateTimer: null,
};

const RANK_COLORS = {
  A: "#c74634",
  B: "#e6a126",
  C: "#2a9d8f",
  D: "#386aa3",
  E: "#7764d8",
  "—": "#9ca3ad",
};

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function endpointId(value) {
  return typeof value === "object" && value !== null ? value.id : value;
}

function scoreHeight(score) {
  return (Math.max(0, Math.min(100, Number(score) || 0)) - 50) * 1.8;
}

function rankColor(rank) {
  return RANK_COLORS[rank] || RANK_COLORS["—"];
}

function floorGeometry() {
  const floors = [
    ["A", 72, "#c74634"],
    ["B", 45, "#e6a126"],
    ["C", 9, "#2a9d8f"],
    ["D", -27, "#386aa3"],
    ["E", -90, "#7764d8"],
  ];
  const nodes = [];
  const links = [];
  floors.forEach(([rank, y, color]) => {
    const corners = [
      [-112, -112], [112, -112], [112, 112], [-112, 112],
    ];
    corners.forEach(([x, z], index) => {
      nodes.push({ id: `floor-${rank}-${index}`, kind: "floor", rank, x, y, z, fx: x, fy: y, fz: z });
    });
    for (let index = 0; index < corners.length; index += 1) {
      links.push({
        source: `floor-${rank}-${index}`,
        target: `floor-${rank}-${(index + 1) % corners.length}`,
        kind: "floor",
        color,
      });
    }
  });
  return { nodes, links };
}

function buildTowerData(graph) {
  const people = graph.nodes.map((node) => {
    const standing = towerState.standings.get(node.id);
    const rank = standing?.rank_label || "—";
    const score = standing ? Number(standing.score) : null;
    return {
      ...node,
      kind: "person",
      score,
      rank,
      rank_position: standing?.rank || null,
      x: Number(node.x3d) || 0,
      y: standing ? scoreHeight(score) : -108,
      z: Number(node.y3d) || 0,
      fx: Number(node.x3d) || 0,
      fy: standing ? scoreHeight(score) : -108,
      fz: Number(node.y3d) || 0,
      towerColor: standing ? node.color : "#aeb3ba",
    };
  });
  const visibleIds = new Set(people.map((node) => node.id));
  const semanticLinks = graph.edges
    .filter((edge) => visibleIds.has(endpointId(edge.source)) && visibleIds.has(endpointId(edge.target)))
    .map((edge) => ({ ...edge, kind: "semantic" }));
  const floor = floorGeometry();
  return { nodes: [...people, ...floor.nodes], links: [...semanticLinks, ...floor.links], people, semanticLinks };
}

function stopRotation() {
  window.clearTimeout(towerState.rotateTimer);
  const controls = towerState.graph?.controls();
  if (controls) controls.autoRotate = false;
}

function resumeRotation() {
  window.clearTimeout(towerState.rotateTimer);
  towerState.rotateTimer = window.setTimeout(() => {
    const controls = towerState.graph?.controls();
    if (controls) controls.autoRotate = true;
  }, 7000);
}

function frameTower(duration = 700) {
  if (!towerState.graph) return;
  towerState.graph.zoomToFit(0, 72, (node) => node.kind === "person");
  const camera = towerState.graph.cameraPosition();
  const target = towerState.graph.controls()?.target || { x: 0, y: 0, z: 0 };
  const closer = 0.72;
  towerState.graph.cameraPosition({
    x: target.x + (camera.x - target.x) * closer,
    y: target.y + (camera.y - target.y) * closer,
    z: target.z + (camera.z - target.z) * closer,
  }, target, duration);
}

function renderLabels(people, links) {
  document.querySelector("#score-tower-labels").innerHTML = [
    ...people.map((node) => `
      <span class="tower-node-label${node.score === null ? " unscored" : ""}" data-node-id="${safe(node.id)}" style="--rank-color:${safe(rankColor(node.rank))}">
        <i>${safe(node.icon)}</i><strong>${safe(node.nickname)}</strong><small>${node.score === null ? "未公開" : `${node.score}点・${safe(node.rank)}`}</small>
      </span>`),
    ...links.map((link, index) => `<span class="tower-link-label" data-link-index="${index}">${Number(link.distance).toFixed(4)}</span>`),
  ].join("");
}

function startLabelLoop() {
  if (towerState.labelFrame) return;
  const update = () => {
    const graph = towerState.graph;
    if (graph) {
      const data = graph.graphData();
      const host = document.querySelector("#score-tower-3d");
      document.querySelectorAll(".tower-node-label").forEach((label) => {
        const node = data.nodes.find((item) => item.id === label.dataset.nodeId);
        if (!node) return;
        const point = graph.graph2ScreenCoords(node.x, node.y, node.z);
        label.hidden = point.x < -100 || point.x > host.clientWidth + 100 || point.y < -50 || point.y > host.clientHeight + 50;
        label.style.transform = `translate3d(${point.x}px,${point.y}px,0) translate(-50%,-50%)`;
      });
      document.querySelectorAll(".tower-link-label").forEach((label) => {
        const link = data.links.filter((item) => item.kind === "semantic")[Number(label.dataset.linkIndex)];
        const source = typeof link?.source === "object" ? link.source : data.nodes.find((item) => item.id === link?.source);
        const target = typeof link?.target === "object" ? link.target : data.nodes.find((item) => item.id === link?.target);
        const visible = towerState.selectedId && source && target && (source.id === towerState.selectedId || target.id === towerState.selectedId);
        label.classList.toggle("visible", Boolean(visible));
        if (!visible) return;
        const point = graph.graph2ScreenCoords((source.x + target.x) / 2, (source.y + target.y) / 2, (source.z + target.z) / 2);
        label.style.transform = `translate3d(${point.x}px,${point.y}px,0) translate(-50%,-50%)`;
      });
    }
    towerState.labelFrame = window.requestAnimationFrame(update);
  };
  towerState.labelFrame = window.requestAnimationFrame(update);
}

function selectNode(nodeId) {
  towerState.selectedId = towerState.selectedId === nodeId ? null : nodeId;
  applySelection();
}

function applySelection() {
  const selectedId = towerState.selectedId;
  const connected = new Set([selectedId]);
  towerState.semanticGraph.edges.forEach((edge) => {
    const source = endpointId(edge.source);
    const target = endpointId(edge.target);
    if (source === selectedId) connected.add(target);
    if (target === selectedId) connected.add(source);
  });
  document.querySelectorAll(".tower-node-label").forEach((label) => {
    const id = label.dataset.nodeId;
    label.classList.toggle("selected", id === selectedId);
    label.classList.toggle("dimmed", Boolean(selectedId) && !connected.has(id));
  });
  if (towerState.graph) {
    towerState.graph
      .nodeVal((node) => node.kind === "person" ? (node.id === selectedId ? 10 : connected.has(node.id) ? 7 : 5.5) : 0.01)
      .nodeColor((node) => {
        if (node.kind !== "person") return "rgba(0,0,0,0)";
        if (!selectedId || connected.has(node.id)) return node.towerColor;
        return "#d4d0ca";
      })
      .linkColor((link) => {
        if (link.kind === "floor") return link.color;
        const highlighted = selectedId && (endpointId(link.source) === selectedId || endpointId(link.target) === selectedId);
        return highlighted ? "#c74634" : "#a9b1ba";
      })
      .linkWidth((link) => {
        if (link.kind === "floor") return 0.45;
        return selectedId && (endpointId(link.source) === selectedId || endpointId(link.target) === selectedId) ? 3.2 : 1.1;
      })
      .refresh();
  }
  renderDetail(selectedId);
}

function renderDetail(nodeId) {
  const detail = document.querySelector("#score-tower-detail");
  const node = towerState.semanticGraph.nodes.find((item) => item.id === nodeId);
  if (!node) {
    detail.hidden = true;
    detail.innerHTML = "";
    return;
  }
  const standing = towerState.standings.get(nodeId);
  detail.hidden = false;
  detail.innerHTML = `
    <button type="button" aria-label="閉じる">×</button>
    <span>SCORE TOWER POSITION</span>
    <h3>${safe(node.icon)} ${safe(node.nickname)}</h3>
    <div class="tower-detail-grid">
      <span><small>価値観タイプ</small><strong>${safe(node.persona_name)}</strong></span>
      <span><small>GAME SCORE</small><strong>${standing ? Number(standing.score) : "未公開"}</strong></span>
      <span><small>RANK</small><strong>${standing ? safe(standing.rank_label) : "—"}</strong></span>
    </div>
    <p>${standing ? "横位置は理想の上司への回答、高さは固定スコアで決まっています。" : "価値観の位置のみ表示しています。ゲームスコアは公開されていません。"}</p>`;
  detail.querySelector("button").addEventListener("click", () => selectNode(nodeId));
}

function renderRanking() {
  const nodeIds = new Set(towerState.semanticGraph.nodes.map((node) => node.id));
  const ranking = [...towerState.standings.values()].slice(0, 5);
  document.querySelector("#tower-ranking").innerHTML = ranking.map((item) => `
    <button type="button" data-node-id="${safe(item.session_id)}" style="--rank-color:${safe(rankColor(item.rank_label))}" ${nodeIds.has(item.session_id) ? "" : "disabled"}>
      <b>${String(item.rank).padStart(2, "0")}</b><strong>${safe(item.nickname)}</strong><em>${Number(item.score)}</em><i>${safe(item.rank_label)}</i>
    </button>`).join("") || "<p>挑戦者を待っています</p>";
  document.querySelectorAll("#tower-ranking button:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => {
      towerState.selectedId = button.dataset.nodeId;
      applySelection();
    });
  });
}

function renderTower(graph) {
  towerState.semanticGraph = graph;
  const data = buildTowerData(graph);
  const signature = JSON.stringify({
    nodes: data.people.map((node) => [node.id, node.x, node.y, node.z]),
    links: data.semanticLinks.map((link) => [endpointId(link.source), endpointId(link.target)]),
  });
  const host = document.querySelector("#score-tower-3d");
  if (!towerState.graph) {
    towerState.graph = new ForceGraph3D(host, { controlType: "orbit" })
      .width(host.clientWidth)
      .height(host.clientHeight)
      .backgroundColor("rgba(0,0,0,0)")
      .showNavInfo(false)
      .nodeId("id")
      .nodeVisibility((node) => node.kind === "person")
      .nodeColor((node) => node.towerColor)
      .nodeVal((node) => node.kind === "person" ? 5.5 : 0.01)
      .nodeOpacity(0.9)
      .nodeResolution(24)
      .linkColor((link) => link.kind === "floor" ? link.color : "#a9b1ba")
      .linkWidth((link) => link.kind === "floor" ? 0.45 : 1.1)
      .linkOpacity(0.5)
      .enableNodeDrag(false)
      .onNodeClick((node) => {
        if (node.kind !== "person") return;
        stopRotation();
        resumeRotation();
        selectNode(node.id);
      })
      .onBackgroundClick(() => {
        if (towerState.selectedId) selectNode(towerState.selectedId);
      });
    const controls = towerState.graph.controls();
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.34;
    controls.minPolarAngle = Math.PI * 0.36;
    controls.maxPolarAngle = Math.PI * 0.56;
    controls.addEventListener("start", stopRotation);
    controls.addEventListener("end", resumeRotation);
  }
  if (signature !== towerState.signature) {
    towerState.signature = signature;
    renderLabels(data.people, data.semanticLinks);
    towerState.graph.graphData({ nodes: data.nodes, links: data.links });
    window.setTimeout(() => frameTower(), 90);
  }
  applySelection();
  renderRanking();
  startLabelLoop();
  document.querySelector("#tower-people").textContent = data.people.length;
  document.querySelector("#tower-scored").textContent = data.people.filter((node) => node.score !== null).length;
}

async function refreshTower() {
  try {
    const [networkResponse, scoreResponse] = await Promise.all([
      fetch("api/network", { cache: "no-store" }),
      fetch("api/mio/venue/score-tower", { cache: "no-store" }),
    ]);
    if (!networkResponse.ok || !scoreResponse.ok) throw new Error("tower data unavailable");
    const [graph, scoreData] = await Promise.all([networkResponse.json(), scoreResponse.json()]);
    towerState.standings = new Map((scoreData.standings || []).map((item) => [item.session_id, item]));
    document.querySelector("#tower-data-mode").textContent = `DATA MODE — ${String(scoreData.data_mode || graph.data_mode || "").toUpperCase()}`;
    renderTower(graph);
  } catch (_) {
    document.querySelector("#tower-data-mode").textContent = "RECONNECTING…";
  }
}

function setupControls() {
  const zoom = (factor) => {
    if (!towerState.graph) return;
    stopRotation();
    resumeRotation();
    const camera = towerState.graph.cameraPosition();
    towerState.graph.cameraPosition({ x: camera.x * factor, y: camera.y * factor, z: camera.z * factor }, undefined, 260);
  };
  document.querySelector("#tower-zoom-in").addEventListener("click", () => zoom(0.78));
  document.querySelector("#tower-zoom-out").addEventListener("click", () => zoom(1.28));
  document.querySelector("#tower-zoom-reset").addEventListener("click", () => frameTower());
}

const resizeObserver = new ResizeObserver(() => {
  if (!towerState.graph) return;
  const host = document.querySelector("#score-tower-3d");
  towerState.graph.width(host.clientWidth).height(host.clientHeight);
});
resizeObserver.observe(document.querySelector("#score-tower-3d"));
setupControls();
refreshTower();
window.setInterval(refreshTower, 5000);
