# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
This file contains the necessary functions for the automatic calibration
of the model parameters.

This calibration consists in minimizing the RMSE between the measured signal
and the output of the Dynawo compputation.
"""

from util_functions import sample_df, rmse, get_col_name_p_q
from scipy.optimize import minimize
from scipy.optimize import differential_evolution
import PyNomad
import numpy as np
from dynawo_functions import run_dynawo, modify_multiple_param_par_file_for_optim, \
    DynawoFailedException, get_simulation_data
from enum import Enum


class OptimMethod(Enum):
    DIFFERENTIAL_EVOLUTION = "differential_evolution"
    NELDER_MEAD = "nelder_mead"
    NOMAD = "Nomad"


def objective_func(
        x, index_to_param_map,
        dynawo_launcher, jobs_file, par_file,
        sampled_measured_p, sampled_measured_q
):
    modify_multiple_param_par_file_for_optim(par_file, x, index_to_param_map)
    try:
        simulation_data_df = run_dynawo(dynawo_launcher, jobs_file)
        sampled_simulation_data_df = sample_df(simulation_data_df)
        col_name_p, col_name_q = get_col_name_p_q()
        sampled_simulated_p = sampled_simulation_data_df[col_name_p].values
        sampled_simulated_q = sampled_simulation_data_df[col_name_q].values
        error = rmse(sampled_measured_p, sampled_measured_q, sampled_simulated_p, sampled_simulated_q)
        return error
    except DynawoFailedException:
        SUPER_HIGH_VALUE_ERROR = 9999
        return SUPER_HIGH_VALUE_ERROR


def prepare_x0(
        selected_sets,
        discrete_variables_allowed=False,  # TODO
        streamlit_logger=None
):
    x0 = []
    bounds = []
    index_to_param_map = dict()
    i = 0
    for set_id in selected_sets:
        for parameter_id in selected_sets[set_id]:
            parameter = selected_sets[set_id][parameter_id]
            param_name = parameter.get_name()
            param_type = parameter.get_type()
            if param_type == "DOUBLE":
                param_value = float(parameter.get_value())
                if streamlit_logger is not None:
                    streamlit_logger.info(set_id + "/" + param_name + " - " + "included amongst the variables to calibrate")
                    streamlit_logger.info("Reference value: " + str(round(param_value, 4))
                                          + ", min bound: " + str(round(parameter.get_min_bound(), 4))
                                          + ", max bound: " + str(round(parameter.get_max_bound(), 4)))
            else:
                if streamlit_logger is not None:
                    streamlit_logger.error(set_id + "/" + param_name + " - " + "Skipped")
                continue
            x0.append(param_value)
            bounds.append((parameter.get_min_bound(), parameter.get_max_bound()))
            index_to_param_map[i] = (set_id, param_name)
            i = i + 1
    if streamlit_logger is not None:
        streamlit_logger.info("")
    return x0, bounds, index_to_param_map


def log_param_values(x, index_to_param_map, streamlit_logger):
    for i in range(len(x)):
        set_id, param_id = index_to_param_map[i]
        streamlit_logger.info(set_id + "/" + param_id + " - "
                              + "value: " + str(round(x[i], 4)))


def log_final_param_values(x_calibrated, x0, index_to_param_map, streamlit_logger):
    for i in range(len(x_calibrated)):
        set_id, param_id = index_to_param_map[i]
        streamlit_logger.info(set_id + "/" + param_id + " - "
                              + "initial value: " + str(round(x0[i], 4)) + " - "
                              + "calibrated value: " + str(round(x_calibrated[i], 4)))


def nelder_mead_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            measured_p,
            measured_q,
            streamlit_logger=None
        ):
    """
    Fast - can't handle discrete variables - good at finding a solution close to the starting value
    """
    discrete_variables_allowed = False  # Nelder-Mead can't manage discrete variables
    x0, bounds, index_to_param_map = prepare_x0(selected_sets, discrete_variables_allowed, streamlit_logger)

    errors = []

    def callback(x):
        # This callback consumes time.
        # Consider adding an option to mute him.
        error = objective_func(x, index_to_param_map, dynawo_launcher, jobs_file, par_file, measured_p, measured_q)
        error = round(error, 4)
        errors.append(error)
        if streamlit_logger is not None:
            iteration_num = len(errors)
            streamlit_logger.info(f"--- Iteration {iteration_num} - rmse: {error}")
            log_param_values(x, index_to_param_map, streamlit_logger)
            streamlit_logger.info("")

    opt_result = minimize(
        lambda x: objective_func(x, index_to_param_map, dynawo_launcher, jobs_file, par_file, measured_p, measured_q),
        x0,
        bounds=bounds,
        method="Nelder-Mead",
        callback=callback,
        options={"maxiter": 100}
    )

    x_calibrated = opt_result.x
    if streamlit_logger is not None:
        log_final_param_values(x_calibrated, x0, index_to_param_map, streamlit_logger)

    calibrated_simulation_data_df = get_simulation_data(jobs_file)
    return calibrated_simulation_data_df


def differential_evolution_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            measured_p,
            measured_q,
            streamlit_logger
        ):
    """
    Slow - can handle discrete variables - can find solutions far from the starting point
    """
    discrete_variables_allowed = True  # TODO differential_evolution can manage discrete variables
    x0, bounds, index_to_param_map = prepare_x0(selected_sets, discrete_variables_allowed, streamlit_logger)

    errors = []

    def callback_de(x, convergence):
        """
        convergence is requested for this callback, but not so informative in this context,
        hence the convergence value is not displayed
        """
        error = objective_func(x, index_to_param_map, dynawo_launcher, jobs_file, par_file, measured_p, measured_q)
        error = round(error, 4)
        errors.append(error)
        generation_num = len(errors)
        if streamlit_logger is not None:
            streamlit_logger.info(f"--- Evaluation of generation {generation_num} - rmse of best: {error}")
            log_param_values(x, index_to_param_map, streamlit_logger)
            streamlit_logger.info("")

    opt_result = differential_evolution(
        lambda x: objective_func(x, index_to_param_map, dynawo_launcher, jobs_file, par_file, measured_p, measured_q),
        bounds=bounds,
        x0=x0,
        atol=0.0001,
        callback=callback_de
    )

    x_calibrated = opt_result.x
    if streamlit_logger is not None:
        log_final_param_values(x_calibrated, x0, index_to_param_map, streamlit_logger)

    calibrated_simulation_data_df = get_simulation_data(jobs_file)
    return calibrated_simulation_data_df


def nomad_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            measured_p,
            measured_q,
            streamlit_logger,
            max_bb_eval=100
        ):
    # TODO - NOMAD can handle discrete and boolean variables
    discrete_variables_allowed = False
    x0, bounds, index_to_param_map = prepare_x0(
        selected_sets,
        discrete_variables_allowed,
        streamlit_logger
    )

    x0 = np.asarray(x0, dtype=float)
    n = x0.size

    # Bounds - NOMAD needs 2 lists
    lower_bounds = [b[0] for b in bounds]
    upper_bounds = [b[1] for b in bounds]

    errors = []

    # Blackbox NOMAD : appelée à chaque évaluation de f
    def nomad_bb(x_eval):
        try:
            x = np.array([x_eval.get_coord(i) for i in range(n)], dtype=float)

            f = objective_func(
                x,
                index_to_param_map,
                dynawo_launcher,
                jobs_file,
                par_file,
                measured_p,
                measured_q
            )

            error = float(f)
            errors.append(error)

            if streamlit_logger is not None:
                iteration_num = len(errors)  # nb d'évaluations
                streamlit_logger.info(f"--- Evaluation {iteration_num} - rmse: {round(error, 4)}")
                log_param_values(x, index_to_param_map, streamlit_logger)
                streamlit_logger.info("")

            raw_bbo = f"{f}"
            x_eval.setBBO(raw_bbo.encode("UTF-8"))

        except Exception:
            print("Unexpected eval error in NOMAD blackbox", sys.exc_info()[0])
            return 0  # evaluation failed

        return 1  # evaluation succeeded

    # Building NOMAD param
    # X0 seems redundant since we provide x0 to PyNomad.optimize,
    # but it is consistent with the official templates
    params = [
        f"DIMENSION {n}",
        "BB_OUTPUT_TYPE OBJ",
        "X0 ( " + " ".join(str(v) for v in x0.tolist()) + " )",
        "LOWER_BOUND ( " + " ".join(str(v) for v in lower_bounds) + " )",
        "UPPER_BOUND ( " + " ".join(str(v) for v in upper_bounds) + " )",
        f"MAX_BB_EVAL {max_bb_eval}",
        # minimal display
        "DISPLAY_DEGREE 0",
        "DISPLAY_ALL_EVAL false",
        "DISPLAY_STATS BBE OBJ"
    ]

    result = PyNomad.optimize(nomad_bb, x0.tolist(), [], [], params)
    x_calibrated = np.array(result["x_best"], dtype=float)

    # Now that the best set of parametrs has been identifified,
    # We re-run a last simulation to get the good calibrated_simulation_data_df
    final_error = objective_func(
        x_calibrated,
        index_to_param_map,
        dynawo_launcher,
        jobs_file,
        par_file,
        measured_p,
        measured_q
    )

    if streamlit_logger is not None:
        log_final_param_values(x_calibrated, x0, index_to_param_map, streamlit_logger)

    calibrated_simulation_data_df = get_simulation_data(jobs_file)
    return calibrated_simulation_data_df


def run_parameter_calibration(
        dynawo_launcher,
        jobs_file,
        par_file,
        selected_sets,
        sampled_measured_p,
        sampled_measured_q,
        base_case_rmse,
        optim_method: OptimMethod,
        streamlit_logger=None
):
    # TODO : add button to stop optimization ?
    if streamlit_logger is not None:
        streamlit_logger.info("Start of calibration")
        streamlit_logger.info("Optimization method: " + optim_method.value)
        streamlit_logger.info("")
        streamlit_logger.info(f"--- Initial parameters - rmse: {round(base_case_rmse, 4)}")
        streamlit_logger.info("")

    if optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION:
        calibrated_simulation_data_df = differential_evolution_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            sampled_measured_p,
            sampled_measured_q,
            streamlit_logger
        )
    elif optim_method == OptimMethod.NELDER_MEAD:
        calibrated_simulation_data_df = nelder_mead_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            sampled_measured_p,
            sampled_measured_q,
            streamlit_logger
        )
    else:
        calibrated_simulation_data_df = nomad_calibration(
            dynawo_launcher,
            jobs_file,
            par_file,
            selected_sets,
            sampled_measured_p,
            sampled_measured_q,
            streamlit_logger
        )

    if streamlit_logger is not None:
        streamlit_logger.info("End of calibration")

    return calibrated_simulation_data_df

