import { useState } from "react";
import { DISPATCH, LEVEL } from "../constants";

function Diagnosis({ d }) {
  const cause = d.primary.length ? d.primary.join(" / ") : "—";
  const meta = [];
  if (d.level === "L1") meta.push(`같은 증상 ${d.same_symptom_count}건`, `재발률 ${Math.round(d.recur_rate * 100)}%`, `신뢰도 ${d.confidence}`);
  if (d.level === "L2") meta.push(`전체 기록 중 ${Math.round(d.share * 100)}%`);
  if (d.natural_recovery) meta.push(`자연복구 이력 ${d.natural_recovery}건`);
  return (
    <div className="diag">
      <div className="row">
        <span className={`badge b-${d.level}`}>{LEVEL[d.level]}</span>
        <span className="muted">{d.group}</span>
      </div>
      <div className="cause">{d.level === "L2" && "(추정) "}{cause}</div>
      <div className="muted">{meta.join(" · ")}</div>
      <div className="muted">근거: {d.basis}</div>
      {d.candidates.length > 0 && (
        <div className="muted">후보: {d.candidates.map(([c, n]) => `${c} ${n}건`).join(", ")}</div>
      )}
      {d.records.length > 0 && (
        <div className="scroll">
          <table className="tbl">
            <thead><tr><th>조치일</th><th>실제원인</th><th>조치내용</th><th>재발</th><th>작업자</th></tr></thead>
            <tbody>
              {d.records.map((r, i) => (
                <tr key={i}>
                  <td>{r.recent && "🔺"}{r.date}</td><td>{r.cause}</td><td>{r.action}</td><td>{r.recur}</td><td>{r.worker}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Equipment({ s }) {
  if (s.equipment.length)
    return s.equipment.map((e) => (
      <div key={e.serial}>
        <div className="muted">{e.serial} · {e.model} · FW {e.firmware}</div>
        <div className="chips">
          {e.signals.map((x) => <span key={x} className="chip">{x}</span>)}
          <span className="muted">{e.signals.length ? "추정 보강" : "신호 없음"}</span>
        </div>
      </div>
    ));
  if (s.equipment_ref.length)
    return <div className="muted">같은 장비구분 기록 없음 · 참고: {s.equipment_ref.map((e) => `${e.equip_type} ${e.model}`).join(", ")}</div>;
  return <div className="muted">장비 기록 없음</div>;
}

function Section({ s }) {
  return (
    <div className="section">
      <h3>
        {s.equip_type}
        <span className={`badge b-${s.dispatch.class}`}>{DISPATCH[s.dispatch.class].label}</span>
        <span className="muted">{s.dispatch.reason}</span>
      </h3>
      <div className="scroll">
        <table className="tbl">
          <thead><tr><th>알람</th><th>등급</th><th>발생~해제</th><th>상태</th></tr></thead>
          <tbody>
            {s.alarms.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td><td>{a.grade}</td><td>{a.start}~{a.end}</td>
                <td>{a.status === "미해제" ? "🔴 미해제" : "해제"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="lbl">원인 판단</div>
      {s.diagnoses.map((d) => <Diagnosis key={d.group} d={d} />)}
      <div className="lbl">장비</div>
      <Equipment s={s} />
      <div className="lbl">챙길 자재</div>
      {s.materials.length ? (
        <div className="chips">
          {s.materials.map((m) => <span key={m.item} className="chip">{m.item}{m.estimated && " (추정)"}</span>)}
        </div>
      ) : (
        <div className="muted">별도 자재 없음</div>
      )}
      {s.past_actions?.length > 0 && <div className="muted">과거 조치: {s.past_actions.join(", ")}</div>}
    </div>
  );
}

export default function Card({ c }) {
  const [open, setOpen] = useState(false);
  const d0 = c.sections[0].diagnoses[0];
  const cause = d0.primary.length ? d0.primary.join(" / ") : "원인 판단 불가";
  return (
    <div className={`card ${c.dispatch.class} ${open ? "open" : ""}`}>
      <div className="head" onClick={() => setOpen(!open)}>
        <div className="row">
          <span className={`badge b-${c.dispatch.class}`}>{DISPATCH[c.dispatch.class].label}</span>
          <span className="muted">{c.dispatch.reason}</span>
        </div>
        <div className="row">
          <span className="title">{c.site.name}</span>
          <span className="muted">{c.site.id} · {c.site.branch}</span>
          {c.site.high_work && <span title="고소작업">⚠️ 고소</span>}
        </div>
        <div className="row">
          <span className="badge b-grade">{c.summary.top_grade}</span>
          <span>{c.summary.top_alarm}</span>
          <span className="muted">
            알람 {c.summary.alarm_count}건{c.summary.unresolved ? ` · 미해제 ${c.summary.unresolved}` : ""} · 장비 {c.sections.length}종
          </span>
        </div>
        <div className="row">
          <span className={`badge b-${d0.level}`}>{LEVEL[d0.level]}</span>
          <span>{d0.level === "L2" && "(추정) "}{cause}</span>
        </div>
      </div>
      {open && (
        <div className="body">
          <div className="caution">{c.cautions.map((x) => <div key={x}>{x}</div>)}</div>
          <div className="contact muted">
            {c.site.address} · 설치형태 {c.site.install_type} · 담당 {c.site.manager}{" "}
            <a href={`tel:${c.site.phone}`}>{c.site.phone}</a>
          </div>
          {c.sections.map((s) => <Section key={s.equip_type} s={s} />)}
        </div>
      )}
    </div>
  );
}
