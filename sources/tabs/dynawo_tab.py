# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the streamlit code for the basecase dynawo simulation tab.
"""


import streamlit as st
import logging
from logger_management import (
    initialize_streamlit_logger,
    clear_streamlit_logger,
    get_streamlit_logs
)
from experience_set import ExperienceSet
from dynawo_functions import (
    run_base_case_for_all,
    SimulationPreconditionError
)
from const import (
    DYNAWO_LAUNCHER_ST_SESSION_KEY,
    EXPERIENCE_SET_ST_SESSION_KEY,
    BASECASE_LOGGER_NAME,
    BASECASE_LOG_AREA_ST_SESSION_KEY,
    BASECASE_LOGGER_ST_SESSION_KEY
)
from msg import MSG_UNEXPECTED_ERROR_BASECASE


def _get_or_create_basecase_logger() -> logging.Logger:
    """
    Ensure the base case logger and log area exist in session_state,
    and return the logger instance.
    """
    if BASECASE_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[BASECASE_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_container = st.session_state[BASECASE_LOG_AREA_ST_SESSION_KEY]

    if BASECASE_LOGGER_ST_SESSION_KEY not in st.session_state:
        streamlit_logger_base_case = initialize_streamlit_logger(
            log_container, BASECASE_LOGGER_NAME, debug=False
        )
        st.session_state[BASECASE_LOGGER_ST_SESSION_KEY] = streamlit_logger_base_case
    else:
        streamlit_logger_base_case = st.session_state[BASECASE_LOGGER_ST_SESSION_KEY]

    return streamlit_logger_base_case


def create_dynawo_tab():
    dynawo_launcher = st.session_state[DYNAWO_LAUNCHER_ST_SESSION_KEY]
    exp_set: ExperienceSet = st.session_state[EXPERIENCE_SET_ST_SESSION_KEY]

    if not exp_set.can_run_base_case():
        st.write(
            "You need to upload a reference experience with Dynawo input files "
            "and reference data before running a simulation."
        )
        return

    def on_click():
        clear_streamlit_logger(BASECASE_LOGGER_NAME)
        streamlit_logger_base_case = _get_or_create_basecase_logger()

        try:
            run_base_case_for_all(
                dynawo_launcher,
                exp_set,
                logger=streamlit_logger_base_case,
            )
        except SimulationPreconditionError as e:
            streamlit_logger_base_case.error(str(e))
        except Exception as e:
            streamlit_logger_base_case.error(
                MSG_UNEXPECTED_ERROR_BASECASE.format(error=e)
            )

    st.button(
        label="Run Dynawo for all experiences",
        key="base_case_dynawo_simulation_button",
        type="primary",
        on_click=on_click,
    )

    # Display logs
    if BASECASE_LOG_AREA_ST_SESSION_KEY not in st.session_state:
        st.session_state[BASECASE_LOG_AREA_ST_SESSION_KEY] = st.empty()
    log_container = st.session_state[BASECASE_LOG_AREA_ST_SESSION_KEY]

    logger = st.session_state.get(BASECASE_LOGGER_ST_SESSION_KEY)
    if logger is not None:
        log_container.code(get_streamlit_logs(logger))
