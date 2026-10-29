"""온도 입력 장치

TAAS는 '입력 장치'만 갈아끼우면 가상 로스터 ↔ 실제 이지스터 1.8을 바꿀 수 있게 만들었다.
모든 입력 장치는 같은 모양을 가진다:
    tick(dt)            dt초 흐름 (가상 로스터만 의미 있음)
    read() -> (bt, et)  지금 원두 온도, 환경 온도
    charge(weight_kg)   생두 투입
    drop()              배출
    set_controls(gas=, exhaust=, drum=)
"""
from __future__ import annotations

import math
import random


class SimulatedRoaster:
    """이지스터 1.8을 흉내 낸 가상 로스터 (연습·시연·개발용)

    52번 노트(주성현 1.2kg) 기록에 맞춤:
      투입 200℃, 화력 104mmAq, 배기 15→50, 드럼 70 → TP 약 1:15 / 95℃, 1차 약 10분 / 약 200℃
    물리 계산이 아니라 'BT RoR이 화력·배기·드럼에 20초쯤 늦게 반응하는' 연습용 모델이다.
    그래서 감압하면 RoR이 바로가 아니라 천천히 꺼지고, 투입온도·투입량·드럼 속도도 진행에 영향을 준다.
    """

    name = "가상 로스터 (이지스터 1.8 흉내)"
    P = dict(gas_k=0.12, base=8.6, slope=0.13, early=0.5, tau=20.0, exo=3.0, barrier=7.0,
             et_gap=0.25, et_add=8.0, kp=0.027, mix=0.21)

    def __init__(self, preheat: float = 200.0, seed: int | None = None):
        self.rng = random.Random(seed)
        self.gas, self.exhaust, self.drum = 18.0, 10.0, 70.0   # 예열 상태 (47·50번)
        self.et = preheat
        self.probe = preheat - 1
        self.bean = 25.0
        self.ror = 0.0
        self.weight = 0.0
        self.loaded = False
        self.t = 0.0
        self.charge_temp = preheat
        self.fc_done = False
        self.fc_left = 0.0

    # ---- 조작 ----
    def set_controls(self, gas=None, exhaust=None, drum=None):
        if gas is not None:
            self.gas = float(gas)
        if exhaust is not None:
            self.exhaust = float(exhaust)
        if drum is not None:
            self.drum = float(drum)

    def charge(self, weight_kg: float = 1.2):
        self.weight = min(max(0.3, weight_kg), 2.2)
        self.charge_temp = self.probe
        self.bean, self.ror, self.t = 25.0, 0.0, 0.0
        self.loaded, self.fc_done, self.fc_left = True, False, 0.0
        self.et -= 22 * (self.weight / 1.2) ** 0.5            # 찬 생두가 들어가며 ET 급락

    def drop(self):
        self.loaded = False
        self.weight = 0.0

    # ---- 시간 흐름 ----
    def tick(self, dt: float = 1.0):
        steps = max(1, int(dt / 0.25))
        for _ in range(steps):
            self._step(dt / steps)

    def _target_ror(self) -> float:
        P, b = self.P, self.bean
        r = P["gas_k"] * self.gas + P["base"]
        r += P["early"] * (100 - b) if b < 100 else -P["slope"] * (b - 100)
        r += (self.charge_temp - 200) * 0.06 * math.exp(-self.t / 180)   # 투입온도 (05·13번)
        r += 0.04 * (self.exhaust - 30) if b > 110 else -0.02 * (self.exhaust - 15)
        if self.drum < 75:
            r -= 0.25 * (75 - self.drum)                                    # 느린 드럼 = 열 덜 받음 (18번)
        r += P["exo"] * min(max(b - 185, 0), 15) / 15                       # 발열 (40번)
        return r * (1.2 / self.weight) ** 0.5

    def _step(self, h: float):
        P = self.P
        if not self.loaded:                                  # 예열·BBP: 빈 드럼
            idle = 165 + 2.0 * self.gas - (self.exhaust - 10) * 0.6
            self.et += (idle - self.et) * 0.03 * h
            self.probe += (self.et - 1 - self.probe) * 0.05 * h
            return
        self.t += h
        if not self.fc_done and self.bean >= 200:
            self.fc_done, self.fc_left = True, 20.0
        self.fc_left = max(0.0, self.fc_left - h)
        self.ror += (self._target_ror() - self.ror) / P["tau"] * h
        dip = P["barrier"] if self.fc_left > 0 else 0.0           # 1차 히트 배리어는 바로 나타남 (43번)
        self.bean += (self.ror - dip) / 60 * h
        et_target = (self.bean + P["et_gap"] * self.gas + P["et_add"] + (self.exhaust - 15) * 0.05
                     + 120 * math.exp(-self.t / 120))                # 초반엔 드럼 축열이 공기를 데움
        self.et += (et_target - self.et) * 0.03 * h
        probe_target = self.bean * (1 - P["mix"]) + self.et * P["mix"]
        kp = P["kp"] if self.t < 80 else 0.08                # 투입 직후엔 프로브가 생두에 묻히는 시간
        self.probe += (probe_target - self.probe) * kp * h

    def read(self):
        n = lambda: self.rng.uniform(-0.1, 0.1)
        return round(self.probe + n(), 1), round(self.et + n(), 1)


class HardwareRoaster:
    """실제 이지스터 1.8 연결 자리 (로스터 설치 후 구현)

    할 일 (docs/ROADMAP.md 1단계):
      - 열전대 2개(BT·ET) → USB 온도 모듈 → 노트북
      - read() 에서 모듈 값을 읽어 (bt, et) 반환
      - 화력·배기·드럼은 기계가 숫자를 안 보내주면 화면 버튼으로 기록 (set_controls 는 기록만)
    """

    name = "실제 로스터 (미연결)"

    def __init__(self, *_, **__):
        raise NotImplementedError("로스터 연결 후 온도 모듈 기종에 맞춰 구현할 것 (docs/ROADMAP.md 1단계)")
