"""HGQ2 MLP, recurrent, and Transformer regressors.

All architectures expose the same fixed deployment interface:
``(batch, 80, 1) -> (batch, 8)``.  The eight outputs are normalized
complex phasor components; physical amplitudes and phases are recovered by
the functions in :mod:`hgq_model.contract`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

try:
    import keras
    from hgq.config import LayerConfigScope, QuantizerConfig, QuantizerConfigScope
    from hgq.layers import (
        QAdd,
        QConv1D,
        QDense,
        QMultiHeadAttention,
        QSimpleRNN,
    )
except ImportError as exc:  # pragma: no cover - gives a useful message in minimal data-only installs
    raise ImportError(
        "Model construction needs Keras and HGQ2. Install with `python -m pip install -e '.[torch]'`."
    ) from exc


SUPPORTED_MODELS = ("mlp", "rnn", "transformer", "residual_bls")


@dataclass(frozen=True)
class ModelConfig:
    """Common architecture and quantization options."""

    window_size: int = 80
    output_dim: int = 8
    weight_integer_bits: int = 1
    weight_fractional_bits: int = 6
    activation_integer_bits: int = 3
    activation_fractional_bits: int = 6
    output_integer_bits: int = 2
    output_fractional_bits: int = 7
    quantizer_trainable: bool = False
    enable_ebops: bool = False
    beta: float = 0.0
    dropout: float = 0.05
    mlp_units: tuple[int, ...] = (64, 48, 32)
    residual_bls_width: int = 64
    residual_bls_blocks: int = 3
    rnn_units: tuple[int, ...] = (24,)
    rnn_patch_size: int = 8
    rnn_patch_filters: int = 16
    rnn_head_units: int = 32
    transformer_dim: int = 16
    transformer_heads: int = 2
    transformer_key_dim: int = 8
    transformer_ff_dim: int = 32
    transformer_patch_size: int = 8
    transformer_head_units: int = 48

    @classmethod
    def from_dict(cls, values: dict[str, Any] | None) -> ModelConfig:
        values = dict(values or {})
        for field in ("mlp_units", "rnn_units"):
            if field in values:
                values[field] = tuple(int(x) for x in values[field])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mlp_units"] = list(self.mlp_units)
        result["rnn_units"] = list(self.rnn_units)
        return result


def _output_quantizer(config: ModelConfig) -> QuantizerConfig:
    return QuantizerConfig(
        "kif",
        place="datalane",
        k0=1,
        i0=config.output_integer_bits,
        f0=config.output_fractional_bits,
        overflow_mode="SAT",
        trainable=config.quantizer_trainable,
        homogeneous_axis=(0,),
    )


def _scopes(config: ModelConfig) -> tuple[QuantizerConfigScope, QuantizerConfigScope, LayerConfigScope]:
    parameter_scope = QuantizerConfigScope(
        place=("weight", "bias"),
        default_q_type="kif",
        k0=1,
        i0=config.weight_integer_bits,
        f0=config.weight_fractional_bits,
        overflow_mode="SAT_SYM",
        trainable=config.quantizer_trainable,
    )
    activation_scope = QuantizerConfigScope(
        place="datalane",
        default_q_type="kif",
        k0=1,
        i0=config.activation_integer_bits,
        f0=config.activation_fractional_bits,
        overflow_mode="SAT",
        trainable=config.quantizer_trainable,
        homogeneous_axis=(0, 1),
    )
    layer_scope = LayerConfigScope(enable_ebops=config.enable_ebops, beta0=config.beta)
    return parameter_scope, activation_scope, layer_scope


def _regression_head(x: Any, config: ModelConfig) -> Any:
    return QDense(
        config.output_dim,
        name="complex_phasors",
        kernel_initializer="zeros",
        bias_initializer="zeros",
        enable_oq=True,
        oq_conf=_output_quantizer(config),
    )(x)


def build_mlp(config: ModelConfig) -> keras.Model:
    """Dense HGQ2 baseline patterned after ``jsc150/get_mlp``.

    The upstream example uses ``QEinsumDenseBatchnorm``.  ``QDense`` is used
    here because it is the ordinary dense HGQ2 primitive and remains stable
    across all three Keras backends, including current Keras/Torch releases.
    """

    parameter_scope, activation_scope, layer_scope = _scopes(config)
    with parameter_scope, activation_scope, layer_scope:
        inputs = keras.Input((config.window_size, 1), name="waveform")
        x = keras.layers.Flatten(name="flatten_window")(inputs)
        for index, units in enumerate(config.mlp_units, start=1):
            x = QDense(
                units,
                activation="relu",
                name=f"mlp_dense_{index}",
            )(x)
            if config.dropout > 0:
                x = keras.layers.Dropout(config.dropout, name=f"mlp_dropout_{index}")(x)
        outputs = _regression_head(x, config)
    return keras.Model(inputs, outputs, name="hgq2_mlp_harmonics")


def build_residual_bls(config: ModelConfig) -> keras.Model:
    """Hardware-oriented HGQ2 residual BLS with a static dense datapath.

    Each block has two quantized dense layers and an explicit ``QAdd`` skip.
    Both the residual stream and branch output are non-negative, so the add is
    equivalent to the post-add ReLU used by the earlier Brevitas prototype.
    The resulting graph contains no recurrence, attention, normalization, or
    dynamic tensor operation.
    """

    if config.residual_bls_width <= 0 or config.residual_bls_blocks <= 0:
        raise ValueError("residual_bls_width and residual_bls_blocks must be positive")
    parameter_scope, activation_scope, layer_scope = _scopes(config)
    with parameter_scope, activation_scope, layer_scope:
        inputs = keras.Input((config.window_size, 1), name="waveform")
        x = keras.layers.Flatten(name="flatten_window")(inputs)
        x = QDense(config.residual_bls_width, activation="relu", name="bls_input_dense")(x)
        for index in range(1, config.residual_bls_blocks + 1):
            branch = QDense(
                config.residual_bls_width,
                activation="relu",
                name=f"bls_block_{index}_dense_1",
            )(x)
            branch = QDense(
                config.residual_bls_width,
                activation="relu",
                name=f"bls_block_{index}_dense_2",
            )(branch)
            x = QAdd(name=f"bls_block_{index}_skip")([x, branch])
        outputs = _regression_head(x, config)
    return keras.Model(inputs, outputs, name="hgq2_residual_bls_harmonics")


def build_rnn(config: ModelConfig) -> keras.Model:
    """Static ``QSimpleRNN`` retaining every state for the regression head.

    ``return_sequences=True`` avoids compressing all 80 samples into the last
    state.  A strided quantized convolution summarizes adjacent recurrent
    states before a static flatten gives the head position-specific access,
    without reverse recurrence, slicing, or unsupported wrapper layers.
    """

    if len(config.rnn_units) != 1 or config.rnn_units[0] <= 0:
        raise ValueError("rnn_units must contain one positive hidden width")
    if config.rnn_patch_size <= 0 or config.window_size % config.rnn_patch_size:
        raise ValueError("rnn_patch_size must divide window_size exactly")
    if config.rnn_patch_filters <= 0:
        raise ValueError("rnn_patch_filters must be positive")
    if config.rnn_head_units <= 0:
        raise ValueError("rnn_head_units must be positive")
    parameter_scope, activation_scope, layer_scope = _scopes(config)
    with parameter_scope, activation_scope, layer_scope:
        inputs = keras.Input((config.window_size, 1), name="waveform")
        x = QSimpleRNN(
            config.rnn_units[0],
            activation="linear",
            dropout=0.0,
            return_sequences=True,
            go_backwards=False,
            unroll=False,
            name="rnn_sequence",
        )(inputs)
        x = QConv1D(
            config.rnn_patch_filters,
            kernel_size=config.rnn_patch_size,
            strides=config.rnn_patch_size,
            padding="valid",
            activation="relu",
            name="rnn_state_patches",
        )(x)
        x = keras.layers.Flatten(name="ordered_state_flatten")(x)
        x = QDense(config.rnn_head_units, activation="relu", name="rnn_head_dense")(x)
        outputs = _regression_head(x, config)
    return keras.Model(inputs, outputs, name="hgq2_rnn_harmonics")


def build_transformer(config: ModelConfig) -> keras.Model:
    """Static patch Transformer composed only of HGQ2/Alkaid-supported ops.

    A static strided ``QConv1D`` turns eight adjacent samples into one ordered
    token.  Flattening the
    attention output instead of global averaging preserves token position at
    the regression head, so no custom positional-encoding layer is needed.
    """

    if config.transformer_dim % config.transformer_heads:
        raise ValueError("transformer_dim must be divisible by transformer_heads")
    if config.transformer_patch_size <= 0 or config.window_size % config.transformer_patch_size:
        raise ValueError("transformer_patch_size must divide window_size exactly")
    if config.transformer_head_units <= 0:
        raise ValueError("transformer_head_units must be positive")
    parameter_scope, activation_scope, layer_scope = _scopes(config)
    with parameter_scope, activation_scope, layer_scope:
        inputs = keras.Input((config.window_size, 1), name="waveform")
        x = QConv1D(
            config.transformer_dim,
            kernel_size=config.transformer_patch_size,
            strides=config.transformer_patch_size,
            padding="valid",
            activation="linear",
            name="patch_embedding",
        )(inputs)
        attention = QMultiHeadAttention(
            config.transformer_heads,
            config.transformer_key_dim,
            dropout=config.dropout,
            name="self_attention",
        )(x, x)
        x = QAdd(name="attention_residual")([x, attention])
        feed_forward = QDense(config.transformer_ff_dim, activation="relu", name="ffn_expand")(x)
        feed_forward = QDense(config.transformer_dim, name="ffn_project")(feed_forward)
        x = QAdd(name="ffn_residual")([x, feed_forward])
        x = keras.layers.Flatten(name="ordered_token_flatten")(x)
        x = QDense(config.transformer_head_units, activation="relu", name="transformer_head_dense")(x)
        outputs = _regression_head(x, config)
    return keras.Model(inputs, outputs, name="hgq2_transformer_harmonics")


def build_model(model_name: str, config: ModelConfig | dict[str, Any] | None = None) -> keras.Model:
    """Build one of the three models with a shared input/output contract."""

    model_name = model_name.lower()
    if model_name not in SUPPORTED_MODELS:
        raise ValueError(f"Unknown model {model_name!r}; choose from {SUPPORTED_MODELS}")
    if not isinstance(config, ModelConfig):
        config = ModelConfig.from_dict(config)
    builders = {
        "mlp": build_mlp,
        "rnn": build_rnn,
        "transformer": build_transformer,
        "residual_bls": build_residual_bls,
    }
    return builders[model_name](config)


def load_model(path: str, *, compile: bool = False) -> keras.Model:
    """Load a saved model after registering project and HGQ2 custom layers."""

    return keras.models.load_model(path, compile=compile)
