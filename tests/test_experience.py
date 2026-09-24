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

# Ajout du répertoire sources au path, comme dans test_util_functions.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")))

from experience import Experience  # à adapter si le nom du module/classe diffère


class TestExperience(unittest.TestCase):

    def setUp(self):
        # Crée un ensemble de dossiers temporaires pour simuler une expérience
        self.temp_dir = tempfile.TemporaryDirectory()
        base_case_dir = os.path.join(self.temp_dir.name, "base_case")
        sensitivity_dir = os.path.join(self.temp_dir.name, "sensitivity")
        calibration_dir = os.path.join(self.temp_dir.name, "calibration")
        custom_calibration_dir = os.path.join(self.temp_dir.name, "custom_calibration")

        os.makedirs(base_case_dir, exist_ok=True)
        os.makedirs(sensitivity_dir, exist_ok=True)
        os.makedirs(calibration_dir, exist_ok=True)
        os.makedirs(custom_calibration_dir, exist_ok=True)

        # Instancie une expérience avec ces dossiers
        self.exp = Experience(
            name="test_experience",
            temp_folder_base_case=base_case_dir,
            temp_folder_sensitivity=sensitivity_dir,
            temp_folder_calibration=calibration_dir,
            temp_folder_custom_calibration=custom_calibration_dir,
        )

    def tearDown(self):
        # Nettoyage du TemporaryDirectory
        self.temp_dir.cleanup()

    def test_initialization_sets_folders_and_defaults(self):
        """Vérifie que l'initialisation de Experience stocke correctement les chemins
        et met les autres attributs à None / {}."""
        self.assertEqual(self.exp.name, "test_experience")
        self.assertTrue(os.path.isdir(self.exp.temp_folder_base_case))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_sensitivity))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_calibration))
        self.assertTrue(os.path.isdir(self.exp.temp_folder_custom_calibration))

        # Attributs de données doivent être à None ou {}
        self.assertIsNone(self.exp.last_zip_hash)
        self.assertIsNone(self.exp.jobs_file)
        self.assertIsNone(self.exp.dyd_file)
        self.assertIsNone(self.exp.par_file)
        self.assertIsNone(self.exp.crv_file)

        self.assertEqual(self.exp.parameters_sets, {})

        self.assertIsNone(self.exp.reference_data_df)
        self.assertIsNone(self.exp.sampled_reference_data_df)
        self.assertIsNone(self.exp.col_name_p)
        self.assertIsNone(self.exp.col_name_q)
        self.assertIsNone(self.exp.t_start)
        self.assertIsNone(self.exp.t_end)

        self.assertIsNone(self.exp.base_case_simulation_data_df)
        self.assertIsNone(self.exp.base_case_correlation_dict)

        self.assertIsNone(self.exp.calibrated_simulation_data_df)
        self.assertIsNone(self.exp.calibrated_correlation_dict)

        self.assertIsNone(self.exp.custom_simulation_data_df)
        self.assertIsNone(self.exp.custom_correlation_dict)

        self.assertIsNone(self.exp.sensitivities)

    @patch("experience.clean_directory")
    def test_reset_calls_clean_directory_on_all_temp_folders(self, mock_clean_directory):
        """Vérifie que reset() appelle clean_directory sur les 4 dossiers temporaires."""
        # On appelle reset
        self.exp.reset()

        # On s'attend à 4 appels (base_case, sensitivity, calibration, custom_calibration)
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
        """Vérifie que reset() remet à None / {} tous les attributs de données."""

        # On simule un état rempli
        self.exp.last_zip_hash = "dummy_hash"
        self.exp.jobs_file = "/tmp/jobs_file.jobs"
        self.exp.dyd_file = "/tmp/model.dyd"
        self.exp.par_file = "/tmp/model.par"
        self.exp.crv_file = "/tmp/model.crv"

        self.exp.parameters_sets = {"SET1": {"P1": object()}}

        self.exp.reference_data_df = "not_a_df_but_for_test"
        self.exp.sampled_reference_data_df = "sampled"
        self.exp.col_name_p = "PGenPu"
        self.exp.col_name_q = "QGenPu"
        self.exp.t_start = 0.0
        self.exp.t_end = 10.0

        self.exp.base_case_simulation_data_df = "base_case_df"
        self.exp.base_case_correlation_dict = {"corr_p": 0.9}

        self.exp.calibrated_simulation_data_df = "calibrated_df"
        self.exp.calibrated_correlation_dict = {"corr_p": 0.95}

        self.exp.custom_simulation_data_df = "custom_df"
        self.exp.custom_correlation_dict = {"corr_p": 0.8}

        self.exp.sensitivities = {"SET1": "sensitivities_df"}

        # On appelle reset()
        self.exp.reset()

        # Vérifie que tout est revenu à None / {}
        self.assertIsNone(self.exp.last_zip_hash)
        self.assertIsNone(self.exp.jobs_file)
        self.assertIsNone(self.exp.dyd_file)
        self.assertIsNone(self.exp.par_file)
        self.assertIsNone(self.exp.crv_file)

        self.assertEqual(self.exp.parameters_sets, {})

        self.assertIsNone(self.exp.reference_data_df)
        self.assertIsNone(self.exp.sampled_reference_data_df)
        self.assertIsNone(self.exp.col_name_p)
        self.assertIsNone(self.exp.col_name_q)
        self.assertIsNone(self.exp.t_start)
        self.assertIsNone(self.exp.t_end)

        self.assertIsNone(self.exp.base_case_simulation_data_df)
        self.assertIsNone(self.exp.base_case_correlation_dict)

        self.assertIsNone(self.exp.calibrated_simulation_data_df)
        self.assertIsNone(self.exp.calibrated_correlation_dict)

        self.assertIsNone(self.exp.custom_simulation_data_df)
        self.assertIsNone(self.exp.custom_correlation_dict)

        self.assertIsNone(self.exp.sensitivities)


if __name__ == "__main__":
    unittest.main()
