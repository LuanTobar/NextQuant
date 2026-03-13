"""
LSTM sequence predictor for return direction.

Architecture:
  - 2-layer LSTM (64 hidden units per layer) with dropout 0.2
  - Input: last `window` normalized close prices (MinMaxScaler per symbol)
  - Target: binary UP/DOWN of next return
  - Retrains every `retrain_every` new observations in a background thread

Output:
  {
    "predicted_return": float,     # expected normalized return
    "direction": "UP" | "DOWN",
    "confidence": float,           # sigmoid output [0, 1]
    "hidden_embedding": list[float],  # last hidden state (64 dims)
    "is_trained": bool,
  }

Note: PyTorch is imported lazily so the module loads even if torch
is not installed — callers receive is_trained=False gracefully.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()

# Lazy torch imports — resolved once at first use
_torch_available: Optional[bool] = None


def _check_torch() -> bool:
    global _torch_available
    if _torch_available is None:
        try:
            import torch  # noqa: F401
            _torch_available = True
        except ImportError:
            _torch_available = False
            logger.warning("PyTorch not installed — LSTMPredictor will return None")
    return _torch_available


class _LSTMNet:
    """Wrapper that keeps all torch objects inside to avoid import errors."""

    def __init__(self, input_size: int, hidden_size: int = 64, num_layers: int = 2, dropout: float = 0.2):
        import torch
        import torch.nn as nn

        class _Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=input_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0.0,
                )
                self.dropout = nn.Dropout(dropout)
                self.fc = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, (h, _) = self.lstm(x)
                last_hidden = h[-1]               # (batch, hidden_size)
                out_last = out[:, -1, :]           # (batch, hidden_size)
                logit = self.fc(self.dropout(out_last))
                return torch.sigmoid(logit), last_hidden

        self.net = _Net()
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        self.criterion = torch.nn.BCELoss()
        self.hidden_size = hidden_size

    def train_step(self, X: np.ndarray, y: np.ndarray) -> float:
        import torch
        self.net.train()
        X_t = torch.tensor(X, dtype=torch.float32).unsqueeze(-1)  # (N, window, 1)
        y_t = torch.tensor(y, dtype=torch.float32).unsqueeze(-1)  # (N, 1)
        self.optimizer.zero_grad()
        preds, _ = self.net(X_t)
        loss = self.criterion(preds, y_t)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
        self.optimizer.step()
        return float(loss.item())

    def predict(self, x: np.ndarray) -> tuple[float, list[float]]:
        import torch
        self.net.eval()
        with torch.no_grad():
            X_t = torch.tensor(x, dtype=torch.float32).unsqueeze(0).unsqueeze(-1)  # (1, window, 1)
            prob, hidden = self.net(X_t)
            return float(prob.item()), hidden[0].tolist()


class LSTMPredictor:
    """
    Streaming LSTM binary direction predictor.

    Buffers the last `window` close prices per symbol.
    Self-labels: after `horizon_bars` ticks, pairs historical windows
    with realized return direction and trains incrementally.
    """

    def __init__(
        self,
        window: int = 60,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
        retrain_every: int = 2_000,
        horizon_bars: int = 60,
        max_labeled: int = 10_000,
    ):
        self.window = window
        self.retrain_every = retrain_every
        self.horizon_bars = horizon_bars
        self.max_labeled = max_labeled
        self._hidden_size = hidden_size
        self._num_layers = num_layers
        self._dropout = dropout

        # Per-symbol price buffer (normalized)
        self._price_buffer: deque[float] = deque(maxlen=window + horizon_bars + 10)
        # Pending: (price_at_t, window_at_t)
        self._pending: deque[tuple[float, np.ndarray]] = deque()
        # Labeled training data
        self._X: list[np.ndarray] = []
        self._y: list[int] = []

        self._obs_count: int = 0
        self._labeled_count: int = 0
        self._model: Optional[_LSTMNet] = None
        self._is_trained: bool = False
        self._lock = threading.Lock()

        # Min/Max scaler state
        self._price_min: float = 0.0
        self._price_max: float = 1.0

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(self, price: float) -> None:
        """Add a new close price observation."""
        if not _check_torch() or price <= 0:
            return

        self._price_buffer.append(price)
        self._obs_count += 1

        # Update scaler bounds (running min/max)
        prices = list(self._price_buffer)
        p_min = min(prices)
        p_max = max(prices)
        if p_max > p_min:
            self._price_min = p_min
            self._price_max = p_max

        # Only start labeling once we have a full window
        if len(self._price_buffer) >= self.window:
            norm_window = self._normalize(np.array(list(self._price_buffer)[-self.window:]))
            self._pending.append((price, norm_window))

        # Label matured pending observations
        while len(self._pending) > self.horizon_bars:
            old_price, old_window = self._pending.popleft()
            future_return = (price - old_price) / old_price if old_price > 0 else 0
            label = 1 if future_return > 0 else 0
            self._X.append(old_window)
            self._y.append(label)
            self._labeled_count += 1

        # Cap buffer
        if len(self._X) > self.max_labeled:
            excess = len(self._X) - self.max_labeled
            self._X = self._X[excess:]
            self._y = self._y[excess:]

        # Retrain trigger
        if self._labeled_count > 0 and self._labeled_count % self.retrain_every == 0:
            threading.Thread(target=self._retrain, daemon=True).start()

    def predict(self, price: Optional[float] = None) -> Optional[dict]:
        """
        Predict direction from the current price window.
        Returns None if model not trained yet or torch unavailable.
        """
        if not _check_torch() or not self._is_trained or self._model is None:
            return None

        if len(self._price_buffer) < self.window:
            return None

        try:
            norm_window = self._normalize(np.array(list(self._price_buffer)[-self.window:]))
            confidence, hidden = self._model.predict(norm_window)

            # Interpret confidence as P(UP)
            direction = "UP" if confidence >= 0.5 else "DOWN"
            # Approximate return from confidence
            predicted_return = (confidence - 0.5) * 0.02  # [-1%, +1%] range

            return {
                "predicted_return": round(predicted_return, 8),
                "direction": direction,
                "confidence": round(confidence, 6),
                "hidden_embedding": [round(v, 4) for v in hidden[:16]],  # first 16 dims
                "is_trained": True,
            }
        except Exception as e:
            logger.warning("LSTM predict error", error=str(e))
            return None

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def labeled_count(self) -> int:
        return self._labeled_count

    # ── Lifecycle: persist / restore ─────────────────────────────────────────

    def save_state(self) -> dict:
        """
        Return a picklable snapshot.
        Torch tensors are converted to numpy so joblib can serialize
        without a torch version dependency at unpickling time.
        """
        net_state: Optional[dict] = None
        if self._model is not None and self._is_trained:
            try:
                import torch  # noqa: F401
                net_state = {
                    k: v.cpu().numpy()
                    for k, v in self._model.net.state_dict().items()
                }
            except Exception as e:
                logger.warning("LSTM state_dict export failed", error=str(e))

        return {
            "is_trained": self._is_trained,
            "labeled_count": self._labeled_count,
            "price_min": self._price_min,
            "price_max": self._price_max,
            "net_state": net_state,
        }

    def load_state(self, state: dict) -> None:
        """
        Restore model state. Reconstructs _LSTMNet from saved weights.
        Silently skips if torch is unavailable or state is empty.
        """
        self._labeled_count = state.get("labeled_count", 0)
        self._price_min = state.get("price_min", 0.0)
        self._price_max = state.get("price_max", 1.0)

        net_state = state.get("net_state")
        if net_state and state.get("is_trained"):
            if not _check_torch():
                logger.warning("LSTM load_state: torch unavailable, skipping weights")
                return
            try:
                import torch
                self._model = _LSTMNet(
                    input_size=1,
                    hidden_size=self._hidden_size,
                    num_layers=self._num_layers,
                    dropout=self._dropout,
                )
                torch_state = {k: torch.from_numpy(v) for k, v in net_state.items()}
                self._model.net.load_state_dict(torch_state)
                self._model.net.eval()
                self._is_trained = True
            except Exception as e:
                logger.warning("LSTM load_state failed, starting fresh", error=str(e))
                self._model = None
                self._is_trained = False
        else:
            self._is_trained = False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _normalize(self, prices: np.ndarray) -> np.ndarray:
        p_range = self._price_max - self._price_min
        if p_range > 0:
            return (prices - self._price_min) / p_range
        return np.zeros_like(prices)

    def _retrain(self) -> None:
        """Train the LSTM on the accumulated labeled sequences (background thread)."""
        try:
            X = np.array(self._X, dtype=np.float32)
            y = np.array(self._y, dtype=np.float32)

            if len(X) < 100 or len(np.unique(y)) < 2:
                return

            with self._lock:
                if self._model is None:
                    self._model = _LSTMNet(
                        input_size=1,
                        hidden_size=self._hidden_size,
                        num_layers=self._num_layers,
                        dropout=self._dropout,
                    )

            # Mini-batch training (3 epochs over all data)
            batch_size = 64
            n = len(X)
            total_loss = 0.0
            n_batches = 0

            for _ in range(3):
                indices = np.random.permutation(n)
                for start in range(0, n, batch_size):
                    batch_idx = indices[start:start + batch_size]
                    loss = self._model.train_step(X[batch_idx], y[batch_idx])
                    total_loss += loss
                    n_batches += 1

            with self._lock:
                self._is_trained = True

            logger.info(
                "LSTM retrained",
                n_samples=n,
                avg_loss=round(total_loss / max(n_batches, 1), 4),
                labeled_total=self._labeled_count,
            )

        except Exception as e:
            logger.error("LSTM retrain failed", error=str(e))
