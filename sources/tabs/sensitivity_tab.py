# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import streamlit as st

from experience_set import ExperienceSet
from dynawo_functions import SimulationPreconditionError
from st_keyup import st_keyup
from util_functions import PowerToCalibrate
from sensitivity_analysis import SensiMethod, run_sensitivity_for_all
from logger_management import initialize_streamlit_logger, get_streamlit_logs


def create_sensitivity_tab():
    exp_set: ExperienceSet = st.session_state["experience_set"]

    if not exp_set.can_run_sensitivity():
        st.write("You need to run a Dynawo simulation on the base_case of the reference experience first.")
        return

    with st.expander("Select parameters to analyze during the sensitivity analysis", expanded=True):
        search_query = st.text_input("Search for a set_id or parameter", key="search_set_id_or_param")

        parameters_sets = exp_set.get_parameters_sets()
        selected_sets = dict()

        filtered_sets = {}
        for set_id in parameters_sets.keys():
            if search_query.lower() in set_id.lower():
                filtered_sets[set_id] = parameters_sets[set_id]
            else:
                filtered_params = {
                    param_id: param for param_id, param in parameters_sets[set_id].items()
                    if search_query.lower() in param_id.lower()
                }
                if filtered_params:
                    filtered_sets[set_id] = filtered_params

        for set_id in filtered_sets:
            with st.expander(set_id):
                selected_params = dict()
                for parameter_id in filtered_sets[set_id]:
                    if st.checkbox(
                            parameter_id,
                            key="sensitivity_" + set_id + "_" + parameter_id,
                            value=False
                    ):
                        selected_params[parameter_id] = parameters_sets[set_id][parameter_id]
                if len(selected_params) > 0:
                    selected_sets[set_id] = selected_params

        if not filtered_sets and search_query:
            st.warning("No set_id or parameter matches your search.")

    with st.expander("Sensitivity analysis parameters", expanded=False):
        power_to_calibrate = st.radio(
            "Estimate sensitivity on",
            [PowerToCalibrate.PQ.value,
             PowerToCalibrate.P.value,
             PowerToCalibrate.Q.value],
            index=0,
            key="sensitivity_power_to_calibrate"
        )
        power_to_calibrate = PowerToCalibrate(power_to_calibrate)

        sensi_method = st.radio(
            "Select method for epsilon calculation",
            [
                SensiMethod.PERCENTAGE.value,
                SensiMethod.FIXED.value,
                SensiMethod.HYBRID.value
            ],
            index=0,
            key="sensitivity_sensi_method"
        )
        sensi_method = SensiMethod(sensi_method)

        sensi_params = {}

        if sensi_method == SensiMethod.PERCENTAGE:
            percentage_epsilon = st_keyup(
                "Percentage epsilon (%)",
                value=10,
                key="Percentage epsilon"
            )
            sensi_params["percentage_epsilon"] = float(percentage_epsilon)

        elif sensi_method == SensiMethod.FIXED:
            fixed_epsilon = st_keyup(
                "Fixed epsilon",
                value=0.1,
                key="Fixed epsilon"
            )
            sensi_params["fixed_epsilon"] = float(fixed_epsilon)

        else:
            fixed_epsilon = st_keyup(
                "Fixed epsilon",
                value=0.1,
                key="Fixed epsilon"
            )
            percentage_epsilon = st_keyup(
                "Percentage epsilon",
                value=10,
                key="Percentage epsilon"
            )
            sensi_params["fixed_epsilon"] = float(fixed_epsilon)
            sensi_params["percentage_epsilon"] = float(percentage_epsilon)

    def on_click():
        if "log_area_base_case_sensitivity" not in st.session_state:
            st.session_state["log_area_base_case_sensitivity"] = st.empty()
        log_container = st.session_state["log_area_base_case_sensitivity"]

        streamlit_logger_sensitivity = initialize_streamlit_logger(
            log_container, "sensitivity_st_logger", debug=False
        )

        parameters_sets_local = exp_set.get_parameters_sets()
        selected_sets_local = {}
        for set_id in parameters_sets_local:
            for parameter_id in parameters_sets_local[set_id]:
                key = "sensitivity_" + set_id + "_" + parameter_id
                if st.session_state.get(key, False):
                    if set_id not in selected_sets_local:
                        selected_sets_local[set_id] = {}
                    selected_sets_local[set_id][parameter_id] = parameters_sets_local[set_id][parameter_id]

        if len(selected_sets_local) > 0:
            dynawo_launcher = st.session_state["dynawo_launcher"]

            try:
                run_sensitivity_for_all(
                    dynawo_launcher,
                    exp_set,
                    selected_sets_local,
                    sensi_method,
                    power_to_calibrate,
                    logger=streamlit_logger_sensitivity,
                    **sensi_params
                )

                st.session_state["log_area_base_case_sensitivity_content"] = get_streamlit_logs(
                    streamlit_logger_sensitivity
                )

            except SimulationPreconditionError as e:
                streamlit_logger_sensitivity.error(str(e))
                st.session_state["log_area_base_case_sensitivity_content"] = get_streamlit_logs(
                    streamlit_logger_sensitivity
                )

            except Exception as e:
                streamlit_logger_sensitivity.error(f"Unexpected error during sensitivity analysis: {e}")
                st.session_state["log_area_base_case_sensitivity_content"] = get_streamlit_logs(
                    streamlit_logger_sensitivity
                )
        else:
            st.session_state[
                "log_area_base_case_sensitivity_content"
            ] = "You should select at least one parameter"

    st.button(
        label="Run Sensitivity Analysis",
        key="sensitivity_analysis_button",
        type="primary",
        on_click=on_click
    )

    log_area_base_case_sensitivity = st.session_state.get("log_area_base_case_sensitivity", st.empty())
    st.session_state["log_area_base_case_sensitivity"] = log_area_base_case_sensitivity
    if "log_area_base_case_sensitivity_content" in st.session_state:
        log_area_base_case_sensitivity.code(
            st.session_state["log_area_base_case_sensitivity_content"]
        )

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
            for set_id in sensitivities:
                st.write("Set id: " + set_id)
                sensitivity_df = sensitivities[set_id]
                st.write(sensitivity_df)

