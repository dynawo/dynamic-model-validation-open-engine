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
import logging
import numpy as np
import PyNomad
from enum import Enum
from typing import Any, Dict, Tuple, List
from scipy.optimize import minimize
from pymoo.core.problem import Problem
from pymoo.algorithms.soo.nonconvex.de import DE
from pymoo.termination import get_termination
from pymoo.optimize import minimize as pymoo_minimize
from util_functions import (
    sample_df,
    rmse,
    PowerToCalibrate
)
from dynawo_functions import (
    run_dynawo,
    modify_multiple_param_par_file_for_optim,
    DynawoFailedException,
    SimulationPreconditionError,
    DynawoParam,
)
from experience_set import ExperienceSet
from typing import TYPE_CHECKING, Union
if TYPE_CHECKING:
    from experience import Experience
from const import SUPER_HIGH_VALUE_ERROR
from msg import (
    MSG_SIMULATION_FAILED,
    MSG_NO_PARAMETERS_SELECTED_CALIBRATION,
    MSG_CALIBRATION_NOT_READY
)


class OptimMethod(Enum):
    NOMAD = "Nomad"
    NELDER_MEAD = "Nelder mead"
    DIFFERENTIAL_EVOLUTION = "Differential evolution"


def _prepare_single_param_for_x0(
    parameter: DynawoParam,
    set_id: str,
    logger: logging.Logger,
) -> Tuple[str, float, float, float] | None:
    """
    Prepare a single parameter for inclusion in x0/bounds/index_to_param_map.

    Returns (param_name, param_value, min_bound, max_bound) or None if the parameter must be skipped.
    """
    param_name = parameter.get_name()
    param_type = parameter.get_type()

    if param_type != "DOUBLE":
        if logger is not None:
            logger.error(
                f"{set_id}/{param_name} - Skipped (type {param_type} not supported)"
            )
        return None

    param_value = float(parameter.get_value())
    min_bound = float(parameter.get_min_bound())
    max_bound = float(parameter.get_max_bound())

    if min_bound == max_bound:
        if logger is not None:
            logger.error(
                f"{set_id}/{param_name} - Skipped (min_bound == max_bound)"
            )
        return None

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

    return param_name, param_value, min_bound, max_bound


def prepare_x0(
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    discrete_variables_allowed: bool = False,  # TODO: need to address boolean variables
    logger: logging.Logger = None,
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

    for set_id, params_in_set in selected_sets.items():
        for parameter_id, parameter in params_in_set.items():
            prepared = _prepare_single_param_for_x0(parameter, set_id, logger)
            if prepared is None:
                continue

            param_name, param_value, min_bound, max_bound = prepared

            x0.append(param_value)
            bounds.append((min_bound, max_bound))
            index_to_param_map[i] = (set_id, param_name)
            i += 1

    if logger is not None:
        logger.info("")

    return x0, bounds, index_to_param_map


def log_param_values(x: np.ndarray, index_to_param_map: Dict[int, Tuple[str, str]], logger: logging.Logger) -> None:
    """
    Log the current parameter values during the optimization.
    """
    for i in range(len(x)):
        set_id, param_id = index_to_param_map[i]
        logger.info(
            f"{set_id}/{param_id} - value: {round(float(x[i]), 4)}"
        )


def log_final_param_values(
    x_calibrated: np.ndarray,
    x0: List[float],
    index_to_param_map: Dict[int, Tuple[str, str]],
    logger: logging.Logger,
) -> None:
    """
    Log the initial and calibrated parameter values after the optimization.
    """
    for i in range(len(x_calibrated)):
        set_id, param_id = index_to_param_map[i]
        logger.info(
            f"{set_id}/{param_id} - initial value: {round(float(x0[i]), 4)} "
            f"- calibrated value: {round(float(x_calibrated[i]), 4)}"
        )


def _clean_calibration_folder(calib_folder: str) -> None:
    """
    Clean the calibration folder: delete files and subdirectories if it exists,
    otherwise create it.
    """
    if os.path.isdir(calib_folder):
        for element in os.listdir(calib_folder):
            path = os.path.join(calib_folder, element)
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
            else:
                shutil.rmtree(path)
    else:
        os.makedirs(calib_folder, exist_ok=True)


def _copy_basecase_to_calibration(base_folder: str, calib_folder: str) -> None:
    """
    Copy base case files into the calibration folder.
    """
    if os.path.isdir(base_folder):
        for element in os.listdir(base_folder):
            src = os.path.join(base_folder, element)
            dst = os.path.join(calib_folder, element)
            if os.path.isfile(src):
                shutil.copy(src, dst)


def _prepare_calibration_folder_for_experience(exp: "Experience", logger: logging.Logger = None) -> None:
    calib_folder = exp.temp_folder_calibration
    base_folder = exp.temp_folder_base_case

    _clean_calibration_folder(calib_folder)
    _copy_basecase_to_calibration(base_folder, calib_folder)

    if logger is not None:
        logger.info(f"[{exp.name}] Calibration folder prepared: {calib_folder}")


def prepare_calibration_folders(
    exp_set: ExperienceSet,
    logger: logging.Logger = None,
) -> None:
    """
    For each experience in the ExperienceSet:
      - clean its temp_folder_calibration,
      - copy files from temp_folder_base_case to temp_folder_calibration.

    The calibration jobs/par file paths can then be derived from each Experience.
    """
    for exp in exp_set.get_all_experiences():
        _prepare_calibration_folder_for_experience(exp, logger)


def objective_func_multi_experience(
    x: np.ndarray,
    index_to_param_map: Dict[int, Tuple[str, str]],
    dynawo_launcher: str,
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

        ok, _ = exp.check_ready_for_automatic_calibration()
        if not ok:
            continue

        weight = exp.get_weight()
        reference_data_df = exp.reference_data_df
        t_start = exp.get_t_start()
        t_end = exp.get_t_end()

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
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    logger: logging.Logger,
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
            logger.warning(MSG_SIMULATION_FAILED)
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def differential_evolution_calibration(
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    popsize: int,
    maxiter: int,
    logger: logging.Logger,
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

        def _evaluate(self, x_values, out, *args, **kwargs):
            f_values = []
            for x in x_values:
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
                f_values.append(val)

            out["F"] = np.array(f_values, dtype=float).reshape(-1, 1)

    problem = DynawoCalibrationProblem()

    algorithm = DE(pop_size=popsize)
    termination = get_termination("n_gen", maxiter)

    def pymoo_callback(alg):
        if logger is None:
            return

        gen = alg.n_gen
        if alg.opt is None or len(alg.opt) == 0:
            return

        x_opt = alg.opt.get("X")[0]
        f_opt = alg.opt.get("F")[0][0]  # scalar

        logger.info(
            f"--- Generation {gen} - rmse of best: {round(float(f_opt), 4)}"
        )
        log_param_values(np.array(x_opt, dtype=float), index_to_param_map, logger)
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
            logger.warning(MSG_SIMULATION_FAILED)
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def _extract_nomad_best_solution(result: Dict[str, Any]) -> np.ndarray:
    """
    Extract the best solution vector from the NOMAD result dict.
    """
    if "x_best_feas" in result and result["x_best_feas"]:
        return np.array(result["x_best_feas"][0], dtype=float)
    if "x_single_best" in result:
        return np.array(result["x_single_best"], dtype=float)
    if "x_best" in result:
        return np.array(result["x_best"], dtype=float)

    raise ValueError("Impossible to retrieve the best solution from the Nomad output.")


def nomad_calibration(
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    logger: logging.Logger,
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

    x_calibrated = _extract_nomad_best_solution(result)

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
            logger.warning(MSG_SIMULATION_FAILED)
        else:
            log_final_param_values(x_calibrated, x0, index_to_param_map, logger)

    return x_calibrated


def _run_optimization(
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    x0: List[float],
    bounds: List[Tuple[float, float]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    power_to_calibrate: PowerToCalibrate,
    optim_method: OptimMethod,
    logger: logging.Logger,
    **optim_params: Union[int, float],
) -> np.ndarray:
    """
    Run the chosen optimization method and return the calibrated parameter vector.
    """
    if optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION:
        popsize_defaut = 15
        maxiter_defaut = 20
        popsize = optim_params.get("popsize", popsize_defaut)
        maxiter = optim_params.get("maxiter", maxiter_defaut)

        return differential_evolution_calibration(
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

    if optim_method == OptimMethod.NELDER_MEAD:
        nm_max_iterations_default = 100
        nm_max_iterations = optim_params.get("nm_max_iterations", nm_max_iterations_default)

        return nelder_mead_calibration(
            dynawo_launcher,
            exp_set,
            x0,
            bounds,
            index_to_param_map,
            power_to_calibrate,
            logger,
            nm_max_iterations,
        )

    # NOMAD
    max_bb_eval_default = 100
    max_bb_eval = optim_params.get("max_bb_eval", max_bb_eval_default)
    timeout_seconds_default = 600
    timeout_seconds = optim_params.get("timeout_seconds", timeout_seconds_default)

    return nomad_calibration(
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


def _update_selected_sets_with_calibration(
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    index_to_param_map: Dict[int, Tuple[str, str]],
    x_calibrated: np.ndarray,
) -> None:
    """
    Update selected_sets with the calibrated values.
    """
    for i, (set_id, param_name) in index_to_param_map.items():
        try:
            param_obj = selected_sets[set_id][param_name]
            param_obj.set_calibrated_value(float(x_calibrated[i]))
        except KeyError:
            continue


def _compute_calibrated_results_for_all_experiences(
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    x_calibrated: np.ndarray,
    index_to_param_map: Dict[int, Tuple[str, str]],
    logger: logging.Logger,
) -> None:
    """
    Run Dynawo with the calibrated parameters for each experience and update
    calibrated_simulation_data_df and calibrated_correlation_dict.
    """
    col_name_p, col_name_q = exp_set.get_col_names()

    for exp in exp_set.get_all_experiences():
        ok, msg = exp.check_ready_for_automatic_calibration()
        if not ok:
            if logger is not None:
                logger.warning(f"[{exp.name}] {msg}")
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


def _prepare_optimization_variables(
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    optim_method: OptimMethod,
    logger: logging.Logger,
) -> Tuple[List[float], List[Tuple[float, float]], Dict[int, Tuple[str, str]]]:
    """
    Prepare optimization variables (x0, bounds, index_to_param_map) based on selected sets.
    """
    # TODO: rework boolean variable management
    discrete_variables_allowed = (optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION)
    x0, bounds, index_to_param_map = prepare_x0(
        selected_sets,
        discrete_variables_allowed,
        logger,
    )
    return x0, bounds, index_to_param_map


def run_parameter_calibration(
    dynawo_launcher: str,
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    optim_method: OptimMethod,
    power_to_calibrate: PowerToCalibrate,
    logger: logging.Logger = None,
    **optim_params
):
    """
    Run the parameter calibration on all experiences in the ExperienceSet.

    The objective is a global RMSE, computed as a weighted average over all experiences.
    """
    if not exp_set.can_run_calibration():
        raise SimulationPreconditionError(MSG_CALIBRATION_NOT_READY)

    if not selected_sets:
        if logger is not None:
            logger.warning(MSG_NO_PARAMETERS_SELECTED_CALIBRATION)
        return None

    if logger is not None:
        logger.info("Start of multi-experience calibration")
        logger.info("Optimization method: " + optim_method.value)
        logger.info("Calibration on: " + power_to_calibrate.value)
        logger.info("")

    prepare_calibration_folders(exp_set, logger=logger)

    # Prepare optimization variables
    x0, bounds, index_to_param_map = _prepare_optimization_variables(
        selected_sets,
        optim_method,
        logger,
    )

    # Run optimization
    x_calibrated = _run_optimization(
        dynawo_launcher,
        exp_set,
        x0,
        bounds,
        index_to_param_map,
        power_to_calibrate,
        optim_method,
        logger,
        **optim_params,
    )

    # Update selected_sets with the outputs of the calibration
    _update_selected_sets_with_calibration(
        selected_sets,
        index_to_param_map,
        x_calibrated,
    )

    # Update the correlation dicts when dynawo is run with the set of best parameters
    _compute_calibrated_results_for_all_experiences(
        dynawo_launcher,
        exp_set,
        x_calibrated,
        index_to_param_map,
        logger,
    )

    if logger is not None:
        logger.info("End of multi-experience calibration")
