"""
Sprint 2.4 — Model Lifecycle Tests
Tests: ModelStore save/load, each model's save_state/load_state, rolling_accuracy, and versioning.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest

from src.models.model_store import ModelStore
from src.models.lgbm_model import LGBMPredictor
from src.models.lstm_model import LSTMPredictor
from src.models.volatility_model import VolatilityPredictor
from src.models.regime_classifier import RegimeClassifier
from src.models.ensemble import EnsemblePredictor, _ScaledClassifier


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_features(n: int = 20, rng=None) -> dict:
    """Build a minimal features dict with n numeric keys."""
    if rng is None:
        rng = np.random.default_rng(0)
    return {f"f_{i}": float(rng.normal()) for i in range(n)}


def _inject_trained_lgbm(lgbm: LGBMPredictor, n_samples: int = 120) -> None:
    """Inject a trained LGBMClassifier directly to avoid slow background threads."""
    from lightgbm import LGBMClassifier
    rng = np.random.default_rng(42)
    X = rng.random((n_samples, 20)).astype(np.float32)
    y = (X[:, 0] > 0.5).astype(np.int32)
    feature_names = [f"f_{i}" for i in range(20)]
    model = LGBMClassifier(n_estimators=10, verbose=-1)
    model.fit(X, y)

    lgbm._model = model
    lgbm._feature_names = feature_names
    lgbm._labeled_X = X.tolist()
    lgbm._labeled_y = y.tolist()
    lgbm._labeled_count = n_samples
    lgbm._is_trained = True


def _inject_trained_meta(ensemble: EnsemblePredictor, n_samples: int = 80) -> None:
    """Inject a trained _ScaledClassifier as ensemble meta-learner."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    rng = np.random.default_rng(7)
    X = rng.random((n_samples, 5)).astype(np.float32)
    y = (X[:, 0] > 0.5).astype(np.int32)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    lr = LogisticRegression(max_iter=200).fit(X_scaled, y)
    ensemble._meta_model = _ScaledClassifier(scaler, lr)
    ensemble._meta_is_trained = True
    ensemble._meta_labeled_count = n_samples


# ── ModelStore tests ──────────────────────────────────────────────────────────

def test_store_save_load_roundtrip(tmp_path):
    store = ModelStore(str(tmp_path))
    data = {"a": 1, "b": [1.0, 2.0, 3.0], "c": None, "nested": {"x": True}}
    assert store.save("test_data", data)
    loaded = store.load("test_data")
    assert loaded == data


def test_store_load_missing_returns_none(tmp_path):
    store = ModelStore(str(tmp_path))
    assert store.load("nonexistent_model") is None


def test_store_record_version_single(tmp_path):
    store = ModelStore(str(tmp_path))
    store.record_version("lgbm", n_samples=500, accuracy=0.54)
    status = store.get_model_status()
    assert "lgbm" in status
    assert status["lgbm"]["n_samples"] == 500
    assert status["lgbm"]["accuracy"] == 0.54
    assert "last_saved" in status["lgbm"]


def test_store_record_version_upserts(tmp_path):
    store = ModelStore(str(tmp_path))
    store.record_version("lgbm", n_samples=500, accuracy=0.54)
    store.record_version("lgbm", n_samples=1000, accuracy=0.56)
    status = store.get_model_status()
    # Should have only the latest entry
    assert status["lgbm"]["n_samples"] == 1000
    assert status["lgbm"]["accuracy"] == 0.56


def test_store_registry_persists_across_instances(tmp_path):
    store1 = ModelStore(str(tmp_path))
    store1.record_version("ensemble", n_samples=300, accuracy=None)

    store2 = ModelStore(str(tmp_path))
    status = store2.get_model_status()
    assert "ensemble" in status
    assert status["ensemble"]["n_samples"] == 300
    assert status["ensemble"]["accuracy"] is None


def test_store_get_model_status_empty(tmp_path):
    store = ModelStore(str(tmp_path))
    assert store.get_model_status() == {}


# ── LGBMPredictor lifecycle tests ─────────────────────────────────────────────

def test_lgbm_save_state_keys():
    lgbm = LGBMPredictor()
    state = lgbm.save_state()
    assert "model" in state
    assert "feature_names" in state
    assert "labeled_count" in state
    assert "is_trained" in state
    assert "importances" in state
    assert "recent_X" in state
    assert "recent_y" in state


def test_lgbm_load_untrained_state():
    lgbm = LGBMPredictor()
    state = lgbm.save_state()
    new_lgbm = LGBMPredictor()
    new_lgbm.load_state(state)
    assert not new_lgbm.is_trained
    assert new_lgbm.labeled_count == 0


def test_lgbm_save_load_preserves_trained_state():
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=120)

    state = lgbm.save_state()
    new_lgbm = LGBMPredictor()
    new_lgbm.load_state(state)

    assert new_lgbm.is_trained
    assert new_lgbm.labeled_count == 120
    assert new_lgbm._feature_names == lgbm._feature_names


def test_lgbm_loaded_model_can_predict():
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=120)

    state = lgbm.save_state()
    new_lgbm = LGBMPredictor()
    new_lgbm.load_state(state)

    features = {f"f_{i}": 0.5 for i in range(20)}
    result = new_lgbm.predict(features)
    assert result is not None
    assert result["is_trained"]
    assert result["direction"] in ("UP", "DOWN")
    assert 0.0 <= result["probability"] <= 1.0


def test_lgbm_rolling_accuracy_untrained_returns_none():
    lgbm = LGBMPredictor()
    assert lgbm.rolling_accuracy() is None


def test_lgbm_rolling_accuracy_insufficient_data_returns_none():
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=50)  # fewer than default n=100
    lgbm._labeled_X = lgbm._labeled_X[:50]
    lgbm._labeled_y = lgbm._labeled_y[:50]
    assert lgbm.rolling_accuracy(n=100) is None


def test_lgbm_rolling_accuracy_returns_valid_float():
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=120)
    acc = lgbm.rolling_accuracy(n=100)
    assert acc is not None
    assert 0.0 <= acc <= 1.0


def test_lgbm_recent_samples_capped_at_500(tmp_path):
    """save_state saves at most 500 recent samples regardless of training set size."""
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=800)
    state = lgbm.save_state()
    assert len(state["recent_X"]) <= 500
    assert len(state["recent_y"]) <= 500


def test_lgbm_full_roundtrip_via_store(tmp_path):
    lgbm = LGBMPredictor()
    _inject_trained_lgbm(lgbm, n_samples=120)

    store = ModelStore(str(tmp_path))
    assert store.save("lgbm", lgbm.save_state())

    new_lgbm = LGBMPredictor()
    state = store.load("lgbm")
    assert state is not None
    new_lgbm.load_state(state)
    assert new_lgbm.is_trained == lgbm.is_trained


# ── VolatilityPredictor lifecycle tests ───────────────────────────────────────

def test_volatility_save_state_keys():
    vol = VolatilityPredictor()
    state = vol.save_state()
    assert "garch_params" in state
    assert "garch_conditional_var" in state


def test_volatility_save_no_data():
    vol = VolatilityPredictor()
    state = vol.save_state()
    assert state["garch_params"] is None
    assert state["garch_conditional_var"] == 0.0


def test_volatility_save_load_preserves_state():
    vol = VolatilityPredictor()
    # Manually inject GARCH params (avoid slow background fitting)
    vol._garch_params = {"omega": 1e-6, "alpha": 0.1, "beta": 0.85}
    vol._garch_conditional_var = 5e-8

    state = vol.save_state()
    new_vol = VolatilityPredictor()
    new_vol.load_state(state)

    assert new_vol._garch_params == vol._garch_params
    assert new_vol._garch_conditional_var == vol._garch_conditional_var


def test_volatility_load_empty_state():
    vol = VolatilityPredictor()
    vol.load_state({})
    assert vol._garch_params is None
    assert vol._garch_conditional_var == 0.0


# ── RegimeClassifier lifecycle tests ─────────────────────────────────────────

def test_regime_save_state_keys():
    regime = RegimeClassifier()
    state = regime.save_state()
    assert "models" in state
    assert "state_maps" in state
    assert "obs_counts" in state


def test_regime_save_load_empty():
    regime = RegimeClassifier()
    state = regime.save_state()
    new_regime = RegimeClassifier()
    new_regime.load_state(state)
    assert len(new_regime._models) == 0
    assert len(new_regime._obs_count) == 0


def test_regime_save_load_preserves_obs_counts():
    regime = RegimeClassifier()
    # Inject some observation counts without needing actual HMM training
    regime._obs_count = {"US:SPY": 300, "US:AAPL": 150}
    state = regime.save_state()

    new_regime = RegimeClassifier()
    new_regime.load_state(state)
    assert new_regime._obs_count == {"US:SPY": 300, "US:AAPL": 150}


def test_regime_full_roundtrip_via_store(tmp_path):
    regime = RegimeClassifier()
    regime._obs_count = {"US:SPY": 500}
    store = ModelStore(str(tmp_path))
    assert store.save("regime", regime.save_state())
    state = store.load("regime")
    assert state is not None
    new_regime = RegimeClassifier()
    new_regime.load_state(state)
    assert new_regime._obs_count.get("US:SPY") == 500


# ── LSTMPredictor lifecycle tests ─────────────────────────────────────────────

def test_lstm_save_state_keys():
    lstm = LSTMPredictor()
    state = lstm.save_state()
    assert "is_trained" in state
    assert "labeled_count" in state
    assert "price_min" in state
    assert "price_max" in state
    assert "net_state" in state


def test_lstm_save_untrained_no_net_state():
    lstm = LSTMPredictor()
    state = lstm.save_state()
    assert state["net_state"] is None
    assert not state["is_trained"]


def test_lstm_load_empty_state():
    lstm = LSTMPredictor()
    lstm.load_state({})
    assert not lstm.is_trained
    assert lstm.labeled_count == 0


def test_lstm_load_state_preserves_scalers():
    lstm = LSTMPredictor()
    lstm._price_min = 95.0
    lstm._price_max = 105.0
    lstm._labeled_count = 250
    # No trained net (skip torch)
    state = lstm.save_state()

    new_lstm = LSTMPredictor()
    new_lstm.load_state(state)
    assert new_lstm._price_min == 95.0
    assert new_lstm._price_max == 105.0
    assert new_lstm._labeled_count == 250


# ── EnsemblePredictor lifecycle tests ────────────────────────────────────────

def test_ensemble_save_state_keys():
    ensemble = EnsemblePredictor()
    state = ensemble.save_state()
    assert "lgbm" in state
    assert "lstm" in state
    assert "vol" in state
    assert "meta_model" in state
    assert "meta_is_trained" in state
    assert "meta_labeled_count" in state


def test_ensemble_save_load_untrained():
    ensemble = EnsemblePredictor()
    state = ensemble.save_state()
    new_ensemble = EnsemblePredictor()
    new_ensemble.load_state(state)
    assert not new_ensemble.lgbm.is_trained
    assert not new_ensemble._meta_is_trained
    assert new_ensemble._meta_labeled_count == 0


def test_ensemble_save_load_with_trained_lgbm():
    ensemble = EnsemblePredictor()
    _inject_trained_lgbm(ensemble.lgbm, n_samples=120)

    state = ensemble.save_state()
    new_ensemble = EnsemblePredictor()
    new_ensemble.load_state(state)

    assert new_ensemble.lgbm.is_trained
    assert new_ensemble.lgbm.labeled_count == 120


def test_ensemble_save_load_with_trained_meta():
    ensemble = EnsemblePredictor()
    _inject_trained_meta(ensemble, n_samples=80)

    state = ensemble.save_state()
    new_ensemble = EnsemblePredictor()
    new_ensemble.load_state(state)

    assert new_ensemble._meta_is_trained
    assert new_ensemble._meta_labeled_count == 80
    assert new_ensemble._meta_model is not None


def test_ensemble_loaded_meta_can_predict():
    ensemble = EnsemblePredictor()
    _inject_trained_lgbm(ensemble.lgbm, n_samples=120)
    _inject_trained_meta(ensemble, n_samples=80)

    state = ensemble.save_state()
    new_ensemble = EnsemblePredictor()
    new_ensemble.load_state(state)

    # Meta-learner should be callable
    import numpy as np
    X_test = [[0.5, 0.5, 0.01, 0.3, 1.0]]
    proba = new_ensemble._meta_model.predict_proba(X_test)
    assert proba.shape == (1, 2)
    assert abs(proba[0].sum() - 1.0) < 1e-6


def test_ensemble_full_roundtrip_via_store(tmp_path):
    ensemble = EnsemblePredictor()
    _inject_trained_lgbm(ensemble.lgbm, n_samples=120)
    _inject_trained_meta(ensemble, n_samples=80)

    store = ModelStore(str(tmp_path))
    assert store.save("ensemble", ensemble.save_state())

    state = store.load("ensemble")
    assert state is not None

    new_ensemble = EnsemblePredictor()
    new_ensemble.load_state(state)
    assert new_ensemble.lgbm.is_trained
    assert new_ensemble._meta_is_trained
