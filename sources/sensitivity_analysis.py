# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
This file contains the necessary functions for the sensitivity analysis.

Sensitivity analysis should help identifying the parameters whose modification
has the greatest impact on RMSE.
"""

import os
import shutil
import pandas as pd
from typing import Dict, Union, Any, Optional
from util_functions import sample_df, rmse, PowerToCalibrate
from dynawo_functions import run_dynawo, modify_one_param_par_file, DynawoFailedException, SimulationPreconditionError
from enum import Enum
from experience import Experience
from experience_set import ExperienceSet


class SensiMethod(Enum):
    FIXED = "Fixed epsilon"
    PERCENTAGE = "Percentage epsilon"
    HYBRID = "Hybrid epsilon"


def calculate_modified_value(
    original_value: float,
    sensi_method: SensiMethod,
    sensi_params: Dict[str, Union[int, float]],
) -> float:
    percentage_epsilon_default = 10.0
    fixed_epsilon_default = 0.1

    percentage_epsilon = float(sensi_params.get("percentage_epsilon", percentage_epsilon_default))
    fixed_epsilon = float(sensi_params.get("fixed_epsilon", fixed_epsilon_default))

    if sensi_method == SensiMethod.PERCENTAGE:
        return original_value * (1.0 + percentage_epsilon / 100.0)
    elif sensi_method == SensiMethod.FIXED:
        return original_value + fixed_epsilon
    elif sensi_method == SensiMethod.HYBRID:
        return original_value * (1.0 + percentage_epsilon / 100.0) + fixed_epsilon
    else:
        raise ValueError(f"Unsupported sensitivity method: {sensi_method}")


def compute_rmse_for_current_setup(
        dynawo_launcher, jobs_file_sensitivity,
        t_start, t_end,
        col_name_p, col_name_q,
        sampled_reference_p, sampled_reference_q,
        power_to_calibrate
) -> float:
    sensitivity_simulation_data_df = run_dynawo(dynawo_launcher, jobs_file_sensitivity)

    sampled_sensitivity_simulation_data_df = sample_df(
        sensitivity_simulation_data_df,
        start_time=t_start,
        end_time=t_end
    )

    sampled_simulated_sensitivity_p = sampled_sensitivity_simulation_data_df[col_name_p].values
    sampled_simulated_sensitivity_q = sampled_sensitivity_simulation_data_df[col_name_q].values

    return rmse(
        sampled_reference_p, sampled_reference_q,
        sampled_simulated_sensitivity_p, sampled_simulated_sensitivity_q,
        power_to_calibrate
    )


def run_sensitivity_analysis(
    dynawo_launcher: Any,
    exp: Experience,
    selected_sets: Dict[str, Dict[str, Any]],
    sensi_method: SensiMethod,
    power_to_calibrate: PowerToCalibrate,
    col_name_p: str,
    col_name_q: str,
    logger: Optional[Any] = None,
    **sensi_params: Any,
) -> Dict[str, pd.DataFrame]:

    t_start = exp.get_t_start()
    t_end = exp.get_t_end()
    reference_data_df = exp.reference_data_df
    temp_folder_sensitivity = exp.temp_folder_sensitivity

    for element in os.listdir(exp.temp_folder_base_case):
        src = os.path.join(exp.temp_folder_base_case, element)
        if os.path.isfile(src):
            shutil.copy(src, temp_folder_sensitivity)

    jobs_file_sensitivity = exp.get_sensitivity_jobs_file()
    par_file_sensitivity = exp.get_sensitivity_par_file()

    sampled_reference_data_df = sample_df(
        reference_data_df,
        start_time=t_start,
        end_time=t_end
    )
    sampled_reference_p = sampled_reference_data_df[col_name_p].values
    sampled_reference_q = sampled_reference_data_df[col_name_q].values

    base_case_rmse = None
    if exp.base_case_correlation_dict is not None:
        if power_to_calibrate == PowerToCalibrate.P:
            base_case_rmse = exp.base_case_correlation_dict.get("rmse_p")
        elif power_to_calibrate == PowerToCalibrate.Q:
            base_case_rmse = exp.base_case_correlation_dict.get("rmse_q")
        else:
            base_case_rmse = exp.base_case_correlation_dict.get("rmse_pq")

    sensitivities = dict()
    for set_id, params_in_set in selected_sets.items():
        sensitivity = dict()
        for parameter_id, parameter in params_in_set.items():
            original_value = parameter.get_original_value()
            param_type = parameter.get_type()

            if param_type == "DOUBLE":
                try:
                    original_double = float(original_value)
                except (TypeError, ValueError):
                    if logger is not None:
                        logger.error(
                            f"{set_id}/{parameter_id} has invalid DOUBLE value '{original_value}' - Skipped"
                        )
                    continue

                modified_param_value = calculate_modified_value(
                    original_double, sensi_method, sensi_params
                )

            elif param_type == "BOOL":
                original_str = str(original_value).strip().lower()
                if original_str in ("true", "1"):
                    original_bool = True
                elif original_str in ("false", "0"):
                    original_bool = False
                else:
                    if logger is not None:
                        logger.error(
                            f"{set_id}/{parameter_id} has invalid BOOL value '{original_value}' - Skipped"
                        )
                    continue

                modified_param_value = not original_bool

            else:
                if logger is not None:
                    logger.error(f"{set_id}/{parameter_id} is neither DOUBLE or BOOL - Skipped")
                continue

            modify_one_param_par_file(par_file_sensitivity, set_id, parameter_id, modified_param_value)

            try:
                rmse_for_param = compute_rmse_for_current_setup(
                    dynawo_launcher, jobs_file_sensitivity,
                    t_start, t_end,
                    col_name_p, col_name_q,
                    sampled_reference_p, sampled_reference_q,
                    power_to_calibrate
                )
                sensitivity[parameter_id] = round(rmse_for_param - base_case_rmse, 6)
                if logger is not None:
                    logger.info(f"{set_id}/{parameter_id} - Done")

            except DynawoFailedException:
                if logger is not None:
                    logger.info(f"{set_id}/{parameter_id} - Simulation failed!")
            finally:
                modify_one_param_par_file(par_file_sensitivity, set_id, parameter_id, original_value)

        sensitivities[set_id] = sensitivity

    for set_id in sensitivities:
        sensitivity_dict = sensitivities[set_id]
        sensitivity_df = pd.DataFrame.from_dict(sensitivity_dict, orient='index', columns=['sensitivity'])
        sensitivity_df = sensitivity_df.reindex(sensitivity_df['sensitivity'].abs().sort_values(ascending=False).index)
        sensitivities[set_id] = sensitivity_df

    return sensitivities


def run_sensitivity_for_all(
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, Any]],
    sensi_method: SensiMethod,
    power_to_calibrate: PowerToCalibrate,
    logger: Optional[Any] = None,
    **sensi_params: Any,
) -> None:
    """
    Run the sensitivity analysis on each experience in the ExperienceSet.
    """
    if not exp_set.can_run_sensitivity():
        raise SimulationPreconditionError(
            "Cannot run sensitivity analysis: reference base case is not calculated."
        )

    if not selected_sets:
        if logger is not None:
            logger.warning("No parameters selected for sensitivity analysis.")
        return

    col_name_p, col_name_q = exp_set.get_col_names()

    for exp in exp_set.get_all_experiences():
        if not exp.is_base_case_calculated():
            if logger is not None:
                logger.warning(
                    f"[{exp.name}] Base case is not calculated - sensitivity analysis skipped."
                )
            exp.sensitivities = None
            continue

        if not exp.has_dynawo_inputs():
            if logger is not None:
                logger.warning(
                    f"[{exp.name}] Dynawo inputs are missing - sensitivity analysis skipped."
                )
            exp.sensitivities = None
            continue

        if not exp.has_reference_values():
            if logger is not None:
                logger.warning(
                    f"[{exp.name}] Reference data are missing - sensitivity analysis skipped."
                )
            exp.sensitivities = None
            continue

        if logger is not None:
            logger.info(f"[{exp.name}] Starting sensitivity analysis...")

        sensitivities = run_sensitivity_analysis(
            dynawo_launcher,
            exp,
            selected_sets,
            sensi_method,
            power_to_calibrate,
            col_name_p,
            col_name_q,
            logger,
            **sensi_params,
        )

        exp.sensitivities = sensitivities

        if logger is not None:
            logger.info(f"Sensitivity analysis completed.")

