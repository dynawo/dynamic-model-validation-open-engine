# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the streamlit code for the automatic calibration tab.
"""


import streamlit as st
import logging
from st_keyup import st_keyup
from util_functions import PowerToCalibrate
from dynawo_functions import (
    SimulationPreconditionError,
    DynawoParam
)
from automatic_calibration import (
    OptimMethod,
    run_parameter_calibration
)
from logger_management import (
    initialize_streamlit_logger,
    get_streamlit_logs
)
from experience_set import ExperienceSet
from tabs.util_functions_streamlit import build_filtered_sets
from typing import Dict, Union
from const import (
    DYNAWO_LAUNCHER_ST_SESSION_KEY,
    EXPERIENCE_SET_ST_SESSION_KEY,
    AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY,
    AUTOMATIC_CALIBRATION_LOGGER_NAME,
    AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY
)
from msg import (
    MSG_NO_PARAMETERS_SELECTED_CALIBRATION,
    MSG_UNEXPECTED_ERROR_AUTOMATIC_CALIBRATION,
    MSG_NO_SET_ID_OR_PARAM_ID_FOUND,
    MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED
)


def _render_double_parameter_row(set_id: str, parameter_id: str, parameter: DynawoParam) -> bool:
    original_value = float(parameter.get_original_value())
    min_bound = str(parameter.get_min_bound())
    max_bound = str(parameter.get_max_bound())

    col_checkbox, col_initial_value, col_min_bound, col_max_bound = st.columns([2, 1, 1, 1])

    with col_checkbox:
        selected = st.checkbox(
            parameter_id,
            key=f"automatic_calibration_{set_id}_{parameter_id}",
            value=False,
        )

    if not selected:
        return False

    with col_initial_value:
        st.text_input(
            "Original value",
            value=original_value,
            key=f"automatic_calibration_initial_{set_id}_{parameter_id}",
            disabled=True,
        )

    with col_min_bound:
        min_bound = st_keyup(
            "Min bound",
            value=min_bound,
            key=f"automatic_calibration_min_bound_{set_id}_{parameter_id}",
        )
        parameter.set_min_bound(min_bound)

    with col_max_bound:
        max_bound = st_keyup(
            "Max bound",
            value=max_bound,
            key=f"automatic_calibration_max_bound_{set_id}_{parameter_id}",
        )
        parameter.set_max_bound(max_bound)

    return True


def _render_parameter_selection(filtered_sets: Dict[str, Dict[str, DynawoParam]], search_query: str) -> Dict[str, Dict[str, DynawoParam]]:
    selected_sets: Dict[str, Dict[str, DynawoParam]] = {}

    for set_id, params_in_set in filtered_sets.items():
        with st.expander(set_id):
            selected_params: Dict[str, DynawoParam] = {}

            for parameter_id, parameter in params_in_set.items():
                if parameter.get_type() != "DOUBLE":
                    continue

                selected = _render_double_parameter_row(set_id, parameter_id, parameter)
                if selected:
                    selected_params[parameter_id] = parameter

            if selected_params:
                selected_sets[set_id] = selected_params

    if not filtered_sets and search_query:
        st.warning(MSG_NO_SET_ID_OR_PARAM_ID_FOUND)

    return selected_sets


def _render_optimization_parameters() -> tuple[PowerToCalibrate, OptimMethod, Dict[str, Union[int, float]]]:
    power_value = st.radio(
        "Calibrate on",
        [PowerToCalibrate.PQ.value,
         PowerToCalibrate.P.value,
         PowerToCalibrate.Q.value],
        index=0,
        key="calibration_power_to_calibrate",
    )
    power_to_calibrate = PowerToCalibrate(power_value)

    optim_value = st.radio(
        "Select optimization method",
        [OptimMethod.NOMAD.value,
         OptimMethod.NELDER_MEAD.value,
         OptimMethod.DIFFERENTIAL_EVOLUTION.value],
        index=0,
    )
    optim_method = OptimMethod(optim_value)

    optim_params: Dict[str, Union[int, float]] = {}

    if optim_method == OptimMethod.NOMAD:
        raw_nomad_max_iterations = st_keyup(
            "Max blackbox iterations",
            value=50,
            key="nomad_max_iterations",
        )
        raw_timeout_seconds = st_keyup(
            "Timeout (seconds)",
            value=600,
            key="timeout_seconds",
        )
        try:
            nomad_max_iterations = max(1, int(raw_nomad_max_iterations))
        except (TypeError, ValueError):
            nomad_max_iterations = 50
        try:
            timeout_seconds = max(1, int(raw_timeout_seconds))
        except (TypeError, ValueError):
            timeout_seconds = 600

        optim_params["max_bb_eval"] = int(nomad_max_iterations)
        optim_params["timeout_seconds"] = int(timeout_seconds)

    elif optim_method == OptimMethod.NELDER_MEAD:
        nm_max_iterations_raw = st_keyup(
            "Max iterations",
            value=50,
            key="nm_max_iterations",
        )
        try:
            nm_max_iterations = max(1, int(nm_max_iterations_raw))
        except (TypeError, ValueError):
            nm_max_iterations = 100
        optim_params["nm_max_iterations"] = int(nm_max_iterations)

    elif optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION:
        raw_popsize = st_keyup(
            "Population size",
            value=15,
            key="de_popsize",
        )
        raw_maxiter = st_keyup(
            "Max iterations",
            value=20,
            key="de_maxiter",
        )
        try:
            popsize = max(1, int(raw_popsize))
        except (TypeError, ValueError):
            popsize = 15
        try:
            maxiter = max(1, int(raw_maxiter))
        except (TypeError, ValueError):
            maxiter = 20

        optim_params["popsize"] = popsize
        optim_params["maxiter"] = maxiter

    return power_to_calibrate, optim_method, optim_params


def _get_or_create_calibration_logger() -> logging.Logger:
    """
    Ensure the calibration logger and log area exist in session_state,
    and return the logger instance.
    """
    if AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_container = st.session_state[AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY]

    if AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY not in st.session_state:
        streamlit_logger_calibration = initialize_streamlit_logger(
            log_container, AUTOMATIC_CALIBRATION_LOGGER_NAME, debug=False
        )
        st.session_state[AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY] = streamlit_logger_calibration
    else:
        streamlit_logger_calibration = st.session_state[AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY]

    return streamlit_logger_calibration


def _calibration_on_click(
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    optim_method: OptimMethod,
    power_to_calibrate: PowerToCalibrate,
    optim_params: Dict[str, Union[int, float]]
) -> None:
    streamlit_logger_calibration = _get_or_create_calibration_logger()

    if selected_sets:
        dynawo_launcher = st.session_state[DYNAWO_LAUNCHER_ST_SESSION_KEY]

        try:
            run_parameter_calibration(
                dynawo_launcher,
                exp_set,
                selected_sets,
                optim_method,
                power_to_calibrate,
                logger=streamlit_logger_calibration,
                **optim_params,
            )

        except SimulationPreconditionError as e:
            streamlit_logger_calibration.error(str(e))

        except Exception as e:
            streamlit_logger_calibration.error(
                MSG_UNEXPECTED_ERROR_AUTOMATIC_CALIBRATION.format(error=e)
            )
    else:
        streamlit_logger_calibration.error(MSG_NO_PARAMETERS_SELECTED_CALIBRATION)


def create_param_calibration_tab():
    exp_set: ExperienceSet = st.session_state[EXPERIENCE_SET_ST_SESSION_KEY]

    if not exp_set.can_run_calibration():
        st.write(MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED)
        return

    # Parameter selection
    with st.expander("Select parameters to calibrate", expanded=True):
        search_query = st.text_input(
            "Search for a set_id or parameter",
            key="calibration_search_set_id_or_param",
        )

        parameters_sets = exp_set.get_parameters_sets()
        filtered_sets = build_filtered_sets(parameters_sets, search_query)
        selected_sets = _render_parameter_selection(filtered_sets, search_query)

    # Optimization parameters
    with st.expander("Optimization parameters", expanded=True):
        power_to_calibrate, optim_method, optim_params = _render_optimization_parameters()

    # Run calibration button
    st.button(
        label="Run Calibration",
        key="calibration_button",
        type="primary",
        on_click=lambda: _calibration_on_click(
            exp_set,
            selected_sets,
            optim_method,
            power_to_calibrate,
            optim_params,
        ),
    )

    # Display logs
    if AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_area_base_case_calibration = st.session_state[AUTOMATIC_CALIBRATION_LOG_AREA_ST_SESSION_KEY]

    logger = st.session_state.get(AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY)
    if logger is not None:
        log_area_base_case_calibration.code(get_streamlit_logs(logger))
