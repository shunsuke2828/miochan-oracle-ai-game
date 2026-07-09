const personaColor = new Map();
const participantDetailCache = new Map();
const networkState = {
  graph: { nodes: [], edges: [] },
  selectedId: null,
  force3d: null,
  graph3dSignature: "",
  labelFrame: null,
  camera: {
    scale: 1,
    x: 0,
    y: 0,
    pointers: new Map(),
    pinch: null,
    dragged: false,
    suppressClick: false,
  },
};

const MIN_ZOOM = 0.55;
const MAX_ZOOM = 3;

async function refreshDisplay() {
  try {
    const [statsResponse, networkResponse, scoreboardResponse] = await Promise.all([
      fetch("api/stats", { cache: "no-store" }),
      fetch("api/network", { cache: "no-store" }),
      fetch("api/mio/venue/scoreboard", { cache: "no-store" }),
    ]);
    if (!statsResponse.ok || !networkResponse.ok || !scoreboardResponse.ok) throw new Error("display data unavailable");

    const [stats, graph, scoreboard] = await Promise.all([
      statsResponse.json(),
      networkResponse.json(),
      scoreboardResponse.json(),
    ]);
    stats.personas.forEach((item) => personaColor.set(item.name, item.color));
    document.querySelector("#participant-count").textContent = stats.participants;
    document.querySelector("#completed-count").textContent = stats.completed;
    document.querySelector("#type-count").textContent = Object.keys(stats.persona_counts).length || 6;
    document.querySelector("#display-data-mode").textContent = `DATA MODE — ${stats.data_mode.toUpperCase()}`;
    renderLegend(stats.personas, stats.persona_counts);
    renderNetwork(graph);
    renderScoreboard(scoreboard);
    renderActivities(stats.recent);
  } catch (_) {
    document.querySelector("#display-data-mode").textContent = "RECONNECTING…";
  }
}

function renderScoreboard(scoreboard) {
  const ranking = scoreboard.ranking || [];
  const top = ranking[0];
  const topButton = document.querySelector("#top-rescue-player");
  document.querySelector("#top-rescue-score").textContent = top?.score || 0;
  document.querySelector("#top-rescue-name").textContent = top?.nickname || "挑戦者を待っています";
  topButton.dataset.nodeId = top?.session_id || "";
  topButton.disabled = !top || !networkState.graph.nodes.some((node) => node.id === top.session_id);
  topButton.onclick = () => focusNode(topButton.dataset.nodeId);
  const nodeIds = new Set(networkState.graph.nodes.map((node) => node.id));
  const remainingRanking = ranking.slice(1);
  document.querySelector("#rescue-ranking").innerHTML = remainingRanking
    .map((item) => {
      const linked = item.session_id && nodeIds.has(item.session_id);
      return `<button type="button" class="score-ranking-item${linked ? " linked" : ""}" data-node-id="${safe(item.session_id || "")}" ${linked ? "" : "disabled"}><b>${String(item.rank).padStart(2, "0")}</b><strong>${safe(item.nickname)}</strong><em>${Number(item.score) || 0}</em><i>${safe(item.rank_label || "E")}</i></button>`;
    })
    .join("") || (top ? "" : '<p>最初のレスキュー隊を待っています</p>');
  document.querySelectorAll(".score-ranking-item.linked").forEach((element) => {
    element.addEventListener("click", () => focusNode(element.dataset.nodeId));
  });
}

function renderLegend(personas, counts) {
  document.querySelector("#persona-legend").innerHTML = personas
    .map((item) => `<span class="legend-item" style="--legend-color:${safe(item.color)}"><i></i>${safe(item.name)} ${counts[item.name] || 0}</span>`)
    .join("");
}

function renderActivities(items) {
  const nodeIds = new Set(networkState.graph.nodes.map((node) => node.id));
  const feed = document.querySelector("#activity-feed");
  feed.innerHTML = items.map((item) => {
    const color = personaColor.get(item.persona_name) || "#f4b653";
    const nodeId = item.session_id && nodeIds.has(item.session_id) ? item.session_id : null;
    if (!nodeId) {
      return `<div class="activity" style="--activity-color:${safe(color)}"><i></i><span><strong>${safe(item.nickname)}</strong> は ${safe(item.persona_name)}</span></div>`;
    }
    const selected = networkState.selectedId === nodeId;
    return `<button type="button" class="activity activity-link${selected ? " selected" : ""}" data-node-id="${safe(nodeId)}" style="--activity-color:${safe(color)}" aria-label="${safe(item.nickname)}をマップで表示" aria-pressed="${selected}"><i></i><span><strong>${safe(item.nickname)}</strong> は ${safe(item.persona_name)}</span><b aria-hidden="true">→</b></button>`;
  }).join("") || '<div class="activity"><span>最初の参加者を待っています</span></div>';
  feed.querySelectorAll(".activity-link").forEach((element) => {
    element.addEventListener("click", () => {
      const nodeId = element.dataset.nodeId;
      if (!nodeId) return;
      selectNode(nodeId);
      if (networkState.selectedId === nodeId) centerNodeInViewport(nodeId);
    });
  });
}

function renderNetwork(graph) {
  networkState.graph = graph;
  if (networkState.selectedId && !graph.nodes.some((node) => node.id === networkState.selectedId)) {
    networkState.selectedId = null;
  }

  if (window.ForceGraph3D) {
    renderNetwork3D(graph);
    return;
  }

  const container = document.querySelector("#network-nodes");
  container.innerHTML = "";
  graph.nodes.forEach((item, index) => {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "network-node";
    node.dataset.nodeId = item.id;
    node.setAttribute("aria-label", `${item.nickname}のつながりを表示`);
    node.style.cssText = `left:${item.x}%;top:${item.y}%;--node-color:${item.color};animation-delay:${index * 60}ms`;
    node.innerHTML = `
      <span class="network-node-size-lock">
        <span class="network-node-content">
          <i><b>${safe(item.icon)}</b></i><small>${safe(item.nickname)}</small>
        </span>
      </span>`;
    node.addEventListener("click", (event) => {
      if (networkState.camera.suppressClick) {
        event.preventDefault();
        return;
      }
      selectNode(item.id);
    });
    container.appendChild(node);
  });
  applySelection();
  requestAnimationFrame(drawConnections);
}

function graphEndpointId(value) {
  return typeof value === "object" && value !== null ? value.id : value;
}

function renderNetwork3D(graph) {
  const host = document.querySelector("#network-3d");
  const fallbackWorld = document.querySelector("#network-world");
  fallbackWorld.hidden = true;
  host.classList.add("active");

  const nodes = graph.nodes.map((node) => ({
    ...node,
    x: Number(node.x3d) || 0,
    y: Number(node.y3d) || 0,
    z: Number(node.z3d) || 0,
    fx: Number(node.x3d) || 0,
    fy: Number(node.y3d) || 0,
    fz: Number(node.z3d) || 0,
    val: 5,
  }));
  const links = graph.edges.map((edge) => ({
    ...edge,
    source: edge.source,
    target: edge.target,
    name: `Oracle VECTOR_DISTANCE(COSINE): ${edge.distance}`,
  }));
  const signature = JSON.stringify({
    nodes: nodes.map(({ id, x, y, z }) => [id, x, y, z]),
    links: links.map(({ source, target, distance }) => [source, target, distance]),
  });

  if (!networkState.force3d) {
    networkState.force3d = new ForceGraph3D(host, { controlType: "orbit" })
      .width(host.clientWidth)
      .height(host.clientHeight)
      .backgroundColor("rgba(0,0,0,0)")
      .showNavInfo(false)
      .nodeId("id")
      .nodeLabel((node) => `${safe(node.icon)} ${safe(node.nickname)}<br>${safe(node.persona_name)}`)
      .nodeColor((node) => node.color)
      .nodeVal((node) => node.val)
      .nodeOpacity(0.88)
      .nodeResolution(24)
      .linkLabel((link) => `Oracle実測 COSINE距離: ${link.distance}`)
      .linkColor(() => "#9aa6b5")
      .linkOpacity(0.55)
      .linkWidth(1.1)
      .linkHoverPrecision(5)
      .enableNodeDrag(false)
      .onNodeClick((node) => selectNode(node.id))
      .onBackgroundClick(() => {
        if (networkState.selectedId) selectNode(networkState.selectedId);
      });
  }

  if (signature !== networkState.graph3dSignature) {
    networkState.graph3dSignature = signature;
    render3DLabels(nodes, links);
    networkState.force3d.graphData({ nodes, links });
    window.setTimeout(() => networkState.force3d?.zoomToFit(650, 70), 80);
  }
  applySelection();
  start3DLabelLoop();
}

function render3DLabels(nodes, links) {
  const labels = document.querySelector("#network-3d-labels");
  labels.innerHTML = [
    ...nodes.map((node) => `
      <span class="network-3d-node-label" data-node-id="${safe(node.id)}">
        <b>${safe(node.icon)}</b><strong>${safe(node.nickname)}</strong>
      </span>`),
    ...links.map((link, index) => `
      <span class="network-3d-link-label" data-link-index="${index}">${Number(link.distance).toFixed(4)}</span>`),
  ].join("");
}

function start3DLabelLoop() {
  if (networkState.labelFrame) return;
  const update = () => {
    const graph3d = networkState.force3d;
    if (graph3d) {
      const data = graph3d.graphData();
      const host = document.querySelector("#network-3d");
      document.querySelectorAll(".network-3d-node-label").forEach((label) => {
        const node = data.nodes.find((item) => item.id === label.dataset.nodeId);
        if (!node) return;
        const point = graph3d.graph2ScreenCoords(node.x, node.y, node.z);
        const visible = point.x >= -80 && point.x <= host.clientWidth + 80
          && point.y >= -50 && point.y <= host.clientHeight + 50;
        label.hidden = !visible;
        label.style.transform = `translate3d(${point.x}px,${point.y}px,0) translate(-50%,-50%)`;
      });
      document.querySelectorAll(".network-3d-link-label").forEach((label) => {
        const link = data.links[Number(label.dataset.linkIndex)];
        const source = typeof link?.source === "object" ? link.source : data.nodes.find((item) => item.id === link?.source);
        const target = typeof link?.target === "object" ? link.target : data.nodes.find((item) => item.id === link?.target);
        if (!source || !target) return;
        const point = graph3d.graph2ScreenCoords(
          (source.x + target.x) / 2,
          (source.y + target.y) / 2,
          (source.z + target.z) / 2,
        );
        label.style.transform = `translate3d(${point.x}px,${point.y}px,0) translate(-50%,-50%)`;
      });
    }
    networkState.labelFrame = window.requestAnimationFrame(update);
  };
  networkState.labelFrame = window.requestAnimationFrame(update);
}

function selectNode(nodeId) {
  networkState.selectedId = networkState.selectedId === nodeId ? null : nodeId;
  applySelection();
  if (!networkState.force3d) drawConnections();
}

function focusNode(nodeId) {
  if (!nodeId || !networkState.graph.nodes.some((node) => node.id === nodeId)) return;
  networkState.selectedId = nodeId;
  applySelection();
  drawConnections();
  centerNodeInViewport(nodeId);
}

function applySelection() {
  const selectedId = networkState.selectedId;
  const connectedIds = new Set();
  if (selectedId) {
    connectedIds.add(selectedId);
    networkState.graph.edges.forEach((edge) => {
      const sourceId = graphEndpointId(edge.source);
      const targetId = graphEndpointId(edge.target);
      if (sourceId === selectedId) connectedIds.add(targetId);
      if (targetId === selectedId) connectedIds.add(sourceId);
    });
  }

  document.querySelectorAll(".network-node").forEach((element) => {
    const id = element.dataset.nodeId;
    element.classList.toggle("selected", id === selectedId);
    element.classList.toggle("connected", Boolean(selectedId) && connectedIds.has(id) && id !== selectedId);
    element.classList.toggle("dimmed", Boolean(selectedId) && !connectedIds.has(id));
  });
  document.querySelectorAll(".activity-link").forEach((element) => {
    const selected = element.dataset.nodeId === selectedId;
    element.classList.toggle("selected", selected);
    element.setAttribute("aria-pressed", String(selected));
  });
  document.querySelectorAll(".network-3d-node-label").forEach((element) => {
    const id = element.dataset.nodeId;
    element.classList.toggle("selected", id === selectedId);
    element.classList.toggle("connected", Boolean(selectedId) && connectedIds.has(id) && id !== selectedId);
    element.classList.toggle("dimmed", Boolean(selectedId) && !connectedIds.has(id));
  });
  document.querySelectorAll(".network-3d-link-label").forEach((element) => {
    const link = networkState.graph.edges[Number(element.dataset.linkIndex)];
    const highlighted = Boolean(selectedId) && link && (
      graphEndpointId(link.source) === selectedId || graphEndpointId(link.target) === selectedId
    );
    element.classList.toggle("selected", highlighted);
    element.classList.toggle("dimmed", Boolean(selectedId) && !highlighted);
  });
  if (networkState.force3d) {
    networkState.force3d
      .nodeColor((node) => {
        if (!selectedId || connectedIds.has(node.id)) return node.color;
        return "#c8c2ba";
      })
      .nodeVal((node) => node.id === selectedId ? 9 : connectedIds.has(node.id) ? 7 : 5)
      .linkColor((link) => {
        const highlighted = selectedId && (
          graphEndpointId(link.source) === selectedId || graphEndpointId(link.target) === selectedId
        );
        return highlighted ? "#c74634" : "#9aa6b5";
      })
      .linkWidth((link) => {
        const highlighted = selectedId && (
          graphEndpointId(link.source) === selectedId || graphEndpointId(link.target) === selectedId
        );
        return highlighted ? 2.8 : 1.1;
      })
      .refresh();
  }
  renderConnectionDetail(selectedId);
}

function centerNodeInViewport(nodeId) {
  if (networkState.force3d) {
    const node = networkState.force3d.graphData().nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const distance = 75;
    const length = Math.hypot(node.x, node.y, node.z);
    const ratio = length ? 1 + distance / length : 1;
    const position = length
      ? { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio }
      : { x: 0, y: 0, z: distance };
    networkState.force3d.cameraPosition(position, node, 700);
    return;
  }
  const node = networkState.graph.nodes.find((item) => item.id === nodeId);
  const viewport = document.querySelector("#network-viewport");
  if (!node || !viewport) return;
  const camera = networkState.camera;
  camera.x = viewport.clientWidth / 2 - (node.x / 100 * viewport.clientWidth * camera.scale);
  camera.y = viewport.clientHeight / 2 - (node.y / 100 * viewport.clientHeight * camera.scale);
  applyCamera();
  const element = document.querySelector(`.network-node[data-node-id="${CSS.escape(nodeId)}"]`);
  element?.focus({ preventScroll: true });
}

function drawConnections() {
  const canvas = document.querySelector("#network-canvas");
  const viewport = document.querySelector("#network-viewport");
  const canvasWidth = viewport.clientWidth;
  const canvasHeight = viewport.clientHeight;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.max(1, Math.round(canvasWidth * ratio));
  canvas.height = Math.max(1, Math.round(canvasHeight * ratio));
  canvas.style.width = `${canvasWidth}px`;
  canvas.style.height = `${canvasHeight}px`;

  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, canvasWidth, canvasHeight);
  const nodes = new Map(networkState.graph.nodes.map((node) => [node.id, node]));

  networkState.graph.edges.forEach((edge) => {
    const source = nodes.get(edge.source);
    const target = nodes.get(edge.target);
    if (!source || !target) return;
    const isSelectedEdge = networkState.selectedId &&
      (edge.source === networkState.selectedId || edge.target === networkState.selectedId);
    const isDimmed = networkState.selectedId && !isSelectedEdge;
    const alpha = isDimmed ? 0.04 : isSelectedEdge ? 0.96 : 0.46;
    const lineWidth = isSelectedEdge ? 2.8 + (edge.similarity - 0.45) * 5 : 1.8;
    const sourceX = source.x / 100 * canvasWidth;
    const sourceY = source.y / 100 * canvasHeight;
    const targetX = target.x / 100 * canvasWidth;
    const targetY = target.y / 100 * canvasHeight;
    const midpointX = (sourceX + targetX) / 2;
    const midpointY = (sourceY + targetY) / 2 - Math.min(28, Math.abs(targetX - sourceX) * 0.06);
    const gradient = context.createLinearGradient(sourceX, sourceY, targetX, targetY);
    gradient.addColorStop(0, colorWithAlpha(source.color, alpha));
    gradient.addColorStop(1, colorWithAlpha(target.color, alpha));

    context.beginPath();
    context.moveTo(sourceX, sourceY);
    context.quadraticCurveTo(midpointX, midpointY, targetX, targetY);
    context.strokeStyle = gradient;
    context.lineWidth = lineWidth;
    context.setLineDash(isSelectedEdge ? [] : [6, 6]);
    context.stroke();
  });
  context.setLineDash([]);
}

async function renderConnectionDetail(selectedId) {
  const detail = document.querySelector("#connection-detail");
  if (!selectedId) {
    detail.hidden = true;
    detail.innerHTML = "";
    return;
  }
  const selected = networkState.graph.nodes.find((node) => node.id === selectedId);
  if (!selected) return;
  const nodeMap = new Map(networkState.graph.nodes.map((node) => [node.id, node]));
  const neighbors = networkState.graph.edges
    .filter((edge) => edge.source === selectedId || edge.target === selectedId)
    .map((edge) => ({
      node: nodeMap.get(edge.source === selectedId ? edge.target : edge.source),
      similarity: edge.similarity,
    }))
    .filter((item) => item.node)
    .sort((left, right) => right.similarity - left.similarity);

  const render = (participantDetail = null, loading = false) => {
    const persona = participantDetail?.persona || {
      tagline: selected.persona_tagline,
      description: selected.persona_description,
    };
    const embedding = participantDetail?.embedding;
    const vectorText = embedding?.values?.length
      ? `[${embedding.values.map((value) => Number(value).toFixed(7)).join(", ")}]`
      : "";
    detail.hidden = false;
    detail.innerHTML = `
    <button type="button" class="connection-close" aria-label="閉じる">×</button>
    <div class="connection-kicker">VECTOR COSINE SIMILARITY</div>
    <strong>${safe(selected.icon)} ${safe(selected.nickname)}</strong>
    <small>${safe(selected.persona_name)}｜価値観の近い参加者</small>
    <section class="persona-detail" style="--persona-color:${safe(selected.color)}">
      <b>${safe(persona.tagline || "")}</b>
      <p>${safe(persona.description || "")}</p>
    </section>
    <div class="connection-list">
      ${neighbors.map((item) => `
        <button type="button" data-node-id="${safe(item.node.id)}" style="--connection-color:${safe(item.node.color)}">
          <i></i><b>${safe(item.node.nickname)}</b><em>${Math.round(item.similarity * 100)}%</em>
        </button>`).join("")}
    </div>
    <section class="detail-oracle">
      <div class="connection-kicker">WHY ORACLE</div>
      <figure class="oracle-generated-flow">
        <img src="assets/illustrations/why-oracle-vector-flow-v2.png?v=1" width="1643" height="957" alt="自然言語の回答をベクトルへ変換し、Oracle AI Databaseに保存して、近い価値観の参加者を検索する流れ" />
        <figcaption>
          <span><b>01</b><strong>意味ベクトル化</strong><small>自然言語 → 1536次元</small></span>
          <span><b>02</b><strong>DB内で保存・演算</strong><small>Oracle AI Database</small></span>
          <span><b>03</b><strong>近い人を検索</strong><small>コサイン類似度</small></span>
        </figcaption>
      </figure>
    </section>
    <section class="vector-detail">
      <div class="connection-kicker">FINAL EMBEDDING</div>
      ${loading ? '<p class="vector-loading">ADBからベクトル値を読み込み中…</p>' : embedding ? `
        <div class="vector-meta"><span>${safe(embedding.model || "cohere.embed-v4.0")}</span><span>${Number(embedding.dimension) || 0} dimensions</span><span>${safe(embedding.region || "us-chicago-1")}</span></div>
        <pre>${safe(vectorText)}</pre>` : '<p class="vector-loading">ベクトル値を取得できませんでした</p>'}
    </section>`;
    detail.querySelector(".connection-close").addEventListener("click", () => selectNode(selectedId));
    detail.querySelectorAll(".connection-list button").forEach((element) => {
      element.addEventListener("click", () => focusNode(element.dataset.nodeId));
    });
  };

  const cached = participantDetailCache.get(selectedId);
  if (cached) {
    render(cached);
    return;
  }
  render(null, true);
  try {
    const response = await fetch(`api/network/${encodeURIComponent(selectedId)}`, { cache: "no-store" });
    if (!response.ok) throw new Error("detail unavailable");
    const participantDetail = await response.json();
    participantDetailCache.set(selectedId, participantDetail);
    if (networkState.selectedId === selectedId) render(participantDetail);
  } catch (_) {
    if (networkState.selectedId === selectedId) render();
  }
}

function colorWithAlpha(color, alpha) {
  const hex = String(color).replace("#", "");
  const value = hex.length === 3 ? hex.split("").map((char) => char + char).join("") : hex;
  const number = Number.parseInt(value, 16);
  const red = number >> 16 & 255;
  const green = number >> 8 & 255;
  const blue = number & 255;
  return `rgba(${red},${green},${blue},${alpha})`;
}

function clampZoom(value) {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, value));
}

function applyCamera() {
  const camera = networkState.camera;
  const world = document.querySelector("#network-world");
  world.style.transform =
    `translate3d(${camera.x}px, ${camera.y}px, 0) scale(${camera.scale})`;
  world.style.setProperty("--camera-inverse", String(1 / camera.scale));
  document.querySelector("#zoom-level").value = `${Math.round(camera.scale * 100)}%`;
}

function setCameraScale(nextScale, anchorX, anchorY) {
  const camera = networkState.camera;
  const scale = clampZoom(nextScale);
  if (Math.abs(scale - camera.scale) < 0.0001) return;
  const worldX = (anchorX - camera.x) / camera.scale;
  const worldY = (anchorY - camera.y) / camera.scale;
  camera.x = anchorX - worldX * scale;
  camera.y = anchorY - worldY * scale;
  camera.scale = scale;
  applyCamera();
}

function zoomFromCenter(delta) {
  const viewport = document.querySelector("#network-viewport");
  setCameraScale(
    networkState.camera.scale + delta,
    viewport.clientWidth / 2,
    viewport.clientHeight / 2,
  );
}

function resetCamera() {
  const camera = networkState.camera;
  camera.scale = 1;
  camera.x = 0;
  camera.y = 0;
  applyCamera();
}

function pinchSnapshot(pointers) {
  const [first, second] = [...pointers.values()].slice(0, 2);
  if (!first || !second) return null;
  return {
    distance: Math.max(1, Math.hypot(second.x - first.x, second.y - first.y)),
    x: (first.x + second.x) / 2,
    y: (first.y + second.y) / 2,
  };
}

function setupNetworkCamera() {
  const viewport = document.querySelector("#network-viewport");
  const camera = networkState.camera;

  if (window.ForceGraph3D) {
    const zoom3D = (factor) => {
      const graph3d = networkState.force3d;
      if (!graph3d) return;
      const current = graph3d.cameraPosition();
      graph3d.cameraPosition(
        { x: current.x * factor, y: current.y * factor, z: current.z * factor },
        undefined,
        260,
      );
    };
    document.querySelector("#zoom-level").value = "3D";
    document.querySelector("#zoom-in").addEventListener("click", () => zoom3D(0.78));
    document.querySelector("#zoom-out").addEventListener("click", () => zoom3D(1.28));
    document.querySelector("#zoom-reset").addEventListener("click", () => {
      networkState.force3d?.zoomToFit(650, 70);
    });
    return;
  }

  viewport.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (camera.pointers.size === 0) {
      camera.dragged = false;
      camera.suppressClick = false;
    }
    camera.pointers.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
      startX: event.clientX,
      startY: event.clientY,
    });
    const captureTarget = event.target instanceof Element ? event.target : viewport;
    captureTarget.setPointerCapture?.(event.pointerId);
    camera.pinch = camera.pointers.size >= 2
      ? pinchSnapshot(camera.pointers)
      : null;
    viewport.classList.add("dragging");
  });

  viewport.addEventListener("pointermove", (event) => {
    const pointer = camera.pointers.get(event.pointerId);
    if (!pointer) return;
    const deltaX = event.clientX - pointer.x;
    const deltaY = event.clientY - pointer.y;
    pointer.x = event.clientX;
    pointer.y = event.clientY;

    if (
      camera.pointers.size >= 2 ||
      Math.hypot(event.clientX - pointer.startX, event.clientY - pointer.startY) > 6
    ) {
      camera.dragged = true;
      camera.suppressClick = true;
    }

    if (camera.pointers.size === 1) {
      camera.x += deltaX;
      camera.y += deltaY;
      applyCamera();
      return;
    }

    const currentPinch = pinchSnapshot(camera.pointers);
    if (!currentPinch || !camera.pinch) {
      camera.pinch = currentPinch;
      return;
    }
    camera.x += currentPinch.x - camera.pinch.x;
    camera.y += currentPinch.y - camera.pinch.y;
    const bounds = viewport.getBoundingClientRect();
    setCameraScale(
      camera.scale * (currentPinch.distance / camera.pinch.distance),
      currentPinch.x - bounds.left,
      currentPinch.y - bounds.top,
    );
    camera.pinch = currentPinch;
  });

  const finishPointer = (event) => {
    if (!camera.pointers.has(event.pointerId)) return;
    camera.pointers.delete(event.pointerId);
    camera.pinch = camera.pointers.size >= 2
      ? pinchSnapshot(camera.pointers)
      : null;
    if (camera.pointers.size === 0) {
      viewport.classList.remove("dragging");
      window.setTimeout(() => {
        camera.dragged = false;
        camera.suppressClick = false;
      }, 0);
    }
  };
  viewport.addEventListener("pointerup", finishPointer);
  viewport.addEventListener("pointercancel", finishPointer);

  viewport.addEventListener("wheel", (event) => {
    event.preventDefault();
    const bounds = viewport.getBoundingClientRect();
    const factor = Math.exp(-event.deltaY * 0.0012);
    setCameraScale(
      camera.scale * factor,
      event.clientX - bounds.left,
      event.clientY - bounds.top,
    );
  }, { passive: false });

  viewport.addEventListener("keydown", (event) => {
    if (event.target !== viewport) return;
    const movements = {
      ArrowLeft: [35, 0],
      ArrowRight: [-35, 0],
      ArrowUp: [0, 35],
      ArrowDown: [0, -35],
    };
    if (movements[event.key]) {
      camera.x += movements[event.key][0];
      camera.y += movements[event.key][1];
      applyCamera();
      event.preventDefault();
    } else if (event.key === "+" || event.key === "=") {
      zoomFromCenter(0.2);
      event.preventDefault();
    } else if (event.key === "-") {
      zoomFromCenter(-0.2);
      event.preventDefault();
    } else if (event.key === "0") {
      resetCamera();
      event.preventDefault();
    }
  });

  document.querySelector("#zoom-in").addEventListener("click", () => zoomFromCenter(0.2));
  document.querySelector("#zoom-out").addEventListener("click", () => zoomFromCenter(-0.2));
  document.querySelector("#zoom-reset").addEventListener("click", resetCamera);
  applyCamera();
}

function loadDisplayMio() {
  const image = document.querySelector("#display-mio-sprite");
  image.onload = () => { image.hidden = false; };
  image.onerror = () => { image.hidden = true; };
  image.src = "assets/miochan/idle.gif?v=2";
}

function safe(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

const resizeObserver = new ResizeObserver(() => {
  if (networkState.force3d) {
    const host = document.querySelector("#network-3d");
    networkState.force3d.width(host.clientWidth).height(host.clientHeight);
  } else {
    drawConnections();
  }
});
resizeObserver.observe(document.querySelector(".network-card"));
setupNetworkCamera();
loadDisplayMio();
refreshDisplay();
window.setInterval(refreshDisplay, 5000);
