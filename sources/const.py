# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file stores various constant used throughout all the application.
"""


import os


# Settings
DEFAULT_SETTINGS = os.path.join(os.path.dirname(__file__), "..", "resources", "settings.yaml")


# Dynawo
REFERENCE_DATA_FILENAME = "reference_data.csv"
CRV_EXT = ".crv"
DYD_EXT = ".dyd"
JOBS_EXT = ".jobs"
PAR_EXT = ".par"

REQUIRED_FILES = [
    REFERENCE_DATA_FILENAME,
    CRV_EXT,
    DYD_EXT,
    JOBS_EXT,
    PAR_EXT,
]

DYNAWO_NS = "http://www.rte-france.com/dynawo"
DYNAWO_PAR_XPATH_TEMPLATE = './/ns:set[@id="{}"]/ns:par[@name="{}"]'


# Similarity metrics
CORRELATION_LABEL = "Correlation"
MAG_METRIC_LABEL = "Mag metric"
PH_METRIC_LABEL = "Ph metric"
RMSE_LABEL = "RMSE"


# Optimization
SUPER_HIGH_VALUE_ERROR = 9999


# Streamlit
DYNAWO_LAUNCHER_ST_SESSION_KEY = "dynawo_launcher"
EXPERIENCE_SET_ST_SESSION_KEY = "experience_set"

PERCENTAGE_EPSILON_ST_SESSION_KEY = "Percentage epsilon"
FIXED_EPSILON_ST_SESSION_KEY = "Fixed epsilon"

DATA_TAB_LOGGER_NAME = "data_tab_st_logger_name"
BASECASE_LOGGER_NAME = "base_case_st_logger_name"
SENSITIVITY_LOGGER_NAME ="sensitivity_st_logger_name"
AUTOMATIC_CALIBRATION_LOGGER_NAME = "calibration_st_logger_name"
CUSTOM_CALIBRATION_LOGGER_NAME = "custom_calibration_st_logger_name"

DATA_TAB_LOG_AREA_ST_SESSION_KEY = "log_area_data_tab"
BASECASE_LOG_AREA_ST_SESSION_KEY = "log_area_base_case"
SENSITIVITY_LOG_AREA_ST_SESSION_KEY = "log_area_base_case_sensitivity"
AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY = "log_area_base_case_calibration"
CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY = "log_area_custom_calibration"

DATA_TAB_LOGGER_ST_SESSION_KEY = "data_tab_logger"
BASECASE_LOGGER_ST_SESSION_KEY = "base_case_logger"
SENSITIVITY_LOGGER_ST_SESSION_KEY = "sensitivity_logger"
AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY = "automatic_calibration_logger"
CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY = "custom_calibration_logger"



