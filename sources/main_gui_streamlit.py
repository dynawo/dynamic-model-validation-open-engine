# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
Main function to run the GUI of the Dynawo Model validation toolbox.
"""


import os
import streamlit as st
from datetime import datetime

from experience_set import ExperienceSet
from settings import Settings

from tabs.data_tab import create_data_tab
from tabs.dynawo_tab import create_dynawo_tab
from tabs.plot_tab import create_plot_tab
from tabs.sensitivity_tab import create_sensitivity_tab
from tabs.param_calibration_tab import create_param_calibration_tab
from tabs.custom_param_calibration_tab import create_custom_calibration_tab


app_title = "Dynawo Model Validation Tool"
st.set_page_config(page_title=app_title, layout="wide")


def create_webpage_header():
    st.title("Dynawo Model Validation Tool")


def init_experience_set():
    script_directory = os.path.dirname(os.path.abspath(__file__))
    base_temp_root = os.path.join(script_directory, "..", "temp")
    os.makedirs(base_temp_root, exist_ok=True)

    if "experience_set" not in st.session_state:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = os.path.join(base_temp_root, run_id)
        os.makedirs(temp_dir, exist_ok=True)

        st.session_state["experience_set"] = ExperienceSet(
            experience_ref=None,
            additional_experiences=[],
            col_name_p=None,
            col_name_q=None,
            temp_dir=temp_dir
        )


def main():
    # Create header
    create_webpage_header()

    # Initialize Dynawo settings
    dynawo_settings = Settings()
    dynawo_launcher = dynawo_settings.get_dynawo_launcher()
    st.session_state["dynawo_launcher"] = dynawo_launcher

    # Initialize the ExperienceSet
    init_experience_set()

    # Creating tabs
    data_tab, dynawo_tab, plot_tab, sensitivity_tab, param_calibration_tab, custom_param_calibration_tab = st.tabs(
        [
            "Upload Data",
            "Run Dynawo Simulation",
            "Visualize Plots",
            "Sensitivity Analysis",
            "Automatic Parameter Calibration",
            "Custom Parameter Calibration",
        ]
    )
    with data_tab:
        create_data_tab()
    with dynawo_tab:
        create_dynawo_tab()
    with plot_tab:
        create_plot_tab()
    with sensitivity_tab:
        create_sensitivity_tab()
    with param_calibration_tab:
        create_param_calibration_tab()
    with custom_param_calibration_tab:
        create_custom_calibration_tab()


if __name__ == "__main__":
    main()
