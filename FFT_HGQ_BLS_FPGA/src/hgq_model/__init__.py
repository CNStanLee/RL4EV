"""HGQ2 harmonic phasor regression utilities.

The package root deliberately imports only the NumPy data/contract layer.
Model construction remains available from :mod:`hgq_model.models` without
making Keras/HGQ2 a requirement for dataset generation and inspection.
"""

from .contract import (
    FS_HZ,
    HARMONICS,
    ORDER_SCALES,
    WINDOW_SIZE,
    DecodedTargets,
    decode_targets,
    encode_targets,
    wrap_phase,
)
from .data import (
    DATASET_FORMAT_VERSION,
    SPLIT_NAMES,
    DatasetConfig,
    SplitData,
    dataset_metadata,
    generate_dataset,
    generate_from_config,
    load_config_json,
    load_dataset,
    load_metadata,
    save_dataset,
    with_split_sizes,
)
from .real_data import build_labeled_dataset, load_labeled_npz

__all__ = [
    "DATASET_FORMAT_VERSION",
    "DecodedTargets",
    "DatasetConfig",
    "FS_HZ",
    "HARMONICS",
    "ORDER_SCALES",
    "SPLIT_NAMES",
    "SplitData",
    "WINDOW_SIZE",
    "build_labeled_dataset",
    "dataset_metadata",
    "decode_targets",
    "encode_targets",
    "generate_dataset",
    "generate_from_config",
    "load_config_json",
    "load_dataset",
    "load_metadata",
    "load_labeled_npz",
    "save_dataset",
    "with_split_sizes",
    "wrap_phase",
]
