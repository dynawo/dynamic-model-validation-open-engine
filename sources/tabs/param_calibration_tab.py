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

from util_functions import PowerToCalibrate
from dynawo_functions import SimulationPreconditionError
from automatic_calibration import OptimMethod, run_parameter_calibration
from logger_management import initialize_streamlit_logger, get_streamlit_logs
from experience_set import ExperienceSet


def create_param_calibration_tab():
    exp_set: ExperienceSet = st.session_state["experience_set"]

    if not exp_set.can_run_calibration():
        st.write("You need to run a Dynawo simulation on the base_case of the reference experience first.")
        return

    with st.expander("Select parameters to calibrate", expanded=True):

        search_query = st.text_input(
            "Search for a set_id or parameter",
            key="calibration_search_set_id_or_param"
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
                    param_type = parameter.get_type()
                    if param_type == "DOUBLE":
                        original_value = float(parameter.get_original_value())
                        min_bound = str(parameter.get_min_bound())
                        max_bound = str(parameter.get_max_bound())
                        col_checkbox, col_initial_value, col_min_bound, col_max_bound = st.columns([2, 1, 1, 1])
                        with col_checkbox:
                            if st.checkbox(
                                parameter_id,
                                key="automatic_calibration_" + set_id + "_" + parameter_id,
                                value=False
                            ):
                                selected_params[parameter_id] = parameter
                        with col_initial_value:
                            if parameter_id in selected_params:
                                st.text_input(
                                    "Original value",
                                    value=original_value,
                                    key="automatic_calibration_initial_" + set_id + "_" + parameter_id,
                                    disabled=True
                                )
                        with col_min_bound:
                            if parameter_id in selected_params:
                                min_bound = st_keyup(
                                    "Min bound",
                                    value=min_bound,
                                    key="automatic_calibration_min_bound_" + set_id + "_" + parameter_id
                                )
                                parameter.set_min_bound(min_bound)
                        with col_max_bound:
                            if parameter_id in selected_params:
                                max_bound = st_keyup(
                                    "Max bound",
                                    value=max_bound,
                                    key="automatic_calibration_max_bound_" + set_id + "_" + parameter_id
                                )
                                parameter.set_max_bound(max_bound)
                    else:
                        continue

                if len(selected_params) > 0:
                    selected_sets[set_id] = selected_params

        if not filtered_sets and search_query:
            st.warning("No set_id or parameter matches your search.")

    with st.expander("Optimization parameters", expanded=True):
        power_to_calibrate = st.radio(
            "Calibrate on",
            [PowerToCalibrate.PQ.value,
             PowerToCalibrate.P.value,
             PowerToCalibrate.Q.value],
            index=0,
            key="calibration_power_to_calibrate"
        )
        power_to_calibrate = PowerToCalibrate(power_to_calibrate)

        optim_method = st.radio(
            "Select optimization method",
            [OptimMethod.NOMAD.value,
             OptimMethod.NELDER_MEAD.value,
             OptimMethod.DIFFERENTIAL_EVOLUTION.value],
            index=0
        )
        optim_method = OptimMethod(optim_method)

        optim_params = {}

        if optim_method == OptimMethod.NOMAD:
            raw_nomad_max_iterations = st_keyup(
                "Max blackbox iterations",
                value=50,
                key="nomad_max_iterations"
            )
            raw_timeout_seconds = st_keyup(
                "Timeout (seconds)",
                value=600,
                key="timeout_seconds"
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
            nm_max_iterations = st_keyup(
                "Max iterations",
                value=50,
                key="nm_max_iterations"
            )
            try:
                nm_max_iterations = max(1, int(nm_max_iterations))
            except (TypeError, ValueError):
                nm_max_iterations = 100
            finally:
                optim_params["nm_max_iterations"] = int(nm_max_iterations)

        elif optim_method == OptimMethod.DIFFERENTIAL_EVOLUTION:
            raw_popsize = st_keyup(
                "Population size",
                value=15,
                key="de_popsize"
            )
            raw_maxiter = st_keyup(
                "Max iterations",
                value=20,
                key="de_maxiter"
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

    def on_click():
        if "log_area_base_case_calibration" not in st.session_state:
            st.session_state["log_area_base_case_calibration"] = st.empty()
        log_container = st.session_state["log_area_base_case_calibration"]

        streamlit_logger_calibration = initialize_streamlit_logger(
            log_container, "calibration_st_logger", debug=False
        )

        if len(selected_sets) > 0:
            dynawo_launcher = st.session_state["dynawo_launcher"]

            try:
                run_parameter_calibration(
                    dynawo_launcher,
                    exp_set,
                    selected_sets,
                    optim_method,
                    power_to_calibrate,
                    logger=streamlit_logger_calibration,
                    **optim_params
                )

                st.session_state["log_area_base_case_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_calibration
                )

            except SimulationPreconditionError as e:
                streamlit_logger_calibration.error(str(e))
                st.session_state["log_area_base_case_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_calibration
                )

            except Exception as e:
                streamlit_logger_calibration.error(
                    f"Unexpected error during automatic calibration: {e}"
                )
                st.session_state["log_area_base_case_calibration_content"] = get_streamlit_logs(
                    streamlit_logger_calibration
                )
        else:
            st.session_state["log_area_base_case_calibration_content"] = (
                "You should select at least one parameter"
            )

    st.button(
        label="Run Calibration",
        key="calibration_button",
        type="primary",
        on_click=on_click
    )

    log_area_base_case_calibration = st.session_state.get("log_area_base_case_calibration", st.empty())
    st.session_state["log_area_base_case_calibration"] = log_area_base_case_calibration
    if "log_area_base_case_calibration_content" in st.session_state:
        log_area_base_case_calibration.code(
            st.session_state["log_area_base_case_calibration_content"]
        )
