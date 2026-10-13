"""브리핑 BE 서버 (표준 라이브러리만 사용).

실행: python server.py [--port 8000]

GET  /api/health   상태 확인 (FE 연결 테스트용)
GET  /api/meta     기준일, 건수, 반복 장애 Top 10
GET  /api/cards    카드 전체
GET  /api/cards/{기지국ID}
POST /api/rebuild  build_briefing.py 다시 실행
"""
import argparse
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import build_briefing

OUTPUT = Path(__file__).parent / "output"
VERSION = "1.0"
_lock = threading.Lock()
_state = {"cards": [], "meta": {}, "built_at": None}


def _fallback_meta(cards):
    th = json.loads((Path(__file__).parent / "config" / "thresholds.json").read_text(encoding="utf-8"))
    return {"base_date": th["base_date"], "alarm_count": sum(c["summary"]["alarm_count"] for c in cards),
            "site_count": len(cards), "top10": []}


def load():
    """output/의 결과를 읽는다. 없으면 빌드하고, 빌드가 안 되면 기존 cards.json으로 동작한다."""
    cards_file, meta_file = OUTPUT / "cards.json", OUTPUT / "meta.json"
    warning = None
    if not cards_file.exists() or not meta_file.exists():
        try:
            build_briefing.main()
        except Exception as e:  # 원본 파일 읽기 실패(DRM 등), 검증 실패
            if not cards_file.exists():
                raise
            warning = f"빌드 실패, 기존 cards.json 사용 (반복 장애 Top 10 없음): {e}"
            print("⚠️", warning)
    with _lock:
        cards = json.loads(cards_file.read_text(encoding="utf-8"))
        _state["cards"] = cards
        _state["meta"] = (json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists()
                          else _fallback_meta(cards))
        _state["warning"] = warning
        _state["built_at"] = datetime.fromtimestamp(cards_file.stat().st_mtime).isoformat(timespec="seconds")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/health":
            return self._send(200, {"status": "ok", "version": VERSION, "cards": len(_state["cards"]),
                                    "built_at": _state["built_at"], "warning": _state.get("warning")})
        if path == "/api/meta":
            return self._send(200, {**_state["meta"], "built_at": _state["built_at"]})
        if path == "/api/cards":
            return self._send(200, _state["cards"])
        if path.startswith("/api/cards/"):
            sid = path.rsplit("/", 1)[1]
            card = next((c for c in _state["cards"] if c["card_id"] == sid), None)
            return self._send(200, card) if card else self._send(404, {"error": f"{sid} 없음"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/api/rebuild":
            return self._send(404, {"error": "not found"})
        try:
            build_briefing.main()
            load()
            self._send(200, {"status": "ok", "cards": len(_state["cards"]), "built_at": _state["built_at"]})
        except (SystemExit, Exception) as e:  # 검증 실패, 원본 읽기 실패
            self._send(500, {"error": f"재생성 실패: {e}"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    load()
    print(f"BE 서버: http://{args.host}:{args.port}/api/health (카드 {len(_state['cards'])}장)")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
