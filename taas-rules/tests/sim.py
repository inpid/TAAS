"""이지스터 1.8 1.2kg 비슷한 가상 로스팅 곡선 (52번 노트 형태: 투입 200 → TP 1:13 / 95℃ → 1차 약 10:00 / 202℃)
감압하면 BT RoR이 15초쯤 꺼졌다가 다시 올라오는 '저점 → 반등' 모양을 흉내 냄 (11번 루프)
일부러 문제 상황을 넣을 수 있음: 수분 와장창, 하강 중 감압, 큰 폭 감압, 깊은 히트 배리어
"""
import math

from taas_rules import Sample


def _dip(x, a):
    """감압 후 x초 뒤 RoR 변화: 15초까지 -a로 꺼지고 45초에 -0.3a로 회복"""
    if x < 0:
        return 0.0
    if x < 15:
        return -a * x / 15
    if x < 45:
        return -a + 0.7 * a * (x - 15) / 30
    return -0.3 * a


def make_roast(wet_dump=False, cut_in_wet=False, bad_cut_falling=False, big_cut=False, deep_fc=False):
    cuts = {340: 2, 400: 3, 460: 3, 520: 4, 570: 4}          # 정상: 반등 확인 후 2~4씩
    if bad_cut_falling:
        cuts[352] = 2                                     # 340 감압 직후 RoR이 꺼지는 중에 또 감압
    if big_cut:
        cuts[400] = 15                                    # 초반 큰 폭 감압
    if cut_in_wet:
        cuts[180] = 2
    samples, bt, et, gas, exhaust = [], 200.0, 230.0, 104.0, 15.0
    for t in range(0, 661):
        if t < 73:
            bt = 95 + (200 - 95) * (1 - t / 73) ** 2.2
        else:
            ror = 7.5 + 16 * math.exp(-(t - 73) / 200)
            ror += sum(_dip(t - tc, 0.8 * a) for tc, a in cuts.items())
            if 590 <= t <= 610:
                ror -= (10 if deep_fc else 5) * (t - 590) / 20
            elif 610 < t <= 640:
                ror -= (10 if deep_fc else 5) * (1 - (t - 610) / 30)
            bt += ror / 60
        if t < 60:
            et = 230 - 60 * (t / 60) ** 0.6
        else:
            et_ror = max(14 - (t - 60) * 0.025, 1.0)
            if wet_dump and 150 <= t <= 215:
                et_ror = -1.0
            et += et_ror / 60
        if t == 74:
            exhaust = 50
        if t in cuts:
            gas -= cuts[t]
        samples.append(Sample(float(t), round(bt, 2), round(et, 2), gas, exhaust, 70))
    return samples
