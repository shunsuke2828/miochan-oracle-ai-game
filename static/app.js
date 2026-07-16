const state = {
  sessionId: null,
  nickname: "",
  panel: "welcome",
  inactivityTimer: null,
  health: null,
  deadlineAt: null,
  timerHandle: null,
  rescuePollHandle: null,
  rescueResultPollHandle: null,
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

const surveyExampleGroups = [
  // 1つの意味グループから毎回1表現だけを選ぶため、同義文は同時表示されません。
  // フクロウタイプ — 裁量と、自分で考える余白
  { id: 'owl_autonomy', persona: 'フクロウタイプ', variants: [
    "目的だけ共有し、進め方は本人の裁量に任せてくれる上司",
    "ゴールを示したあとは、細かな手順まで口を出さない上司",
    "仕事の狙いを伝えたら、自分なりの進め方を尊重してくれる上司",
  ] },
  { id: 'owl_pace', persona: 'フクロウタイプ', variants: [
    "静かに考える時間を尊重し、返事を急かさない上司",
    "すぐに答えを求めず、考えを整理する時間をくれる上司",
    "結論を急かさず、自分のペースで考えさせてくれる上司",
  ] },
  { id: 'owl_trust', persona: 'フクロウタイプ', variants: [
    "一度任せた仕事には、必要以上に口を出さない上司",
    "任せると決めたら、途中で細かく介入しすぎない上司",
    "信頼して裁量を任せ、必要なときだけ助言してくれる上司",
  ] },
  { id: 'owl_hint', persona: 'フクロウタイプ', variants: [
    "答えを押しつけず、考える時間とヒントをくれる上司",
    "正解を先に言わず、考える時間とヒントをくれる上司",
    "困ったときも答えを決めつけず、考えるきっかけをくれる上司",
  ] },
  { id: 'owl_focus', persona: 'フクロウタイプ', variants: [
    "集中している時間を尊重し、不要な確認で邪魔をしない上司",
    "深く考える仕事では、静かな時間と裁量を守ってくれる上司",
    "細かな報告を求めすぎず、自分のペースで集中させてくれる上司",
  ] },

  // イルカタイプ — 人と組織をつなぐ力
  { id: 'dolphin_cross_team', persona: 'イルカタイプ', variants: [
    "部署を越えて必要な人をつなぎ、協力を集めてくれる上司",
    "部門の壁を越えて人をつなぎ、連携を後押しする上司",
    "別部署とも橋渡しをして、必要な協力を引き出す上司",
  ] },
  { id: 'dolphin_expert', persona: 'イルカタイプ', variants: [
    "困ったとき、その分野に詳しい専門家を紹介してくれる上司",
    "自分だけで抱えず、詳しい人や専門家につないでくれる上司",
    "課題に合う専門家を見つけ、相談の場をつくってくれる上司",
  ] },
  { id: 'dolphin_bridge', persona: 'イルカタイプ', variants: [
    "チーム同士の橋渡しをして、連携をスムーズにする上司",
    "関係するチームをつなぎ、協力しやすい流れをつくる上司",
    "組織間の橋渡し役になり、連携の詰まりを解消する上司",
  ] },
  { id: 'dolphin_involve', persona: 'イルカタイプ', variants: [
    "立場を越えて周囲を巻き込み、一緒に進めてくれる上司",
    "必要な人を柔軟に巻き込み、チームで前に進める上司",
    "社内外の仲間を巻き込み、協力の輪を広げる上司",
  ] },
  { id: 'dolphin_share', persona: 'イルカタイプ', variants: [
    "情報を抱え込まず、必要な人へ共有して協力を促す上司",
    "必要な情報を開いて共有し、人と人の連携を助ける上司",
    "情報の流れを整え、関係者が協力しやすくする上司",
  ] },

  // 小鳥タイプ — 対話とチームの納得感
  { id: 'bird_listen', persona: '小鳥タイプ', variants: [
    "自分と異なる意見でも、まず話を聞き、対話してくれる上司",
    "反対意見もいったん受け止め、対話から考えてくれる上司",
    "意見が違っても遮らず、最後まで話を聞いてくれる上司",
  ] },
  { id: 'bird_fair', persona: '小鳥タイプ', variants: [
    "チーム全員を公平に扱い、えこひいきをしない上司",
    "立場に関係なく、みんなを公平に尊重してくれる上司",
    "声の大きさに左右されず、全員の意見を公平に扱う上司",
  ] },
  { id: 'bird_consensus', persona: '小鳥タイプ', variants: [
    "みんなの意見を聞き、対話しながら答えをつくる上司",
    "チームで対話を重ね、納得できる答えを一緒につくる上司",
    "一方的に決めず、みんなの意見から結論をまとめる上司",
  ] },
  { id: 'bird_voice', persona: '小鳥タイプ', variants: [
    "会議でチーム全員が話せるよう、発言を促してくれる上司",
    "発言の少ない人にも声をかけ、全員の話を聞く上司",
    "会議で誰も置いていかず、みんなが話せる場をつくる上司",
  ] },
  { id: 'bird_credit', persona: '小鳥タイプ', variants: [
    "チームの成功を自分の手柄にせず、みんなを称える上司",
    "成果を独り占めせず、チーム全員の貢献を称える上司",
    "良い結果が出たとき、関わったみんなに感謝を伝える上司",
  ] },

  // 猫タイプ — 柔軟な働き方と安心感
  { id: 'cat_life', persona: '猫タイプ', variants: [
    "仕事と生活の事情を尊重し、柔軟に対応する上司",
    "家庭や生活の状況を理解し、働き方を柔軟に調整する上司",
    "仕事だけでなく生活も大切にし、無理のない働き方を認める上司",
  ] },
  { id: 'cat_health', persona: '猫タイプ', variants: [
    "体調が悪いときに無理をさせず、安心して休ませてくれる上司",
    "体調を気づかい、無理せず休める安心感をつくる上司",
    "不調のときは仕事より回復を優先し、休ませてくれる上司",
  ] },
  { id: 'cat_remote', persona: '猫タイプ', variants: [
    "家庭の事情に合わせ、リモートなど柔軟な働き方を認める上司",
    "事情に応じてリモートや時間変更を柔軟に選ばせてくれる上司",
    "場所や時間に縛りすぎず、柔軟な働き方を支える上司",
  ] },
  { id: 'cat_support', persona: '猫タイプ', variants: [
    "困ったときは支え、普段は信頼して見守ってくれる上司",
    "必要なときには助け、普段は安心して見守ってくれる上司",
    "いつも干渉せず、普段は見守り、困った瞬間にはそっと支える上司",
  ] },
  { id: 'cat_workload', persona: '猫タイプ', variants: [
    "忙しい時期でも無理な期限を押しつけず、負担を調整する上司",
    "仕事が重なったとき、無理が出ないよう負担を柔軟に見直す上司",
    "無理が続かないよう、業務量と締切を調整してくれる上司",
  ] },

  // 鷹タイプ — 明確な判断と優先順位
  { id: 'hawk_priority', persona: '鷹タイプ', variants: [
    "目標と優先順位を明確に示してくれる上司",
    "何を目指し、何から進めるかを明確にする上司",
    "チームの目標と仕事の優先順位をはっきり示す上司",
  ] },
  { id: 'hawk_decision', persona: '鷹タイプ', variants: [
    "必要なときは素早く決断し、責任を引き受ける上司",
    "迷う場面でも素早く判断し、その決断に責任を持つ上司",
    "重要な局面で方針を決断し、責任を背負ってくれる上司",
  ] },
  { id: 'hawk_meeting', persona: '鷹タイプ', variants: [
    "会議を短く整理し、次にやることを明確にする上司",
    "議論を整理して、会議後の行動を明確に決める上司",
    "会議の結論と次にやる担当を、その場で明確にする上司",
  ] },
  { id: 'hawk_policy', persona: '鷹タイプ', variants: [
    "判断基準が一貫していて、迷わず方針を示す上司",
    "一貫した判断軸を持ち、進む方針を明確に伝える上司",
    "状況が変わっても判断基準を説明し、方針を示す上司",
  ] },
  { id: 'hawk_role', persona: '鷹タイプ', variants: [
    "役割と期限をはっきり決め、成果まで導いてくれる上司",
    "誰がいつまでに何をするかを明確に決める上司",
    "役割・期限・期待する成果を最初にはっきり示す上司",
  ] },

  // クマタイプ — 挑戦と成長を長い目で支える力
  { id: 'bear_failure', persona: 'クマタイプ', variants: [
    "失敗を学びに変え、次の挑戦を応援してくれる上司",
    "失敗を責めるより学びを見つけ、再挑戦を応援する上司",
    "うまくいかなかった経験を成長に変え、次の挑戦を支える上司",
  ] },
  { id: 'bear_feedback', persona: 'クマタイプ', variants: [
    "良かった点と改善点を具体的にフィードバックする上司",
    "成長につながるよう、強みと改善点を具体的に伝える上司",
    "次に活かせるフィードバックを、わかりやすく返してくれる上司",
  ] },
  { id: 'bear_strength', persona: 'クマタイプ', variants: [
    "メンバーの強みを見つけ、成長できる仕事を任せる上司",
    "一人ひとりの強みを伸ばせる仕事と学びの機会をくれる上司",
    "得意なことを見つけ、さらに成長できる役割を任せる上司",
  ] },
  { id: 'bear_challenge', persona: 'クマタイプ', variants: [
    "挑戦したい気持ちを応援し、新しい機会をつくってくれる上司",
    "やってみたい挑戦を後押しし、実践の機会をくれる上司",
    "新しいことへ挑戦できるよう、背中を押してくれる上司",
  ] },
  { id: 'bear_career', persona: 'クマタイプ', variants: [
    "一人ひとりのキャリアを考え、長い目で育ててくれる上司",
    "目先の成果だけでなく、将来のキャリアと成長を支える上司",
    "本人のキャリアを一緒に考え、長期的に育ててくれる上司",
  ] },
];

function shuffledSurveyExamples() {
  const examples = surveyExampleGroups.map((group) => (
    group.variants[Math.floor(Math.random() * group.variants.length)]
  ));
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

function stopRescueResultPolling() {
  window.clearTimeout(state.rescueResultPollHandle);
  state.rescueResultPollHandle = null;
}

function showRescueScoring() {
  state.rescueFinishing = true;
  stopRescueTimer();
  stopRescuePolling();
  setRescueDisabled(true);
  const scoringStatus = document.querySelector("#rescue-scoring-status");
  scoringStatus.textContent = "回答を保存しました。AIがまとめて採点しています";
  scoringStatus.classList.add("pending");
  setMioState("running", "アドバイスをまとめて<br>採点しているよ！");
}

async function pollRescueResult() {
  stopRescueResultPolling();
  if (!state.sessionId || !state.rescueFinishing) return;
  try {
    const result = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}/result`);
    if (result.status === "finished") {
      renderRescueResult(result);
      return;
    }
  } catch (_) {
    // A transient gateway or database error is retried without blocking the UI.
  }
  state.rescueResultPollHandle = window.setTimeout(pollRescueResult, 900);
}

async function pollRescueState() {
  if (!state.sessionId || state.panel !== "rescue" || state.rescueBusy || state.rescueFinishing) return;
  try {
    const current = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}`);
    state.rescueTurn = Math.max(state.rescueTurn, current.turn_no);
    renderRescueState(current);
    if (current.status === "scoring") {
      showRescueScoring();
      pollRescueResult();
      return;
    }
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
  showRescueScoring();
  try {
    const result = await api(`api/mio/sessions/${encodeURIComponent(state.sessionId)}/finish`, { method: "POST" });
    if (result.status === "finished") renderRescueResult(result);
    else pollRescueResult();
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
  stopRescueResultPolling();
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
  stopRescueResultPolling();
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
    if (current.status === "scoring") {
      setPanel("rescue");
      renderRescueState(current);
      showRescueScoring();
      pollRescueResult();
      return;
    }
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
