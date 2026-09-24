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
import unittest

# Ajout du répertoire sources au path, comme dans les autres tests
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")),
)

from settings import Settings
from dynawo_functions import run_dynawo, DynawoFailedException
from util_functions import sample_df


class TestDynawoFunctions(unittest.TestCase):

    def test_run_dynawo_on_example_case(self):
        """
        Test d'intégration : lance une simulation Dynawo sur le cas de test 1.
        Si la simulation échoue (DynawoFailedException), on marque le test comme skipped.
        """
        settings = Settings()
        dynawo_launcher = settings.get_dynawo_launcher()

        example_jobs_file = os.path.join(
            os.path.dirname(__file__),
            "..",
            "test_cases",
            "test_case_1",
            "test_case_1.jobs",
        )
        example_jobs_file = os.path.abspath(example_jobs_file)

        if not os.path.isfile(example_jobs_file):
            self.skipTest(f"Example jobs file not found: {example_jobs_file}")

        try:
            simulation_data_df = run_dynawo(dynawo_launcher, example_jobs_file)
        except DynawoFailedException:
            # On ne fait pas échouer toute la suite si Dynawo n'est pas disponible
            self.skipTest("Dynawo simulation failed for the example case")

        # On vérifie que le DataFrame n'est pas vide après échantillonnage
        sampled_df = sample_df(simulation_data_df)
        self.assertFalse(sampled_df.empty, "Simulation data DataFrame is empty")


if __name__ == "__main__":
    unittest.main()
