const state = {
  sessionId: null,
  nickname: "",
  panel: "welcome",
  inactivityTimer: null,
  health: null,
  deadlineAt: null,
  timerHandle: null,
  rescuePollHandle: null,
  rescueTurn: 1,
  rescueBusy: false,
  rescueFinishing: false,
  surveyResult: null,
  publicConsent: true,
  rankingConsent: true,
  gameConsent: true,
  gameStarted: false,
  timerUrgentShown: false,
};
const rescueStorageKey = "mio-rescue-session";

const surveyExampleTexts = [
  "目的を伝えたら、細かく口を出さず任せてくれる上司",
  "困ったときに相談しやすく、最後まで話を聞いてくれる上司",
  "目標と優先順位を明確に示してくれる上司",
  "失敗を責めず、次にどう活かすか一緒に考える上司",
  "良かった点と改善点を具体的にフィードバックする上司",
  "メンバーの強みを見つけ、活かせる仕事を任せる上司",
  "必要なときは素早く決断し、責任を引き受ける上司",
  "自分と異なる意見でも、まず受け止めてくれる上司",
  "チーム全員を公平に扱い、えこひいきをしない上司",
  "挑戦したい気持ちを応援し、機会をつくってくれる上司",
  "忙しいときほど落ち着いて、状況を整理してくれる上司",
  "現場の事情を理解し、無理な期限を押しつけない上司",
  "成果だけでなく、努力や成長の過程も見てくれる上司",
  "率直に話せて、言いにくいことも安心して相談できる上司",
  "方針が変わるとき、理由と背景をきちんと説明する上司",
  "仕事を抱え込まず、チームを信頼して任せる上司",
  "メンバー同士をつなぎ、協力しやすくしてくれる上司",
  "一人ひとりのキャリアや将来について考えてくれる上司",
  "仕事と生活の事情を尊重し、柔軟に対応する上司",
  "判断基準が一貫していて、言うことが頻繁に変わらない上司",
  "自分の間違いを認め、素直に謝ることができる上司",
  "会議を短く整理し、次にやることを明確にする上司",
  "細かな進め方より、期待する成果を伝えてくれる上司",
  "相談には答えを押しつけず、考えるヒントをくれる上司",
  "チームの成功を自分の手柄にせず、みんなを称える上司",
  "問題が起きたとき、部下を守りながら解決に動く上司",
  "新しいアイデアを面白がり、まず試してみようと言う上司",
  "静かに考える時間を尊重し、返事を急かさない上司",
  "感情的に怒らず、事実に基づいて話す上司",
  "ユーモアがあり、チームが前向きになれる空気をつくる上司",
];

function shuffledSurveyExamples() {
  const examples = [...surveyExampleTexts];
  for (let index = examples.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [examples[index], examples[swapIndex]] = [examples[swapIndex], examples[index]];
  }
  return examples;
}

function renderSurveyExamples() {
  const track = document.querySelector("#survey-examples");
  const fragment = document.createDocumentFragment();
  shuffledSurveyExamples().forEach((example) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = example;
    fragment.appendChild(button);
  });
  track.replaceChildren(fragment);
  track.scrollLeft = 0;
}

const mioStates = {
  welcome: { file: "generated-v1/listening.gif", caption: "READY TO LISTEN", alt: "話を聞くみおちゃん" },
  idle: { file: "generated-v1/listening.gif", caption: "LISTENING", alt: "話を聞くみおちゃん" },
  waiting: { file: "generated-v1/thinking.gif", caption: "THINKING WITH AI", alt: "考えているみおちゃん" },
  thinking: { file: "generated-v1/thinking.gif", caption: "THINKING", alt: "考えているみおちゃん" },
  review: { file: "generated-v1/thinking.gif", caption: "SELECT AI REVIEW", alt: "回答を確認するみおちゃん" },
  running: { file: "generated-v1/thinking.gif", caption: "VECTOR SCORING", alt: "採点中のみおちゃん" },
  jumping: { file: "generated-v1/celebrate.gif", caption: "RESCUE COMPLETE", alt: "成功を喜ぶみおちゃん" },
  failed: { file: "generated-v1/retry.gif", caption: "LET'S TRY AGAIN", alt: "やさしく再挑戦をお願いするみおちゃん" },
  anxious: { file: "generated-v1/anxious.gif", caption: "FEELING ANXIOUS", alt: "不安そうなみおちゃん" },
  overwhelmed: { file: "generated-v1/overwhelmed.gif", caption: "TOO MUCH WORK", alt: "仕事を抱えすぎたみおちゃん" },
  presentation: { file: "generated-v1/presentation.gif", caption: "PRESENTATION PRACTICE", alt: "発表を練習するみおちゃん" },
  timePressure: { file: "generated-v1/time-pressure.gif", caption: "TIME IS RUNNING", alt: "残り時間を気にするみおちゃん" },
  idea: { file: "generated-v1/idea.gif", caption: "GOT AN IDEA", alt: "ひらめいたみおちゃん" },
  relieved: { file: "generated-v1/relieved.gif", caption: "FEELING RELIEVED", alt: "安心したみおちゃん" },
  listening: { file: "generated-v1/listening.gif", caption: "LISTENING TO YOU", alt: "アドバイスを聞くみおちゃん" },
  retry: { file: "generated-v1/retry.gif", caption: "ONE MORE TRY", alt: "もう一度お願いするみおちゃん" },
};

const challengeMioStates = {
  quiz_01: "presentation",
  quiz_02: "listening",
  quiz_03: "thinking",
  quiz_04: "anxious",
  quiz_05: "overwhelmed",
  quiz_06: "listening",
  quiz_07: "anxious",
  quiz_08: "retry",
  quiz_09: "thinking",
  quiz_10: "idea",
};

const stage = document.querySelector("#mio-stage");
const sprite = document.querySelector("#mio-sprite");
const speech = document.querySelector("#mio-speech");
const caption = document.querySelector("#state-caption-text");
const toast = document.querySelector("#toast");
const mioAssetVersion = "4";
const mioPreloads = new Map();
let mioStateRequest = 0;

function preloadMioAsset(selected) {
  const source = `assets/miochan/${selected.file}?v=${mioAssetVersion}`;
  if (!mioPreloads.has(source)) {
    const image = new Image();
    image.src = source;
    mioPreloads.set(source, image);
  }
  return { image: mioPreloads.get(source), source };
}

function setMioState(name, message) {
  const selected = mioStates[name] || mioStates.idle;
  const request = ++mioStateRequest;
  stage.dataset.state = name;
  caption.textContent = selected.caption;
  sprite.alt = selected.alt;
  const { image, source } = preloadMioAsset(selected);
  if (sprite.dataset.source === source && !sprite.hidden) {
    if (message) speech.innerHTML = message;
    return;
  }
  const showLoadedAsset = () => {
    if (request !== mioStateRequest) return;
    sprite.src = source;
    sprite.dataset.source = source;
    sprite.hidden = false;
  };
  if (image.complete && image.naturalWidth > 0) showLoadedAsset();
  else image.addEventListener("load", showLoadedAsset, { once: true });
  if (message) speech.innerHTML = message;
}

function setMioForChallenge(result) {
  if (state.timerUrgentShown) {
    setMioState("timePressure", safeSpeech(result.mio_message));
    return;
  }
  const selectedState = challengeMioStates[result.challenge_type] || "anxious";
  setMioState(selectedState, safeSpeech(result.mio_message));
}

Object.values(mioStates).forEach(preloadMioAsset);

function activatePipeline(...names) {
  document.querySelectorAll("[data-pipeline]").forEach((card) => {
    card.classList.toggle("active", names.includes(card.dataset.pipeline));
  });
}

function setPanel(name) {
  state.panel = name;
  document.body.classList.toggle("welcome-panel-active", name === "welcome");
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.panel === name);
  });
  const order = ["welcome", "survey", "game-guide", "countdown", "rescue", "rescue-result", "result"];
  const currentIndex = order.indexOf(name);
  document.querySelectorAll("[data-step-dot]").forEach((dot, index) => {
    dot.classList.toggle("active", index === currentIndex);
    dot.classList.toggle("done", index < currentIndex);
  });
  if (name === "survey") renderSurveyExamples();
  resetInactivityTimer();
}

function resetInactivityTimer() {
  window.clearTimeout(state.inactivityTimer);
  if (!state.sessionId || state.panel === "rescue") return;
  state.inactivityTimer = window.setTimeout(() => {
    showToast("安全のためセッションをリセットしました");
    resetExperience();
  }, 180_000);
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3000);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = "処理を完了できませんでした";
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) {
      // Use the generic message.
    }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function loadHealth() {
  try {
    state.health = await api("api/health");
    const status = document.querySelector("#system-status");
    status.querySelector("span:last-child").textContent =
      state.health.data_mode === "adb" ? "ADB LIVE" : "SAFE DEMO MODE";
    status.classList.toggle("warning", state.health.data_mode !== "adb");
  } catch (_) {
    const status = document.querySelector("#system-status");
    status.querySelector("span:last-child").textContent = "OFFLINE";
    status.classList.add("warning");
  }
}

document.querySelector("#start-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  const nickname = document.querySelector("#nickname").value.trim();
  const gameConsent = true;
  const publicConsent = true;
  const rankingConsent = true;
  if (!nickname) return;
  button.disabled = true;
  setMioState("waiting", "アンケートを<br>準備しているよ…");
  try {
    const result = await api("api/sessions", {
      method: "POST",
      body: JSON.stringify({
        nickname,
        public_consent: publicConsent,
        ranking_consent: rankingConsent,
      }),
    });
    state.sessionId = result.session_id;
    state.nickname = nickname;
    state.publicConsent = publicConsent;
    state.rankingConsent = rankingConsent;
    state.gameConsent = gameConsent;
    state.gameStarted = false;
    sessionStorage.setItem(rescueStorageKey, JSON.stringify({
      sessionId: state.sessionId,
      nickname: state.nickname,
      publicConsent: state.publicConsent,
      rankingConsent: state.rankingConsent,
      gameConsent: state.gameConsent,
      gameStarted: false,
    }));
    setPanel("survey");
    setMioState("idle", "あなたの理想の上司を<br>教えてね");
    activatePipeline("database", "vector");
    document.querySelector("#survey-answer").focus();
  } catch (error) {
    setMioState("failed", "ごめんね。<br>もう一度試してみて！");
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

function startRescueTimer() {
  stopRescueTimer();
  state.timerUrgentShown = false;
  updateRescueTimer();
  state.timerHandle = window.setInterval(updateRescueTimer, 250);
}

function stopRescueTimer() {
  window.clearInterval(state.timerHandle);
  state.timerHandle = null;
}

function startRescuePolling() {
  stopRescuePolling();
  state.rescuePollHandle = window.setInterval(pollRescueState, 1200);
}

function stopRescuePolling() {
  window.clearInterval(state.rescuePollHandle);
  state.rescuePollHandle = null;
}

async function pollRescueState() {
  if (!state.sessionId || state.panel !== "rescue" || state.rescueBusy || state.rescueFinishing) return;
  try {
    const current = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}`);
    state.rescueTurn = Math.max(state.rescueTurn, current.turn_no);
    renderRescueState(current);
    if (Number(current.difficulty) === 0 && !current.game_finished) {
      finishRescue();
      return;
    }
    if (current.game_finished) {
      stopRescueTimer();
      stopRescuePolling();
      const result = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}/result`);
      renderRescueResult(result);
    }
  } catch (_) {
    // Retry transient ADB or network errors on the next poll.
  }
}

function updateRescueTimer() {
  if (!state.deadlineAt || state.panel !== "rescue") return;
  const remainingMs = Math.max(0, state.deadlineAt - Date.now());
  const seconds = Math.ceil(remainingMs / 1000);
  document.querySelector("#rescue-timer").textContent =
    `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  document.querySelector("#rescue-timer").classList.toggle("urgent", seconds <= 10);
  if (seconds <= 10 && seconds > 0 && !state.timerUrgentShown) {
    state.timerUrgentShown = true;
    setMioState("timePressure", "あと少し！<br>最後まで一緒に考えてね");
  }
  if (remainingMs <= 0) finishRescue();
}

function renderRescueState(result) {
  document.querySelector("#rescue-score").textContent = result.score ?? result.total_score ?? 0;
  document.querySelector("#rescue-coins").textContent = result.coins ?? 0;
  document.querySelector("#rescue-combo").textContent = result.combo ? `${result.combo}×` : "—";
  const difficulty = Number(result.difficulty ?? 100);
  document.querySelector("#difficulty-value").textContent = `${difficulty}%`;
  document.querySelector("#difficulty-bar").style.width = `${difficulty}%`;
  document.querySelector("#rescue-message").textContent = result.mio_message || "もう少し一緒に考えてくれる？";
  const scoringStatus = document.querySelector("#rescue-scoring-status");
  scoringStatus.textContent = result.scoring_pending
    ? `回答を保存済み・DB内で採点中${result.pending_turns ? ` (${result.pending_turns})` : ""}`
    : "採点結果を反映済み";
  scoringStatus.classList.toggle("pending", Boolean(result.scoring_pending));
  renderRescueChoices(result.choices || []);
  setMioForChallenge(result);
}

function renderRescueChoices(choices) {
  const container = document.querySelector("#rescue-choices");
  container.replaceChildren();
  choices.forEach((choice, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = `<b>${String.fromCharCode(65 + index)}</b><span>${escapeHtml(choice)}</span>`;
    button.addEventListener("click", () => submitRescueAnswer("choice", choice));
    container.appendChild(button);
  });
}

function setRescueDisabled(disabled) {
  document.querySelectorAll("#rescue-choices button, #rescue-form input, #rescue-form button")
    .forEach((element) => { element.disabled = disabled; });
}

document.querySelector("#rescue-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#rescue-answer");
  const answer = input.value.trim();
  if (answer.length < 2) return;
  input.value = "";
  submitRescueAnswer("free_text", answer);
});

async function submitRescueAnswer(answerType, answer) {
  if (state.rescueBusy || !state.sessionId) return;
  state.rescueBusy = true;
  setRescueDisabled(true);
  setMioState(answerType === "free_text" ? "listening" : "review", answerType === "free_text"
    ? "あなたの言葉を<br>しっかり聞いているよ…"
    : "回答をADBに<br>保存しているよ…");
  try {
    const result = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}/turns`, {
      method: "POST",
      body: JSON.stringify({
        turn_no: state.rescueTurn,
        answer_type: answerType,
        user_answer: answer,
      }),
    });
    if (result.accepted) {
      state.rescueTurn = result.turn_no + 1;
      renderRescueState(result);
      showToast(result.scoring_pending
        ? "回答を保存しました。採点はバックグラウンドで進みます"
        : `${result.turn_score >= 0 ? "+" : ""}${result.turn_score} POINT`);
      setMioForChallenge(result);
    }
    if (result.game_finished) {
      stopRescueTimer();
      renderRescueResult(result.result);
    }
  } catch (error) {
    setMioState("failed", "安全な方法で<br>もう一度試してね");
    showToast(error.message);
  } finally {
    state.rescueBusy = false;
    if (state.panel === "rescue") setRescueDisabled(false);
  }
}

function setMioFromEmotion(emotion, message) {
  const states = { anxious: "anxious", confused: "retry", relieved: "relieved", happy: "jumping" };
  setMioState(states[emotion] || "idle", safeSpeech(message));
}

async function finishRescue() {
  if (state.rescueFinishing || state.panel !== "rescue") return;
  if (state.rescueBusy) {
    window.setTimeout(finishRescue, 300);
    return;
  }
  state.rescueFinishing = true;
  stopRescueTimer();
  stopRescuePolling();
  setRescueDisabled(true);
  setMioState("running", "最後の回答をDB内で<br>ベクトル化・採点しています…");
  try {
    const result = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}/finish`, { method: "POST" });
    renderRescueResult(result);
  } catch (error) {
    state.rescueFinishing = false;
    showToast(error.message);
    window.setTimeout(finishRescue, 700);
  }
}

function renderRescueResult(result) {
  if (!result) return;
  state.rescueFinishing = false;
  stopRescuePolling();
  setPanel("rescue-result");
  const clearedLabel = result.cleared ? "RESCUE COMPLETE" : "TIME UP";
  document.querySelector("#rescue-result-content").innerHTML = `
    <div class="rescue-result-kicker">${clearedLabel}</div>
    <h2>結果発表！</h2>
    <div class="rescue-rank rank-${escapeHtml(result.rank_label)}">${escapeHtml(result.rank_label)}</div>
    <strong class="rescue-final-score">${Number(result.final_score) || 0}<small>/ 100</small></strong>
    <div class="rescue-result-grid">
      <span><small>COIN</small><b>${Number(result.coins) || 0}</b></span>
      <span><small>TITLE</small><b>${escapeHtml(result.title_label || "レスキュー隊")}</b></span>
    </div>
    <blockquote>${escapeHtml(result.mio_message || "助けてくれてありがとう！")}</blockquote>`;
  const resultState = result.cleared || ["A", "B"].includes(result.rank_label)
    ? "jumping"
    : result.rank_label === "E" ? "retry" : "relieved";
  setMioState(resultState, safeSpeech(result.mio_message));
  activatePipeline("genai", "database", "vector");
}

document.querySelector("#to-result").addEventListener("click", () => {
  if (!state.surveyResult) {
    showToast("アンケート結果を読み込めませんでした");
    return;
  }
  renderResult(state.surveyResult);
  setPanel("result");
  setMioState("jumping", "見つけた！<br>理想が近い人たちです");
  activatePipeline("database", "vector");
});

const surveyExamples = document.querySelector("#survey-examples");
surveyExamples.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const textarea = document.querySelector("#survey-answer");
  textarea.value = button.textContent;
  textarea.dispatchEvent(new Event("input"));
  textarea.focus();
});

surveyExamples.addEventListener("wheel", (event) => {
  if (Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
  const previous = surveyExamples.scrollLeft;
  surveyExamples.scrollLeft += event.deltaY;
  if (surveyExamples.scrollLeft !== previous) event.preventDefault();
}, { passive: false });

surveyExamples.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
    surveyExamples.scrollBy({ left: event.key === "ArrowRight" ? 180 : -180, behavior: "smooth" });
    event.preventDefault();
  }
});

document.querySelector("#survey-answer").addEventListener("input", (event) => {
  document.querySelector("#char-count").textContent = `${event.target.value.length} / 500`;
  resetInactivityTimer();
});

document.querySelector("#survey-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const answer = document.querySelector("#survey-answer").value.trim();
  const button = event.submitter;
  if (!answer || !state.sessionId) return;
  button.disabled = true;
  setMioState("waiting", "アンケートを<br>分析しているよ…");
  activatePipeline("database", "vector");
  try {
    state.surveyResult = await api("api/survey", {
      method: "POST",
      body: JSON.stringify({ session_id: state.sessionId, answer }),
    });
    sessionStorage.setItem(rescueStorageKey, JSON.stringify({
      sessionId: state.sessionId,
      nickname: state.nickname,
      publicConsent: state.publicConsent,
      rankingConsent: state.rankingConsent,
      gameConsent: state.gameConsent,
      gameStarted: false,
      surveyResult: state.surveyResult,
    }));
    setPanel("game-guide");
    setMioState("idea", "次は60秒ゲーム！<br>説明を読んでね");
    activatePipeline("genai", "database", "vector");
  } catch (error) {
    setMioState("failed", "アンケートを<br>もう一度送ってみてね");
    showToast(error.message);
    setPanel("survey");
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#start-game").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!state.sessionId || !state.surveyResult || state.gameStarted) return;
  button.disabled = true;
  setPanel("countdown");
  setMioState("waiting", "ゲーム開始まで<br>もう少しだよ…");
  activatePipeline("genai", "database", "vector");
  try {
    await runCountdown();
    const game = await api("api/mio/sessions", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        nickname: state.nickname,
        consent: state.gameConsent,
        public_consent: state.publicConsent,
        ranking_consent: state.rankingConsent,
      }),
    });
    state.gameStarted = true;
    state.rescueTurn = game.turn_no;
    state.deadlineAt = new Date(game.deadline_at).getTime();
    sessionStorage.setItem(rescueStorageKey, JSON.stringify({
      sessionId: state.sessionId,
      nickname: state.nickname,
      publicConsent: state.publicConsent,
      rankingConsent: state.rankingConsent,
      gameConsent: state.gameConsent,
      gameStarted: true,
      surveyResult: state.surveyResult,
    }));
    setPanel("rescue");
    renderRescueState(game);
    setMioForChallenge(game);
    activatePipeline("genai", "database", "vector");
    startRescueTimer();
    startRescuePolling();
  } catch (error) {
    setMioState("failed", "ゲームを安全な方法で<br>やり直してみよう");
    showToast(error.message);
    setPanel("game-guide");
  } finally {
    button.disabled = false;
  }
});

function delay(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function runCountdown() {
  const countdown = document.querySelector("#countdown-number");
  for (const number of [3, 2, 1]) {
    countdown.textContent = String(number);
    countdown.classList.remove("pop");
    void countdown.offsetWidth;
    countdown.classList.add("pop");
    await delay(900);
  }
  countdown.textContent = "START";
  countdown.classList.remove("pop");
  void countdown.offsetWidth;
  countdown.classList.add("pop");
}

function renderResult(result) {
  const persona = result.persona;
  const matches = result.matches || [];
  const matchRows = matches.map((match, index) => `
    <div class="match">
      <span class="match-rank">0${index + 1}</span>
      <div><strong>${escapeHtml(match.nickname)}</strong><small>${escapeHtml(match.reason)}</small></div>
      <span class="match-score">${Math.round(match.score * 100)}%</span>
    </div>`).join("");
  document.querySelector("#result-content").innerHTML = `
    <div class="result-hero" style="--persona-color:${escapeHtml(persona.color)}">
      <div class="result-label">YOUR IDEAL BOSS STYLE</div>
      <div class="result-icon">${escapeHtml(persona.icon)}</div>
      <h2>${escapeHtml(persona.name)}</h2>
      <div class="result-tagline">${escapeHtml(persona.tagline)}</div>
      <p class="result-description">${escapeHtml(persona.description)}</p>
    </div>
    <div class="keyword-row">${result.keywords.map((item) => `<span># ${escapeHtml(item)}</span>`).join("")}</div>
    <div class="match-title"><strong>会場で価値観が近い人</strong><span>AI VECTOR SEARCH</span></div>
    <div class="matches">${matchRows || "<p>次の参加者を待っています…</p>"}</div>
    <div class="result-tech">✦ DB内で生成した1536次元ベクトルをOracle AI Databaseで検索しました</div>`;
}

document.querySelector("#restart").addEventListener("click", resetExperience);

function resetExperience() {
  stopRescueTimer();
  stopRescuePolling();
  window.clearTimeout(state.inactivityTimer);
  state.sessionId = null;
  state.nickname = "";
  state.deadlineAt = null;
  state.rescueTurn = 1;
  state.rescueBusy = false;
  state.rescueFinishing = false;
  state.surveyResult = null;
  state.publicConsent = true;
  state.rankingConsent = true;
  state.gameConsent = true;
  state.gameStarted = false;
  state.timerUrgentShown = false;
  sessionStorage.removeItem(rescueStorageKey);
  document.querySelector("#start-form").reset();
  document.querySelector("#nickname").value = "";
  document.querySelector("#survey-answer").value = "";
  document.querySelector("#char-count").textContent = "0 / 500";
  document.querySelector("#rescue-answer").value = "";
  setPanel("welcome");
  setMioState("welcome", "こんにちは！<br>60秒で助けてくれる？");
  activatePipeline();
}

async function restoreRescueSession() {
  let saved;
  try {
    saved = JSON.parse(sessionStorage.getItem(rescueStorageKey) || "null");
  } catch (_) {
    sessionStorage.removeItem(rescueStorageKey);
    return;
  }
  if (!saved?.sessionId) return;
  state.sessionId = saved.sessionId;
  state.nickname = saved.nickname || "";
  state.publicConsent = saved.publicConsent !== false;
  state.rankingConsent = saved.rankingConsent !== false;
  state.gameConsent = saved.gameConsent !== false;
  state.gameStarted = saved.gameStarted !== false;
  state.surveyResult = saved.surveyResult || null;
  if (!state.gameStarted) {
    if (state.surveyResult) {
      setPanel("game-guide");
      setMioState("idea", "次は60秒ゲーム！<br>説明を読んでね");
      activatePipeline("genai", "database", "vector");
    } else {
      setPanel("survey");
      setMioState("idle", "あなたの理想の上司を<br>教えてね");
      activatePipeline("database", "vector");
    }
    return;
  }
  try {
    const current = await api(`api/mio/sessions/${encodeURIComponent(saved.sessionId)}`);
    state.nickname = current.nickname || saved.nickname || "";
    state.rescueTurn = current.turn_no;
    state.deadlineAt = new Date(current.deadline_at).getTime();
    if (current.game_finished) {
      const result = await api(`api/mio/sessions/${encodeURIComponent(saved.sessionId)}/result`);
      renderRescueResult(result);
      return;
    }
    setPanel("rescue");
    renderRescueState(current);
    setMioForChallenge(current);
    activatePipeline("genai", "database", "vector");
    if (current.expired) finishRescue();
    else {
      startRescueTimer();
      startRescuePolling();
    }
  } catch (_) {
    sessionStorage.removeItem(rescueStorageKey);
  }
}

function safeSpeech(value) {
  return escapeHtml(value || "").replaceAll("\n", "<br>");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

["pointerdown", "keydown", "touchstart"].forEach((eventName) => {
  document.addEventListener(eventName, resetInactivityTimer, { passive: true });
});

document.querySelector("#mobile-start-cta").addEventListener("click", () => {
  document.querySelector("#interaction-card").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
  window.setTimeout(() => document.querySelector("#nickname").focus({ preventScroll: true }), 450);
});

setMioState("welcome", "こんにちは！<br>60秒で助けてくれる？");
loadHealth();
restoreRescueSession();
