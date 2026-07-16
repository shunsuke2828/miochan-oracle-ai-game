const adminState = {
  participants: [],
  selected: new Set(),
  query: "",
  filter: "all",
};

const personaStyle = {
  "フクロウタイプ": { icon: "🦉", color: "#7766d7" },
  "イルカタイプ": { icon: "🐬", color: "#19a7a0" },
  "小鳥タイプ": { icon: "🐦", color: "#f3a529" },
  "猫タイプ": { icon: "🐈", color: "#ec6f75" },
  "鷹タイプ": { icon: "🦅", color: "#335c91" },
  "クマタイプ": { icon: "🐻", color: "#4f9d69" },
};

async function loadParticipants() {
  const refresh = document.querySelector("#refresh-button");
  refresh.classList.add("loading");
  refresh.disabled = true;
  try {
    const response = await fetch("api/admin/participants", { cache: "no-store" });
    if (!response.ok) throw new Error("参加者一覧を取得できませんでした");
    const result = await response.json();
    adminState.participants = result.participants || [];
    const validIds = new Set(adminState.participants.map((item) => item.session_id));
    adminState.selected.forEach((id) => {
      if (!validIds.has(id)) adminState.selected.delete(id);
    });
    document.querySelector("#admin-data-mode").textContent =
      result.data_mode === "adb" ? "ORACLE ADB LIVE" : "MEMORY DEMO";
    renderStats();
    renderParticipants();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    refresh.classList.remove("loading");
    refresh.disabled = false;
  }
}

function filteredParticipants() {
  const query = adminState.query.toLocaleLowerCase("ja");
  return adminState.participants.filter((item) => {
    const matchesQuery = !query || [item.nickname, item.persona_name, item.answer]
      .some((value) => String(value || "").toLocaleLowerCase("ja").includes(query));
    const matchesFilter = adminState.filter === "all"
      || (adminState.filter === "completed" && item.completed)
      || (adminState.filter === "pending" && !item.completed)
      || (adminState.filter === "visitor" && !item.is_seed);
    return matchesQuery && matchesFilter;
  });
}

function renderStats() {
  const participants = adminState.participants;
  document.querySelector("#total-count").textContent = participants.length;
  document.querySelector("#completed-count").textContent = participants.filter((item) => item.completed).length;
  document.querySelector("#public-count").textContent = participants.filter((item) => item.public_consent).length;
}

function renderParticipants() {
  const rows = filteredParticipants();
  const tbody = document.querySelector("#participant-rows");
  tbody.innerHTML = rows.map(participantRow).join("");
  document.querySelector("#empty-state").hidden = rows.length > 0;
  tbody.querySelectorAll("input[data-session-id]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) adminState.selected.add(checkbox.dataset.sessionId);
      else adminState.selected.delete(checkbox.dataset.sessionId);
      updateSelectionUi();
    });
  });
  tbody.querySelectorAll("button[data-detail-id]").forEach((button) => {
    button.addEventListener("click", () => openParticipantDetail(button.dataset.detailId));
  });
  updateSelectionUi();
}

function participantRow(item) {
  const persona = personaStyle[item.persona_name] || { icon: "—", color: "#8a929f" };
  const date = formatDate(item.created_at);
  return `
    <tr>
      <td class="select-column">
        <input type="checkbox" data-session-id="${safe(item.session_id)}"
          aria-label="${safe(item.nickname)}を選択"
          ${adminState.selected.has(item.session_id) ? "checked" : ""}
          ${item.is_seed ? "disabled" : ""} />
      </td>
      <td>
        <div class="nickname-cell">
          <span class="nickname-avatar">${safe(persona.icon)}</span>
          <span><strong>${safe(item.nickname)}${item.is_seed ? '<i class="seed-badge">デモ初期データ</i>' : ""}</strong><small>${safe(item.session_id.slice(0, 12))}</small></span>
        </div>
      </td>
      <td>${item.completed
        ? `<span class="persona-badge" style="--persona-color:${safe(persona.color)}">${safe(persona.icon)} ${safe(item.persona_name)}</span>`
        : '<span class="pending-badge">未診断</span>'}</td>
      <td class="answer-cell">${item.answer ? `<span title="${safe(item.answer)}">${safe(item.answer)}</span>` : "<em>回答なし</em>"}</td>
      <td><span class="visibility-badge ${item.public_consent ? "public" : ""}"><i></i>マップ${item.public_consent ? "公開" : "非公開"}</span><br /><span class="visibility-badge ${item.ranking_consent ? "public" : ""}"><i></i>順位${item.ranking_consent ? "公開" : "非公開"}</span></td>
      <td class="date-cell"><strong>${safe(date.date)}</strong><small>${safe(date.time)}・会話 ${Number(item.message_count) || 0}件</small></td>
      <td><button type="button" class="detail-button" data-detail-id="${safe(item.session_id)}">詳細を見る</button></td>
    </tr>`;
}

function updateSelectionUi() {
  const visibleDeletable = filteredParticipants().filter((item) => !item.is_seed);
  const selectedVisible = visibleDeletable.filter((item) => adminState.selected.has(item.session_id));
  const selectAll = document.querySelector("#select-all");
  selectAll.checked = visibleDeletable.length > 0 && selectedVisible.length === visibleDeletable.length;
  selectAll.indeterminate = selectedVisible.length > 0 && selectedVisible.length < visibleDeletable.length;
  selectAll.disabled = visibleDeletable.length === 0;
  document.querySelector("#selected-count").textContent = adminState.selected.size;
  document.querySelector("#selection-bar").hidden = adminState.selected.size === 0;
}

document.querySelector("#select-all").addEventListener("change", (event) => {
  filteredParticipants().filter((item) => !item.is_seed).forEach((item) => {
    if (event.target.checked) adminState.selected.add(item.session_id);
    else adminState.selected.delete(item.session_id);
  });
  renderParticipants();
});

document.querySelector("#participant-search").addEventListener("input", (event) => {
  adminState.query = event.target.value.trim();
  renderParticipants();
});

document.querySelector("#status-filter").addEventListener("change", (event) => {
  adminState.filter = event.target.value;
  renderParticipants();
});

document.querySelector("#refresh-button").addEventListener("click", loadParticipants);
document.querySelector("#clear-selection").addEventListener("click", () => {
  adminState.selected.clear();
  renderParticipants();
});

document.querySelector("#open-delete").addEventListener("click", () => {
  const selected = adminState.participants.filter((item) => adminState.selected.has(item.session_id));
  if (!selected.length) return;
  document.querySelector("#delete-description").textContent = `${selected.length}名の参加者を完全に削除します。`;
  document.querySelector("#delete-names").innerHTML = selected
    .map((item) => `<span>${safe(item.nickname)}</span>`)
    .join("");
  document.querySelector("#delete-dialog").showModal();
});

document.querySelector("#confirm-delete").addEventListener("click", async () => {
  const button = document.querySelector("#confirm-delete");
  button.disabled = true;
  try {
    const response = await fetch("api/admin/participants", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: [...adminState.selected] }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "参加者を削除できませんでした");
    document.querySelector("#delete-dialog").close();
    adminState.selected.clear();
    showToast(`${result.deleted}名の参加者を削除しました`);
    await loadParticipants();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

async function openParticipantDetail(sessionId) {
  const dialog = document.querySelector("#participant-detail-dialog");
  const content = document.querySelector("#participant-detail-content");
  content.innerHTML = '<div class="detail-loading">データを読み込んでいます…</div>';
  dialog.showModal();
  try {
    const response = await fetch(`api/admin/participants/${encodeURIComponent(sessionId)}`, {
      cache: "no-store",
    });
    const detail = await response.json();
    if (!response.ok) throw new Error(detail.detail || "参加者の詳細を取得できませんでした");
    renderParticipantDetail(detail);
  } catch (error) {
    content.innerHTML = `<div class="detail-error">${safe(error.message)}</div>`;
  }
}

function renderParticipantDetail(detail) {
  const participant = detail.participant;
  const office = detail.office_preference;
  const rescue = detail.rescue;
  const messages = detail.initial_qa.messages || [];
  const vectorValues = office.values || [];
  const vectorText = `[${vectorValues.map((value) => Number(value).toFixed(7)).join(", ")}]`;
  const qaRows = messages.length
    ? messages.map((message) => {
      const isUser = message.role === "user";
      const sources = (message.source_labels || []).length
        ? `<small>参照: ${(message.source_labels || []).map(safe).join(" / ")}</small>`
        : "";
      return `<article class="qa-message ${isUser ? "question" : "answer"}">
        <span>${isUser ? "Q" : "A"}</span>
        <div><strong>${isUser ? "参加者の質問" : "みおちゃんの回答"}</strong><p>${safe(message.content)}</p>${sources}</div>
      </article>`;
    }).join("")
    : '<p class="no-data">初回QAの履歴はありません。</p>';
  const rescueTurns = rescue && rescue.turns && rescue.turns.length
    ? rescue.turns.map((turn) => `<article class="rescue-turn-row">
        <header><b>TURN ${turn.turn_no}</b><span>${safe(turn.challenge_type)}</span><em>${Number(turn.turn_score) >= 0 ? "+" : ""}${Number(turn.turn_score)} pt</em></header>
        <p><strong>みおちゃん</strong>${safe(turn.mio_message)}</p>
        <p><strong>回答</strong>${safe(turn.user_answer)}</p>
        <footer>
          <span>類似度 <b>${turn.ideal_similarity == null ? "—" : `${Math.round(Number(turn.ideal_similarity) * 100)}%`}</b></span>
          <span>${turn.scoring_pending ? "DB内で採点中" : `困り度 <b>${turn.difficulty_before} → ${turn.difficulty_after}</b>`}</span>
          <span>Embedding <b>${safe(turn.embedding_model)} / ${Number(turn.embedding_dimension)}次元</b></span>
        </footer>
      </article>`).join("")
    : '<p class="no-data">レスキューの回答履歴はありません。</p>';
  const rescueSection = rescue ? `<section class="detail-section rescue-admin-section">
      <div class="detail-section-title"><div><span>STEP 2</span><h3>60秒レスキュー</h3></div><b class="vector-status included">MIO-RS</b></div>
      <div class="rescue-admin-summary">
        <span><small>SCORE</small><b>${Number(rescue.final_score)}</b></span>
        <span><small>COIN</small><b>${Number(rescue.coins)}</b></span>
        <span><small>RANK</small><b>${safe(rescue.rank_label || "—")}</b></span>
        <span><small>TITLE</small><b>${safe(rescue.title_label || "—")}</b></span>
      </div>
      <div class="rescue-admin-turns">${rescueTurns}</div>
    </section>` : `<section class="detail-section"><div class="detail-section-title"><div><span>STEP 2</span><h3>60秒レスキュー</h3></div></div><p class="no-data">レスキュー結果はありません。</p></section>`;

  document.querySelector("#participant-detail-content").innerHTML = `
    <section class="detail-identity">
      <div><span>ニックネーム</span><strong>${safe(participant.nickname)}</strong></div>
      <div><span>診断結果</span><strong>${safe(participant.persona_name || "未診断")}</strong></div>
      <div><span>SESSION ID</span><code>${safe(participant.session_id)}</code></div>
    </section>

    <section class="relationship-note">
      <strong>2つの体験のつながり</strong>
      <p>Step1の「理想の上司」回答だけをDB内で1536次元ベクトルへ変換し、近い参加者の検索と会場マップに使用しています。Step2のレスキュー回答は採点専用で、会場マップには表示しません。両者は同じセッションIDで紐づいています。</p>
    </section>

    ${rescueSection}

    ${messages.length ? `<section class="detail-section"><div class="detail-section-title"><div><span>LEGACY</span><h3>旧QA履歴</h3></div><b class="vector-status excluded">マップ対象外</b></div><div class="qa-history">${qaRows}</div></section>` : ""}

    <section class="detail-section">
      <div class="detail-section-title"><div><span>STEP 1</span><h3>理想の上司</h3></div><b class="vector-status included">ベクトル化対象</b></div>
      <div class="natural-language-card">
        <span>QUESTION</span><strong>${safe(office.question)}</strong>
        <span>ANSWER — VECTOR SOURCE TEXT</span><p>${safe(office.answer || "回答なし")}</p>
      </div>
    </section>

    <section class="detail-section vector-section">
      <div class="detail-section-title"><div><span>ORACLE AI DATABASE</span><h3>保存されたベクトル値</h3></div><button type="button" id="copy-vector" ${vectorValues.length ? "" : "disabled"}>値をコピー</button></div>
      <div class="vector-metadata">
        <span><b>${safe(office.storage_type)}</b>型</span>
        <span><b>${Number(office.dimension) || 0}</b>次元</span>
        <span><b>COSINE</b>類似度</span>
        <span><b>${safe(office.model || "-")}</b>モデル</span>
        <span><b>${safe(office.region || "-")}</b>リージョン</span>
        <span><b>${safe(office.operation || "-")}</b>DB内処理</span>
      </div>
      <pre class="vector-values">${vectorValues.length ? safe(vectorText) : "ベクトルはまだ保存されていません。"}</pre>
    </section>`;

  const copyButton = document.querySelector("#copy-vector");
  if (copyButton && vectorValues.length) {
    copyButton.addEventListener("click", () => {
      copyText(vectorText);
      showToast("ベクトル値をコピーしました");
    });
  }
}

function copyText(value) {
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: "日時不明", time: "" };
  return {
    date: new Intl.DateTimeFormat("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date),
    time: new Intl.DateTimeFormat("ja-JP", { hour: "2-digit", minute: "2-digit" }).format(date),
  };
}

function showToast(message, isError = false) {
  const toast = document.querySelector("#admin-toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function safe(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadParticipants();
