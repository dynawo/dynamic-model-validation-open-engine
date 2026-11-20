# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the streamlit code for the custom calibration tab.
"""


import streamlit as st
import logging
from st_keyup import st_keyup
from logger_management import (
    initialize_streamlit_logger,
    clear_streamlit_logger,
    get_streamlit_logs
)
from dynawo_functions import (
    run_custom_calibration_for_all,
    SimulationPreconditionError,
    DynawoParam
)
from experience_set import ExperienceSet
from tabs.util_functions_streamlit import build_filtered_sets
from typing import Dict
from const import (
    DYNAWO_LAUNCHER_ST_SESSION_KEY,
    EXPERIENCE_SET_ST_SESSION_KEY,
    CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY,
    CUSTOM_CALIBRATION_LOGGER_NAME,
    CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY
)
from msg import (
    MSG_NO_PARAMETERS_SELECTED_CUSTOM,
    MSG_UNEXPECTED_ERROR_CUSTOM_CALIBRATION,
    MSG_NO_SET_ID_OR_PARAM_ID_FOUND,
    MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED
)


def _render_custom_parameter_row(set_id: str, parameter_id: str, parameter: DynawoParam) -> bool:
    col_checkbox, col_initial_value, col_input = st.columns([2, 1, 1])

    with col_checkbox:
        selected = st.checkbox(
            parameter_id,
            key=f"custom_calibration_{set_id}_{parameter_id}",
            value=False,
        )

    if not selected:
        return False

    with col_initial_value:
        st.text_input(
            "Original value",
            value=parameter.get_original_value(),
            key=f"custom_calibration_initial_{set_id}_{parameter_id}",
            disabled=True,
        )

    with col_input:
        new_value = st_keyup(
            "New value",
            value=parameter.get_value(),
            key=f"custom_calibration_input_{set_id}_{parameter_id}",
        )
        parameter.set_value(new_value)

    return True


def _render_custom_parameter_selection(
    filtered_sets: Dict[str, Dict[str, DynawoParam]],
    search_query: str,
) -> Dict[str, Dict[str, DynawoParam]]:
    selected_sets: Dict[str, Dict[str, DynawoParam]] = {}

    for set_id, params_in_set in filtered_sets.items():
        with st.expander(set_id):
            selected_params: Dict[str, DynawoParam] = {}

            for parameter_id, parameter in params_in_set.items():
                selected = _render_custom_parameter_row(set_id, parameter_id, parameter)
                if selected:
                    selected_params[parameter_id] = parameter

            if selected_params:
                selected_sets[set_id] = selected_params

    if not filtered_sets and search_query:
        st.warning(MSG_NO_SET_ID_OR_PARAM_ID_FOUND)

    return selected_sets


def _get_or_create_custom_calibration_logger() -> logging.Logger:
    """
    Ensure the custom calibration logger and log area exist in session_state,
    and return the logger instance.
    """
    if CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_container = st.session_state[CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY]

    if CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY not in st.session_state:
        streamlit_logger_custom_calibration = initialize_streamlit_logger(
            log_container, CUSTOM_CALIBRATION_LOGGER_NAME, debug=False
        )
        st.session_state[CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY] = streamlit_logger_custom_calibration
    else:
        streamlit_logger_custom_calibration = st.session_state[CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY]

    return streamlit_logger_custom_calibration


def _custom_calibration_on_click(
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, DynawoParam]],
) -> None:
    clear_streamlit_logger(CUSTOM_CALIBRATION_LOGGER_NAME)
    streamlit_logger_custom_calibration = _get_or_create_custom_calibration_logger()

    if selected_sets:
        dynawo_launcher = st.session_state[DYNAWO_LAUNCHER_ST_SESSION_KEY]

        try:
            run_custom_calibration_for_all(
                dynawo_launcher,
                exp_set,
                selected_sets,
                logger=streamlit_logger_custom_calibration,
            )

        except SimulationPreconditionError as e:
            streamlit_logger_custom_calibration.error(str(e))

        except Exception as e:
            streamlit_logger_custom_calibration.error(
                MSG_UNEXPECTED_ERROR_CUSTOM_CALIBRATION.format(error=e)
            )
    else:
        streamlit_logger_custom_calibration.error(MSG_NO_PARAMETERS_SELECTED_CUSTOM)


def create_custom_calibration_tab():
    exp_set: ExperienceSet = st.session_state[EXPERIENCE_SET_ST_SESSION_KEY]

    if not exp_set.can_run_custom_calibration():
        st.write(MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED)
        return

    with st.expander("Select parameters to calibrate", expanded=True):
        search_query = st.text_input(
            "Search for a set_id or parameter",
            key="custom_calibration_search_set_id_or_param",
        )

        parameters_sets = exp_set.get_parameters_sets()
        filtered_sets = build_filtered_sets(parameters_sets, search_query)
        selected_sets = _render_custom_parameter_selection(filtered_sets, search_query)

    st.button(
        label="Run Dynawo Simulation with custom parameters",
        key="custom_calibration_button",
        type="primary",
        on_click=lambda: _custom_calibration_on_click(exp_set, selected_sets),
    )

    # Display logs
    if CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_area_custom_calibration = st.session_state[CUSTOM_CALIBRATION_LOG_AREA_ST_SESSION_KEY]

    logger = st.session_state.get(CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY)
    if logger is not None:
        log_area_custom_calibration.code(get_streamlit_logs(logger))
