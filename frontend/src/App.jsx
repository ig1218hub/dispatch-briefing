import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchCards, fetchMeta, getApiBase, saveApiBase } from "./api";
import { DISPATCH, GRADE, LEVEL } from "./constants";
import BackendSettings from "./components/BackendSettings";
import Card from "./components/Card";

const PAGE = 50;

export default function App() {
  const [base, setBase] = useState(getApiBase);
  const [status, setStatus] = useState({ state: "busy", msg: "" });
  const [cards, setCards] = useState([]);
  const [meta, setMeta] = useState(null);
  const [f, setF] = useState({ dispatch: "", q: "", branch: "", grade: "", level: "" });
  const [limit, setLimit] = useState(PAGE);

  const load = useCallback(async (url) => {
    setStatus({ state: "busy", msg: "" });
    try {
      const [c, m] = await Promise.all([fetchCards(url), fetchMeta(url)]);
      setCards(c);
      setMeta(m);
      setStatus({ state: "ok", msg: "" });
    } catch (e) {
      setCards([]);
      setMeta(null);
      setStatus({ state: "fail", msg: e.message });
    }
  }, []);

  useEffect(() => { load(base); }, [base, load]);

  function apply(url) {
    saveApiBase(url);
    if (url === base) load(url);
    else setBase(url);
  }

  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setLimit(PAGE); };

  const branches = useMemo(() => [...new Set(cards.map((c) => c.site.branch))].sort(), [cards]);
  const counts = useMemo(() => {
    const d = { now: 0, remote: 0, later: 0 }, l = { L1: 0, L2: 0, L3: 0 };
    cards.forEach((c) => {
      d[c.dispatch.class]++;
      c.sections.forEach((s) => s.diagnoses.forEach((x) => l[x.level]++));
    });
    return { d, l };
  }, [cards]);

  const list = useMemo(() => {
    const q = f.q.trim().toLowerCase();
    return cards
      .filter((c) =>
        (!f.dispatch || c.dispatch.class === f.dispatch) &&
        (!f.branch || c.site.branch === f.branch) &&
        (!f.grade || c.summary.top_grade === f.grade) &&
        (!f.level || c.sections.some((s) => s.diagnoses.some((d) => d.level === f.level))) &&
        (!q || [c.site.id, c.site.name, ...c.sections.flatMap((s) => s.alarms.map((a) => a.name))].join(" ").toLowerCase().includes(q)))
      .sort((a, b) =>
        DISPATCH[a.dispatch.class].order - DISPATCH[b.dispatch.class].order ||
        GRADE[a.summary.top_grade] - GRADE[b.summary.top_grade] ||
        b.summary.unresolved - a.summary.unresolved ||
        b.summary.alarm_count - a.summary.alarm_count);
  }, [cards, f]);

  return (
    <div className="wrap">
      <header>
        <h1>출동 전 브리핑</h1>
        <p>{meta ? `기준일 ${meta.base_date} · 알람 ${meta.alarm_count}건 · 기지국 ${meta.site_count}곳 · 빌드 ${meta.built_at}` : "BE 연결 대기"}</p>
      </header>

      <BackendSettings key={base} base={base} status={status} onApply={apply} onReload={() => load(base)} />

      {status.state === "busy" && <div className="empty">불러오는 중…</div>}
      {status.state === "fail" && <div className="empty">⚠️ BE에서 데이터를 가져오지 못했습니다. 위에서 BE 주소를 확인하세요.</div>}

      {status.state === "ok" && (
        <>
          <div className="kpis">
            {Object.entries(DISPATCH).map(([k, v]) => (
              <div key={k} className={`kpi ${k} ${f.dispatch === k ? "active" : ""}`}
                   onClick={() => { setF({ ...f, dispatch: f.dispatch === k ? "" : k }); setLimit(PAGE); }}>
                <b>{counts.d[k]}</b><span>{v.label}</span>
              </div>
            ))}
          </div>
          <div className="sub">
            {Object.entries(counts.l).map(([k, n]) => <span key={k} className={`badge b-${k}`}>{LEVEL[k]} {n}</span>)}
          </div>

          <details className="top10">
            <summary>🔁 반복 장애 Top 10</summary>
            <table className="tbl">
              <thead><tr><th>#</th><th>기지국</th><th>조치이력</th><th>재발 Y</th><th>같은 증상 최다</th></tr></thead>
              <tbody>
                {meta.top10.length === 0 && <tr><td colSpan={5} className="muted">데이터 없음 (원본 파일로 다시 생성 필요)</td></tr>}
                {meta.top10.map((r, i) => (
                  <tr key={r.id}><td>{i + 1}</td><td>{r.id} {r.name}</td><td>{r.total}</td><td>{r.recur}</td><td>{r.max_same}</td></tr>
                ))}
              </tbody>
            </table>
          </details>

          <div className="filters">
            <input value={f.q} onChange={set("q")} placeholder="기지국ID·기지국명·알람명 검색" />
            <select value={f.branch} onChange={set("branch")}>
              <option value="">전체 지사</option>
              {branches.map((b) => <option key={b}>{b}</option>)}
            </select>
            <select value={f.grade} onChange={set("grade")}>
              <option value="">전체 등급</option>
              {Object.keys(GRADE).map((g) => <option key={g}>{g}</option>)}
            </select>
            <select value={f.level} onChange={set("level")}>
              <option value="">전체 근거</option>
              <option value="L1">근거</option><option value="L2">추정</option><option value="L3">이력 없음</option>
            </select>
          </div>

          <div className="muted" style={{ marginBottom: 8 }}>{list.length}장</div>
          {list.length === 0 && <div className="empty">조건에 맞는 카드가 없습니다</div>}
          {list.slice(0, limit).map((c) => <Card key={c.card_id} c={c} />)}
          {list.length > limit && (
            <button className="btn" style={{ width: "100%" }} onClick={() => setLimit(limit + PAGE)}>
              더 보기 ({list.length - limit}장 남음)
            </button>
          )}
        </>
      )}
    </div>
  );
}
