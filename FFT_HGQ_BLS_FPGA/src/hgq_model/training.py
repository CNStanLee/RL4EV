"""Reproducible training loop shared by all HGQ2 regressors."""

from __future__ import annotations

import os

# Keras selects its backend at import time.  The environment variable remains
# overridable, while Torch is a practical default for local and ONNX workflows.
os.environ.setdefault("KERAS_BACKEND", os.environ.get("HGQ_BACKEND", "torch"))

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import hgq
import keras
import numpy as np

from .config import save_json
from .data import load_dataset
from .models import ModelConfig, build_model


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int = 80
    batch_size: int = 128
    learning_rate: float = 2.0e-3
    weight_decay: float = 1.0e-5
    patience: int = 12
    reduce_lr_patience: int = 5
    min_learning_rate: float = 1.0e-5
    seed: int = 2026
    verbose: int = 2
    loss: str = "huber"

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> TrainingConfig:
        return cls(**dict(values or {}))


def _history_to_json(history: keras.callbacks.History) -> dict[str, list[float]]:
    return {key: [float(item) for item in values] for key, values in history.history.items()}


def _split_array(split: Any, name: str) -> np.ndarray:
    if hasattr(split, name):
        return np.asarray(getattr(split, name))
    return np.asarray(split[name])


def train_model(
    model_name: str,
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    model_config: ModelConfig | dict[str, Any] | None = None,
    training_config: TrainingConfig | dict[str, Any] | None = None,
) -> tuple[keras.Model, dict[str, Any]]:
    """Train one architecture and save its best checkpoint and metadata."""

    model_config = model_config if isinstance(model_config, ModelConfig) else ModelConfig.from_dict(model_config)
    training_config = (
        training_config if isinstance(training_config, TrainingConfig) else TrainingConfig.from_dict(training_config)
    )
    if model_config.window_size <= 0 or model_config.output_dim != 8:
        raise ValueError("The deployment contract requires a positive window and exactly 8 outputs")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    keras.utils.set_random_seed(training_config.seed)
    np.random.seed(training_config.seed)

    splits = load_dataset(dataset_path)
    train_split = splits["train"]
    val_split = splits["val"]
    x_train = _split_array(train_split, "waveform_norm").astype(np.float32, copy=False)
    y_train = _split_array(train_split, "target").astype(np.float32, copy=False)
    x_val = _split_array(val_split, "waveform_norm").astype(np.float32, copy=False)
    y_val = _split_array(val_split, "target").astype(np.float32, copy=False)

    if x_train.shape[1:] != (model_config.window_size, 1):
        raise ValueError(
            f"Dataset input shape {x_train.shape[1:]} does not match model shape {(model_config.window_size, 1)}"
        )
    if y_train.shape[1:] != (model_config.output_dim,):
        raise ValueError(f"Dataset target shape {y_train.shape[1:]} does not match {(model_config.output_dim,)}")

    model = build_model(model_name, model_config)
    optimizer = keras.optimizers.AdamW(
        learning_rate=training_config.learning_rate,
        weight_decay=training_config.weight_decay,
        clipnorm=1.0,
    )
    if training_config.loss == "mse":
        loss = keras.losses.MeanSquaredError()
    elif training_config.loss == "huber":
        loss = keras.losses.Huber(delta=0.2)
    else:
        raise ValueError("training loss must be 'huber' or 'mse'")
    model.compile(
        optimizer=optimizer,
        loss=loss,
        metrics=[keras.metrics.MeanAbsoluteError(name="complex_mae")],
        jit_compile=False,
    )

    checkpoint_path = output_dir / "model.keras"
    callbacks: list[keras.callbacks.Callback] = [
        keras.callbacks.TerminateOnNaN(),
        keras.callbacks.ModelCheckpoint(
            checkpoint_path,
            monitor="val_loss",
            mode="min",
            save_best_only=True,
            verbose=0,
        ),
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            mode="min",
            patience=training_config.patience,
            restore_best_weights=True,
            verbose=1 if training_config.verbose else 0,
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            mode="min",
            factor=0.5,
            patience=training_config.reduce_lr_patience,
            min_lr=training_config.min_learning_rate,
            verbose=1 if training_config.verbose else 0,
        ),
        keras.callbacks.CSVLogger(output_dir / "history.csv"),
    ]

    started = time.perf_counter()
    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=training_config.epochs,
        batch_size=training_config.batch_size,
        shuffle=True,
        callbacks=callbacks,
        verbose=training_config.verbose,
    )
    training_seconds = time.perf_counter() - started

    # ModelCheckpoint already wrote the best epoch; load it so returned and
    # subsequently evaluated weights exactly match the artifact on disk.
    model = keras.models.load_model(checkpoint_path, compile=False)
    history_json = _history_to_json(history)
    best_epoch = int(np.argmin(history_json["val_loss"]) + 1)
    metadata = {
        "model": model_name,
        "model_config": model_config.to_dict(),
        "training_config": asdict(training_config),
        "backend": keras.backend.backend(),
        "keras_version": keras.__version__,
        "hgq2_version": getattr(hgq, "__version__", "unknown"),
        "dataset": str(Path(dataset_path).resolve()),
        "train_examples": int(x_train.shape[0]),
        "validation_examples": int(x_val.shape[0]),
        "best_epoch": best_epoch,
        "best_val_loss": float(min(history_json["val_loss"])),
        "training_seconds": float(training_seconds),
        "total_parameter_variables": int(model.count_params()),
        "trainable_parameter_values": int(sum(int(np.prod(variable.shape)) for variable in model.trainable_variables)),
    }
    save_json(output_dir / "history.json", history_json)
    save_json(output_dir / "metadata.json", metadata)
    return model, metadata
