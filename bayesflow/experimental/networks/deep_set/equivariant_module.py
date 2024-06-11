
import keras
from keras import ops, layers
from keras.saving import register_keras_serializable

from bayesflow.experimental.types import Tensor
from bayesflow.experimental.utils import keras_kwargs
from .invariant_module import InvariantModule


@register_keras_serializable(package="bayesflow.networks.deep_set")
class EquivariantModule(keras.Layer):
    """Implements an equivariant module performing an equivariant transform.

    For details and justification, see:

    [1] Bloem-Reddy, B., & Teh, Y. W. (2020). Probabilistic Symmetries and Invariant Neural Networks.
    J. Mach. Learn. Res., 21, 90-1. https://www.jmlr.org/papers/volume21/19-322/19-322.pdf
    """

    def __init__(
        self,
        num_dense_equivariant: int = 2,
        num_dense_invariant_inner: int = 2,
        num_dense_invariant_outer: int = 2,
        units_equivariant: int = 128,
        units_invariant_inner: int = 128,
        units_invariant_outer: int = 128,
        pooling: str | keras.Layer = "mean",
        activation: str = "gelu",
        kernel_initializer: str = "he_normal",
        dropout: float = 0.05,
        layer_norm: bool = True,
        spectral_normalization: bool = False,
        **kwargs
    ):
        """Creates an equivariant module according to [1] which combines equivariant transforms
        with nested invariant transforms, thereby enabling interactions between set members.

        Parameters
        ----------
        #TODO
        """

        super().__init__(**keras_kwargs(kwargs))

        self.invariant_module = InvariantModule(
            num_dense_inner=num_dense_invariant_inner,
            num_dense_outer=num_dense_invariant_outer,
            units_inner=units_invariant_inner,
            units_outer=units_invariant_outer,
            activation=activation,
            kernel_initializer=kernel_initializer,
            dropout=dropout,
            pooling=pooling,
            spectral_normalization=spectral_normalization,
            **kwargs
        )

        self.input_projection = layers.Dense(units_equivariant)
        self.equivariant_fc = keras.Sequential(name="EquivariantFC")
        for _ in range(num_dense_equivariant):
            layer = layers.Dense(
                units=units_equivariant,
                activation=activation,
                kernel_initializer=kernel_initializer,
            )
            if spectral_normalization:
                layer = layers.SpectralNormalization(layer)
            self.equivariant_fc.add(layer)

        self.ln = layers.LayerNormalization() if layer_norm else None

    def call(self, input_set: Tensor, **kwargs) -> Tensor:
        """Performs the forward pass of a learnable equivariant transform.

        Parameters
        ----------
        #TODO

        Returns
        -------
        #TODO
        """

        training = kwargs.get("training", False)
        input_set = self.input_projection(input_set)

        # Store shape of input_set, will be (batch_size, ..., set_size, some_dim)
        shape = ops.shape(input_set)

        # Example: Output dim is (batch_size, ..., set_size, representation_dim)
        invariant_summary = self.invariant_module(input_set, training=training)
        invariant_summary = ops.expand_dims(invariant_summary, axis=-2)
        tiler = [1] * len(shape)
        tiler[-2] = shape[-2]
        invariant_summary = ops.tile(invariant_summary, tiler)

        # Concatenate each input entry with the repeated invariant embedding
        output_set = ops.concatenate([input_set, invariant_summary], axis=-1)

        # Pass through final equivariant transform + residual
        output_set = input_set + self.equivariant_fc(output_set, training=training)
        if self.ln is not None:
            output_set = self.ln(output_set, training=training)

        return output_set

    def build(self, input_shape):
        self.call(keras.ops.zeros(input_shape))
