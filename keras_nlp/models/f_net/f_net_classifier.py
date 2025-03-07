# Copyright 2022 The KerasNLP Authors
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
from keras_nlp.models.f_net.f_net_backbone import FNetBackbone
from keras_nlp.models.f_net.f_net_backbone import f_net_kernel_initializer
from keras_nlp.models.f_net.f_net_preprocessor import FNetPreprocessor
from keras_nlp.models.f_net.f_net_presets import backbone_presets
from keras_nlp.models.task import Task
from keras_nlp.utils.python_utils import classproperty


@keras_nlp_export("keras_nlp.models.FNetClassifier")
class FNetClassifier(Task):
    """An end-to-end f_net model for classification tasks.

    This model attaches a classification head to a
    `keras_nlp.model.FNetBackbone` instance, mapping from the backbone outputs
    to logits suitable for a classification task. For usage of this model with
    pre-trained weights, use the `from_preset()` constructor.

    This model can optionally be configured with a `preprocessor` layer, in
    which case it will automatically apply preprocessing to raw inputs during
    `fit()`, `predict()`, and `evaluate()`. This is done by default when
    creating the model with `from_preset()`.

    Disclaimer: Pre-trained models are provided on an "as is" basis, without
    warranties or conditions of any kind.

    Args:
        backbone: A `keras_nlp.models.FNetBackbone` instance.
        num_classes: int. Number of classes to predict.
        preprocessor: A `keras_nlp.models.FNetPreprocessor` or `None`. If
            `None`, this model will not apply preprocessing, and inputs should
            be preprocessed before calling the model.
        activation: Optional `str` or callable. The
            activation function to use on the model outputs. Set
            `activation="softmax"` to return output probabilities.
            Defaults to `None`.
        hidden_dim: int. The size of the pooler layer.
        dropout: float. The dropout probability value, applied after the dense
            layer.

    Examples:

    Raw string data.
    ```python
    features = ["The quick brown fox jumped.", "I forgot my homework."]
    labels = [0, 3]

    # Pretrained classifier.
    classifier = keras_nlp.models.FNetClassifier.from_preset(
        "f_net_base_en",
        num_classes=4,
    )
    classifier.fit(x=features, y=labels, batch_size=2)
    classifier.predict(x=features, batch_size=2)

    # Re-compile (e.g., with a new learning rate).
    classifier.compile(
        loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),
        optimizer=keras.optimizers.Adam(5e-5),
        jit_compile=True,
    )
    # Access backbone programmatically (e.g., to change `trainable`).
    classifier.backbone.trainable = False
    # Fit again.
    classifier.fit(x=features, y=labels, batch_size=2)
    ```

    Preprocessed integer data.
    ```python
    features = {
        "token_ids": np.ones(shape=(2, 12), dtype="int32"),
        "segment_ids": np.array([[0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0]] * 2),
    }
    labels = [0, 3]

    # Pretrained classifier without preprocessing.
    classifier = keras_nlp.models.FNetClassifier.from_preset(
        "f_net_base_en",
        num_classes=4,
        preprocessor=None,
    )
    classifier.fit(x=features, y=labels, batch_size=2)
    ```
    """

    def __init__(
        self,
        backbone,
        num_classes,
        preprocessor=None,
        activation=None,
        dropout=0.1,
        **kwargs,
    ):
        # === Layers ===
        self.backbone = backbone
        self.preprocessor = preprocessor
        self.output_dropout = keras.layers.Dropout(
            dropout,
            name="output_dropout",
        )
        self.output_dense = keras.layers.Dense(
            num_classes,
            kernel_initializer=f_net_kernel_initializer(),
            activation=activation,
            name="logits",
        )

        # === Functional Model ===
        inputs = backbone.input
        pooled = backbone(inputs)["pooled_output"]
        pooled = self.output_dropout(pooled)
        outputs = self.output_dense(pooled)
        super().__init__(
            inputs=inputs,
            outputs=outputs,
            **kwargs,
        )

        # === Config ===
        self.num_classes = num_classes
        self.activation = keras.activations.get(activation)
        self.dropout = dropout

        # === Default compilation ===
        logit_output = self.activation == keras.activations.linear
        self.compile(
            loss=keras.losses.SparseCategoricalCrossentropy(
                from_logits=logit_output
            ),
            optimizer=keras.optimizers.Adam(5e-5),
            metrics=[keras.metrics.SparseCategoricalAccuracy()],
            jit_compile=True,
        )

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "num_classes": self.num_classes,
                "dropout": self.dropout,
                "activation": keras.activations.serialize(self.activation),
            }
        )
        return config

    @classproperty
    def backbone_cls(cls):
        return FNetBackbone

    @classproperty
    def preprocessor_cls(cls):
        return FNetPreprocessor

    @classproperty
    def presets(cls):
        return copy.deepcopy(backbone_presets)
