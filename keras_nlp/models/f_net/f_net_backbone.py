# Copyright 2023 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy

from keras_nlp.api_export import keras_nlp_export
from keras_nlp.backend import keras
from keras_nlp.layers.modeling.f_net_encoder import FNetEncoder
from keras_nlp.layers.modeling.position_embedding import PositionEmbedding
from keras_nlp.layers.modeling.reversible_embedding import ReversibleEmbedding
from keras_nlp.models.backbone import Backbone
from keras_nlp.models.f_net.f_net_presets import backbone_presets
from keras_nlp.utils.keras_utils import gelu_approximate
from keras_nlp.utils.python_utils import classproperty


def f_net_kernel_initializer(stddev=0.02):
    return keras.initializers.RandomNormal(stddev=stddev)


def f_net_bias_initializer(stddev=0.02):
    return keras.initializers.RandomNormal(stddev=stddev)


@keras_nlp_export("keras_nlp.models.FNetBackbone")
class FNetBackbone(Backbone):
    """A FNet encoder network.

    This class implements a bi-directional Fourier Transform-based encoder as
    described in ["FNet: Mixing Tokens with Fourier Transforms"](https://arxiv.org/abs/2105.03824).
    It includes the embedding lookups and `keras_nlp.layers.FNetEncoder` layers,
    but not the masked language model or next sentence prediction heads.

    The default constructor gives a fully customizable, randomly initialized
    FNet encoder with any number of layers and embedding dimensions. To
    load preset architectures and weights, use the `from_preset()` constructor.

    Note: unlike other models, FNet does not take in a `"padding_mask"` input,
    the `"<pad>"` token is handled equivalently to all other tokens in the input
    sequence.

    Disclaimer: Pre-trained models are provided on an "as is" basis, without
    warranties or conditions of any kind.

    Args:
        vocabulary_size: int. The size of the token vocabulary.
        num_layers: int. The number of FNet layers.
        hidden_dim: int. The size of the FNet encoding and pooler layers.
        intermediate_dim: int. The output dimension of the first Dense layer in
            a two-layer feedforward network for each FNet layer.
        dropout: float. Dropout probability for the embeddings and FNet encoder.
        max_sequence_length: int. The maximum sequence length that this encoder
            can consume. If None, `max_sequence_length` uses the value from
            sequence length. This determines the variable shape for positional
            embeddings.
        num_segments: int. The number of types that the 'segment_ids' input can
            take.

    Examples:
    ```python
    input_data = {
        "token_ids": np.ones(shape=(1, 12), dtype="int32"),
        "segment_ids": np.array([[0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0]]),
    }

    # Pretrained BERT encoder.
    model = keras_nlp.models.FNetBackbone.from_preset("f_net_base_en")
    model(input_data)

    # Randomly initialized FNet encoder with a custom config.
    model = keras_nlp.models.FNetBackbone(
        vocabulary_size=32000,
        num_layers=4,
        hidden_dim=256,
        intermediate_dim=512,
        max_sequence_length=128,
    )
    model(input_data)
    ```
    """

    def __init__(
        self,
        vocabulary_size,
        num_layers,
        hidden_dim,
        intermediate_dim,
        dropout=0.1,
        max_sequence_length=512,
        num_segments=4,
        **kwargs,
    ):
        # === Layers ===
        self.token_embedding = ReversibleEmbedding(
            input_dim=vocabulary_size,
            output_dim=hidden_dim,
            embeddings_initializer=f_net_kernel_initializer(),
            name="token_embedding",
        )
        self.position_embedding = PositionEmbedding(
            initializer=f_net_kernel_initializer(),
            sequence_length=max_sequence_length,
            name="position_embedding",
        )
        self.segment_embedding = keras.layers.Embedding(
            input_dim=num_segments,
            output_dim=hidden_dim,
            embeddings_initializer=f_net_kernel_initializer(),
            name="segment_embedding",
        )
        self.embeddings_add = keras.layers.Add()
        self.embeddings_layer_norm = keras.layers.LayerNormalization(
            name="embeddings_layer_norm",
            axis=-1,
            epsilon=1e-12,
            dtype="float32",
        )
        self.embedding_projection = keras.layers.Dense(
            hidden_dim,
            kernel_initializer=f_net_kernel_initializer(),
            bias_initializer=f_net_bias_initializer(),
            name="embedding_projection",
        )
        self.embeddings_dropout = keras.layers.Dropout(
            dropout,
            name="embeddings_dropout",
        )
        self.transformer_layers = []
        for i in range(num_layers):
            layer = FNetEncoder(
                intermediate_dim=intermediate_dim,
                activation=gelu_approximate,
                dropout=dropout,
                layer_norm_epsilon=1e-12,
                kernel_initializer=f_net_kernel_initializer(),
                bias_initializer=f_net_bias_initializer(),
                name=f"f_net_layer_{i}",
            )
            self.transformer_layers.append(layer)
        self.pooled_dense = keras.layers.Dense(
            hidden_dim,
            kernel_initializer=f_net_kernel_initializer(),
            bias_initializer=f_net_bias_initializer(),
            activation="tanh",
            name="pooled_dense",
        )

        # === Functional Model ===
        token_id_input = keras.Input(
            shape=(None,), dtype="int32", name="token_ids"
        )
        segment_id_input = keras.Input(
            shape=(None,), dtype="int32", name="segment_ids"
        )
        # Embed tokens, positions, and segment ids.
        tokens = self.token_embedding(token_id_input)
        positions = self.position_embedding(tokens)
        segments = self.segment_embedding(segment_id_input)
        # Sum, normalize and apply dropout to embeddings.
        x = self.embeddings_add((tokens, positions, segments))
        x = self.embeddings_layer_norm(x)
        x = self.embedding_projection(x)
        x = self.embeddings_dropout(x)
        # Apply successive FNet encoder blocks.
        for transformer_layer in self.transformer_layers:
            x = transformer_layer(x)
        # Index of classification token in the vocabulary
        cls_token_index = 0
        # Construct the two FNet outputs. The pooled output is a dense layer on
        # top of the [CLS] token.
        sequence_output = x
        pooled_output = self.pooled_dense(x[:, cls_token_index, :])
        # Instantiate using Functional API Model constructor
        super().__init__(
            inputs={
                "token_ids": token_id_input,
                "segment_ids": segment_id_input,
            },
            outputs={
                "sequence_output": sequence_output,
                "pooled_output": pooled_output,
            },
            **kwargs,
        )

        # === Config ===
        self.vocabulary_size = vocabulary_size
        self.num_layers = num_layers
        self.hidden_dim = hidden_dim
        self.intermediate_dim = intermediate_dim
        self.dropout = dropout
        self.max_sequence_length = max_sequence_length
        self.num_segments = num_segments
        self.cls_token_index = cls_token_index

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "vocabulary_size": self.vocabulary_size,
                "num_layers": self.num_layers,
                "hidden_dim": self.hidden_dim,
                "intermediate_dim": self.intermediate_dim,
                "dropout": self.dropout,
                "max_sequence_length": self.max_sequence_length,
                "num_segments": self.num_segments,
            }
        )
        return config

    @classproperty
    def presets(cls):
        return copy.deepcopy(backbone_presets)
