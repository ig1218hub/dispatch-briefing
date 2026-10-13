import { useState } from "react";
import { normalizeBase, testConnection, rebuild } from "../api";

export default function BackendSettings({ base, status, onApply, onReload }) {
  const [input, setInput] = useState(base);
  const [test, setTest] = useState({ state: "idle", msg: "" });

  async function runTest() {
    const url = normalizeBase(input);
    setInput(url);
    setTest({ state: "busy", msg: "테스트 중…" });
    try {
      const r = await testConnection(url);
      setTest({ state: "ok", msg: `✅ 연결 성공 · ${r.ms}ms · 카드 ${r.cards}장 · 빌드 ${r.built_at} · v${r.version}${r.warning ? `\n⚠️ ${r.warning}` : ""}` });
      return url;
    } catch (e) {
      setTest({ state: "fail", msg: `❌ ${e.message}` });
      return null;
    }
  }

  async function apply() {
    const url = await runTest();
    if (url) onApply(url);
  }

  async function runRebuild() {
    setTest({ state: "busy", msg: "데이터 다시 생성 중…" });
    try {
      const r = await rebuild(base);
      setTest({ state: "ok", msg: `✅ 재생성 완료 · 카드 ${r.cards}장 · ${r.built_at}` });
      onReload();
    } catch (e) {
      setTest({ state: "fail", msg: `❌ 재생성 실패: ${e.message}` });
    }
  }

  return (
    <details className="be" open={status.state !== "ok"}>
      <summary>
        <span className={`dot ${status.state}`} /> BE 연결 <span className="muted">{base}</span>
      </summary>
      <div className="be-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && apply()}
          placeholder="http://localhost:8000 또는 https://xxxx.trycloudflare.com"
          aria-label="BE 주소"
        />
        <button className="btn" onClick={runTest} disabled={test.state === "busy"}>테스트</button>
        <button className="btn primary" onClick={apply} disabled={test.state === "busy"}>적용</button>
      </div>
      {test.msg && <div className={`msg ${test.state}`}>{test.msg}</div>}
      {status.state === "fail" && <div className="msg fail">현재 주소 오류: {status.msg}</div>}
      <div className="be-row">
        <button className="btn" onClick={onReload} disabled={test.state === "busy"}>새로고침</button>
        <button className="btn" onClick={runRebuild} disabled={test.state === "busy" || status.state !== "ok"}>
          데이터 다시 생성
        </button>
      </div>
    </details>
  );
}
