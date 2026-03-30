# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import PyNomad
import unittest
import sys


class TestNomad(unittest.TestCase):

    @staticmethod
    def dummy_blackbox_function(x):
        """
        - x = [x_1, x_2, x_3, x_4]. x_1 and x_2 are floats, x_3 is boolean, x_4 is discrete
        - f is the objective function
        - g_1, g_2 are the constraints
        """
        try:
            x_1 = x.get_coord(0)
            x_2 = x.get_coord(1)
            x_3 = x.get_coord(2)
            x_4 = x.get_coord(3)

            # f is the objective function to minimize
            # Obviously the absolute min is x_min = [5, 2, 1, 3]
            # The upcoming contraint g_1 will force x_1 to be 6 instead of 5
            # Then f_min = 1**2 + 0**2 + 10 - 1 + 0.4**2 = 10.16
            f = (x_1 - 5)**2 + (x_2 - 2)**2 + 10 - x_3 + (x_4 - 2.6)**2

            # Constraints need to take the shape of g(x) <= 0
            # Constraint 1: x_1 >= 6  => g1(x) = 6 - x_1 <= 0
            # Constraint 2: x_2 >= 0  => g2(x) = -x2 <= 0
            g_1 = 6 - x_1
            g_2 = -x_2

            # Format attendu : "f g1 g2" encodé en bytes
            raw_blackbox_object = f"{f} {g_1} {g_2}"
            x.setBBO(raw_blackbox_object.encode("UTF-8"))

        except Exception:
            print("Unexpected eval error", sys.exc_info()[0])
            return 0

        return 1

    def test_nomad_dummy_blackbox_function(self):

        # initial values for the first iteration
        # x_1: float
        # x_2: float
        # x_3: discrete
        # x_4: boolean (0 => False, 1 => True)
        x_0 = [4.0, 1.0, 0, 5]

        params = [
            "DIMENSION 4",
            "BB_INPUT_TYPE ( R R B I)",
            "LOWER_BOUND ( -10 -10 0 1 )",  # lower bounds
            "UPPER_BOUND ( 10 10 1 5 )",  # upper bounds
            "BB_OUTPUT_TYPE OBJ EB EB",  # OBJ => objective function, EB ("EXTREME BARRIER" = hard constraint) => constraint, EB ("EXTREME BARRIER")
            "MAX_BB_EVAL 200",
            "DISPLAY_DEGREE 0",  # 0 => No log at the console
            "DISPLAY_ALL_EVAL false"  # Additional logs, we dont want them in the test
        ]

        result = PyNomad.optimize(TestNomad.dummy_blackbox_function, x_0, [], [], params)

        self.assertAlmostEqual(result["x_best"][0], 6, places=6)
        self.assertAlmostEqual(result["x_best"][1], 2, places=6)
        self.assertAlmostEqual(result["x_best"][2], 1, places=6)
        self.assertAlmostEqual(result["x_best"][3], 3, places=6)
        self.assertAlmostEqual(result["f_best"], 10.16, places=6)


if __name__ == "__main__":
    unittest.main()