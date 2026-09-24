# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add the sources directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")))

from experience import Experience  # type: ignore


class TestExperience(unittest.TestCase):

    def setUp(self):
        # Create a temporary root directory for the experience
        self.temp_dir = tempfile.TemporaryDirectory()

        # Instantiate an Experience; it will create its own subfolders
        self.exp = Experience(
            name="test_experience",
            temp_dir_exp=self.temp_dir.name,
            weight=1.0,
            zip_file=None,
            logger=None,
        )

    def tearDown(self):
        # Clean up the TemporaryDirectory
        self.temp_dir.cleanup()

    def test_initialization_sets_folders_and_defaults(self):
        """Check that Experience initialization creates folders and sets attributes to defaults."""
        self.assertEqual(self.exp.name, "test_experience")

        # Folders must exist
        self.assertTrue(os.path.isdir(self.exp.temp_dir_exp))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_base_case))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_sensitivity))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_calibration))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_custom_calibration))

        # Hash and Dynawo inputs
        self.assertIsNone(self.exp.file_hash)
        self.assertIsNone(self.exp.jobs_file)
        self.assertIsNone(self.exp.dyd_file)
        self.assertIsNone(self.exp.par_file)
        self.assertIsNone(self.exp.crv_file)

        # Parameters and reference data
        self.assertEqual(self.exp.parameters_sets, {})
        self.assertIsNone(self.exp.reference_data_df)

        # Time window
        self.assertIsNone(self.exp.get_t_start())
        self.assertIsNone(self.exp.get_t_end())

        # Simulation outputs
        self.assertIsNone(self.exp.base_case_simulation_data_df)
        self.assertIsNone(self.exp.base_case_correlation_dict)

        self.assertIsNone(self.exp.calibrated_simulation_data_df)
        self.assertIsNone(self.exp.calibrated_correlation_dict)

        self.assertIsNone(self.exp.custom_simulation_data_df)
        self.assertIsNone(self.exp.custom_correlation_dict)

        # Sensitivities
        self.assertIsNone(self.exp.sensitivities)

    @patch("experience.clean_directory")
    def test_reset_calls_clean_directory_on_all_temp_folders(self, mock_clean_directory):
        """Check that reset() calls clean_directory on all four temporary folders."""
        self.exp.reset()

        expected_calls = {
            self.exp.temp_folder_base_case,
            self.exp.temp_folder_sensitivity,
            self.exp.temp_folder_calibration,
            self.exp.temp_folder_custom_calibration,
        }
        actual_calls = {call.args[0] for call in mock_clean_directory.call_args_list}

        self.assertSetEqual(actual_calls, expected_calls)
        self.assertEqual(mock_clean_directory.call_count, 4)

    def test_reset_resets_all_data_attributes(self):
        """Check that reset() sets all data-related attributes back to None / {}."""

        # Simulate a populated state
        self.exp.file_hash = "dummy_hash"
        self.exp.jobs_file = "/tmp/jobs_file.jobs"
        self.exp.dyd_file = "/tmp/model.dyd"
        self.exp.par_file = "/tmp/model.par"
        self.exp.crv_file = "/tmp/model.crv"

        self.exp.parameters_sets = {"SET1": {"P1": object()}}

        self.exp.reference_data_df = "not_a_df_but_for_test"  # type: ignore
        self.exp.set_t_start(0.0)
        self.exp.set_t_end(10.0)

        self.exp.base_case_simulation_data_df = "base_case_df"  # type: ignore
        self.exp.base_case_correlation_dict = {"corr_p": 0.9}

        self.exp.calibrated_simulation_data_df = "calibrated_df"  # type: ignore
        self.exp.calibrated_correlation_dict = {"corr_p": 0.95}

        self.exp.custom_simulation_data_df = "custom_df"  # type: ignore
        self.exp.custom_correlation_dict = {"corr_p": 0.8}

        self.exp.sensitivities = {"SET1": "sensitivities_df"}  # type: ignore

        # Call reset()
        self.exp.reset()

        # Hash and Dynawo inputs
        self.assertIsNone(self.exp.file_hash)
        self.assertIsNone(self.exp.jobs_file)
        self.assertIsNone(self.exp.dyd_file)
        self.assertIsNone(self.exp.par_file)
        self.assertIsNone(self.exp.crv_file)

        # Parameters and reference data
        self.assertEqual(self.exp.parameters_sets, {})
        self.assertIsNone(self.exp.reference_data_df)

        # Time window
        self.assertIsNone(self.exp.get_t_start())
        self.assertIsNone(self.exp.get_t_end())

        # Simulation outputs
        self.assertIsNone(self.exp.base_case_simulation_data_df)
        self.assertIsNone(self.exp.base_case_correlation_dict)

        self.assertIsNone(self.exp.calibrated_simulation_data_df)
        self.assertIsNone(self.exp.calibrated_correlation_dict)

        self.assertIsNone(self.exp.custom_simulation_data_df)
        self.assertIsNone(self.exp.custom_correlation_dict)

        # Sensitivities
        self.assertIsNone(self.exp.sensitivities)


if __name__ == "__main__":
    unittest.main()
