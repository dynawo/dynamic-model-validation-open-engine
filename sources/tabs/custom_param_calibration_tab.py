# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import streamlit as st

from st_keyup import st_keyup
from logger_management import initialize_streamlit_logger, get_streamlit_logs
from dynawo_functions import run_custom_calibration_for_all, SimulationPreconditionError
from experience_set import ExperienceSet


def create_custom_calibration_tab():
    exp_set: ExperienceSet = st.session_state["experience_set"]

    if not exp_set.can_run_custom_calibration():
        st.write("You need to run a Dynawo simulation on the base_case of the reference experience first.")
        return

    with st.expander("Select parameters to calibrate", expanded=True):

        search_query = st.text_input(
            "Search for a set_id or parameter",
            key="custom_calibration_search_set_id_or_param"
        )

        parameters_sets = exp_set.get_parameters_sets()
        selected_sets = dict()

        filtered_sets = {}
        for set_id in parameters_sets.keys():
            if search_query.lower() in set_id.lower():
                filtered_sets[set_id] = parameters_sets[set_id]
            else:
                filtered_params = {}
                for parameter_id, parameter in parameters_sets[set_id].items():
                    if search_query.lower() in parameter_id.lower():
                        filtered_params[parameter_id] = parameter
                if filtered_params:
                    filtered_sets[set_id] = filtered_params

        for set_id in filtered_sets:
            with st.expander(set_id):
                selected_params = dict()
                for parameter_id in filtered_sets[set_id]:
                    parameter = filtered_sets[set_id][parameter_id]
                    col_checkbox, col_initial_value, col_input = st.columns([2, 1, 1])
                    with col_checkbox:
                        if st.checkbox(
                            parameter_id,
                            key="custom_calibration_" + set_id + "_" + parameter_id,
                            value=False
                        ):
                            selected_params[parameter_id] = parameter
                    with col_initial_value:
                        if parameter_id in selected_params:
                            st.text_input(
                                "Original value",
                                value=parameter.get_original_value(),
                                key="custom_calibration_initial_" + set_id + "_" + parameter_id,
                                disabled=True
                            )
                    with col_input:
                        if parameter_id in selected_params:
                            new_value = st_keyup(
                                "New value",
                                value=parameter.get_value(),
                                key="custom_calibration_input_" + set_id + "_" + parameter_id
                            )
                            parameter.set_value(new_value)
                            selected_params[parameter_id] = parameter

                if len(selected_params) > 0:
                    selected_sets[set_id] = selected_params

        if not filtered_sets and search_query:
            st.warning("No set_id or parameter matches your search.")

    def on_click():
        if "log_area_custom_calibration" not in st.session_state:
            st.session_state["log_area_custom_calibration"] = st.empty()
        log_container = st.session_state["log_area_custom_calibration"]

        streamlit_logger_custom_calibration = initialize_streamlit_logger(
            log_container, "custom_calibration_st_logger", debug=False
        )

        if len(selected_sets) > 0:
            dynawo_launcher = st.session_state["dynawo_launcher"]

            try:
                run_custom_calibration_for_all(
                    dynawo_launcher,
                    exp_set,
                    selected_sets,
                    logger=streamlit_logger_custom_calibration,
                )

                st.session_state["log_area_custom_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_custom_calibration
                )

            except SimulationPreconditionError as e:
                streamlit_logger_custom_calibration.error(str(e))
                st.session_state["log_area_custom_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_custom_calibration
                )

            except Exception as e:
                streamlit_logger_custom_calibration.error(
                    f"Unexpected error during custom calibration simulations: {e}"
                )
                st.session_state["log_area_custom_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_custom_calibration
                )
        else:
            st.session_state["log_area_custom_calibration_content"] = (
                "You should select at least one parameter"
            )

    st.button(
        label="Run Dynawo Simulation with custom parameters",
        key="custom_calibration_button",
        type="primary",
        on_click=on_click
    )

    log_area_custom_calibration = st.session_state.get("log_area_custom_calibration", st.empty())
    st.session_state["log_area_custom_calibration"] = log_area_custom_calibration
    if "log_area_custom_calibration_content" in st.session_state:
        log_area_custom_calibration.code(st.session_state["log_area_custom_calibration_content"])
