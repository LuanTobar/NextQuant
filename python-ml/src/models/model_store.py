"""
ModelStore — unified persistence, versioning, and status tracking for all ML models.

Responsibilities:
  - Save / load model state dicts using joblib (all models use picklable state)
  - Maintain a registry.json with one record per model: last_saved, n_samples, accuracy
  - Expose get_model_status() for the /health endpoint

Directory layout under base_path/:
  ensemble.pkl   — EnsemblePredictor full state (LGBM + LSTM + Vol + meta)
  regime.pkl     — RegimeClassifier state (GaussianHMM dict per symbol)
  registry.json  — version/accuracy history per model name
"""

from __future__ import annotations

import json
import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class ModelStore:
    """
    Thin persistence layer over joblib + a JSON registry.

    Usage:
        store = ModelStore("/app/models")
        # save
        store.save("ensemble", ensemble.save_state())
        # load
        state = store.load("ensemble")
        if state:
            ensemble.load_state(state)
        # drift / versioning
        store.record_version("ensemble", n_samples=1200, accuracy=0.54)
        # health
        status = store.get_model_status()
    """

    def __init__(self, base_path: str):
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        self._registry_path = self._base / "registry.json"
        self._registry: dict = self._load_registry()

    # ── Save / Load ──────────────────────────────────────────────────────────

    def save(self, name: str, data: Any) -> bool:
        """
        Serialize `data` to {base_path}/{name}.pkl using joblib.
        Returns True on success, False on error (best-effort).
        """
        try:
            import joblib
            path = self._base / f"{name}.pkl"
            joblib.dump(data, path, compress=3)
            logger.debug("ModelStore saved", name=name, path=str(path))
            return True
        except Exception as e:
            logger.warning("ModelStore save failed", name=name, error=str(e))
            return False

    def load(self, name: str) -> Optional[Any]:
        """
        Deserialize {base_path}/{name}.pkl using joblib.
        Returns None if file does not exist or loading fails.
        """
        try:
            import joblib
            path = self._base / f"{name}.pkl"
            if not path.exists():
                return None
            data = joblib.load(path)
            logger.debug("ModelStore loaded", name=name, path=str(path))
            return data
        except Exception as e:
            logger.warning("ModelStore load failed", name=name, error=str(e))
            return None

    # ── Registry / Versioning ─────────────────────────────────────────────────

    def record_version(
        self,
        model_name: str,
        n_samples: int,
        accuracy: Optional[float] = None,
    ) -> None:
        """
        Upsert the registry entry for `model_name` with current timestamp,
        sample count, and optional accuracy. Persists to registry.json.
        """
        self._registry[model_name] = {
            "last_saved": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "n_samples": n_samples,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
        }
        self._save_registry()

    def get_registry(self) -> dict:
        """Return the full registry dict."""
        return dict(self._registry)

    def get_model_status(self) -> dict:
        """
        Return a status dict suitable for the /health endpoint.
        Merges registry data; safe to call with an empty registry.
        """
        return dict(self._registry)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _load_registry(self) -> dict:
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug("Registry load failed, starting fresh", error=str(e))
        return {}

    def _save_registry(self) -> None:
        try:
            self._registry_path.write_text(
                json.dumps(self._registry, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug("Registry persist failed", error=str(e))
