"""Deterministic synthetic harmonic-waveform dataset generation.

The four dataset splits are generated from independent random streams and
scenario namespaces.  ``train``, ``val``, and ``test_id`` share an in-domain
distribution while ``test_ood`` deliberately combines frequency, noise,
front-end, interference, quantization, and clipping shifts.

Only NumPy and the Python standard library are used here.  This keeps data
generation usable on machines that do not have Keras/HGQ2 installed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .contract import (
    FS_HZ,
    HARMONICS,
    ORDER_SCALES,
    WINDOW_SIZE,
    encode_targets,
    wrap_phase,
)

DATASET_FORMAT_VERSION = "1.0"
SPLIT_NAMES = ("train", "val", "test_id", "test_ood")
_SPLIT_STREAM_IDS = {"train": 11, "val": 23, "test_id": 37, "test_ood": 53}


@dataclass(frozen=True)
class DatasetConfig:
    """Dataset sizes and reproducibility controls.

    The signal contract itself is intentionally not configurable: every model
    and generated artifact uses 4 kHz, 80 samples, and harmonics 1/3/5/7.
    """

    seed: int = 20_260_803
    n_train: int = 12_000
    n_val: int = 2_000
    n_test_id: int = 2_000
    n_test_ood: int = 4_000
    samples_per_scenario: int = 8
    normalization_floor: float = 1.0e-7

    def __post_init__(self) -> None:
        if int(self.seed) != self.seed or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        object.__setattr__(self, "seed", int(self.seed))
        for name in ("n_train", "n_val", "n_test_id", "n_test_ood"):
            value = getattr(self, name)
            if int(value) != value or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            object.__setattr__(self, name, int(value))
        if int(self.samples_per_scenario) != self.samples_per_scenario:
            raise ValueError("samples_per_scenario must be an integer")
        if self.samples_per_scenario <= 0:
            raise ValueError("samples_per_scenario must be positive")
        object.__setattr__(self, "samples_per_scenario", int(self.samples_per_scenario))
        if not np.isfinite(self.normalization_floor) or self.normalization_floor <= 0:
            raise ValueError("normalization_floor must be finite and positive")
        object.__setattr__(self, "normalization_floor", float(self.normalization_floor))

    @property
    def split_sizes(self) -> dict[str, int]:
        return {
            "train": int(self.n_train),
            "val": int(self.n_val),
            "test_id": int(self.n_test_id),
            "test_ood": int(self.n_test_ood),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> DatasetConfig:
        """Parse flat or nested JSON-style configuration mappings.

        Accepted size forms include ``n_train``, ``train_size``, and a nested
        ``"splits": {"train": ...}`` (``"sizes"`` is also accepted).
        A top-level ``"dataset"`` object may be used by larger pipeline
        configuration files.
        """

        if values is None:
            return cls()
        document = dict(values)
        if "dataset" in document:
            nested = document.pop("dataset")
            if not isinstance(nested, Mapping):
                raise ValueError("config field 'dataset' must be a JSON object")
            # A pipeline document may contain model/training/path sections
            # beside this one; they must not leak into DatasetConfig.
            document = dict(nested)

        for container_name in ("splits", "sizes", "split_sizes"):
            if container_name in document:
                sizes = document.pop(container_name)
                if not isinstance(sizes, Mapping):
                    raise ValueError(f"config field {container_name!r} must be an object")
                for split_name, value in sizes.items():
                    key = f"n_{split_name}"
                    if key in document and document[key] != value:
                        raise ValueError(f"conflicting values for {key}")
                    document[key] = value

        aliases = {
            "train_size": "n_train",
            "val_size": "n_val",
            "test_id_size": "n_test_id",
            "test_ood_size": "n_test_ood",
            "scenario_size": "samples_per_scenario",
        }
        for alias, canonical in aliases.items():
            if alias in document:
                value = document.pop(alias)
                if canonical in document and document[canonical] != value:
                    raise ValueError(f"conflicting values for {canonical}")
                document[canonical] = value

        # Permit a config to state the immutable contract, but reject mismatch.
        contract_fields = {
            "fs_hz": FS_HZ,
            "window_size": WINDOW_SIZE,
            "harmonics": HARMONICS.tolist(),
            "order_scales": ORDER_SCALES.tolist(),
        }
        for key, expected in contract_fields.items():
            if key not in document:
                continue
            actual = document.pop(key)
            actual_array = np.asarray(actual)
            expected_array = np.asarray(expected)
            if actual_array.shape != expected_array.shape or not np.allclose(
                actual_array, expected_array, rtol=0.0, atol=1e-12
            ):
                raise ValueError(f"{key} is fixed by the model contract to {expected}")

        document.pop("output", None)
        document.pop("output_path", None)
        document.pop("compression", None)
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(document) - allowed)
        if unknown:
            raise ValueError(f"unknown dataset config fields: {', '.join(unknown)}")
        return cls(**document)


@dataclass(frozen=True)
class SplitData:
    """Arrays belonging to one leakage-isolated dataset split."""

    waveform_norm: NDArray[np.float32]
    target: NDArray[np.float32]
    scale: NDArray[np.float32]
    amplitude: NDArray[np.float32]
    phase_end: NDArray[np.float32]
    phase_relative: NDArray[np.float32]
    f0: NDArray[np.float32]
    clean_waveform: NDArray[np.float32]
    raw_waveform: NDArray[np.float32]
    scenario_id: NDArray[np.str_]

    def __len__(self) -> int:
        return int(self.waveform_norm.shape[0])

    @property
    def x(self) -> NDArray[np.float32]:
        """Training-input alias."""

        return self.waveform_norm

    @property
    def y(self) -> NDArray[np.float32]:
        """Training-target alias."""

        return self.target

    @property
    def normalized(self) -> NDArray[np.float32]:
        return self.waveform_norm

    @property
    def clean(self) -> NDArray[np.float32]:
        return self.clean_waveform

    @property
    def raw(self) -> NDArray[np.float32]:
        return self.raw_waveform

    @property
    def amp(self) -> NDArray[np.float32]:
        return self.amplitude

    @property
    def scenario(self) -> NDArray[np.str_]:
        return self.scenario_id

    def validate(self) -> None:
        n_samples = len(self)
        expected_shapes = {
            "waveform_norm": (n_samples, WINDOW_SIZE, 1),
            "target": (n_samples, 2 * HARMONICS.size),
            "scale": (n_samples,),
            "amplitude": (n_samples, HARMONICS.size),
            "phase_end": (n_samples, HARMONICS.size),
            "phase_relative": (n_samples, HARMONICS.size),
            "f0": (n_samples,),
            "clean_waveform": (n_samples, WINDOW_SIZE),
            "raw_waveform": (n_samples, WINDOW_SIZE),
            "scenario_id": (n_samples,),
        }
        for name, expected in expected_shapes.items():
            value = np.asarray(getattr(self, name))
            if value.shape != expected:
                raise ValueError(f"{name} has shape {value.shape}; expected {expected}")
            if value.dtype == object:
                raise ValueError(f"{name} must not use object dtype (pickle is forbidden)")
            if name != "scenario_id" and not np.all(np.isfinite(value)):
                raise ValueError(f"{name} contains non-finite values")
        if np.any(self.scale <= 0.0):
            raise ValueError("scale must be strictly positive")
        if np.any(self.amplitude < 0.0):
            raise ValueError("amplitude must be non-negative")
        if np.max(np.abs(self.waveform_norm)) > 1.000_01:
            raise ValueError("waveform_norm must lie within [-1, 1]")


def _scenario_index(n_samples: int, samples_per_scenario: int) -> tuple[NDArray[np.int64], int]:
    index = np.arange(n_samples, dtype=np.int64) // samples_per_scenario
    return index, int(index[-1]) + 1


def _log_uniform(
    rng: np.random.Generator,
    low: float,
    high: float,
    size: int | tuple[int, ...],
) -> NDArray[np.float64]:
    return np.exp(rng.uniform(np.log(low), np.log(high), size=size))


def _independent_rng(seed: int, split_name: str) -> np.random.Generator:
    # Split IDs are constants rather than Python hashes, which are process-randomized.
    seed_words = (seed & 0xFFFF_FFFF, seed >> 32, _SPLIT_STREAM_IDS[split_name])
    return np.random.default_rng(np.random.SeedSequence(seed_words))


def _add_interference(
    analog: NDArray[np.float64],
    *,
    rng: np.random.Generator,
    f0: NDArray[np.float64],
    fundamental_amplitude: NDArray[np.float64],
    time_from_end: NDArray[np.float64],
    ood: bool,
) -> None:
    """Add non-target integer harmonics and interharmonics in place."""

    n_samples = analog.shape[0]
    extra_orders = (2, 4, 6, 9) if not ood else (2, 4, 6, 8, 9, 11)
    extra_max = 0.035 if not ood else 0.16
    for order in extra_orders:
        extra_amplitude = fundamental_amplitude * extra_max * rng.beta(1.2, 3.0, n_samples)
        extra_phase = rng.uniform(-np.pi, np.pi, n_samples)
        angle = 2.0 * np.pi * order * f0[:, None] * time_from_end[None, :] + extra_phase[:, None]
        analog += extra_amplitude[:, None] * np.sin(angle)

    interharmonic_count = 1 if not ood else 3
    interharmonic_max = 0.025 if not ood else 0.12
    for _ in range(interharmonic_count):
        frequency_ratio = rng.uniform(0.45, 9.5 if not ood else 12.5, n_samples)
        # Keep the nuisance tone distinguishable from all regression targets.
        nearest_distance = np.min(np.abs(frequency_ratio[:, None] - HARMONICS[None, :]), axis=1)
        too_close = nearest_distance < 0.22
        frequency_ratio[too_close] += 0.45
        extra_amplitude = fundamental_amplitude * interharmonic_max * rng.beta(1.25, 2.5, n_samples)
        extra_phase = rng.uniform(-np.pi, np.pi, n_samples)
        angle = 2.0 * np.pi * frequency_ratio[:, None] * f0[:, None] * time_from_end[None, :] + extra_phase[:, None]
        analog += extra_amplitude[:, None] * np.sin(angle)


def _colored_unit_noise(
    rng: np.random.Generator,
    n_samples: int,
    scenario_index: NDArray[np.int64],
    n_scenarios: int,
    *,
    ood: bool,
) -> NDArray[np.float64]:
    white = rng.normal(size=(n_samples, WINDOW_SIZE))
    rho_range = (0.0, 0.35) if not ood else (0.35, 0.92)
    rho = rng.uniform(*rho_range, n_scenarios)[scenario_index]
    innovation_scale = np.sqrt(np.maximum(1.0 - rho * rho, 1.0e-6))
    for sample_index in range(1, WINDOW_SIZE):
        white[:, sample_index] = rho * white[:, sample_index - 1] + innovation_scale * white[:, sample_index]
    rms = np.sqrt(np.mean(np.square(white), axis=1))
    return white / np.maximum(rms[:, None], 1.0e-12)


def _generate_split(
    split_name: str,
    n_samples: int,
    config: DatasetConfig,
) -> SplitData:
    rng = _independent_rng(config.seed, split_name)
    ood = split_name == "test_ood"
    scenario_index, n_scenarios = _scenario_index(n_samples, config.samples_per_scenario)

    if ood:
        low_side = rng.random(n_scenarios) < 0.5
        f0_scenario = np.where(
            low_side,
            rng.uniform(46.0, 48.5, n_scenarios),
            rng.uniform(51.5, 54.0, n_scenarios),
        )
        base_gain = _log_uniform(rng, 0.18, 3.8, n_scenarios)
        ratio_multiplier = rng.uniform(0.65, 2.0, (n_scenarios, 3))
    else:
        f0_scenario = rng.uniform(49.0, 51.0, n_scenarios)
        base_gain = _log_uniform(rng, 0.45, 2.4, n_scenarios)
        ratio_multiplier = rng.beta(1.3, 2.8, (n_scenarios, 3))

    f0 = f0_scenario[scenario_index]
    fundamental_amplitude = base_gain[scenario_index] * np.exp(rng.normal(0.0, 0.035 if not ood else 0.09, n_samples))
    amplitude = np.empty((n_samples, HARMONICS.size), dtype=np.float64)
    amplitude[:, 0] = fundamental_amplitude
    amplitude[:, 1:] = (
        fundamental_amplitude[:, None]
        * ORDER_SCALES[None, 1:]
        * ratio_multiplier[scenario_index]
        * np.exp(rng.normal(0.0, 0.06 if not ood else 0.12, (n_samples, 3)))
    )

    fundamental_phase = rng.uniform(-np.pi, np.pi, n_samples)
    phase_relative = np.empty_like(amplitude)
    phase_relative[:, 0] = 0.0
    phase_relative[:, 1:] = rng.uniform(-np.pi, np.pi, (n_samples, 3))
    phase_end = wrap_phase(fundamental_phase[:, None] * HARMONICS[None, :] + phase_relative)
    # Recompute after wrapping so the stored value exactly follows the contract.
    phase_relative = wrap_phase(phase_end - phase_end[:, :1] * HARMONICS[None, :])

    time_from_end = (np.arange(WINDOW_SIZE, dtype=np.float64) - (WINDOW_SIZE - 1)) / FS_HZ
    harmonic_angle = (
        2.0 * np.pi * f0[:, None, None] * HARMONICS[None, :, None] * time_from_end[None, None, :]
        + phase_end[:, :, None]
    )
    clean = np.sum(amplitude[:, :, None] * np.sin(harmonic_angle), axis=1)
    analog = clean.copy()
    _add_interference(
        analog,
        rng=rng,
        f0=f0,
        fundamental_amplitude=fundamental_amplitude,
        time_from_end=time_from_end,
        ood=ood,
    )

    trend_axis = np.linspace(-1.0, 1.0, WINDOW_SIZE, dtype=np.float64)
    if ood:
        dc_fraction = rng.uniform(-0.35, 0.35, n_scenarios)[scenario_index]
        linear_fraction = rng.uniform(-0.28, 0.28, n_scenarios)[scenario_index]
        quadratic_fraction = rng.uniform(-0.16, 0.16, n_scenarios)[scenario_index]
    else:
        dc_fraction = rng.uniform(-0.08, 0.08, n_scenarios)[scenario_index]
        linear_fraction = rng.uniform(-0.045, 0.045, n_scenarios)[scenario_index]
        quadratic_fraction = rng.uniform(-0.015, 0.015, n_scenarios)[scenario_index]
    analog += fundamental_amplitude[:, None] * (
        dc_fraction[:, None]
        + linear_fraction[:, None] * trend_axis[None, :]
        + quadratic_fraction[:, None] * (np.square(trend_axis[None, :]) - 1.0 / 3.0)
    )

    snr_bounds = (11.0, 30.0) if ood else (33.0, 62.0)
    snr_db = rng.uniform(*snr_bounds, n_scenarios)[scenario_index]
    noise = _colored_unit_noise(
        rng,
        n_samples,
        scenario_index,
        n_scenarios,
        ood=ood,
    )
    clean_rms = np.sqrt(np.mean(np.square(clean), axis=1))
    noise_rms = clean_rms / np.power(10.0, snr_db / 20.0)
    analog += noise * noise_rms[:, None]
    if ood:
        impulse_mask = rng.random((n_samples, WINDOW_SIZE)) < 0.012
        impulses = rng.normal(size=(n_samples, WINDOW_SIZE))
        analog += impulse_mask * impulses * fundamental_amplitude[:, None] * 0.22

    if ood:
        adc_bits = rng.integers(7, 11, n_scenarios)[scenario_index]
        clip_factor = rng.uniform(0.48, 0.92, n_scenarios)[scenario_index]
    else:
        adc_bits = rng.integers(11, 17, n_scenarios)[scenario_index]
        clip_factor = rng.uniform(0.92, 1.35, n_scenarios)[scenario_index]
    analog_peak = np.max(np.abs(analog), axis=1)
    clip_level = np.maximum(analog_peak * clip_factor, config.normalization_floor)
    quantization_levels = np.power(2.0, adc_bits - 1) - 1.0
    adc_normalized = np.clip(analog / clip_level[:, None], -1.0, 1.0)
    raw = np.rint(adc_normalized * quantization_levels[:, None]) / quantization_levels[:, None] * clip_level[:, None]
    scale = np.maximum(np.max(np.abs(raw), axis=1), config.normalization_floor)
    waveform_norm = (raw / scale[:, None])[..., None]
    target = encode_targets(amplitude, phase_end, scale)

    scenario_id = np.asarray(
        [f"{split_name}/scenario-{scenario_number:08d}" for scenario_number in scenario_index],
        dtype="<U40",
    )
    split = SplitData(
        waveform_norm=np.asarray(waveform_norm, dtype=np.float32),
        target=np.asarray(target, dtype=np.float32),
        scale=np.asarray(scale, dtype=np.float32),
        amplitude=np.asarray(amplitude, dtype=np.float32),
        phase_end=np.asarray(phase_end, dtype=np.float32),
        phase_relative=np.asarray(phase_relative, dtype=np.float32),
        f0=np.asarray(f0, dtype=np.float32),
        clean_waveform=np.asarray(clean, dtype=np.float32),
        raw_waveform=np.asarray(raw, dtype=np.float32),
        scenario_id=scenario_id,
    )
    split.validate()
    return split


def generate_dataset(
    config: DatasetConfig | Mapping[str, Any] | None = None,
) -> dict[str, SplitData]:
    """Generate all four deterministic, scenario-disjoint splits."""

    if not isinstance(config, DatasetConfig):
        config = DatasetConfig.from_mapping(config)
    return {
        split_name: _generate_split(split_name, n_samples, config)
        for split_name, n_samples in config.split_sizes.items()
    }


def load_config_json(path: str | Path) -> DatasetConfig:
    """Load a :class:`DatasetConfig` from a UTF-8 JSON document."""

    config_path = Path(path)
    with config_path.open(encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, Mapping):
        raise ValueError("dataset config JSON root must be an object")
    return DatasetConfig.from_mapping(document)


def generate_from_config(
    config: DatasetConfig | Mapping[str, Any] | str | Path,
    output_path: str | Path | None = None,
) -> dict[str, SplitData]:
    """Generate from an object/mapping/JSON path and optionally save an NPZ.

    If a JSON/mapping contains ``output`` or ``output_path``, that value is
    used when the explicit ``output_path`` argument is omitted.
    """

    inferred_output: str | Path | None = None
    if isinstance(config, (str, Path)):
        with Path(config).open(encoding="utf-8") as stream:
            document = json.load(stream)
        if not isinstance(document, Mapping):
            raise ValueError("dataset config JSON root must be an object")
        inferred_output = document.get("output_path", document.get("output"))
        parsed_config = DatasetConfig.from_mapping(document)
    elif isinstance(config, DatasetConfig):
        parsed_config = config
    else:
        inferred_output = config.get("output_path", config.get("output"))
        parsed_config = DatasetConfig.from_mapping(config)

    dataset = generate_dataset(parsed_config)
    destination = output_path if output_path is not None else inferred_output
    if destination is not None:
        save_dataset(destination, dataset, config=parsed_config)
    return dataset


_STORAGE_FIELDS = {
    "normalized": "waveform_norm",
    "target": "target",
    "scale": "scale",
    "amp": "amplitude",
    "phase_end": "phase_end",
    "phase_relative": "phase_relative",
    "f0": "f0",
    "clean": "clean_waveform",
    "raw": "raw_waveform",
    "scenario": "scenario_id",
}


def dataset_metadata(config: DatasetConfig | None = None) -> dict[str, Any]:
    """Return JSON-serializable provenance and contract metadata."""

    metadata: dict[str, Any] = {
        "format_version": DATASET_FORMAT_VERSION,
        "generator": "hgq_model.data",
        "numpy_version": np.__version__,
        "fs_hz": FS_HZ,
        "window_size": WINDOW_SIZE,
        "harmonics": HARMONICS.tolist(),
        "order_scales": ORDER_SCALES.tolist(),
        "target_order": ["c1", "s1", "c3", "s3", "c5", "s5", "c7", "s7"],
        "phase_reference": "window_last_sample",
        "relative_phase": "wrap(psi_h - h * psi_1)",
        "normalization": "normalized = raw / max(abs(raw)); target uses the same scale",
        "array_key_pattern": "{split}_{field}",
        "array_fields": list(_STORAGE_FIELDS),
        "clean_definition": "sum of only the labeled 1/3/5/7 sine harmonics",
        "raw_definition": "clean plus nuisance, noise, drift, clipping, and ADC quantization",
        "splits": list(SPLIT_NAMES),
        "split_policy": "independent RNG streams and disjoint scenario namespaces",
        "test_ood_shift": {
            "f0_hz": "[46, 48.5] union [51.5, 54] versus ID [49, 51]",
            "noise": "lower SNR, stronger colored noise, and impulses",
            "nuisance": "larger DC/drift, non-target harmonics, and interharmonics",
            "adc": "7-10 bit and systematic clipping versus ID 11-16 bit/mild clipping",
        },
    }
    if config is not None:
        metadata["config"] = config.to_dict()
    return metadata


def save_dataset(
    path: str | Path,
    dataset: Mapping[str, SplitData],
    *,
    config: DatasetConfig | None = None,
    compressed: bool = True,
) -> Path:
    """Save an NPZ that is fully readable with ``allow_pickle=False``."""

    destination = Path(path)
    if destination.suffix.lower() != ".npz":
        destination = destination.with_suffix(".npz")
    destination.parent.mkdir(parents=True, exist_ok=True)
    missing = [name for name in SPLIT_NAMES if name not in dataset]
    if missing:
        raise ValueError(f"dataset is missing splits: {', '.join(missing)}")

    arrays: dict[str, NDArray[Any]] = {
        "format_version": np.asarray(DATASET_FORMAT_VERSION),
        "metadata_json": np.asarray(json.dumps(dataset_metadata(config), sort_keys=True, separators=(",", ":"))),
        "split_names": np.asarray(SPLIT_NAMES),
        "fs_hz": np.asarray(FS_HZ, dtype=np.float64),
        "window_size": np.asarray(WINDOW_SIZE, dtype=np.int64),
        "harmonics": HARMONICS.copy(),
        "order_scales": ORDER_SCALES.copy(),
    }
    for split_name in SPLIT_NAMES:
        split = dataset[split_name]
        split.validate()
        for storage_name, attribute_name in _STORAGE_FIELDS.items():
            value = np.asarray(getattr(split, attribute_name))
            if value.dtype == object:
                raise ValueError(f"{split_name}.{attribute_name} has object dtype; pickle is forbidden")
            arrays[f"{split_name}_{storage_name}"] = value

    saver = np.savez_compressed if compressed else np.savez
    saver(destination, **arrays)
    return destination


def load_dataset(path: str | Path) -> dict[str, SplitData]:
    """Load and validate a saved dataset without enabling pickle."""

    result: dict[str, SplitData] = {}
    with np.load(Path(path), allow_pickle=False) as archive:
        if "format_version" not in archive:
            raise ValueError("not an HGQ_MODEL dataset: format_version is missing")
        version = str(archive["format_version"].item())
        if version != DATASET_FORMAT_VERSION:
            raise ValueError(f"unsupported dataset format {version!r}; expected {DATASET_FORMAT_VERSION!r}")
        split_names = tuple(str(item) for item in archive["split_names"].tolist())
        if split_names != SPLIT_NAMES:
            raise ValueError(f"dataset splits are {split_names}; expected exactly {SPLIT_NAMES}")
        archive_fs = float(archive["fs_hz"].item())
        archive_window = int(archive["window_size"].item())
        archive_harmonics = np.asarray(archive["harmonics"])
        archive_scales = np.asarray(archive["order_scales"])
        if archive_fs != FS_HZ or archive_window != WINDOW_SIZE:
            raise ValueError("dataset sampling/window contract does not match this package")
        if not np.array_equal(archive_harmonics, HARMONICS) or not np.allclose(
            archive_scales, ORDER_SCALES, rtol=0.0, atol=0.0
        ):
            raise ValueError("dataset harmonic target contract does not match this package")
        for split_name in split_names:
            missing = [
                f"{split_name}_{storage_name}"
                for storage_name in _STORAGE_FIELDS
                if f"{split_name}_{storage_name}" not in archive
            ]
            if missing:
                raise ValueError(f"dataset archive is missing fields: {', '.join(missing)}")
            loaded = {
                attribute_name: np.asarray(archive[f"{split_name}_{storage_name}"])
                for storage_name, attribute_name in _STORAGE_FIELDS.items()
            }
            split = SplitData(**loaded)
            split.validate()
            result[split_name] = split
    return result


def load_metadata(path: str | Path) -> dict[str, Any]:
    """Read only the JSON metadata from an NPZ, still with pickle disabled."""

    with np.load(Path(path), allow_pickle=False) as archive:
        if "metadata_json" not in archive:
            raise ValueError("dataset archive has no metadata_json field")
        document = json.loads(str(archive["metadata_json"].item()))
    if not isinstance(document, dict):
        raise ValueError("metadata_json must contain a JSON object")
    return document


def with_split_sizes(config: DatasetConfig, **sizes: int) -> DatasetConfig:
    """Convenience helper for tests and small pipeline smoke runs."""

    changes = {f"n_{name}": value for name, value in sizes.items()}
    unknown = sorted(set(changes) - {"n_train", "n_val", "n_test_id", "n_test_ood"})
    if unknown:
        raise ValueError(f"unknown split sizes: {', '.join(unknown)}")
    return replace(config, **changes)


__all__ = [
    "DATASET_FORMAT_VERSION",
    "DatasetConfig",
    "SPLIT_NAMES",
    "SplitData",
    "dataset_metadata",
    "generate_dataset",
    "generate_from_config",
    "load_config_json",
    "load_dataset",
    "load_metadata",
    "save_dataset",
    "with_split_sizes",
]
