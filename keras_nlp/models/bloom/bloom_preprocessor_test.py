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

import pytest

from keras_nlp.models.bloom.bloom_preprocessor import BloomPreprocessor
from keras_nlp.models.bloom.bloom_tokenizer import BloomTokenizer
from keras_nlp.tests.test_case import TestCase


class BloomPreprocessorTest(TestCase):
    def setUp(self):
        self.vocab = ["<pad>", "<s>", "</s>"]
        self.vocab += ["!", "air", "Ġair", "plane", "Ġat", "port"]
        self.vocab = dict([(token, i) for i, token in enumerate(self.vocab)])
        self.merges = ["Ġ a", "Ġ t", "Ġ i", "Ġ b", "a i", "p l", "n e"]
        self.merges += ["Ġa t", "p o", "r t", "Ġt h", "ai r", "pl a", "po rt"]
        self.merges += ["Ġai r", "Ġa i", "pla ne"]
        self.tokenizer = BloomTokenizer(
            vocabulary=self.vocab,
            merges=self.merges,
        )
        self.init_kwargs = {
            "tokenizer": self.tokenizer,
            "sequence_length": 8,
        }
        self.input_data = ["airplane at airport"]

    def test_preprocessor_basics(self):
        self.run_preprocessing_layer_test(
            cls=BloomPreprocessor,
            init_kwargs=self.init_kwargs,
            input_data=self.input_data,
            expected_output={
                "token_ids": [[1, 4, 6, 7, 5, 8, 2, 0]],
                "padding_mask": [[1, 1, 1, 1, 1, 1, 1, 0]],
            },
        )

    def test_no_start_end_token(self):
        input_data = ["airplane at airport"] * 4

        preprocessor = BloomPreprocessor(
            tokenizer=BloomTokenizer(
                vocabulary=self.vocab,
                merges=self.merges,
            ),
            sequence_length=8,
            add_start_token=False,
            add_end_token=False,
        )
        x = preprocessor(input_data)
        self.assertAllEqual(x["token_ids"], [[4, 6, 7, 5, 8, 0, 0, 0]] * 4)
        self.assertAllEqual(x["padding_mask"], [[1, 1, 1, 1, 1, 0, 0, 0]] * 4)

    def test_sequence_length_override(self):
        input_data = "airplane at airport"
        preprocessor = BloomPreprocessor(**self.init_kwargs)
        x = preprocessor(input_data, sequence_length=4)
        self.assertAllEqual(x["token_ids"], [1, 4, 6, 2])

    @pytest.mark.extra_large
    def test_all_presets(self):
        for preset in BloomPreprocessor.presets:
            self.run_preset_test(
                cls=BloomPreprocessor,
                preset=preset,
                input_data=self.input_data,
            )
