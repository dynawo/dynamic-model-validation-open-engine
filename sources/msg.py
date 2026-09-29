# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file stores the messages logged by the application.
"""


MSG_DYNAWO_FAILED = "Dynawo simulation failed!"
MSG_SIMULATION_FAILED = "All the Dynawo simulations failed during the calibration. The results cannot be exploited."
MSG_UNEXPECTED_ERROR_BASECASE = "Unexpected error during base case simulation: {error}"
MSG_UNEXPECTED_ERROR_AUTOMATIC_CALIBRATION = "Unexpected error during automatic calibration: {error}"
MSG_UNEXPECTED_ERROR_CUSTOM_CALIBRATION = "Unexpected error during custom calibration simulations: {error}"
MSG_UNEXPECTED_ERROR_SENSITIVITY = "Unexpected error during sensitivity analysis: {error}"

MSG_BASECASE_NOT_READY = (
    "Cannot run base case: reference experience is not ready "
    "(missing reference data and/or Dynawo inputs)."
)
MSG_CALIBRATION_NOT_READY = (
    "Cannot run automatic calibration: reference base case is not calculated."
)
MSG_CUSTOM_CALIBRATION_NOT_READY = (
    "Cannot run custom calibration: reference base case is not calculated."
)
MSG_SENSITIVITY_NOT_READY = (
    "Cannot run sensitivity analysis: reference base case is not calculated."
)
MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED = "You need to run a Dynawo simulation on the base_case of the reference experience first."

MSG_NO_PARAMETERS_SELECTED_CALIBRATION = "No parameters selected for automatic calibration."
MSG_NO_PARAMETERS_SELECTED_SENSITIVITY = "No parameters selected for sensitivity analysis."
MSG_NO_PARAMETERS_SELECTED_CUSTOM = "No parameters selected for custom calibration."

MSG_INFO_ADD_EXP_ADDED = (
    "Additional experience '{name}' has been loaded and added to the ExperienceSet."
)
MSG_ERR_LOADING_REF_EXP = "Error while loading reference experience: {error}"
MSG_ERR_LOADING_ADD_EXP = "Error while loading additional experience '{name}': {error}"

MSG_ERR_INFERRING_PQ_COLS = "Error while inferring P/Q column names: {error}"

MSG_NO_SET_ID_OR_PARAM_ID_FOUND = "No set_id or parameter matches your search."
