"""TAAS 실시간 로스팅 경고 엔진 (이지스터 1.8 기준)

근거: 로스팅 지식 노트 11·21·37·39·43·49·50·51번 (knowledge/notes/)
사용법:
    eng = RoastEngine()                       # config.json 자동 로드
    for s in samples:                         # 투입 시점부터 1~2초 간격 권장
        for a in eng.update(s): print(a)
    eng.check_gas_cut(new_gas)                # 화력 내리기 '전에' 물어보고 싶을 때
숫자 기준은 전부 config.json에 있음. 코드는 건드리지 말고 config만 고칠 것.
"""
from __future__ import annotations

import json
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).with_name("config.json")


@dataclass
class Sample:
    t: float                      # 투입 후 경과 초
    bt: float                     # 원두 온도 ℃
    et: float                     # 환경(드럼 공기) 온도 ℃
    gas: Optional[float] = None   # 화력 mmAq
    exhaust: Optional[float] = None  # 배기 팬값
    drum: Optional[float] = None  # 드럼 rpm


@dataclass
class Alert:
    t: float
    level: str        # "정보" / "제안" / "경고"
    code: str         # 프로그램용 식별자
    message: str
    note: str = ""    # 근거 노트 번호

    def __str__(self) -> str:
        m, s = divmod(int(self.t), 60)
        tail = f"  (노트 {self.note})" if self.note else ""
        return f"[{m}:{s:02d}] {self.level} · {self.message}{tail}"


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"


@dataclass
class _State:
    samples: list = field(default_factory=list)
    times: list = field(default_factory=list)
    bt_ror: list = field(default_factory=list)
    et_ror: list = field(default_factory=list)
    bt_tp: Optional[float] = None
    et_tp: Optional[float] = None
    wet_active: bool = False
    wet_rise_since: Optional[float] = None
    wet_seen: bool = False
    fc_t: Optional[float] = None
    fc_ror_before: Optional[float] = None
    fc_depth_reported: bool = False
    aa_step1: bool = False
    aa_step2: bool = False
    aa_step3: bool = False
    exhaust_ups: int = 0
    exhaust_warned: bool = False
    stall_since: Optional[float] = None
    last_gas_cut_t: Optional[float] = None


class RoastEngine:
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.c = config
        self.s = _State()

    # ---------- 기본 계산 ----------
    def _value_at(self, t: float, series: list) -> Optional[float]:
        """t초 시점(이전 가장 가까운 샘플)의 값"""
        i = bisect_left(self.s.times, t)
        if i >= len(self.s.times):
            i = len(self.s.times) - 1
        if self.s.times[i] > t:
            i -= 1
        return series[i] if i >= 0 else None

    def _ror(self, key: str) -> Optional[float]:
        w = self.c["ror"]["window_sec"]
        cur = self.s.samples[-1]
        t0 = cur.t - w
        if t0 < self.s.times[0]:
            return None
        past = self._value_at(t0, self.s.samples)
        dt = cur.t - past.t
        if dt <= 0:
            return None
        return (getattr(cur, key) - getattr(past, key)) * 60.0 / dt

    def _ror_ago(self, series: list, sec: float) -> Optional[float]:
        return self._value_at(self.s.times[-1] - sec, series) if self.s.times else None

    def _ror_slope(self, sec: float) -> Optional[float]:
        """최근 sec초 동안 BT RoR 변화 (℃/min 를 분당으로) — 음수면 RoR 하강 중"""
        now, past = self.s.bt_ror[-1], self._ror_ago(self.s.bt_ror, sec)
        if now is None or past is None:
            return None
        return (now - past) * 60.0 / sec

    # ---------- 공개 API ----------
    def update(self, sample: Sample) -> list[Alert]:
        st = self.s
        prev = st.samples[-1] if st.samples else None
        st.samples.append(sample)
        st.times.append(sample.t)
        st.bt_ror.append(self._ror("bt"))
        st.et_ror.append(self._ror("et"))

        out: list[Alert] = []
        if prev is None:
            out.append(Alert(sample.t, "정보", "AA_START",
                             "투입: 배기는 최저로 시작 (표면 선건조 방지)", "37·46"))
            return out

        self._detect_tp(out)
        self._detect_wet_dump(out)
        if prev.gas is not None and sample.gas is not None and sample.gas != prev.gas:
            out += self._judge_gas_change(prev.gas, sample.gas, applied=True)
            if sample.gas < prev.gas:
                st.last_gas_cut_t = sample.t
        self._detect_first_crack(out)
        self._aero_accel(out, prev)
        return out

    def check_gas_cut(self, new_gas: float) -> list[Alert]:
        """화력을 바꾸기 전에 호출 → 지금 바꿔도 되는지 경고 목록 반환 (빈 목록이면 OK)"""
        cur = self.s.samples[-1]
        if cur.gas is None:
            return []
        return self._judge_gas_change(cur.gas, new_gas, applied=False)

    # ---------- 감지기 ----------
    def _detect_tp(self, out: list) -> None:
        st, cur = self.s, self.s.samples[-1]
        if st.bt_tp is None:
            low = min(st.samples, key=lambda x: x.bt)
            if cur.bt >= low.bt + 1.0 and low is not st.samples[0]:
                st.bt_tp = low.t
                out.append(Alert(cur.t, "정보", "BT_TP",
                                 f"터닝포인트 {_mmss(low.t)} / {low.bt:.1f}℃ — 내 기준 배치 TP와 비교 (다르면 BBP 먼저 의심)", "13·25"))
        if st.et_tp is None:
            low = min(st.samples, key=lambda x: x.et)
            if cur.et >= low.et + 1.0 and low is not st.samples[0]:
                st.et_tp = low.t
                out.append(Alert(cur.t, "정보", "ET_TP", f"ET 터닝포인트 {_mmss(low.t)}", "50"))

    def _detect_wet_dump(self, out: list) -> None:
        c, st, cur = self.c["wet_dump"], self.s, self.s.samples[-1]
        now = st.et_ror[-1]
        if st.bt_tp is None or now is None:
            return
        if st.wet_active:
            past = self._ror_ago(st.et_ror, 2)
            rising = past is not None and now > past
            if rising:
                st.wet_rise_since = st.wet_rise_since or cur.t
                if cur.t - st.wet_rise_since >= c["recover_sec"]:
                    st.wet_active = False
                    out.append(Alert(cur.t, "정보", "WET_DUMP_END",
                                     "ET RoR 회복 — 평소 루프(저점 → 상승 확인 → 감압) 재개", "51·11"))
            else:
                st.wet_rise_since = None
            return
        if st.wet_seen or cur.t - st.bt_tp > c["search_after_tp_sec"]:
            return
        before = self._ror_ago(st.et_ror, c["drop_window_sec"])
        if before is not None and before - now >= c["et_ror_drop"] and now <= c["et_ror_floor"]:
            st.wet_active = st.wet_seen = True
            st.wet_rise_since = None
            out.append(Alert(cur.t, "경고", "WET_DUMP",
                             "수분 대량 방출(와장창): 화력·배기 손대지 말고 안정될 때까지 대기. "
                             "시간이 길어지면 다음 배치 투입온도↑ (화력↑ 금지)", "51"))

    def _detect_first_crack(self, out: list) -> None:
        c, st, cur = self.c["first_crack"], self.s, self.s.samples[-1]
        now = st.bt_ror[-1]
        if now is None:
            return
        if st.fc_t is None:
            if not (c["bt_min"] <= cur.bt <= c["bt_max"]):
                return
            if st.last_gas_cut_t is not None and cur.t - st.last_gas_cut_t <= c["ignore_after_gas_cut_sec"]:
                return
            before = self._ror_ago(st.bt_ror, c["drop_window_sec"])
            if before is not None and before - now >= c["bt_ror_drop"]:
                st.fc_t, st.fc_ror_before = cur.t, before
                out.append(Alert(cur.t, "정보", "FC_CANDIDATE",
                                 f"1차 후보 (히트 배리어) BT {cur.bt:.1f}℃ — 소리와 같이 확인해서 마킹", "43"))
            return
        if not st.fc_depth_reported and cur.t - st.fc_t <= 40:
            depth = st.fc_ror_before - now
            if depth >= c["deep_barrier"]:
                st.fc_depth_reported = True
                out.append(Alert(cur.t, "경고", "FC_DEEP",
                                 f"1차 후 RoR {depth:.1f}℃/min 급락(크래시 경향) — 지금 열을 더 넣지 말고, "
                                 "다음 배치 투입~150℃ 구간 열을 늘릴 것", "12·38·43"))

    def _aero_accel(self, out: list, prev: Sample) -> None:
        c, st, cur = self.c["aero_accel"], self.s, self.s.samples[-1]
        if prev.exhaust is not None and cur.exhaust is not None and cur.exhaust > prev.exhaust:
            st.exhaust_ups += 1
            if st.exhaust_ups > c["max_steps"] and not st.exhaust_warned:
                st.exhaust_warned = True
                out.append(Alert(cur.t, "경고", "AA_OVER",
                                 f"배기 가속 {st.exhaust_ups}회 — 과조작, 원인 분리가 어려워짐", "37·21"))
        if not st.aa_step1 and st.et_tp is not None:
            st.aa_step1 = True
            out.append(Alert(cur.t, "제안", "AA_STEP1", "배기 1단계 가속 (ET TP 통과)", "37·50"))
        if not st.aa_step2 and st.bt_tp is not None and c["step2_bt_min"] <= cur.bt <= c["step2_bt_max"]:
            st.aa_step2 = True
            out.append(Alert(cur.t, "제안", "AA_STEP2",
                             "배기 2단계 가속 (BT 140~150℃, 발열 시작 구간) + 감압 루프 시작", "37·40·11"))
        if not st.aa_step3 and st.fc_t is None:
            ror = st.bt_ror[-1]
            fc_target = self.c["first_crack"]["expected_bt"]
            slope = self._ror_slope(10)
            if ror and ror > 0 and (fc_target - cur.bt) / ror * 60 <= c["fc_lead_sec"]:
                if slope is not None and slope >= -0.5:          # 하강이 멈춤/정체
                    st.stall_since = st.stall_since or cur.t
                    if cur.t - st.stall_since >= c["stall_sec"]:
                        st.aa_step3 = True
                        out.append(Alert(cur.t, "제안", "AA_STEP3",
                                         "배기 3단계 가속 (1차 임박 + BT RoR 정체) — 과열 차단", "37·27"))
                else:
                    st.stall_since = None

    def _judge_gas_change(self, old: float, new: float, applied: bool) -> list[Alert]:
        st, cur = self.s, self.s.samples[-1]
        out: list[Alert] = []
        verb = "했음" if applied else "하려 함"
        if st.wet_active:
            out.append(Alert(cur.t, "경고", "GAS_IN_WET_DUMP",
                             f"수분 와장창 구간에 화력 변경{verb} — 안정될 때까지 보류", "51"))
            return out
        if new > old:
            return out
        cb, cf = self.c["big_gas_cut"], self.c["gas_cut_while_falling"]
        step = old - new
        limit = cb["max_step_late"] if cur.bt >= cb["late_bt"] else cb["max_step_early"]
        if step > limit:
            out.append(Alert(cur.t, "경고", "GAS_BIG_CUT",
                             f"화력 {old:g}→{new:g} ({step:g} 감압) — 이 구간 최대 {limit:g}. "
                             "톱니 RoR·베이크드 위험, 작게 나눠서", "39·11"))
        short, long_ = self._ror_slope(cf["short_sec"]), self._ror_slope(cf["long_sec"])
        if short is not None and long_ is not None and short < long_ - cf["margin"]:
            out.append(Alert(cur.t, "경고", "GAS_CUT_FALLING",
                             f"BT RoR이 아직 내려가는 중에 감압{verb} — 저점 → 상승 확인 후에 줄일 것", "11·39"))
        return out
