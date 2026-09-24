# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import streamlit as st

from logger_management import initialize_streamlit_logger, get_streamlit_logs
from experience_set import ExperienceSet
from dynawo_functions import run_base_case_for_all, SimulationPreconditionError


def create_dynawo_tab():
    dynawo_launcher = st.session_state["dynawo_launcher"]
    exp_set: ExperienceSet = st.session_state["experience_set"]

    if not exp_set.can_run_base_case():
        st.write(
            "You need to upload a reference experience with Dynawo input files "
            "and reference data before running a simulation."
        )
        return

    def on_click():
        if "log_area_base_case" not in st.session_state:
            st.session_state["log_area_base_case"] = st.empty()
        log_container = st.session_state["log_area_base_case"]

        streamlit_logger_base_case = initialize_streamlit_logger(
            log_container, "base_case_st_logger", debug=False
        )

        try:
            run_base_case_for_all(
                dynawo_launcher,
                exp_set,
                logger=streamlit_logger_base_case,
            )

            st.session_state["log_area_base_case_content"] = get_streamlit_logs(
                streamlit_logger_base_case
            )

        except SimulationPreconditionError as e:
            streamlit_logger_base_case.error(str(e))
            st.session_state["log_area_base_case_content"] = get_streamlit_logs(
                streamlit_logger_base_case
            )

        except Exception as e:
            streamlit_logger_base_case.error(f"Unexpected error during Dynawo base case simulation: {e}")
            st.session_state["log_area_base_case_content"] = get_streamlit_logs(
                streamlit_logger_base_case
            )

    st.button(
        label="Run Dynawo for all experiences",
        key="base_case_dynawo_simulation_button",
        type="primary",
        on_click=on_click,
    )

    log_container = st.session_state.get("log_area_base_case", st.empty())
    st.session_state["log_area_base_case"] = log_container
    if "log_area_base_case_content" in st.session_state:
        log_container.code(st.session_state["log_area_base_case_content"])
