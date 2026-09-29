# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the streamlit code for the sensitivity analysis tab.
"""


import streamlit as st
import logging
from typing import Dict, Union
from experience_set import ExperienceSet
from dynawo_functions import (
    SimulationPreconditionError,
    DynawoParam
)
from st_keyup import st_keyup
from util_functions import PowerToCalibrate
from sensitivity_analysis import (
    SensiMethod,
    run_sensitivity_for_all
)
from logger_management import (
    initialize_streamlit_logger,
    get_streamlit_logs
)
from tabs.util_functions_streamlit import build_filtered_sets
from const import (
    DYNAWO_LAUNCHER_ST_SESSION_KEY,
    EXPERIENCE_SET_ST_SESSION_KEY,
    PERCENTAGE_EPSILON_ST_SESSION_KEY,
    FIXED_EPSILON_ST_SESSION_KEY,
    SENSITIVITY_LOG_AREA_ST_SESSION_KEY,
    SENSITIVITY_LOGGER_NAME,
    SENSITIVITY_LOGGER_ST_SESSION_KEY
)
from msg import (
    MSG_NO_PARAMETERS_SELECTED_SENSITIVITY,
    MSG_UNEXPECTED_ERROR_SENSITIVITY,
    MSG_NO_SET_ID_OR_PARAM_ID_FOUND,
    MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED
)


def _render_parameter_selection(
    filtered_sets: Dict[str, Dict[str, DynawoParam]],
    search_query: str,
) -> Dict[str, Dict[str, DynawoParam]]:
    selected_sets: Dict[str, Dict[str, DynawoParam]] = {}

    for set_id, params_in_set in filtered_sets.items():
        with st.expander(set_id):
            selected_params: Dict[str, DynawoParam] = {}
            for parameter_id in params_in_set:
                if st.checkbox(
                    parameter_id,
                    key=f"sensitivity_{set_id}_{parameter_id}",
                    value=False,
                ):
                    selected_params[parameter_id] = params_in_set[parameter_id]
            if selected_params:
                selected_sets[set_id] = selected_params

    if not filtered_sets and search_query:
        st.warning(MSG_NO_SET_ID_OR_PARAM_ID_FOUND)

    return selected_sets


def _render_sensitivity_parameters() -> tuple[PowerToCalibrate, SensiMethod, Dict[str, Union[int, float]]]:
    power_value = st.radio(
        "Estimate sensitivity on",
        [PowerToCalibrate.PQ.value,
         PowerToCalibrate.P.value,
         PowerToCalibrate.Q.value],
        index=0,
        key="sensitivity_power_to_calibrate",
    )
    power_to_calibrate = PowerToCalibrate(power_value)

    sensi_value = st.radio(
        "Select method for epsilon calculation",
        [
            SensiMethod.PERCENTAGE.value,
            SensiMethod.FIXED.value,
            SensiMethod.HYBRID.value,
        ],
        index=0,
        key="sensitivity_sensi_method",
    )
    sensi_method = SensiMethod(sensi_value)

    sensi_params: Dict[str, Union[int, float]] = {}

    percentage_epsilon_label = "Percentage epsilon (%)"
    fixed_epsilon_label = "Fixed epsilon"

    if sensi_method == SensiMethod.PERCENTAGE:
        percentage_epsilon = st_keyup(
            percentage_epsilon_label,
            value=10,
            key=PERCENTAGE_EPSILON_ST_SESSION_KEY,
        )
        sensi_params["percentage_epsilon"] = float(percentage_epsilon)

    elif sensi_method == SensiMethod.FIXED:
        fixed_epsilon = st_keyup(
            fixed_epsilon_label,
            value=0.1,
            key=FIXED_EPSILON_ST_SESSION_KEY,
        )
        sensi_params["fixed_epsilon"] = float(fixed_epsilon)

    else:  # HYBRID
        fixed_epsilon = st_keyup(
            fixed_epsilon_label,
            value=0.1,
            key=FIXED_EPSILON_ST_SESSION_KEY,
        )
        percentage_epsilon = st_keyup(
            percentage_epsilon_label,
            value=10,
            key=PERCENTAGE_EPSILON_ST_SESSION_KEY,
        )
        sensi_params["fixed_epsilon"] = float(fixed_epsilon)
        sensi_params["percentage_epsilon"] = float(percentage_epsilon)

    return power_to_calibrate, sensi_method, sensi_params


def _get_or_create_sensitivity_logger() -> logging.Logger:
    """
    Ensure the sensitivity logger and log area exist in session_state,
    and return the logger instance.
    """
    if SENSITIVITY_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[SENSITIVITY_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_container = st.session_state[SENSITIVITY_LOG_AREA_ST_SESSION_KEY]

    if SENSITIVITY_LOGGER_ST_SESSION_KEY not in st.session_state:
        streamlit_logger_sensitivity = initialize_streamlit_logger(
            log_container, SENSITIVITY_LOGGER_NAME, debug=False
        )
        st.session_state[SENSITIVITY_LOGGER_ST_SESSION_KEY] = streamlit_logger_sensitivity
    else:
        streamlit_logger_sensitivity = st.session_state[SENSITIVITY_LOGGER_ST_SESSION_KEY]

    return streamlit_logger_sensitivity


def _sensitivity_on_click(
    exp_set: ExperienceSet,
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    sensi_method: SensiMethod,
    power_to_calibrate: PowerToCalibrate,
    sensi_params: Dict[str, Union[int, float]],
) -> None:
    streamlit_logger_sensitivity = _get_or_create_sensitivity_logger()

    if selected_sets:
        dynawo_launcher = st.session_state[DYNAWO_LAUNCHER_ST_SESSION_KEY]

        try:
            run_sensitivity_for_all(
                dynawo_launcher,
                exp_set,
                selected_sets,
                sensi_method,
                power_to_calibrate,
                logger=streamlit_logger_sensitivity,
                **sensi_params
            )

        except SimulationPreconditionError as e:
            streamlit_logger_sensitivity.error(str(e))

        except Exception as e:
            streamlit_logger_sensitivity.error(MSG_UNEXPECTED_ERROR_SENSITIVITY.format(error=e))
    else:
        streamlit_logger_sensitivity.error(MSG_NO_PARAMETERS_SELECTED_SENSITIVITY)


def _render_sensitivity_results(exp_set: ExperienceSet) -> None:
    if len(exp_set.get_all_experiences()) >= 2:
        weighted_sensitivities = exp_set.compute_weighted_sensitivities()
        if weighted_sensitivities:
            st.write("**Weighted sensitivities over all experiences**")
            for set_id, df in weighted_sensitivities.items():
                st.write("Set id: " + set_id)
                st.write(df)

    for exp in exp_set.get_all_experiences():
        sensitivities = exp.sensitivities
        if sensitivities is not None:
            st.write(f"**Sensitivities for experience '{exp.name}'**")
            for set_id, sensitivity_df in sensitivities.items():
                st.write("Set id: " + set_id)
                st.write(sensitivity_df)


def create_sensitivity_tab():
    exp_set: ExperienceSet = st.session_state[EXPERIENCE_SET_ST_SESSION_KEY]

    if not exp_set.can_run_sensitivity():
        st.write(MSG_DYNAWO_SIMULATION_ON_BASECASE_REQUIRED)
        return

    # Parameter selection
    with st.expander("Select parameters to analyze during the sensitivity analysis", expanded=True):
        search_query = st.text_input(
            "Search for a set_id or parameter",
            key="search_set_id_or_param",
        )

        parameters_sets = exp_set.get_parameters_sets()
        filtered_sets = build_filtered_sets(parameters_sets, search_query)
        selected_sets = _render_parameter_selection(filtered_sets, search_query)

    # Sensitivity analysis parameters
    with st.expander("Sensitivity analysis parameters", expanded=False):
        power_to_calibrate, sensi_method, sensi_params = _render_sensitivity_parameters()

    # Run button
    st.button(
        label="Run Sensitivity Analysis",
        key="sensitivity_analysis_button",
        type="primary",
        on_click=lambda: _sensitivity_on_click(
            exp_set,
            selected_sets,
            sensi_method,
            power_to_calibrate,
            sensi_params
        ),
    )

    # Logs
    if SENSITIVITY_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[SENSITIVITY_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_area = st.session_state[SENSITIVITY_LOG_AREA_ST_SESSION_KEY]

    logger = st.session_state.get(SENSITIVITY_LOGGER_ST_SESSION_KEY)
    if logger is not None:
        log_area.code(get_streamlit_logs(logger))

    # Results
    _render_sensitivity_results(exp_set)
