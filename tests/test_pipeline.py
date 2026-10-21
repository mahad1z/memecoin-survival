import numpy as np
import pandas as pd

from memesurv import data, survival, synthetic


def test_cif_simple_case():
    # 4 tokens: two die at t=1, one graduates at t=2, one censored at t=3
    cif = survival.cumulative_incidence(np.array([1, 1, 2, 3]), np.array([1, 1, 2, 0]))
    end = survival.cif_at(cif, 3)
    assert np.isclose(end["cif_dead"], 0.5)
    assert np.isclose(end["cif_grad"], 0.25)
    assert np.isclose(end["cif_dead"] + end["cif_grad"] + end["surv"], 1.0)


def test_auc_bounds():
    assert survival.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert survival.auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0


def test_landmark_excludes_early_deaths():
    df = data.add_features(synthetic.make(2000, seed=3))
    lm = data.landmark(df)
    assert (lm["duration_hours"] > data.LANDMARK_HOURS).all()
    assert (lm["t_lm"] > 0).all()


def test_cox_recovers_planted_effect():
    df = data.add_features(synthetic.make(15000, seed=1))
    lm = data.landmark(df)
    feats = list(data.FEATURES)
    z, _ = data.standardise(lm, feats)
    table, _ = survival.cox_cause_specific(z, feats)
    hr = table.set_index("feature")["HR"]
    assert hr["dev_sold_5m"] > 1.3        # planted as a strong risk factor
    assert hr["log_traders_5m"] < 1.0     # planted as protective


def test_load_roundtrip(tmp_path):
    p = tmp_path / "t.csv"
    synthetic.make(500).to_csv(p, index=False)
    df = data.load(str(p))
    assert len(df) == 500
    assert set(df["outcome"]) <= set(data.OUTCOMES)
