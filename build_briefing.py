"""출동 전 브리핑 카드 생성기 (SPEC.md v0.2).

실행: python build_briefing.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
CONFIG = ROOT / "config"
OUTPUT = ROOT / "output"

GRADE_ORDER = {"Critical": 0, "Major": 1, "Minor": 2, "Warning": 3}
DISPATCH_ORDER = {"now": 0, "remote": 1, "later": 2}
DISPATCH_LABEL = {"now": "🔴 지금 바로 출동", "remote": "🟡 원격 조치 먼저", "later": "🟢 다음 정기점검"}
LEVEL_LABEL = {"L1": "근거", "L2": "추정(전체 통계)", "L3": "이력 없음"}
NATURAL = "원인 미상(자연복구)"


# ---------- 로드 (§3) ----------

def load_config():
    def read(name):
        return json.loads((CONFIG / name).read_text(encoding="utf-8"))
    return {
        "groups": read("symptom_groups.json"),
        "materials": read("materials.json"),
        "th": read("thresholds.json"),
    }


def load_data():
    alarms = pd.read_csv(ROOT / "alarm_log_20261008.csv", encoding="utf-8-sig")
    sites = pd.read_excel(ROOT / "site_master.xlsx")
    equip = pd.read_excel(ROOT / "장비이력.xlsx")
    hist = pd.read_excel(ROOT / "조치이력.xlsx")
    for df in (alarms, sites, equip, hist):
        df["기지국ID"] = df["기지국ID"].astype(str).str.strip()
    return alarms, sites, equip, hist


# ---------- 연결 (§4) ----------

def build_group_map(groups):
    """알람명 → 증상그룹 (§4.2)."""
    return {name: g for g, v in groups.items() for name in v["alarms"]}


def normalize(alarms, hist, equip, cfg):
    """증상그룹 부여, 날짜 변환, 기준일 이전 기록만 남김 (§4.3, §4.5)."""
    gmap = build_group_map(cfg["groups"])
    base = pd.Timestamp(cfg["th"]["base_date"])
    alarms = alarms.copy()
    hist = hist.copy()
    equip = equip.copy()
    alarms["group"] = alarms["알람명"].map(gmap).fillna(alarms["알람명"])
    hist["group"] = hist["증상"].map(gmap).fillna(hist["증상"])
    unmapped = sorted(set(alarms.loc[~alarms["알람명"].isin(gmap), "알람명"])
                      | set(hist.loc[~hist["증상"].isin(gmap), "증상"]))
    hist["조치일"] = pd.to_datetime(hist["조치일"])
    hist = hist[hist["조치일"] < base].reset_index(drop=True)
    for col in ("설치일", "최근교체일"):
        equip[col] = pd.to_datetime(equip[col])
    return alarms, hist, equip, unmapped


def write_join_report(alarms, sites, equip, hist, unmapped):
    """output/join_report.md (§4.5)."""
    a_sites = sorted(set(alarms["기지국ID"]))
    n = len(a_sites)
    no_master = [s for s in a_sites if s not in set(sites["기지국ID"])]
    no_equip = [s for s in a_sites if s not in set(equip["기지국ID"])]
    no_hist = [s for s in a_sites if s not in set(hist["기지국ID"])]
    pairs = alarms[["기지국ID", "장비구분"]].drop_duplicates()
    eq_pairs = set(map(tuple, equip[["기지국ID", "장비구분"]].values))
    pair_hit = sum(tuple(p) in eq_pairs for p in pairs.values)

    def pct(k):
        return f"{k}/{n} ({k / n:.0%})"

    lines = [
        "# 연결 결과 리포트", "",
        f"- 알람 {len(alarms)}건 · 기지국 {n}곳 · 섹션(기지국+장비구분) {len(pairs)}개",
        f"- 조치이력(기준일 이전) {len(hist)}건", "",
        "| 연결 | 결과 |", "|---|---|",
        f"| 알람 ↔ site_master | {pct(n - len(no_master))} |",
        f"| 알람 ↔ 장비이력 (기지국) | {pct(n - len(no_equip))} |",
        f"| 알람 ↔ 장비이력 (기지국+장비구분) | {pair_hit}/{len(pairs)} ({pair_hit / len(pairs):.0%}) |",
        f"| 알람 ↔ 조치이력 (기지국) | {pct(n - len(no_hist))} |",
        f"| 증상그룹 미매핑 알람명 | {len(unmapped)}건 {'✅' if not unmapped else '⚠️'} |", "",
    ]
    for title, items in (("site_master에 없는 기지국", no_master), ("장비 기록 없는 기지국", no_equip),
                         ("조치이력 없는 기지국", no_hist), ("미매핑 알람명", unmapped)):
        lines += [f"## {title} ({len(items)})", "", ", ".join(items) if items else "없음", ""]
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "join_report.md").write_text("\n".join(lines), encoding="utf-8")


# ---------- 판단 (§5 ~ §8) ----------

def _top_causes(df):
    """최다 원인(동률 모두), 비율, 후보 2~3위."""
    counts = df["실제원인"].value_counts()
    top = int(counts.iloc[0])
    primary = [c for c, k in counts.items() if k == top]
    candidates = [[c, int(k)] for c, k in counts.items() if k < top][:2]
    return primary, top / len(df), candidates


def diagnose(site_id, group, hist, cfg):
    """증상그룹 하나의 원인 판단: L1 / L2 / L3 (§5)."""
    th = cfg["th"]
    base = pd.Timestamp(th["base_date"])
    recs = hist[(hist["기지국ID"] == site_id) & (hist["group"] == group)].sort_values("조치일", ascending=False)
    natural = int((recs["실제원인"] == NATURAL).sum())
    valid = recs[recs["실제원인"] != NATURAL]
    records = [{
        "date": r["조치일"].strftime("%Y-%m-%d"),
        "recent": bool((base - r["조치일"]).days <= th["recent_days"]),
        "cause": r["실제원인"], "action": r["조치내용"], "recur": r["재발여부"], "worker": r["작업자"],
    } for _, r in recs.iterrows()]
    d = {"group": group, "same_symptom_count": len(recs), "natural_recovery": natural, "records": records,
         "recur_rate": round(float((recs["재발여부"] == "Y").mean()), 2) if len(recs) else None,
         "has_recur": bool((recs["재발여부"] == "Y").any()),
         "primary": [], "share": None, "confidence": None, "candidates": []}
    if len(valid):
        primary, share, cands = _top_causes(valid)
        high = len(valid) >= th["l1_high_min_count"] and share >= th["l1_high_min_share"] and len(primary) == 1
        d.update(level="L1", primary=primary, share=round(share, 2), candidates=cands,
                 confidence="높음" if high else "보통",
                 basis="조치이력 " + ", ".join(sorted(valid["조치일"].dt.strftime("%Y-%m-%d"))))
    else:
        pool = hist[(hist["group"] == group) & (hist["실제원인"] != NATURAL)]
        if len(pool):
            primary, share, cands = _top_causes(pool)
            d.update(level="L2", primary=primary, share=round(share, 2), candidates=cands,
                     basis=f"전체 조치이력 같은 증상 {len(pool)}건 통계")
        else:
            d.update(level="L3", basis="같은 증상 기록 없음")
    d["label"] = LEVEL_LABEL[d["level"]]
    return d


def equipment_signals(equip_rows, cfg):
    """장비 신호: 고장 다발 / 최근 변경 / 미조치 / 노후 (§5.1)."""
    th = cfg["th"]
    base = pd.Timestamp(th["base_date"])
    out = []
    for _, e in equip_rows.iterrows():
        note = "" if pd.isna(e["비고"]) else str(e["비고"])
        ref = e["최근교체일"] if pd.notna(e["최근교체일"]) else e["설치일"]
        age = int((base - ref).days // 365.25) if pd.notna(ref) else None
        signals = []
        if e["누적고장횟수"] >= th["fault_many"]:
            signals.append(f"📈 누적고장 {int(e['누적고장횟수'])}회")
        if "펌웨어 업그레이드" in note:
            signals.append(f"🔧 {note}")
        if pd.notna(e["최근교체일"]) and (base - e["최근교체일"]).days <= th["recent_change_days"]:
            signals.append(f"🔧 {(base - e['최근교체일']).days}일 전 교체")
        if "미교체" in note:
            signals.append(f"⚠️ {note}")
        if age is not None and age >= th["old_years"]:
            signals.append(f"🕰️ 설치 {age}년차")
        out.append({"serial": e["장비시리얼"], "equip_type": e["장비구분"], "maker": e["제조사"],
                    "model": e["모델"], "firmware": str(e["펌웨어"]),
                    "installed": e["설치일"].strftime("%Y-%m-%d") if pd.notna(e["설치일"]) else None,
                    "replaced": e["최근교체일"].strftime("%Y-%m-%d") if pd.notna(e["최근교체일"]) else None,
                    "age_years": age, "fault_count": int(e["누적고장횟수"]), "note": note, "signals": signals})
    return out


def materials_for(diagnoses, cfg):
    """원인 → 자재, L2는 (추정) 표시 (§6)."""
    table = cfg["materials"]["materials"]
    items = {}
    for d in diagnoses:
        if d["level"] == "L3":
            continue
        for cause in d["primary"]:
            for m in table.get(cause, []):
                est = d["level"] == "L2"
                items[m] = items.get(m, True) and est  # 근거 있는 쪽이 하나라도 있으면 추정 아님
    return [{"item": k, "estimated": v} for k, v in items.items()]


def cautions_for(site, sections, diagnoses):
    """주의사항 (§7)."""
    out = []
    if site["high_work"]:
        out.append("⚠️ 고소작업: 안전대·2인 1조, 강풍·우천 시 작업 중지")
    t = site["install_type"]
    if t in ("철탑", "폴"):
        out.append("승주 장비 지참")
    elif t == "옥탑":
        out.append(f"건물 출입 사전 연락 (담당 {site['manager']} {site['phone']})")
    elif t == "실내":
        out.append("출입 승인 확인")
    causes = {c for d in diagnoses for c in d["primary"]}
    if any(s["equip_type"] == "정류기" for s in sections) or causes & {"차단기 트립", "한전 일시 정전"}:
        out.append("⚡ 전기 작업: 절연 장비 지참")
    if any(d["level"] == "L1" and (d["recur_rate"] or 0) >= 0.5 for d in diagnoses):
        out.append("🔁 재발 이력: 근본 원인 확인 필요")
    return out


def cause_class(cause, cfg):
    for k, v in cfg["materials"]["cause_class"].items():
        if cause in v:
            return k
    return "UNKNOWN"


def classify_section(section, cfg):
    """섹션 분류 + 하루 반복 가중 (§8.2, §8.3)."""
    alarms, diags = section["alarms"], section["diagnoses"]
    unres = [a for a in alarms if a["status"] == "미해제"]
    unres_grades = {a["grade"] for a in unres}
    cls = {(d["group"], cause_class(c, cfg)) for d in diags for c in (d["primary"] or [None])}
    classes = {c for _, c in cls}
    hw_recur = any(cause_class(c, cfg) == "HW" and d["has_recur"] and d["level"] == "L1"
                   for d in diags for c in d["primary"])
    grades = {a["grade"] for a in alarms}

    if unres_grades & {"Critical", "Major"}:
        k, why = "now", f"미해제 {min(unres_grades & {'Critical', 'Major'}, key=GRADE_ORDER.get)}"
    elif hw_recur:
        k, why = "now", "HW 원인 + 재발 이력"
    elif "EXTERNAL" in classes and unres:
        k, why = "now", "미해제 + 협력사 조치 원인"
    elif "REMOTE" in classes:
        k, why = "remote", "원격 확인 가능 원인"
    elif unres:
        k, why = "remote", f"미해제 {min(unres_grades, key=GRADE_ORDER.get)}"
    elif "Critical" in grades:
        k, why = "remote", "해제 Critical"
    else:
        k, why = "later", f"해제 {min(grades, key=GRADE_ORDER.get)}"

    counts = pd.Series([a["group"] for a in alarms]).value_counts()
    if counts.iloc[0] >= cfg["th"]["same_day_repeat"] and k != "now":
        k = "now" if k == "remote" else "remote"
        why += f" · 오늘 {int(counts.iloc[0])}회 반복 ↑"
    return {"class": k, "reason": why}


def _alarm_rows(df):
    def hm(v):
        return "—" if pd.isna(v) else str(v)[11:16]
    return [{"id": r["알람ID"], "name": r["알람명"], "group": r["group"], "grade": r["등급"],
             "start": hm(r["발생시각"]), "end": hm(r["해제시각"]), "status": r["상태"]}
            for _, r in df.sort_values("발생시각").iterrows()]


def _representative(df):
    """최고 등급 → 최다 건수 → 최초 발생 (§4.1)."""
    t = df.assign(g=df["등급"].map(GRADE_ORDER), n=df.groupby("알람명")["알람명"].transform("size"))
    return t.sort_values(["g", "n", "발생시각"], ascending=[True, False, True]).iloc[0]


def build_cards(alarms, sites, equip, hist, cfg):
    """기지국당 카드 1장, 장비구분별 섹션 (§4.1, §9.2)."""
    site_idx = sites.set_index("기지국ID")
    cards = []
    for sid, sdf in alarms.groupby("기지국ID"):
        m = site_idx.loc[sid]
        site = {"id": sid, "name": m["기지국명"], "branch": m["지사"], "address": m["주소"],
                "install_type": m["설치형태"], "high_work": m["고소작업여부"] == "Y",
                "manager": m["담당자"], "phone": m["담당자연락처"]}
        sections = []
        for etype, edf in sdf.groupby("장비구분"):
            rep = _representative(edf)
            groups = [rep["group"]] + [g for g in edf["group"].unique() if g != rep["group"]]
            diags = [diagnose(sid, g, hist, cfg) for g in groups]
            eq = equip[(equip["기지국ID"] == sid) & (equip["장비구분"] == etype)]
            ref = equip[equip["기지국ID"] == sid] if eq.empty else eq.iloc[0:0]
            sec = {"equip_type": etype, "top_alarm": rep["알람명"], "top_grade": rep["등급"],
                   "alarms": _alarm_rows(edf), "diagnoses": diags,
                   "equipment": equipment_signals(eq, cfg),
                   "equipment_ref": [{"serial": r["장비시리얼"], "equip_type": r["장비구분"], "model": r["모델"],
                                      "firmware": str(r["펌웨어"])} for _, r in ref.iterrows()],
                   "materials": materials_for(diags, cfg),
                   "past_actions": sorted({r["action"] for d in diags for r in d["records"]})}
            sec["dispatch"] = classify_section(sec, cfg)
            sections.append(sec)
        sections.sort(key=lambda s: (DISPATCH_ORDER[s["dispatch"]["class"]], GRADE_ORDER[s["top_grade"]]))
        top = sections[0]
        all_diags = [d for s in sections for d in s["diagnoses"]]
        cards.append({
            "card_id": sid, "site": site,
            "dispatch": {"class": top["dispatch"]["class"],
                         "reason": f"{top['dispatch']['reason']} ({top['equip_type']})"},
            "summary": {"alarm_count": len(sdf), "top_grade": top["top_grade"],
                        "unresolved": int((sdf["상태"] == "미해제").sum()), "top_alarm": top["top_alarm"]},
            "cautions": cautions_for(site, sections, all_diags),
            "sections": sections,
        })
    cards.sort(key=lambda c: (DISPATCH_ORDER[c["dispatch"]["class"]], GRADE_ORDER[c["summary"]["top_grade"]],
                              -c["summary"]["unresolved"], -c["summary"]["alarm_count"]))
    return cards


# ---------- 출력 (§9) ----------

def repeat_ranking(hist, sites, n):
    names = sites.set_index("기지국ID")["기지국명"]
    g = hist.groupby("기지국ID").agg(total=("실제원인", "size"), recur=("재발여부", lambda s: int((s == "Y").sum())))
    g["max_same"] = hist.groupby(["기지국ID", "group"]).size().groupby(level=0).max()
    g = g.sort_values(["total", "recur", "max_same"], ascending=False).head(n)
    return [{"id": i, "name": names.get(i, ""), "total": int(r.total), "recur": int(r.recur),
             "max_same": int(r.max_same)} for i, r in g.iterrows()]


def card_md(c):
    s = c["site"]
    lines = [f"# {s['name']} ({s['id']})", "",
             f"**{DISPATCH_LABEL[c['dispatch']['class']]}** — {c['dispatch']['reason']}", "",
             f"- {s['branch']} · {s['address']} · {s['install_type']} · 고소작업 {'Y' if s['high_work'] else 'N'}",
             f"- 담당 {s['manager']} {s['phone']}",
             f"- 오늘 알람 {c['summary']['alarm_count']}건 · 최고 {c['summary']['top_grade']} · 미해제 {c['summary']['unresolved']}",
             "", "## 주의사항", ""] + [f"- {x}" for x in c["cautions"]]
    for sec in c["sections"]:
        lines += ["", f"## {sec['equip_type']} — {DISPATCH_LABEL[sec['dispatch']['class']]} ({sec['dispatch']['reason']})", "",
                  "| 알람 | 등급 | 발생~해제 | 상태 |", "|---|---|---|---|"]
        lines += [f"| {a['name']} | {a['grade']} | {a['start']}~{a['end']} | {a['status']} |" for a in sec["alarms"]]
        for d in sec["diagnoses"]:
            cause = " / ".join(d["primary"]) or "—"
            if d["level"] == "L2":
                cause = f"(추정) {cause}"
            lines += ["", f"**[{d['label']}] {d['group']}: {cause}**", ""]
            meta = [f"같은 증상 {d['same_symptom_count']}건"]
            if d["share"] is not None:
                meta.append(f"비율 {d['share']:.0%}")
            if d["confidence"]:
                meta.append(f"신뢰도 {d['confidence']}")
            if d["natural_recovery"]:
                meta.append(f"자연복구 이력 {d['natural_recovery']}건")
            lines += [f"- {' · '.join(meta)}", f"- 근거: {d['basis']}"]
            if d["candidates"]:
                lines.append("- 후보: " + ", ".join(f"{a} {b}건" for a, b in d["candidates"]))
            for r in d["records"]:
                lines.append(f"  - {'🔺' if r['recent'] else ''}{r['date']} {r['cause']} → {r['action']} (재발 {r['recur']}, {r['worker']})")
        lines += ["", "**장비** (신호는 추정 보강)"]
        if sec["equipment"]:
            lines += [f"- {e['serial']} {e['model']} FW {e['firmware']} · {' '.join(e['signals']) or '신호 없음'}" for e in sec["equipment"]]
        elif sec["equipment_ref"]:
            lines.append("- 같은 장비구분 기록 없음 · 참고: " + ", ".join(f"{e['equip_type']} {e['model']}" for e in sec["equipment_ref"]))
        else:
            lines.append("- 장비 기록 없음")
        mats = ", ".join(m["item"] + (" (추정)" if m["estimated"] else "") for m in sec["materials"]) or "별도 자재 없음"
        lines += ["", f"**챙길 자재**: {mats}"]
        if sec["past_actions"]:
            lines.append(f"- 과거 조치: {', '.join(sec['past_actions'])}")
    return "\n".join(lines) + "\n"


def _json_default(o):
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def write_outputs(cards, meta, top10):
    """cards.json, meta.json, cards/{기지국ID}.md (§9.1 ~ §9.2). 화면은 frontend/ (React)."""
    (OUTPUT / "cards").mkdir(parents=True, exist_ok=True)
    (OUTPUT / "cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
    (OUTPUT / "meta.json").write_text(json.dumps({**meta, "top10": top10}, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in cards:
        (OUTPUT / "cards" / f"{c['card_id']}.md").write_text(card_md(c), encoding="utf-8")


def write_analysis(equip, hist, sites, cfg):
    """반복 장애 순위, 펌웨어·연식 비교 (§9.4)."""
    small = cfg["th"]["small_sample"]
    gtype = {g: v["equip_type"] for g, v in cfg["groups"].items()}
    h = hist.assign(etype=hist["group"].map(gtype))

    def top_cause(rows):
        keys = set(zip(rows["기지국ID"], rows["장비구분"]))
        sub = h[[k in keys for k in zip(h["기지국ID"], h["etype"])]]
        sub = sub[sub["실제원인"] != NATURAL]
        if sub.empty:
            return "—"
        vc = sub["실제원인"].value_counts()
        return f"{vc.index[0]} ({int(vc.iloc[0])}/{len(sub)})"

    lines = ["# 분석", "", "## 반복 장애 기지국 Top 20", "",
             "| # | 기지국 | 조치이력 | 재발 Y | 같은 증상 최다 |", "|---|---|---|---|---|"]
    for i, r in enumerate(repeat_ranking(hist, sites, 20), 1):
        lines.append(f"| {i} | {r['id']} {r['name']} | {r['total']} | {r['recur']} | {r['max_same']} |")

    lines += ["", "## 펌웨어 비교", "", "| 장비구분 | 모델 | 펌웨어 | 장비 수 | 평균 누적고장 | 주요 원인 | 비고 |",
              "|---|---|---|---|---|---|---|"]
    fw = equip.assign(펌웨어=equip["펌웨어"].astype(str)).groupby(["장비구분", "모델", "펌웨어"])
    rows = sorted(fw, key=lambda kv: -kv[1]["누적고장횟수"].mean())
    for (et, mo, f), g in rows:
        lines.append(f"| {et} | {mo} | {f} | {len(g)} | {g['누적고장횟수'].mean():.2f} | {top_cause(g)} | "
                     f"{'표본 적음' if len(g) < small else ''} |")

    lines += ["", "## 연식 비교", "", "| 장비구분 | 설치연도 | 장비 수 | 평균 누적고장 | 주요 원인 | 비고 |", "|---|---|---|---|---|---|"]
    bins = pd.cut(equip["설치일"].dt.year, [0, 2017, 2020, 2023, 9999], labels=["~2017", "2018-2020", "2021-2023", "2024~"])
    for (et, b), g in equip.assign(bin=bins).groupby(["장비구분", "bin"], observed=True):
        lines.append(f"| {et} | {b} | {len(g)} | {g['누적고장횟수'].mean():.2f} | {top_cause(g)} | "
                     f"{'표본 적음' if len(g) < small else ''} |")
    (OUTPUT / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(cards, alarms, hist, sites, cfg):
    """자동 검증 (§11). 실패 항목 목록을 돌려준다."""
    base = pd.Timestamp(cfg["th"]["base_date"])
    gmap = build_group_map(cfg["groups"])
    hist_keys = set(zip(hist["기지국ID"], hist["조치일"].dt.strftime("%Y-%m-%d")))
    diags = [(c, s, d) for c in cards for s in c["sections"] for d in s["diagnoses"]]
    high = set(sites.loc[sites["고소작업여부"] == "Y", "기지국ID"])
    checks = {
        "카드 수 = 알람 기지국 수": len(cards) == alarms["기지국ID"].nunique(),
        "섹션 수 = 기지국+장비구분 조합 수": sum(len(c["sections"]) for c in cards)
            == len(alarms[["기지국ID", "장비구분"]].drop_duplicates()),
        "알람명 전부 증상그룹 매핑": set(alarms["알람명"]) <= set(gmap),
        "근거 기록이 전부 기준일 이전": bool((hist["조치일"] < base).all()),
        "L1 조치일이 조치이력에 존재": all((c["card_id"], r["date"]) in hist_keys
                                    for c, _, d in diags if d["level"] == "L1" for r in d["records"]),
        "L2/L3에 근거 배지 없음": all(d["label"] != "근거" for _, _, d in diags if d["level"] != "L1"),
        "자연복구만으로 L1 없음": all(any(r["cause"] != NATURAL for r in d["records"])
                               for _, _, d in diags if d["level"] == "L1"),
        "미해제 Critical/Major 카드는 🔴": all(c["dispatch"]["class"] == "now" for c in cards
            if any(a["status"] == "미해제" and a["grade"] in ("Critical", "Major") for s in c["sections"] for a in s["alarms"])),
        "Critical 포함 카드는 🟢 아님": all(c["dispatch"]["class"] != "later" for c in cards
            if any(a["grade"] == "Critical" for s in c["sections"] for a in s["alarms"])),
        "고소작업 Y 카드에 고소 주의": all(any("고소작업" in x for x in c["cautions"]) for c in cards if c["card_id"] in high),
    }
    return [k for k, ok in checks.items() if not ok], checks


def main():
    cfg = load_config()
    alarms, sites, equip, hist = load_data()
    alarms, hist, equip, unmapped = normalize(alarms, hist, equip, cfg)
    write_join_report(alarms, sites, equip, hist, unmapped)
    cards = build_cards(alarms, sites, equip, hist, cfg)
    failed, checks = validate(cards, alarms, hist, sites, cfg)
    for k, ok in checks.items():
        print(("✅" if ok else "❌"), k)
    if failed:
        raise SystemExit(f"검증 실패 {len(failed)}건")
    meta = {"base_date": cfg["th"]["base_date"], "alarm_count": len(alarms), "site_count": len(cards)}
    write_outputs(cards, meta, repeat_ranking(hist, sites, 10))
    write_analysis(equip, hist, sites, cfg)
    cnt = pd.Series([c["dispatch"]["class"] for c in cards]).value_counts().to_dict()
    lv = pd.Series([d["level"] for c in cards for s in c["sections"] for d in s["diagnoses"]]).value_counts().to_dict()
    print(f"카드 {len(cards)}장 · 분류 {cnt} · 판단 {lv}")


if __name__ == "__main__":
    main()
