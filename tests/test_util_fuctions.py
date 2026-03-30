# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import os
import unittest
from unittest.mock import patch
import tempfile
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")))

from util_functions import (
    get_measured_data,
    remove_rows_with_same_index,
    sample_df,
    pearson_corr,
    similarity_metrics,
    rmse,
    clean_directory,
    get_file_hash
)


class TestUtilFunctions(unittest.TestCase):

    @patch("util_functions.st")
    def test_get_measured_data(self, mock_st):
        csv_path = os.path.join(os.path.dirname(__file__), "..", "test_cases", "test_case_1", "measured_data.csv")
        measured_data_df = get_measured_data(csv_path)

        # Index must be "time"
        self.assertEqual(measured_data_df.index.name, "time")
        # No duplicated allowed
        self.assertFalse(measured_data_df.index.duplicated().any())

    def test_remove_rows_with_same_index(self):
        df = pd.DataFrame(
            {
                "time": [0.0, 0.0, 0.1],
                "val": [1, 2, 3],
            }
        ).set_index("time")

        result = remove_rows_with_same_index(df)
        self.assertListEqual(list(result.index), [0.0, 0.1])
        self.assertEqual(result.loc[0.0, "val"], 1)

    # TODO
    def test_sample_df(self):
        # Initial dataframe with 1 sec timestep
        df = pd.DataFrame(
            {
                "time": [0.0, 1],
                "val": [0.0, 5],
            }
        ).set_index("time")

        # We want one value every 0.1 second
        sampled = sample_df(df, sampling_frequency=10)

        # Checking indices
        expected_index = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]
        self.assertTrue(np.allclose(sampled.index.values, expected_index))

        # Checking values
        self.assertEqual(sampled.loc[0.0, "val"], 0.0)
        self.assertEqual(sampled.loc[1, "val"], 5)
        self.assertAlmostEqual(sampled.loc[0.3, "val"], 1.5, places=6)

    def test_pearson_corr_identical_arrays_is_one(self):
        x = [1, 2, 3, 4]
        y = [1, 2, 3, 4]
        corr = pearson_corr(x, y)
        self.assertAlmostEqual(corr, 1.0, places=6)

    def test_pearson_corr_reversed_arrays_is_minus_one(self):
        x = [1, 2, 3, 4]
        y = [4, 3, 2, 1]
        corr = pearson_corr(x, y)
        self.assertAlmostEqual(corr, -1.0, places=6)

    def test_similarity_metrics_identical_signals_is_one(self):
        x = np.array([1.0, 2.0, 3.0, 4.0])
        y = np.array([1.0, 2.0, 3.0, 4.0])

        m_alpha, a_beta = similarity_metrics(x, y)

        self.assertAlmostEqual(m_alpha, 1.0, places=6)
        self.assertAlmostEqual(a_beta, 1.0, places=6)

    def test_rmse_identical_values_is_zero(self):
        measured_p = np.array([1.0, 2.0])
        measured_q = np.array([3.0, 4.0])
        simulated_p = np.array([1.0, 2.0])
        simulated_q = np.array([3.0, 4.0])

        rmse_identical_values = rmse(measured_p, measured_q, simulated_p, simulated_q)

        self.assertEqual(rmse_identical_values, 0.0)

    def test_rmse_different_values(self):
        measured_p = np.array([1.0])
        measured_q = np.array([1.0])
        simulated_p = np.array([2.0])
        simulated_q = np.array([2.0])

        # mse = (1^2 + 1^2) = 2 -> rmse = sqrt(2)
        rmse_different_values = rmse(measured_p, measured_q, simulated_p, simulated_q)

        self.assertAlmostEqual(
            rmse_different_values,
            np.sqrt(2),
            places=6,
        )

    def test_get_file_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")

            with open(file_path, "wb") as f:
                f.write(b"toto")

            with open(file_path, "rb") as f:
                file_hash = get_file_hash(f)

            expected_hash = "31f7a65e315586ac198bd798b6629ce4903d0899476d5741a9f32e2e521b6a66"

            self.assertEqual(file_hash, expected_hash)


if __name__ == "__main__":
    unittest.main()