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
import tempfile
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")))

from settings import Settings


YAML_CONTENT = """
dynawo_launcher:
  value: "/usr/bin/dynawo"
  description: "Path to Dynawo executable"
"""


class TestSettings(unittest.TestCase):
    def test_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = os.path.join(tmpdir, "settings.yaml")
            with open(yaml_path, "w") as f:
                f.write(YAML_CONTENT)

            settings = Settings(settings_file=yaml_path)

            path_to_dynawo_launcher = settings.get_dynawo_launcher()

            self.assertEqual(path_to_dynawo_launcher, "/usr/bin/dynawo")


if __name__ == "__main__":
    unittest.main()
