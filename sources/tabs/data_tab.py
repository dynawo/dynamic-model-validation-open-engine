# tabs/data_tab.py
# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import os
import streamlit as st

from logger_management import clear_streamlit_logger, initialize_streamlit_logger
from util_functions import get_file_hash
from experience_set import ExperienceSet
from experience import Experience, ExperienceLoadError


def create_data_tab():
    exp_set: ExperienceSet = st.session_state["experience_set"]

    col_1, col_2, col_3 = st.columns([1, 1, 2])

    # col 3 is used for the logs
    # col 3 implemented before col 1 because log_area is going to be used by col 1 and col 2
    with col_3:
        st.write("### Experience logs")

        if "data_tab_log_area" not in st.session_state:
            st.session_state["data_tab_log_area"] = st.empty()

        log_area = st.session_state["data_tab_log_area"]

        if "data_tab_logger" not in st.session_state:
            data_tab_logger = initialize_streamlit_logger(
                log_area, "data_tab_st_logger", debug=False
            )
            st.session_state["data_tab_logger"] = data_tab_logger
            log_area.text("No experience loaded yet.")
        else:
            st.session_state["data_tab_logger"]

    # upload of the reference experience
    with col_1:
        st.write("### Load reference experience")

        zipped_data_ref = st.file_uploader(
            "Upload zip file for reference experience",
            type="zip",
            key="zip_ref",
        )
        exp_ref = exp_set.experience_ref
        if zipped_data_ref is not None:
            current_hash = get_file_hash(zipped_data_ref)
            if exp_ref is None or exp_ref.file_hash != current_hash:
                reinit_analysis(exp_set)

                clear_streamlit_logger("data_tab_st_logger")
                log_area = st.session_state["data_tab_log_area"]
                data_tab_logger = initialize_streamlit_logger(
                    log_area, "data_tab_st_logger", debug=False
                )
                st.session_state["data_tab_logger"] = data_tab_logger

                try:
                    exp_name = get_zip_filename_without_extension(zipped_data_ref)
                    zipped_data_ref.seek(0)

                    temp_dir_exp_ref = os.path.join(exp_set.temp_dir, "experience_ref")
                    os.makedirs(temp_dir_exp_ref, exist_ok=True)

                    exp_ref = Experience(
                        name=exp_name,
                        temp_dir_exp=temp_dir_exp_ref,
                        weight=1.0,
                        zip_file=zipped_data_ref,
                        logger=data_tab_logger,
                    )
                    exp_set.experience_ref = exp_ref
                    try:
                        exp_set.initialize_col_names_from_exp_ref()
                    except ValueError as e:
                        raise ExperienceLoadError(str(e)) from e

                except ExperienceLoadError as e:
                    data_tab_logger.error(str(e))
                except Exception as e:
                    data_tab_logger.error(f"Unexpected error while loading reference experience: {e}")

    reference_is_loaded = exp_set.is_experience_ref_loaded()
    col_name_p, col_name_q = exp_set.get_col_names()

    # Additional experiences
    with col_2:
        st.write("### Load additional experiences")

        if not reference_is_loaded:
            st.file_uploader(
                "Upload zip file for additional experience",
                type="zip",
                key="zip_additional",
                disabled=True,
            )
            st.info("You must load a reference experience before adding additional experiences.")
        else:
            zipped_data_add = st.file_uploader(
                "Upload zip file for additional experience",
                type="zip",
                key="zip_additional",
                disabled=False,
            )

            if zipped_data_add is not None:

                clear_streamlit_logger("data_tab_st_logger")
                log_area = st.session_state["data_tab_log_area"]
                data_tab_logger = initialize_streamlit_logger(
                    log_area, "data_tab_st_logger", debug=False
                )
                st.session_state["data_tab_logger"] = data_tab_logger

                try:
                    exp_name = get_zip_filename_without_extension(zipped_data_add)
                    zipped_data_add.seek(0)

                    temp_dir_exp_add = os.path.join(exp_set.temp_dir, exp_name)
                    os.makedirs(temp_dir_exp_add, exist_ok=True)

                    exp_add = Experience(
                        name=exp_name,
                        temp_dir_exp=temp_dir_exp_add,
                        weight=1.0,
                        zip_file=zipped_data_add,
                        logger=data_tab_logger,
                    )

                    if exp_add.reference_data_df is None:
                        raise ExperienceLoadError(
                            f"Failed to load additional experience '{exp_name}' (no reference_data_df)."
                        )

                    # Add to the list and consistency check
                    # (col_name_p and col_name_q are consistent, hash not already present)
                    exp_set.add_experience(exp_add)

                    data_tab_logger.info(
                        f"Additional experience '{exp_name}' has been loaded and added to the ExperienceSet."
                    )

                except ExperienceLoadError as e:
                    data_tab_logger.error(str(e))
                except ValueError as e:
                    data_tab_logger.error(str(e))
                except Exception as e:
                    data_tab_logger.error(f"Unexpected error while loading additional experience: {e}")

    st.write("---")


    # List the information for each loaded experience
    for exp in exp_set.get_all_experiences():
        with st.expander(exp.name):
            if exp.reference_data_df is not None and col_name_p is not None and col_name_q is not None:
                st.write("**Adjust time range for RMSE and correlation metrics calculation**")
                t_start = exp.get_t_start()
                t_end = exp.get_t_end()
                reference_data_df = exp.reference_data_df

                col_t_start, col_t_end = st.columns(2)
                with col_t_start:
                    new_t_start = st.number_input(
                        f"Start time (s) - {exp.name}",
                        min_value=float(min(reference_data_df.index)),
                        max_value=float(t_end),
                        value=float(t_start),
                        step=0.1,
                        key=f"{exp.name}_t_start",
                    )
                with col_t_end:
                    new_t_end = st.number_input(
                        f"End time (s) - {exp.name}",
                        min_value=float(new_t_start),
                        max_value=float(max(reference_data_df.index)),
                        value=float(t_end),
                        step=0.1,
                        key=f"{exp.name}_t_end",
                    )

                if new_t_start != t_start or new_t_end != t_end:
                    exp.set_t_start(new_t_start)
                    exp.set_t_end(new_t_end)

                    if exp.base_case_simulation_data_df is not None:
                        base_case_correlation_dict = exp.compute_correlation_dict(
                            simulation_df=exp.base_case_simulation_data_df,
                            col_name_p=col_name_p,
                            col_name_q=col_name_q,
                        )
                        exp.base_case_correlation_dict = base_case_correlation_dict

                    if exp.calibrated_simulation_data_df is not None:
                        calibrated_correlation_dict = exp.compute_correlation_dict(
                            simulation_df=exp.calibrated_simulation_data_df,
                            col_name_p=col_name_p,
                            col_name_q=col_name_q,
                        )
                        exp.calibrated_correlation_dict = calibrated_correlation_dict

                    if exp.custom_simulation_data_df is not None:
                        custom_correlation_dict = exp.compute_correlation_dict(
                            simulation_df=exp.custom_simulation_data_df,
                            col_name_p=col_name_p,
                            col_name_q=col_name_q,
                        )
                        exp.custom_correlation_dict = custom_correlation_dict

                    st.rerun()

            weight = exp.get_weight()
            col_weight, col_empty = st.columns(2)
            with col_weight:
                new_weight = st.number_input(
                    f"Weight - {exp.name}",
                    min_value=1,
                    max_value=999,
                    value=int(weight),
                    step=1,
                    key=f"{exp.name}_weight",
                )
            with col_empty:
                st.write("")
            if new_weight != weight:
                exp.set_weight(new_weight)

            if exp.reference_data_df is not None:
                ref_status_icon = "✅"
                ref_label = f"{ref_status_icon} P and Q reference data (reference_data.csv)"
            else:
                ref_status_icon = "❌"
                ref_label = f"{ref_status_icon} P and Q reference data (reference_data.csv)"

            with st.expander(ref_label):
                if exp.reference_data_df is not None:
                    st.write(exp.reference_data_df)
                else:
                    st.write("Data have not been uploaded yet")

            if exp.jobs_file is not None:
                jobs_status_icon = "✅"
                uploaded_jobs_name = os.path.basename(exp.jobs_file)
                jobs_label = f"{jobs_status_icon} Dynawo jobs file"
            else:
                jobs_status_icon = "❌"
                jobs_label = f"{jobs_status_icon} Dynawo jobs file"

            with st.expander(jobs_label):
                if exp.jobs_file is not None:
                    st.write("jobs file has been uploaded: " + uploaded_jobs_name)
                else:
                    st.write("jobs file has not been uploaded yet")

            if exp.dyd_file is not None:
                dyd_status_icon = "✅"
                uploaded_dyd_name = os.path.basename(exp.dyd_file)
                dyd_label = f"{dyd_status_icon} Dynawo dyd file"
            else:
                dyd_status_icon = "❌"
                dyd_label = f"{dyd_status_icon} Dynawo dyd file"

            with st.expander(dyd_label):
                if exp.dyd_file is not None:
                    st.write("dyd file has been uploaded: " + uploaded_dyd_name)
                else:
                    st.write("dyd file has not been uploaded yet")

            if exp.par_file is not None:
                par_status_icon = "✅"
                uploaded_par_name = os.path.basename(exp.par_file)
                par_label = f"{par_status_icon} Dynawo par file"
            else:
                par_status_icon = "❌"
                par_label = f"{par_status_icon} Dynawo par file"

            with st.expander(par_label):
                if exp.par_file is not None:
                    st.write("par file has been uploaded: " + uploaded_par_name)
                else:
                    st.write("par file has not been uploaded yet")

            if exp.crv_file is not None:
                crv_status_icon = "✅"
                uploaded_crv_name = os.path.basename(exp.crv_file)
                crv_label = f"{crv_status_icon} Dynawo crv file"
            else:
                crv_status_icon = "❌"
                crv_label = f"{crv_status_icon} Dynawo crv file"

            with st.expander(crv_label):
                if exp.crv_file is not None:
                    st.write("crv file has been uploaded: " + uploaded_crv_name)
                else:
                    st.write("crv file has not been uploaded yet")


def reinit_analysis(exp_set: ExperienceSet):
    """
    Re-initialize the reference experience (if any), all additional experiences,
    and clear loggers and related Streamlit session_state entries.
    """
    # Reset reference experience (but keep the object so its temp_dir_exp is reused)
    if exp_set.experience_ref is not None:
        exp_set.experience_ref.reset()

    # Reset and drop all additional experiences (they are tied to the old reference)
    for exp in exp_set.additional_experiences:
        exp.reset()
    exp_set.additional_experiences.clear()

    # Clear Streamlit loggers
    clear_streamlit_logger("base_case_st_logger")
    clear_streamlit_logger("sensitivity_st_logger")
    clear_streamlit_logger("calibration_st_logger")
    clear_streamlit_logger("custom_calibration_st_logger")
    clear_streamlit_logger("data_tab_st_logger")

    # P/Q columns must be re-inferred from the new reference
    exp_set.set_col_names(None, None)

    # Clear stored log content in session_state
    for key in [
        "log_area_base_case_content",
        "log_area_base_case_sensitivity_content",
        "log_area_base_case_calibration_content",
        "log_area_custom_calibration_content",
    ]:
        if key in st.session_state:
            del st.session_state[key]


def get_zip_filename_without_extension(zip_file):
    return os.path.splitext(zip_file.name)[0]
