const KEY = "briefing.apiBase";
const DEFAULT_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function getApiBase() {
  try {
    return localStorage.getItem(KEY) || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}

export function saveApiBase(base) {
  try {
    localStorage.setItem(KEY, base);
  } catch {
    /* 저장 불가 환경은 이번 세션만 사용 */
  }
}

export function normalizeBase(input) {
  let s = input.trim().replace(/\/+$/, "");
  if (s && !/^https?:\/\//i.test(s)) s = "http://" + s;
  return s;
}

async function request(base, path, { method = "GET", timeout = 8000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  try {
    const res = await fetch(base + path, { method, signal: ctrl.signal });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new Error(body?.error || `HTTP ${res.status}`);
    return body;
  } catch (e) {
    if (e.name === "AbortError") throw new Error(`응답 없음 (${timeout / 1000}초 초과)`);
    if (e instanceof TypeError) throw new Error("연결 실패: 주소, 서버 실행 여부, CORS를 확인하세요");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export async function testConnection(base) {
  const t0 = performance.now();
  const body = await request(base, "/api/health", { timeout: 5000 });
  if (body?.status !== "ok") throw new Error("브리핑 BE가 아닙니다 (/api/health 응답 이상)");
  return { ...body, ms: Math.round(performance.now() - t0) };
}

export const fetchCards = (base) => request(base, "/api/cards", { timeout: 20000 });
export const fetchMeta = (base) => request(base, "/api/meta");
export const rebuild = (base) => request(base, "/api/rebuild", { method: "POST", timeout: 60000 });
