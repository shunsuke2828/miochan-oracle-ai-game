import http from "k6/http";
import { check, sleep } from "k6";
import exec from "k6/execution";
import { Counter, Rate } from "k6/metrics";

const BASE_URL = (__ENV.BASE_URL || "").replace(/\/$/, "");
const RUN_ID = __ENV.RUN_ID || "manual";
const RUN_PREFIX = __ENV.RUN_PREFIX || `LT${RUN_ID.slice(-6)}`;
const VUS = Number(__ENV.VUS || 150);
const GAME_START_EPOCH_MS = Number(__ENV.GAME_START_EPOCH_MS || Date.now() + 300000);
const HOLD_UNTIL_EPOCH_MS = Number(
  __ENV.HOLD_UNTIL_EPOCH_MS || GAME_START_EPOCH_MS + 300000,
);
const STAGGER = (__ENV.STAGGER || "true") === "true";

const apiFailures = new Rate("mio_api_failures");
const gateway429s = new Counter("mio_gateway_429s");
const completedJourneys = new Counter("mio_completed_journeys");
const createdSessions = new Counter("mio_created_sessions");

export const options = {
  scenarios: {
    attendees: {
      executor: "per-vu-iterations",
      vus: VUS,
      iterations: 1,
      maxDuration: "15m",
      gracefulStop: "10s",
    },
  },
  thresholds: {
    checks: [{ threshold: "rate>0.99", abortOnFail: true, delayAbortEval: "30s" }],
    mio_api_failures: [
      { threshold: "rate<0.02", abortOnFail: true, delayAbortEval: "30s" },
    ],
    mio_gateway_429s: ["count==0"],
    "http_req_duration{endpoint:state}": ["p(95)<1000"],
    "http_req_duration{endpoint:turn}": ["p(95)<1000"],
    "http_req_duration{endpoint:create_session}": ["p(95)<2000"],
    "http_req_duration{endpoint:survey}": ["p(95)<10000"],
    "http_req_duration{endpoint:finish}": ["p(95)<2000"],
    "http_req_duration{endpoint:result}": ["p(95)<1000"],
  },
};

const surveyAnswers = [
  "意見をまず受け止め、目的を共有した上で挑戦を任せてくれる上司",
  "失敗を責めるより状況を一緒に整理し、次の行動を考えてくれる上司",
  "期待する成果を明確に伝え、進め方には適度な裁量をくれる上司",
  "困ったときに相談しやすく、優先順位を一緒に整えてくれる上司",
  "良かった点と改善点を具体的に伝え、成長を応援してくれる上司",
  "異なる意見も歓迎し、安心して発言できる雰囲気をつくる上司",
  "メンバーの強みを見つけ、少し難しい仕事へ背中を押してくれる上司",
  "忙しいときほど声をかけ、仕事量や期限を現実的に調整する上司",
  "結論だけでなく背景や判断理由も共有し、納得して動ける上司",
  "成果をきちんと認め、チームで喜びを分かち合ってくれる上司",
];

const freeTextAnswers = [
  "不安になるのは自然だよ。まず伝えたいことを三つに整理して、一緒に確認しよう。",
  "教えてくれてありがとう。何が起きたかを整理して、影響の大きいものから対応しよう。",
  "違和感に気づいてくれて助かるよ。理由とリスクを一緒に確認して方針を決めよう。",
  "抱えている仕事を全部並べて、今日やるものと後回しにするものを一緒に決めよう。",
  "頑張った点は伝わっているよ。期待との差を確認して、次に直すことを一つ決めよう。",
];

function endpointParams(endpoint) {
  return {
    headers: { "Content-Type": "application/json" },
    tags: { endpoint },
    timeout: endpoint === "finish" ? "30s" : endpoint === "survey" ? "20s" : "10s",
  };
}

function parsed(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

function recordResponse(response, label, expected = [200]) {
  const ok = expected.includes(response.status);
  apiFailures.add(!ok, { endpoint: label });
  if (response.status === 429) gateway429s.add(1);
  check(response, { [`${label} returned ${expected.join("/")}`]: () => ok });
  return ok;
}

function waitUntil(epochMs) {
  const remaining = epochMs - Date.now();
  if (remaining > 0) sleep(remaining / 1000);
}

function preparationDelay(vuId) {
  if (!STAGGER) return Math.random() * 2;
  if (vuId <= 25) return Math.random() * 30;
  if (vuId <= 75) return 120 + Math.random() * 40;
  return 180 + Math.random() * 45;
}

function compactNickname(vuId) {
  const suffix = String(vuId).padStart(3, "0");
  return `${RUN_PREFIX.slice(0, 12)}${suffix}`.slice(0, 16);
}

function loadVisitorAssets() {
  const requests = [
    ["GET", `${BASE_URL}/`, null, { tags: { endpoint: "page" }, timeout: "10s" }],
    ["GET", `${BASE_URL}/static/app.js`, null, { tags: { endpoint: "asset" }, timeout: "10s" }],
    ["GET", `${BASE_URL}/static/styles.css`, null, { tags: { endpoint: "asset" }, timeout: "10s" }],
    ["GET", `${BASE_URL}/assets/miochan/idle.gif`, null, { tags: { endpoint: "asset" }, timeout: "10s" }],
  ];
  for (const response of http.batch(requests)) recordResponse(response, "asset", [200, 304]);
}

function createParticipant(nickname, vuId) {
  const response = http.post(
    `${BASE_URL}/api/sessions`,
    JSON.stringify({ nickname, public_consent: false, ranking_consent: false }),
    endpointParams("create_session"),
  );
  if (!recordResponse(response, "create_session")) return null;
  const body = parsed(response);
  if (!body || !body.session_id) return null;
  createdSessions.add(1);
  console.log(`__MIO_SESSION__ ${RUN_ID} ${vuId} ${body.session_id} ${nickname}`);
  return body.session_id;
}

function submitSurvey(sessionId, vuId) {
  const answer = surveyAnswers[(vuId - 1) % surveyAnswers.length];
  const response = http.post(
    `${BASE_URL}/api/survey`,
    JSON.stringify({ session_id: sessionId, answer }),
    endpointParams("survey"),
  );
  return recordResponse(response, "survey");
}

function startGame(sessionId, nickname) {
  const response = http.post(
    `${BASE_URL}/api/mio/sessions`,
    JSON.stringify({
      session_id: sessionId,
      nickname,
      consent: true,
      public_consent: false,
      ranking_consent: false,
    }),
    endpointParams("game_start"),
  );
  if (!recordResponse(response, "game_start")) return null;
  return parsed(response);
}

function pollState(sessionId) {
  const response = http.get(
    `${BASE_URL}/api/mio/sessions/${encodeURIComponent(sessionId)}`,
    endpointParams("state"),
  );
  if (!recordResponse(response, "state")) return null;
  return parsed(response);
}

function submitTurn(sessionId, game, vuId, turnIndex) {
  const useFreeText = (vuId + turnIndex) % 5 === 0;
  const choices = Array.isArray(game.choices) ? game.choices : [];
  const answerType = useFreeText || choices.length === 0 ? "free_text" : "choice";
  const answer = answerType === "free_text"
    ? freeTextAnswers[(vuId + turnIndex) % freeTextAnswers.length]
    : choices[(vuId + turnIndex) % choices.length];
  const response = http.post(
    `${BASE_URL}/api/mio/sessions/${encodeURIComponent(sessionId)}/turns`,
    JSON.stringify({
      turn_no: Number(game.turn_no),
      answer_type: answerType,
      user_answer: answer,
    }),
    endpointParams("turn"),
  );
  if (!recordResponse(response, "turn")) return null;
  return parsed(response);
}

function finishGame(sessionId) {
  const response = http.post(
    `${BASE_URL}/api/mio/sessions/${encodeURIComponent(sessionId)}/finish`,
    null,
    endpointParams("finish"),
  );
  if (!recordResponse(response, "finish", [200, 202])) return null;
  return parsed(response);
}

function fetchResult(sessionId) {
  const response = http.get(
    `${BASE_URL}/api/mio/sessions/${encodeURIComponent(sessionId)}/result`,
    endpointParams("result"),
  );
  if (!recordResponse(response, "result", [200, 202])) return null;
  return parsed(response);
}

function waitForFinalResult(sessionId, initial) {
  let result = initial;
  const timeoutAt = Date.now() + 180000;
  let nextPollAt = Date.now();
  while (Date.now() < timeoutAt) {
    if (result && result.status === "finished") return result;
    waitUntil(nextPollAt);
    result = fetchResult(sessionId) || result;
    nextPollAt += 1000;
    if (nextPollAt < Date.now()) nextPollAt = Date.now();
  }
  return result;
}

function playGame(sessionId, initial, vuId) {
  let game = initial;
  let finished = Boolean(game.game_finished);
  let turnIndex = 0;
  let nextAnswerAt = Date.now() + 7000 + Math.random() * 2000;
  let nextPollAt = Date.now();
  const deadline = new Date(game.deadline_at).getTime();

  while (!finished && Date.now() < deadline) {
    waitUntil(nextPollAt);
    game = pollState(sessionId) || game;
    nextPollAt += 1000;
    if (nextPollAt < Date.now()) nextPollAt = Date.now();
    finished = Boolean(game.game_finished);
    if (finished) break;

    if (Date.now() >= nextAnswerAt && Number(game.turn_no) > 0) {
      turnIndex += 1;
      game = submitTurn(sessionId, game, vuId, turnIndex) || game;
      finished = Boolean(game.game_finished);
      nextAnswerAt = Date.now() + 7000 + Math.random() * 2000;
    }
  }

  if (!finished) {
    waitUntil(deadline + 1200);
    game = finishGame(sessionId) || game;
  }
  waitForFinalResult(sessionId, game);
}

function sustainReadLoad(sessionId) {
  let nextPollAt = Date.now();
  while (Date.now() < HOLD_UNTIL_EPOCH_MS) {
    waitUntil(nextPollAt);
    pollState(sessionId);
    nextPollAt += 1000;
    if (nextPollAt < Date.now()) nextPollAt = Date.now();
  }
}

export default function () {
  if (!BASE_URL) exec.test.abort("BASE_URL is required");
  const vuId = exec.vu.idInTest;
  sleep(preparationDelay(vuId));
  loadVisitorAssets();

  const nickname = compactNickname(vuId);
  const sessionId = createParticipant(nickname, vuId);
  if (!sessionId) return;
  if (!submitSurvey(sessionId, vuId)) return;

  waitUntil(GAME_START_EPOCH_MS);
  const game = startGame(sessionId, nickname);
  if (!game) return;
  playGame(sessionId, game, vuId);
  sustainReadLoad(sessionId);
  completedJourneys.add(1);
}
