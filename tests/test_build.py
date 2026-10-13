"""실행: python -m unittest discover -s tests"""
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_briefing as b  # noqa: E402

CFG = b.load_config()


def hist_df(rows):
    df = pd.DataFrame(rows, columns=["조치일", "기지국ID", "group", "실제원인", "조치내용", "재발여부", "작업자"])
    df["조치일"] = pd.to_datetime(df["조치일"])
    return df


def section(alarms, diags):
    return {"alarms": alarms, "diagnoses": diags}


def alarm(grade, status="해제", group="G"):
    return {"grade": grade, "status": status, "group": group}


def diag(level, primary, has_recur=False, group="G"):
    return {"level": level, "primary": primary, "has_recur": has_recur, "group": group}


class TestDiagnose(unittest.TestCase):
    H = hist_df([
        ["2026-09-01", "S1", "G", "SFP 불량", "SFP 교체", "Y", "a"],
        ["2026-03-01", "S1", "G", "SFP 불량", "SFP 교체", "N", "a"],
        ["2026-02-01", "S1", "G", "광커넥터 오염", "광커넥터 클리닝", "N", "a"],
        ["2026-01-01", "S2", "G", "광커넥터 오염", "광커넥터 클리닝", "N", "a"],
        ["2026-01-01", "S3", "G", b.NATURAL, "경과관찰 후 자연해소", "N", "a"],
        ["2026-01-01", "S3", "H", b.NATURAL, "경과관찰 후 자연해소", "N", "a"],
    ])

    def test_l1_high(self):
        d = b.diagnose("S1", "G", self.H, CFG)
        self.assertEqual((d["level"], d["primary"], d["confidence"]), ("L1", ["SFP 불량"], "높음"))
        self.assertEqual(d["candidates"], [["광커넥터 오염", 1]])
        self.assertTrue(d["records"][0]["recent"])  # 2026-09-01 은 90일 이내
        self.assertFalse(d["records"][1]["recent"])

    def test_l2_when_only_other_sites(self):
        d = b.diagnose("S9", "G", self.H, CFG)
        self.assertEqual(d["level"], "L2")
        self.assertEqual(sorted(d["primary"]), ["SFP 불량", "광커넥터 오염"])  # 2:2 동률 → 모두
        self.assertIsNone(d["confidence"])
        self.assertEqual(d["records"], [])

    def test_natural_only_falls_back(self):
        d = b.diagnose("S3", "G", self.H, CFG)
        self.assertEqual(d["level"], "L2")
        self.assertEqual(d["natural_recovery"], 1)
        self.assertEqual(b.diagnose("S3", "H", self.H, CFG)["level"], "L3")

    def test_tie_is_normal_confidence(self):
        h = hist_df([["2026-01-01", "S1", "G", "SFP 불량", "x", "N", "a"],
                     ["2026-02-01", "S1", "G", "포트 불량", "x", "N", "a"]])
        d = b.diagnose("S1", "G", h, CFG)
        self.assertEqual((sorted(d["primary"]), d["confidence"]), (["SFP 불량", "포트 불량"], "보통"))


class TestClassify(unittest.TestCase):
    def k(self, alarms, diags):
        return b.classify_section(section(alarms, diags), CFG)["class"]

    def test_unresolved_major_now(self):
        self.assertEqual(self.k([alarm("Major", "미해제")], [diag("L3", [])]), "now")

    def test_hw_recur_now(self):
        self.assertEqual(self.k([alarm("Minor")], [diag("L1", ["SFP 불량"], True)]), "now")

    def test_remote_cause(self):
        self.assertEqual(self.k([alarm("Minor")], [diag("L2", ["일시적 SW 오류"])]), "remote")

    def test_resolved_critical_remote(self):
        self.assertEqual(self.k([alarm("Critical")], [diag("L3", [])]), "remote")

    def test_resolved_minor_later(self):
        self.assertEqual(self.k([alarm("Minor")], [diag("L2", ["SFP 불량"])]), "later")

    def test_repeat_bumps(self):
        self.assertEqual(self.k([alarm("Minor")] * 3, [diag("L2", ["SFP 불량"])]), "remote")
        self.assertEqual(self.k([alarm("Minor")] * 3, [diag("L2", ["일시적 SW 오류"])]), "now")


class TestHelpers(unittest.TestCase):
    def test_materials_estimated(self):
        m = b.materials_for([{"level": "L2", "primary": ["SFP 불량"]}], CFG)
        self.assertTrue(all(x["estimated"] for x in m))
        m = b.materials_for([{"level": "L1", "primary": ["SFP 불량"]}], CFG)
        self.assertFalse(any(x["estimated"] for x in m))

    def test_signals(self):
        e = pd.DataFrame([{"장비시리얼": "X", "장비구분": "RU", "제조사": "m", "모델": "M", "펌웨어": "1",
                           "설치일": pd.Timestamp("2015-01-01"), "최근교체일": pd.Timestamp("2026-09-01"),
                           "누적고장횟수": 4, "비고": "배터리 미교체"}])
        s = " ".join(b.equipment_signals(e, CFG)[0]["signals"])
        for word in ("누적고장 4회", "일 전 교체", "미교체"):
            self.assertIn(word, s)
        self.assertNotIn("노후", s)  # 최근교체일 기준이라 노후 아님

    def test_cautions(self):
        site = {"high_work": True, "install_type": "철탑", "manager": "m", "phone": "p"}
        c = b.cautions_for(site, [{"equip_type": "정류기"}], [])
        self.assertTrue(any("고소작업" in x for x in c) and any("승주" in x for x in c) and any("전기" in x for x in c))


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        alarms, sites, equip, hist = b.load_data()
        cls.alarms, cls.hist, cls.equip, cls.unmapped = b.normalize(alarms, hist, equip, CFG)
        cls.sites = sites
        cls.cards = b.build_cards(cls.alarms, sites, cls.equip, cls.hist, CFG)

    def test_validate_passes(self):
        failed, _ = b.validate(self.cards, self.alarms, self.hist, self.sites, CFG)
        self.assertEqual(failed, [])

    def test_counts(self):
        self.assertEqual(len(self.cards), 225)
        self.assertEqual(sum(len(c["sections"]) for c in self.cards), 371)
        self.assertEqual(self.unmapped, [])

    def test_l1_matches_source(self):
        """L1 원인이 원본 조치이력의 최다 원인과 같은지 독립 계산으로 대조."""
        for c in self.cards:
            for s in c["sections"]:
                for d in s["diagnoses"]:
                    if d["level"] != "L1":
                        continue
                    r = self.hist[(self.hist["기지국ID"] == c["card_id"]) & (self.hist["group"] == d["group"])
                                  & (self.hist["실제원인"] != b.NATURAL)]
                    vc = r["실제원인"].value_counts()
                    self.assertEqual(sorted(d["primary"]), sorted(vc[vc == vc.max()].index))

    def test_json_serializable(self):
        json.dumps(self.cards, ensure_ascii=False, default=b._json_default)


if __name__ == "__main__":
    unittest.main()
