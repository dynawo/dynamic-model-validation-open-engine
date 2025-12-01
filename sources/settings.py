# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
Description of the Settings class.
Check resources/settings.yaml for additional information.
"""

import os
import yaml


DEFAULT_SETTINGS = os.path.join(os.path.dirname(__file__), "..", "resources", "settings.yaml")


class Settings:
    def __init__(self, settings_file=None):
        if settings_file is None:
            settings_file = DEFAULT_SETTINGS
        with open(settings_file, 'r') as file:
            self._config = yaml.safe_load(file)
        for key, value in self._config.items():
            setattr(self, key, value['value'])

    def __repr__(self):
        params = [f"{key}={getattr(self, key)}" for key in self._config]
        return f"Settings({', '.join(params)})"

    def get_description(self, key):
        if key in self._config and 'description' in self._config[key]:
            return self._config[key]['description']
        else:
            raise KeyError(f"No description available for parameter '{key}'")

    def get_dynawo_launcher(self):
        return self.dynawo_launcher
