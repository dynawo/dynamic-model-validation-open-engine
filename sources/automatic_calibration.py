# automatic_calibration.py
# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
Automatic calibration of model parameters (multi-experience version).

The calibration consists in minimizing a global RMSE (weighted average)
between the reference signals and the outputs of Dynawo computations
across all experiences in an ExperienceSet.

All calibration is performed on copies of the base_case files, located
in each Experience's temp_folder_calibration, so that original .par
files are never overwritten.
"""

import os
import shutil
import sys
from enum import Enum
from typing import Any, Dict, Tuple, List, Optional

import numpy as np
import PyNomad
from scipy.optimize import minimize
from pymoo.core.problem import Problem
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.termination import get_termination
from pymoo.optimize import minimize as pymoo_minimize

from util_functions import sample_df, rmse, PowerToCalibrate
from dynawo_functions import (
    run_dynawo,
    modify_multiple_param_par_file_for_optim,
    DynawoFailedException,
    SimulationPreconditionError
)
from experience_set import ExperienceSet

SUPER_HIGH_VALUE_ERROR = 9999


class OptimMethod(Enum):
    NOMAD = "Nomad"
    NELDER_MEAD = "Nelder mead"
    DIFFERENTIAL_EVOLUTION = "Differential evolution"


def prepare_x0(
    selected_sets: Dict[str, Dict[str, Any]],
    discrete_variables_allowed: bool = False,  # TODO: need to address boolean variables
    logger: Any = None,
) -> Tuple[List[float], List[Tuple[float, float]], Dict[int, Tuple[str, str]]]:
    """
    Prepare:
      - x0: initial values of the optimization variables,
      - bounds: list of (min_bound, max_bound) tuples,
      - index_to_param_map: map index -> (set_id, param_name).

    Only parameters of type DOUBLE are handled for now.
    """
    x0: List[float] = []
    bounds: List[Tuple[float, float]] = []
    index_to_param_map: Dict[int, Tuple[str, str]] = {}
    i = 0

    for set_id in selected_sets:
        for parameter_id in selected_sets[set_id]:
            parameter = selected_sets[set_id][parameter_id]
            param_name = parameter.get_name()
            param_type = parameter.get_type()

            if param_type != "DOUBLE":
                if logger is not None:
                    logger.error(
                        f"{set_id}/{param_name} - Skipped (type {param_type} not supported)"
                    )
                continue

            param_value = float(parameter.get_value())
            min_bound = float(parameter.get_min_bound())
            max_bound = float(parameter.get_max_bound())

            if min_bound == max_bound:
                if logger is not None:
                    logger.error(
                        f"{set_id}/{param_name} - Skipped (min_bound == max_bound)"
                    )
                continue

            original_value = param_value

            if param_value < min_bound:
                param_value = min_bound
                if logger is not None:
                    logger.warning(
                        f"{set_id}/{param_name} - Original value {round(original_value, 4)} "
                        f"below lower bound {round(min_bound, 4)}. "
                        f"Initial value set to {round(param_value, 4)}."
                    )
            elif param_value > max_bound:
                param_value = max_bound
                if logger is not None:
                    logger.warning(
                        f"{set_id}/{param_name} - Original value {round(original_value, 4)} "
                        f"above upper bound {round(max_bound, 4)}. "
                        f"Initial value set to {round(param_value, 4)}."
                    )

            if logger is not None:
                logger.info(
                    f"{set_id}/{param_name} - included amongst the variables to calibrate"
                )
                logger.info(
                    "Initial value: " + str(round(param_value, 4))
                    + ", min bound: " + str(round(min_bound, 4))
                    + ", max bound: " + str(round(max_bound, 4))
                )

            x0.append(param_value)
            bounds.append((min_bound, max_bound))
            index_to_param_map[i] = (set_id, param_name)
            i += 1

    if logger is not None:
        logger.info("")

    return x0, bounds, index_to_param_map


def log_param_values(x: np.ndarray, index_to_param_map: Dict[int, Tuple[str, str]], logger: Any) -> None:
    """ Log the current parameter values during the optimization. """
    for i in range(len(x)):
        set_id, param_id = index_to_param_map[i]
        logger.info(
            f"{set_id}/{param_id} - value: {round(float(x[i]), 4)}"
        )


def log_final_param_values(
    x_calibrated: np.ndarray,
    x0: List[float],
    index_to_param_map: Dict[int, Tuple[str, str]],
    logger: Any,
) -> None:
    """ Log the initial and calibrated parameter values after the optimization. """
    for i in range(len(x_calibrated)):
        set_id, param_id = index_to_param_map[i]
        logger.info(
            f"{set_id}/{param_id} - initial value: {round(float(x0[i]), 4)} "
            f"- calibrated value: {round(float(x_calibrated[i]), 4)}"
        )


def prepare_calibration_folders(
    exp_set: ExperienceSet,
    logger: Any = None
) -> None:
    """
    For each experience in the ExperienceSet:
      - clean its temp_folder_calibration,
      - copy files from temp_folder_base_case to temp_folder_calibration.

    The calibration jobs/par file paths can then be derived from each Experience.
    """
    for exp in exp_set.get_all_experiences():
        calib_folder = exp.temp_folder_calibration
        base_folder = exp.temp_folder_base_case

        # Cleaning
        if os.path.isdir(calib_folder):
            for element in os.listdir(calib_folder):
                path = os.path.join(calib_folder, element)
                if os.path.isfile(path) or os.path.islink(path):
                    os.unlink(path)
                else:
                    shutil.rmtree(path)
        else:
            os.makedirs(calib_folder, exist_ok=True)

        # Copy of basecase files into the calibration folder
        if os.path.isdir(base_folder):
            for element in os.listdir(base_folder):
                src = os.path.join(base_folder, element)
                dst = os.path.join(calib_folder, element)
                if os.path.isfile(src):
                    shutil.copy(src, dst)

        if logger is not None:
            logger.info(
                f"[{exp.name}] Calibration folder prepared: {calib_folder}"
            )


def objective_func_multi_experience(
    x: np.ndarray,
    index_to_param_map: Dict[int, Tuple[str, str]],
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    power_to_calibrate: PowerToCalibrate,
) -> float:
    """
    Global calibration objective:
      global_RMSE = weighted average of the RMSE over all experiences in the ExperienceSet.
    """
    col_name_p, col_name_q = exp_set.get_col_names()

    total_weighted_error = 0.0
    total_weight = 0.0

    for exp in exp_set.get_all_experiences():
        weight = exp.get_weight()
        if weight <= 0.0:  # should not happen
            continue
        if not exp.has_dynawo_inputs() or not exp.has_reference_values():
            continue

        reference_data_df = exp.reference_data_df

        t_start = exp.get_t_start()
        t_end = exp.get_t_end()
        if t_start is None or t_end is None or reference_data_df is None:
            continue

        jobs_file_calib = exp.get_automatic_calibration_jobs_file()
        par_file_calib = exp.get_automatic_calibration_par_file()

        modify_multiple_param_par_file_for_optim(par_file_calib, x, index_to_param_map)

        try:
            simulation_data_df = run_dynawo(dynawo_launcher, jobs_file_calib)

            sampled_simulation_data_df = sample_df(
                simulation_data_df,
                start_time=t_start,
                end_time=t_end,
            )
            sampled_reference_data_df = sample_df(
                reference_data_df,
                start_time=t_start,
                end_time=t_end,
            )

            sampled_simulated_p = sampled_simulation_data_df[col_name_p].values
            sampled_simulated_q = sampled_simulation_data_df[col_name_q].values
            sampled_reference_p = sampled_reference_data_df[col_name_p].values
            sampled_reference_q = sampled_reference_data_df[col_name_q].values

            error_exp = rmse(
                sampled_reference_p,
                sampled_reference_q,
                sampled_simulated_p,
                sampled_simulated_q,
                power_to_calibrate,
            )
        except DynawoFailedException:
            error_exp = SUPER_HIGH_VALUE_ERROR

        total_weighted_error += weight * error_exp
        total_weight += weight

    # In case, should not happen since exp.weight must be > 0
    if total_weight == 0.0:
        return SUPER_HIGH_VALUE_ERROR

    return total_weighted_error / total_weight


def nelder_mead_calibration(
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    logger: Any,
    nm_max_iterations: int,
) -> np.ndarray:
    """
    Calibration using the scipy Nelder-Mead method.
    """
    errors: List[float] = []

    def callback(x):
        x_arr = np.array(x, dtype=float)
        error = objective_func_multi_experience(
            x_arr,
            index_to_param_map,
            dynawo_launcher,
            exp_set,
            power_to_calibrate,
        )

        error = round(float(error), 4)
        errors.append(error)
        if logger is not None:
            iteration_num = len(errors)
            logger.info(f"--- Iteration {iteration_num} - global rmse: {error}")
            log_param_values(x_arr, index_to_param_map, logger)
            logger.info("")

    opt_result = minimize(
        lambda x: objective_func_multi_experience(
            np.array(x, dtype=float),
            index_to_param_map,
            dynawo_launcher,
            exp_set,
            power_to_calibrate,
        ),
        x0,
        bounds=bounds,
        method="Nelder-Mead",
        callback=callback,
        options={"maxiter": nm_max_iterations},
    )

    x_calibrated = np.array(opt_result.x, dtype=float)
    if logger is not None:
        if opt_result.fun >= SUPER_HIGH_VALUE_ERROR:
            logger.warning(
                "All the Dynawo simulations failed during the calibration. "
                "The results cannot be exploited."
            )
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def differential_evolution_calibration(
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    popsize: int,
    maxiter: int,
    logger: Any,
) -> np.ndarray:
    """
    Calibration using the pymoo Differential Evolution method.
    """
    n_var = len(bounds)
    if n_var == 0:
        raise ValueError("No continuous parameter selected for calibration.")

    xl = np.array([b[0] for b in bounds], dtype=float)
    xu = np.array([b[1] for b in bounds], dtype=float)

    objective_call_counter = {"count": 0}

    class DynawoCalibrationProblem(Problem):
        def __init__(self):
            super().__init__(
                n_var=n_var,
                n_obj=1,
                n_constr=0,
                xl=xl,
                xu=xu,
            )

        def _evaluate(self, X, out, *args, **kwargs):
            F = []
            for x in X:
                objective_call_counter["count"] += 1
                if logger is not None:
                    logger.info(
                        f"OBJECTIVE CALL #{objective_call_counter['count']}"
                    )

                val = objective_func_multi_experience(
                    np.array(x, dtype=float),
                    index_to_param_map,
                    dynawo_launcher,
                    exp_set,
                    power_to_calibrate,
                )
                F.append(val)

            out["F"] = np.array(F, dtype=float).reshape(-1, 1)

    problem = DynawoCalibrationProblem()

    algorithm = DE(pop_size=popsize)
    termination = get_termination("n_gen", maxiter)

    def pymoo_callback(alg):
        if logger is None:
            return

        gen = alg.n_gen
        if alg.opt is None or len(alg.opt) == 0:
            return

        X_opt = alg.opt.get("X")[0]
        F_opt = alg.opt.get("F")[0][0]  # scalar

        logger.info(
            f"--- Generation {gen} - rmse of best: {round(float(F_opt), 4)}"
        )
        log_param_values(np.array(X_opt, dtype=float), index_to_param_map, logger)
        logger.info("")

    res = pymoo_minimize(
        problem,
        algorithm,
        termination,
        seed=1,
        verbose=False,
        callback=pymoo_callback,
    )

    x_calibrated = np.array(res.X, dtype=float)
    f_calibrated = float(res.F) if res.F is not None else None

    if logger is not None:
        logger.info(
            f"Total OBJECTIVE calls (launches of Dynawo) = {objective_call_counter['count']}"
        )

        if f_calibrated is not None and f_calibrated >= SUPER_HIGH_VALUE_ERROR:
            logger.warning(
                "All the Dynawo simulations failed during the calibration. "
                "The results cannot be exploited."
            )
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def nomad_calibration(
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    logger: Any,
    max_bb_eval: int,
    timeout_seconds: int,
) -> np.ndarray:
    """
    Calibration using the NOMAD method.
    """

    x0_arr = np.asarray(x0, dtype=float)
    n = x0_arr.size

    lower_bounds = [b[0] for b in bounds]
    upper_bounds = [b[1] for b in bounds]

    errors: List[float] = []

    def nomad_bb(x_eval):
        try:
            x = np.array([x_eval.get_coord(i) for i in range(n)], dtype=float)

            f = objective_func_multi_experience(
                x,
                index_to_param_map,
                dynawo_launcher,
                exp_set,
                power_to_calibrate,
            )

            error = float(f)
            errors.append(error)

            if logger is not None:
                iteration_num = len(errors)
                logger.info(
                    f"--- Evaluation {iteration_num} - global rmse: {round(error, 4)}"
                )
                log_param_values(x, index_to_param_map, logger)
                logger.info("")

            raw_bbo = f"{f}"
            x_eval.setBBO(raw_bbo.encode("UTF-8"))

        except Exception:
            print("Unexpected eval error in NOMAD blackbox", sys.exc_info()[0])
            return 0

        return 1

    params = [
        f"DIMENSION {n}",
        "BB_OUTPUT_TYPE OBJ",
        "X0 ( " + " ".join(str(v) for v in x0_arr.tolist()) + " )",
        "LOWER_BOUND ( " + " ".join(str(v) for v in lower_bounds) + " )",
        "UPPER_BOUND ( " + " ".join(str(v) for v in upper_bounds) + " )",
        f"MAX_BB_EVAL {max_bb_eval}",
        "DISPLAY_DEGREE 0",
        "DISPLAY_ALL_EVAL false",
        "DISPLAY_STATS BBE OBJ",
        f"MAX_TIME {timeout_seconds}",
    ]

    try:
        result = PyNomad.optimize(nomad_bb, x0_arr.tolist(), [], [], params)
    except KeyboardInterrupt:
        if logger is not None:
            logger.warning("Calibration interrupted by user (Nomad stopped).")
        raise

    if "x_best_feas" in result and result["x_best_feas"]:
        x_calibrated = np.array(result["x_best_feas"][0], dtype=float)
    elif "x_single_best" in result:
        x_calibrated = np.array(result["x_single_best"], dtype=float)
    elif "x_best" in result:
        x_calibrated = np.array(result["x_best"], dtype=float)
    else:
        raise ValueError("Impossible to retrieve the best solution from the Nomad output.")

    final_error = objective_func_multi_experience(
        x_calibrated,
        index_to_param_map,
        dynawo_launcher,
        exp_set,
        power_to_calibrate,
    )

    if logger is not None:
        logger.info(result.get("stop_reason", ""))
        if final_error >= SUPER_HIGH_VALUE_ERROR:
            logger.warning(
                "All the Dynawo simulations failed during the calibration. "
                "The results cannot be exploited."
            )
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def run_parameter_calibration(
    dynawo_launcher: Any,
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, Any]],
    optim_method: OptimMethod,
    power_to_calibrate: PowerToCalibrate,
    logger: Any = None,
    **optim_params
):
    """
    Run the parameter calibration on all experiences in the ExperienceSet.

    The objective is a global RMSE, computed as a weighted average over all experiences.
    """
    if not exp_set.can_run_calibration():
        raise SimulationPreconditionError(
            "Cannot run automatic calibration: reference base case is not calculated."
        )

    if not selected_sets:
        if logger is not None:
            logger.warning("No parameters selected for automatic calibration.")
        return None

    if logger is not None:
        logger.info("Start of multi-experience calibration")
        logger.info("Optimization method: " + optim_method.value)
        logger.info("Calibration on: " + power_to_calibrate.value)
        logger.info("")

    prepare_calibration_folders(exp_set, logger=logger)

    # TODO: rework boolean variable management
    discrete_variables_allowed = (optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION)
    x0, bounds, index_to_param_map = prepare_x0(
        selected_sets,
        discrete_variables_allowed,
        logger,
    )

    if optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION:
        popsize_defaut = 15
        maxiter_defaut = 20
        popsize = optim_params.get("popsize", popsize_defaut)
        maxiter = optim_params.get("maxiter", maxiter_defaut)

        x_calibrated = differential_evolution_calibration(
            dynawo_launcher,
            exp_set,
            x0,
            bounds,
            index_to_param_map,
            power_to_calibrate,
            popsize,
            maxiter,
            logger,
        )

    elif optim_method == OptimMethod.NELDER_MEAD:
        nm_max_iterations_default = 100
        nm_max_iterations = optim_params.get("nm_max_iterations", nm_max_iterations_default)

        x_calibrated = nelder_mead_calibration(
            dynawo_launcher,
            exp_set,
            x0,
            bounds,
            index_to_param_map,
            power_to_calibrate,
            logger,
            nm_max_iterations,
        )

    else:  # NOMAD
        max_bb_eval_default = 100
        max_bb_eval = optim_params.get("max_bb_eval", max_bb_eval_default)
        timeout_seconds_default = 600
        timeout_seconds = optim_params.get("timeout_seconds", timeout_seconds_default)

        x_calibrated = nomad_calibration(
            dynawo_launcher,
            exp_set,
            x0,
            bounds,
            index_to_param_map,
            power_to_calibrate,
            logger,
            max_bb_eval,
            timeout_seconds,
        )

    # Update selected_sets with the outputs of the calibration
    for i, (set_id, param_name) in index_to_param_map.items():
        try:
            param_obj = selected_sets[set_id][param_name]
            param_obj.set_calibrated_value(float(x_calibrated[i]))
        except KeyError:
            continue

    # Update the correlation dicts when dynawo is run with the set of best parameters
    col_name_p, col_name_q = exp_set.get_col_names()
    for exp in exp_set.get_all_experiences():
        if not exp.has_dynawo_inputs() or not exp.has_reference_values():
            exp.calibrated_simulation_data_df = None
            exp.calibrated_correlation_dict = None
            continue

        jobs_file_calib = exp.get_automatic_calibration_jobs_file()
        par_file_calib = exp.get_automatic_calibration_par_file()

        modify_multiple_param_par_file_for_optim(par_file_calib, x_calibrated, index_to_param_map)

        try:
            sim_df = run_dynawo(dynawo_launcher, jobs_file_calib)
            exp.calibrated_simulation_data_df = sim_df

            corr_dict = exp.compute_correlation_dict(
                simulation_df=sim_df,
                col_name_p=col_name_p,
                col_name_q=col_name_q,
            )
            exp.calibrated_correlation_dict = corr_dict

        except DynawoFailedException:
            exp.calibrated_simulation_data_df = None
            exp.calibrated_correlation_dict = None

    if logger is not None:
        logger.info("End of multi-experience calibration")


