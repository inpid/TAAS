import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from taas_rules import RoastEngine  # noqa: E402
from sim import make_roast  # noqa: E402


def run(**kw):
    eng, alerts = RoastEngine(), []
    for s in make_roast(**kw):
        alerts += eng.update(s)
    return alerts


def codes(alerts):
    return [a.code for a in alerts]


def first(alerts, code):
    return next(a for a in alerts if a.code == code)


def test_normal_roast_has_no_warnings():
    a = run()
    assert [x for x in a if x.level == "경고"] == [], [str(x) for x in a]
    tp = first(a, "BT_TP")
    assert 70 <= tp.t <= 80
    assert "AA_STEP1" in codes(a) and "AA_STEP2" in codes(a)
    fc = first(a, "FC_CANDIDATE")
    assert 595 <= fc.t <= 615


def test_step2_at_140_150():
    s2 = first(run(), "AA_STEP2")
    sample_bt = next(x.bt for x in make_roast() if x.t == s2.t)
    assert 140 <= sample_bt <= 150


def test_wet_dump_detected_and_released():
    a = run(wet_dump=True)
    w = first(a, "WET_DUMP")
    assert 150 <= w.t <= 200
    assert first(a, "WET_DUMP_END").t > w.t


def test_gas_change_during_wet_dump_is_blocked():
    a = run(wet_dump=True, cut_in_wet=True)
    assert "GAS_IN_WET_DUMP" in codes(a)


def test_cut_while_ror_falling():
    a = run(bad_cut_falling=True)
    assert "GAS_CUT_FALLING" in codes(a)


def test_big_cut():
    assert "GAS_BIG_CUT" in codes(run(big_cut=True))


def test_deep_heat_barrier():
    assert "FC_DEEP" in codes(run(deep_fc=True))
    assert "FC_DEEP" not in codes(run())


def test_check_before_cut():
    eng = RoastEngine()
    for s in make_roast():
        if s.t > 400:
            break
        eng.update(s)
    assert eng.check_gas_cut(101) == [] or all(x.code != "GAS_BIG_CUT" for x in eng.check_gas_cut(101))
    assert any(x.code == "GAS_BIG_CUT" for x in eng.check_gas_cut(80))
