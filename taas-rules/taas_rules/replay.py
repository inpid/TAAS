"""저장된 로스팅 로그(CSV)를 다시 돌려서 경고가 어디서 떴을지 확인
CSV 열 이름: time(초 또는 m:ss), bt, et, gas, exhaust, drum  (gas·exhaust·drum은 없어도 됨)
실행: python -m taas_rules.replay 로그.csv
"""
import csv
import sys

from .engine import RoastEngine, Sample


def _sec(v: str) -> float:
    if ":" in v:
        m, s = v.split(":")
        return int(m) * 60 + float(s)
    return float(v)


def _num(row, key):
    v = (row.get(key) or "").strip()
    return float(v) if v else None


def replay(path: str) -> list:
    eng, alerts = RoastEngine(), []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): v for k, v in row.items()}
            s = Sample(_sec(row["time"]), float(row["bt"]), float(row["et"]),
                       _num(row, "gas"), _num(row, "exhaust"), _num(row, "drum"))
            alerts += eng.update(s)
    return alerts


if __name__ == "__main__":
    for a in replay(sys.argv[1]):
        print(a)
