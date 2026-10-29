"""로스팅 한 배치의 진행 관리: 투입 → 이벤트·조작 기록 → 경고 → 배출 → 저장"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from taas_rules import RoastEngine, Sample

BATCH_DIR = Path(__file__).resolve().parents[1] / "batches"
EVENT_NAMES = {"charge": "투입", "tp": "TP", "yellow": "옐로", "fc": "1차", "fc_end": "1차 끝",
               "sc": "2차", "drop": "배출"}


class RoastSession:
    def __init__(self, source, speed: float = 1.0):
        self.source = source
        self.speed = speed
        self.lock = threading.RLock()
        self.status = "idle"                 # idle(예열·BBP) / roasting / done
        self.meta: dict = {}
        self.reference: dict | None = None
        self._reset_batch()
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)

    # ---------- 루프 ----------
    def start(self):
        self._thread.start()

    def stop(self):
        self._stop = True

    def _loop(self):
        while not self._stop:
            time.sleep(1.0 / max(self.speed, 0.1))
            self.step()

    def step(self):
        """시뮬레이션 1초 진행 (테스트에서도 직접 호출)"""
        with self.lock:
            self.source.tick(1.0)
            bt, et = self.source.read()
            self.live = {"bt": bt, "et": et}
            if self.status != "roasting":
                return
            self.t += 1.0
            s = Sample(self.t, bt, et, self.source.gas, self.source.exhaust, self.source.drum)
            new = self.engine.update(s)
            if self.t <= self._suppress_gas_until:
                new = [a for a in new if not a.code.startswith("GAS_")]
            st = self.engine.s
            self.samples.append({"t": self.t, "bt": bt, "et": et,
                                 "bt_ror": st.bt_ror[-1], "et_ror": st.et_ror[-1],
                                 "gas": s.gas, "exhaust": s.exhaust, "drum": s.drum})
            for a in new:
                self.alerts.append({"t": a.t, "level": a.level, "code": a.code, "message": a.message, "note": a.note})
                if a.code == "BT_TP" and "tp" not in self._event_types():
                    tp = st.bt_tp
                    self._add_event("tp", tp, self._bt_at(tp), auto=True)
                if a.code == "FC_CANDIDATE" and "fc" not in self._event_types():
                    self._add_event("fc", a.t, bt, auto=True)

    # ---------- 조작 ----------
    def charge(self, name: str = "", weight: float = 1.2, note: str = ""):
        with self.lock:
            if self.status == "roasting":
                return {"ok": False, "error": "이미 로스팅 중"}
            self._reset_batch()
            bt, et = self.source.read()
            self.meta = {"name": name or "이름 없음", "weight_in": weight, "note": note,
                         "started": datetime.now().isoformat(timespec="seconds"),
                         "charge_bt": bt, "charge_et": et, "source": self.source.name,
                         "bbp": dict(self._bbp)}
            self.source.charge(weight)
            self.status = "roasting"
            self.engine.update(Sample(0.0, bt, et, self.source.gas, self.source.exhaust, self.source.drum))
            self.samples.append({"t": 0.0, "bt": bt, "et": et, "bt_ror": None, "et_ror": None,
                                 "gas": self.source.gas, "exhaust": self.source.exhaust, "drum": self.source.drum})
            self.alerts.append({"t": 0.0, "level": "정보", "code": "AA_START",
                                "message": "투입: 배기는 최저로 시작 (표면 선건조 방지)", "note": "37·46"})
            self._add_event("charge", 0.0, bt)
            return {"ok": True}

    def control(self, name: str, value: float, force: bool = False):
        with self.lock:
            cur = {"gas": self.source.gas, "exhaust": self.source.exhaust, "drum": self.source.drum}[name]
            if self.status == "roasting" and name == "gas" and not force:
                warns = [a for a in self.engine.check_gas_cut(value) if a.level == "경고"]
                if warns:
                    return {"ok": False, "confirm": True,
                            "warnings": [{"message": a.message, "note": a.note} for a in warns]}
            self.source.set_controls(**{name: value})
            if self.status == "roasting":
                self.controls.append({"t": self.t, "name": name, "from": cur, "to": value, "forced": force})
                if name == "gas":
                    # 화면에서 이미 확인(또는 강제 적용)한 조작 → 다음 샘플에서 같은 경고를 또 띄우지 않음
                    self._suppress_gas_until = self.t + 1
                    if force:
                        self.alerts.append({"t": self.t, "level": "정보", "code": "GAS_FORCED",
                                            "message": f"경고 무시하고 화력 {cur:g}→{value:g} 적용 (기록됨)", "note": ""})
            return {"ok": True}

    def event(self, kind: str):
        with self.lock:
            if self.status != "roasting":
                return {"ok": False, "error": "로스팅 중이 아님"}
            bt = self.samples[-1]["bt"]
            self.events = [e for e in self.events if not (e["type"] == kind and e.get("auto"))]
            self._add_event(kind, self.t, bt)
            if kind == "drop":
                self.source.drop()
                self.source.set_controls(gas=0, exhaust=10)     # BBP 쿨다운: 화력 0·배기 최저 (47·50번)
                self.alerts.append({"t": self.t, "level": "제안", "code": "BBP_START",
                                    "message": "BBP 쿨다운 시작 (화력 0·배기 최저). 투입온도 −10℃까지 식힌 뒤 화력 18~20으로 재가열",
                                    "note": "45·47·50"})
                self.status = "done"
                self._bbp = {"drop_t": time.time(), "min_bt": bt}
                path = self.save()
                return {"ok": True, "saved": path.name}
            return {"ok": True}

    def finish(self, weight_out: float | None = None, color_whole: float | None = None,
               color_ground: float | None = None, cup: str = ""):
        """배출 후 결과 입력 (41·25번: 손실률·색도로 일관성 판정)"""
        with self.lock:
            m = self.meta
            if weight_out:
                m["weight_out"] = weight_out
                m["loss_pct"] = round((m["weight_in"] - weight_out) / m["weight_in"] * 100, 1)
            if color_whole is not None:
                m["color_whole"] = color_whole
            if color_ground is not None:
                m["color_ground"] = color_ground
            if cup:
                m["cup"] = cup
            path = self.save()
            return {"ok": True, "saved": path.name, "loss_pct": m.get("loss_pct")}

    def new_batch(self):
        with self.lock:
            self.status = "idle"
            self._reset_batch()
            return {"ok": True}

    def set_speed(self, x: float):
        self.speed = min(max(x, 0.5), 20)
        return {"ok": True, "speed": self.speed}

    # ---------- 저장·불러오기 ----------
    def save(self) -> Path:
        BATCH_DIR.mkdir(exist_ok=True)
        if not self.meta.get("file"):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w가-힣-]+", "_", self.meta.get("name", "batch"))[:30]
            self.meta["file"] = f"{stamp}_{safe}.json"
        path = BATCH_DIR / self.meta["file"]
        data = {"meta": self.meta, "summary": self.summary(), "events": self.events,
                "controls": self.controls, "alerts": self.alerts, "samples": self.samples}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    @staticmethod
    def list_batches():
        out = []
        for p in sorted(BATCH_DIR.glob("*.json"), reverse=True):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out.append({"file": p.name, "name": d["meta"].get("name"), "started": d["meta"].get("started"),
                            "weight_in": d["meta"].get("weight_in"), **(d.get("summary") or {})})
            except Exception:
                continue
        return out

    def set_reference(self, file: str | None):
        with self.lock:
            if not file:
                self.reference = None
                return {"ok": True}
            p = BATCH_DIR / Path(file).name
            if not p.exists():
                return {"ok": False, "error": "파일 없음"}
            d = json.loads(p.read_text(encoding="utf-8"))
            self.reference = {"file": p.name, "name": d["meta"].get("name"), "events": d["events"],
                              "samples": [{k: s[k] for k in ("t", "bt", "et", "bt_ror")} for s in d["samples"]]}
            return {"ok": True}

    # ---------- 상태 ----------
    def summary(self) -> dict:
        ev = {e["type"]: e for e in self.events}
        end = ev["drop"]["t"] if "drop" in ev else self.t
        out = {"total": end}
        if "tp" in ev:
            out["tp"] = {"t": ev["tp"]["t"], "bt": ev["tp"]["bt"]}
        if "fc" in ev:
            fc = ev["fc"]["t"]
            out["fc"] = {"t": fc, "bt": ev["fc"]["bt"]}
            out["dev_time"] = end - fc
            out["dtr"] = round((end - fc) / end * 100, 1) if end else None
        y = ev.get("yellow", {}).get("t")
        if y and end:
            fc = ev.get("fc", {}).get("t", end)
            out["phases"] = {"dry": round(y / end * 100, 1), "maillard": round((fc - y) / end * 100, 1),
                             "dev": round((end - fc) / end * 100, 1)}
        if "drop" in ev:
            out["drop"] = {"t": ev["drop"]["t"], "bt": ev["drop"]["bt"]}
        return out

    def state(self, since: int = 0, alerts_since: int = 0) -> dict:
        with self.lock:
            return {"status": self.status, "t": self.t, "speed": self.speed, "live": self.live,
                    "source": self.source.name,
                    "controls_now": {"gas": self.source.gas, "exhaust": self.source.exhaust, "drum": self.source.drum},
                    "meta": self.meta, "events": self.events, "controls": self.controls,
                    "samples": self.samples[since:], "n_samples": len(self.samples),
                    "alerts": self.alerts[alerts_since:], "n_alerts": len(self.alerts),
                    "summary": self.summary() if self.status != "idle" else None,
                    "bbp": self._bbp_state(),
                    "reference": self.reference}

    # ---------- 내부 ----------
    def _reset_batch(self):
        self.t = 0.0
        self.engine = RoastEngine()
        self.samples, self.events, self.controls, self.alerts = [], [], [], []
        self.meta = {}
        self._suppress_gas_until = -1.0
        if not hasattr(self, "_bbp"):
            self._bbp = {}
        if not hasattr(self, "live"):
            self.live = {"bt": None, "et": None}

    def _bbp_state(self):
        if not self._bbp.get("drop_t") or self.status == "roasting":
            return None
        return {"since_drop_sec": round(time.time() - self._bbp["drop_t"]), "drop_bt": self._bbp.get("min_bt")}

    def _event_types(self):
        return {e["type"] for e in self.events}

    def _bt_at(self, t):
        for s in reversed(self.samples):
            if s["t"] <= t:
                return s["bt"]
        return None

    def _add_event(self, kind, t, bt, auto=False):
        self.events = [e for e in self.events if e["type"] != kind]
        self.events.append({"type": kind, "label": EVENT_NAMES.get(kind, kind), "t": t, "bt": bt, "auto": auto})
        self.events.sort(key=lambda e: e["t"])
