"""가상 로스터로 한 배치를 처음부터 끝까지 돌려보는 테스트"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.session as S  # noqa: E402
from app.sources import SimulatedRoaster  # noqa: E402


def run_batch(tmp_path, cuts):
    S.BATCH_DIR = tmp_path
    s = S.RoastSession(SimulatedRoaster(seed=3))
    for _ in range(600):
        s.step()
    s.control("gas", 104)
    s.control("exhaust", 15)
    assert s.charge("테스트", 1.2)["ok"]
    results = {}
    for _ in range(900):
        s.step()
        if s.t == 80:
            s.control("exhaust", 50)
        if s.t == 255:
            s.event("yellow")
        if s.t in cuts:
            results[s.t] = s.control("gas", cuts[s.t])
        if s.samples[-1]["bt"] >= 210:
            break
    return s, results


def test_full_batch_saved(tmp_path):
    s, _ = run_batch(tmp_path, {330: 101, 390: 98, 510: 91, 560: 87})
    sm = s.summary()
    assert 65 <= sm["tp"]["t"] <= 90 and 88 <= sm["tp"]["bt"] <= 100      # TP 약 1:16 / 94℃
    assert "fc" in sm and 540 <= sm["fc"]["t"] <= 660                       # 1차 약 10분
    r = s.event("drop")
    assert r["ok"] and (tmp_path / r["saved"]).exists()
    assert s.source.gas == 0                                                # BBP 쿨다운 자동 전환
    fin = s.finish(1.05, 61, 83, "테스트")
    assert fin["loss_pct"] == 12.5
    assert s.summary()["phases"]["dry"] > 0
    assert S.RoastSession.list_batches()[0]["name"] == "테스트"


def test_big_cut_asks_confirmation(tmp_path):
    _, res = run_batch(tmp_path, {400: 85})
    assert res[400].get("confirm") is True and res[400]["ok"] is False


def test_reference_overlay(tmp_path):
    s, _ = run_batch(tmp_path, {330: 101})
    f = s.event("drop")["saved"]
    s.new_batch()
    assert s.set_reference(f)["ok"] and len(s.reference["samples"]) > 100
