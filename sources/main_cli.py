# main_cli.py
# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
Main function to run a parameter calibration session without a GUI.

This CLI script:
  - prepares an ExperienceSet with a reference experience loaded,
  - prepares a selection of parameters to calibrate,
  - chooses an optimization method and its parameters,
  - runs the calibration and logger.infos the calibrated values.

This script is a template, and should be adapted for each study.
"""


import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from typing import Any, Dict, List
from settings import Settings
from experience import Experience, ExperienceLoadError
from experience_set import ExperienceSet
from util_functions import PowerToCalibrate
from dynawo_functions import run_base_case_for_all, SimulationPreconditionError
from automatic_calibration import (
    run_parameter_calibration,
    OptimMethod,
)


def main(
        exp_set: ExperienceSet,
        selected_sets,
        logger,
        optim_method: OptimMethod,
        power_to_calibrate: PowerToCalibrate,
        **optim_params,
) -> None:

    # Settings / Dynawo launcher
    settings = Settings()
    dynawo_launcher = settings.get_dynawo_launcher()
    logger.info(f"Dynawo launcher: {dynawo_launcher}")

    # Base case Dynawo
    try:
        logger.info("Starting Dynawo base case simulation for all experiences...")
        run_base_case_for_all(
            dynawo_launcher=dynawo_launcher,
            exp_set=exp_set,
            logger=logger,
        )
        logger.info("Dynawo base case simulation completed.")
    except SimulationPreconditionError as e:
        logger.error(f"Cannot run base case: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error during base case simulation: {e}")
        sys.exit(1)

    # Automatic parameter calibration
    logger.info("Starting calibration...")
    run_parameter_calibration(
        dynawo_launcher=dynawo_launcher,
        exp_set=exp_set,
        selected_sets=selected_sets,
        optim_method=optim_method,
        power_to_calibrate=power_to_calibrate,
        logger=logger,
        **optim_params,
    )

    # Display and dump results
    display_calibration_results(selected_sets, logger)

    calib_json_path = os.path.join(exp_set.temp_dir, "calibrated_parameters.json")
    dump_calibrated_parameters(selected_sets, calib_json_path, logger)

    corr_csv_path = os.path.join(exp_set.temp_dir, "correlation_indicators.csv")
    dump_correlation_indicators(exp_set, corr_csv_path, logger)

    plots_dir = os.path.join(exp_set.temp_dir, "plots")
    save_calibration_plots(exp_set, plots_dir, logger)


def prepare_experience_set(
    exp_ref_zipfile: str,
    logger,
    additional_zipfiles: list[str] | None = None,
) -> ExperienceSet:
    script_directory = os.path.dirname(os.path.abspath(__file__))
    base_temp_root = os.path.join(script_directory, "..", "temp")
    os.makedirs(base_temp_root, exist_ok=True)

    # ExperienceSet
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(base_temp_root, run_id)
    os.makedirs(temp_dir, exist_ok=True)
    exp_set = ExperienceSet(
        experience_ref=None,
        additional_experiences=[],
        col_name_p=None,
        col_name_q=None,
        temp_dir=temp_dir,
    )

    # Reference experience
    temp_dir_exp_ref = os.path.join(temp_dir, "experience_ref")
    os.makedirs(temp_dir_exp_ref, exist_ok=True)
    exp_name_ref = os.path.splitext(os.path.basename(exp_ref_zipfile))[0]
    try:
        with open(exp_ref_zipfile, "rb") as f:
            exp_ref = Experience(
                name=exp_name_ref,
                temp_dir_exp=temp_dir_exp_ref,
                weight=1.0,
                zip_file=f,
                logger=logger,
            )
    except ExperienceLoadError as e:
        logger.error(f"Error while loading reference experience: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error while loading reference experience: {e}")
        sys.exit(1)

    exp_set.experience_ref = exp_ref

    # Initialize col_name_p and col_name_q now that we have the exp_ref
    try:
        exp_set.initialize_col_names_from_exp_ref()
    except ValueError as e:
        logger.error(f"Error while inferring P/Q column names: {e}")
        sys.exit(1)

    # Additional experiences
    if additional_zipfiles:
        for zip_path in additional_zipfiles:
            exp_name_add = os.path.splitext(os.path.basename(zip_path))[0]
            temp_dir_exp_add = os.path.join(temp_dir, exp_name_add)
            os.makedirs(temp_dir_exp_add, exist_ok=True)

            try:
                exp_add = Experience(
                    name=exp_name_add,
                    temp_dir_exp=temp_dir_exp_add,
                    weight=1.0,
                    path_to_zip=zip_path,
                    logger=logger,
                )
            except ExperienceLoadError as e:
                logger.error(f"Error while loading additional experience '{exp_name_add}': {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error while loading additional experience '{exp_name_add}': {e}")
                continue

            try:
                exp_set.add_experience(exp_add)
                logger.info(
                    f"Additional experience '{exp_name_add}' has been loaded and added to the ExperienceSet."
                )
            except ValueError as e:
                logger.error(f"Cannot add additional experience '{exp_name_add}': {e}")

    return exp_set


def prepare_parameter_to_calibrate(
        parameters_sets,
        set_id, param_id,
        logger,
        min_bound=None, max_bound=None
):
    try:
        dynawo_param = parameters_sets[set_id][param_id]
    except KeyError as e:
        logger.error(f"Missing parameter '{param_id}' in set '{set_id}': {e}")
        sys.exit(1)

    if min_bound is not None:
        dynawo_param.set_min_bound(min_bound)
    if max_bound is not None:
        dynawo_param.set_max_bound(max_bound)

    return (set_id, dynawo_param)


def prepare_selected_sets(params):
    selected_sets = {}

    for set_id, dynawo_param in params:
        param_name = dynawo_param.get_name()

        if set_id not in selected_sets:
            selected_sets[set_id] = {}

        selected_sets[set_id][param_name] = dynawo_param

    return selected_sets


def dump_calibrated_parameters(selected_sets, output_path: str, logger) -> None:
    """
    Dump the calibrated parameters in a json file.

    Format :
    {
      "set_id": {
        "param_name": {
          "original_value": ...,
          "calibrated_value": ...,
          "min_bound": ...,
          "max_bound": ...
        },
        ...
      },
      ...
    }
    """
    calibrated_dict: Dict[str, Dict[str, Dict[str, float]]] = {}

    for set_id, params_dict in selected_sets.items():
        calibrated_dict[set_id] = {}
        for param_name, param_obj in params_dict.items():
            try:
                original_value = float(param_obj.get_original_value())
            except Exception:
                original_value = None

            calibrated_value = param_obj.get_calibrated_value()
            try:
                min_bound = float(param_obj.get_min_bound())
            except Exception:
                min_bound = None
            try:
                max_bound = float(param_obj.get_max_bound())
            except Exception:
                max_bound = None

            calibrated_dict[set_id][param_name] = {
                "original_value": original_value,
                "calibrated_value": calibrated_value,
                "min_bound": min_bound,
                "max_bound": max_bound,
            }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calibrated_dict, f, indent=2)

    logger.info(f"Calibrated parameters dumped to {output_path}")


def dump_correlation_indicators(exp_set: ExperienceSet, output_path: str, logger) -> None:
    """
    Dump the correlation indicators as a csv file.
    """
    rows: List[Dict[str, Any]] = []

    def add_row(exp, case_name: str, corr_dict: Dict[str, float]):
        if corr_dict is None:
            return
        row = {"experience": exp.name, "case": case_name}
        for key, value in corr_dict.items():
            row[key] = value
        rows.append(row)

    for exp in exp_set.get_all_experiences():
        add_row(exp, "base_case", exp.base_case_correlation_dict)
        add_row(exp, "calibrated", exp.calibrated_correlation_dict)
        add_row(exp, "custom", exp.custom_correlation_dict)

    if not rows:
        logger.info("No correlation indicators available to dump.")
        return

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    logger.info(f"Correlation indicators dumped to {output_path}")


def save_calibration_plots(exp_set: ExperienceSet, output_dir: str, logger) -> None:
    """
    Save, for each experience, a Plotly P/Q figure showing:
      - the reference (reference_data_df)
      - the base_case simulation (base_case_simulation_data_df)
      - the calibrated simulation (calibrated_simulation_data_df)

    The figures are written as HTML files in output_dir (one per experience).
    """
    os.makedirs(output_dir, exist_ok=True)

    col_name_p, col_name_q = exp_set.get_col_names()
    if col_name_p is None or col_name_q is None:
        logger.error("P/Q column names are not initialized in ExperienceSet.")
        return

    for exp in exp_set.get_all_experiences():
        if not exp.has_reference_values():
            logger.info(f"[{exp.name}] No reference_data_df - plots skipped.")
            continue

        reference_data_df = exp.reference_data_df
        base_df = exp.base_case_simulation_data_df
        calib_df = exp.calibrated_simulation_data_df

        if base_df is None and calib_df is None:
            logger.info(f"[{exp.name}] No base_case or calibrated simulation - plots skipped.")
            continue

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=(f"P - {exp.name}", f"Q - {exp.name}")
        )

        # Reference P and Q
        fig.add_trace(
            go.Scatter(
                x=reference_data_df.index,
                y=reference_data_df[col_name_p].values,
                mode="lines",
                name="P_reference",
                line=dict(color="magenta"),
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=reference_data_df.index,
                y=reference_data_df[col_name_q].values,
                mode="lines",
                name="Q_reference",
                line=dict(color="magenta"),
            ),
            row=1, col=2,
        )

        # Basecase P and Q
        if base_df is not None:
            fig.add_trace(
                go.Scatter(
                    x=base_df.index,
                    y=base_df[col_name_p].values,
                    mode="lines",
                    name="P_base_case",
                    line=dict(color="blue"),
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=base_df.index,
                    y=base_df[col_name_q].values,
                    mode="lines",
                    name="Q_base_case",
                    line=dict(color="blue"),
                ),
                row=1, col=2,
            )

        # Calibrated P and Q
        if calib_df is not None:
            fig.add_trace(
                go.Scatter(
                    x=calib_df.index,
                    y=calib_df[col_name_p].values,
                    mode="lines",
                    name="P_calibrated",
                    line=dict(color="green"),
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=calib_df.index,
                    y=calib_df[col_name_q].values,
                    mode="lines",
                    name="Q_calibrated",
                    line=dict(color="green"),
                ),
                row=1, col=2,
            )

        fig.update_layout(
            title=f"Calibration results - {exp.name}",
            xaxis_title="time (s)",
            xaxis2_title="time (s)",
        )

        output_path = os.path.join(output_dir, f"{exp.name}_calibration.html")
        fig.write_html(output_path)
        logger.info(f"[{exp.name}] Calibration plot saved to {output_path}")


def display_calibration_results(selected_sets, logger):
    logger.info("")
    logger.info("==============================================")
    logger.info(" Calibration completed")
    logger.info("==============================================")
    logger.info("")
    
    if not selected_sets:
        logger.info("No parameter was selected for calibration.")
        logger.info("==============================================")
        return

    for set_id_local, params_dict in selected_sets.items():
        for param_id_local, param_obj in params_dict.items():
            try:
                original_value = float(param_obj.get_original_value())
            except Exception:
                original_value = None

            calibrated_value = param_obj.get_calibrated_value()

            logger.info(f"Parameter: set_id='{set_id_local}', name='{param_id_local}'")
            if original_value is not None:
                logger.info(f"  Original value : {original_value}")
            else:
                logger.info("  Original value : (unknown)")
            if calibrated_value is not None:
                logger.info(f"  Calibrated value (best RMSE) : {calibrated_value}")
            else:
                logger.info("  Calibrated value (best RMSE) : (not available)")
            logger.info("")

    logger.info("==============================================")
    logger.info("")


if __name__ == "__main__":

    # Logger
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("main_cli")

    # Exp set
    exp_ref_zipfile = os.path.join(
        "test_cases",
        "dynawo_branch_3713_add_lvrt_hvrt_models",
        "test_case_1_H",
        "test_case_1.zip",
    )
    exp_set = prepare_experience_set(exp_ref_zipfile, logger)

    # Dynamic parameters to calibrate
    parameters_sets = exp_set.get_parameters_sets()

    param_H = prepare_parameter_to_calibrate(
        parameters_sets,
        set_id="SynchronousGenerator",
        param_id="generator_H",
        logger=logger,
        min_bound=0.0, max_bound=5.0,
    )

    param_XpdPu = prepare_parameter_to_calibrate(
        parameters_sets,
        set_id="SynchronousGenerator",
        param_id="generator_XpdPu",
        logger=logger,
        min_bound=0.0,
        max_bound=1.0,
    )
    params = [param_H, param_XpdPu]
    selected_sets = prepare_selected_sets(params)

    # Solver configuration
    optim_method = OptimMethod.NOMAD
    power_to_calibrate = PowerToCalibrate.PQ
    optim_params = {
        "max_bb_eval": 5,      # max blackbox iteration
        "timeout_seconds": 600  # timeout (sec)
    }

    # logging general information
    temp_dir = exp_set.temp_dir
    col_name_p, col_name_q = exp_set.get_col_names()
    logger.info(f"Using temp_dir for this run: {temp_dir}")
    logger.info(f"Reference P column: {col_name_p}")
    logger.info(f"Reference Q column: {col_name_q}")
    logger.info("")
    logger.info("Selected parameters for calibration:")
    for set_id in selected_sets:
        for pid in selected_sets[set_id]:
            logger.info(f"  - {set_id}/{pid}")
    logger.info("")

    # Run the calibration
    main(exp_set, selected_sets, logger, optim_method, power_to_calibrate, **optim_params)
