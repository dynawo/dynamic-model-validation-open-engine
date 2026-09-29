# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the streamlit code for the loading the data tab.
"""


import os
import streamlit as st
from logger_management import (
    clear_streamlit_logger,
    initialize_streamlit_logger
)
from util_functions import get_file_hash
from experience_set import ExperienceSet
from experience import (
    Experience,
    ExperienceLoadError
)
from const import (
    EXPERIENCE_SET_ST_SESSION_KEY,
    DATA_TAB_LOGGER_NAME,
    BASECASE_LOGGER_NAME,
    SENSITIVITY_LOGGER_NAME,
    AUTOMATIC_CALIBRATION_LOGGER_NAME,
    CUSTOM_CALIBRATION_LOGGER_NAME,
    DATA_TAB_LOG_AREA_ST_SESSION_KEY,
    DATA_TAB_LOGGER_ST_SESSION_KEY,
    BASECASE_LOGGER_ST_SESSION_KEY,
    SENSITIVITY_LOGGER_ST_SESSION_KEY,
    AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY,
    CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY,
)
from msg import (
    MSG_ERR_LOADING_REF_EXP,
    MSG_ERR_LOADING_ADD_EXP,
    MSG_INFO_ADD_EXP_ADDED
)


def _setup_experience_logs(col_3):
    with col_3:
        st.write("### Experience logs")

        if DATA_TAB_LOG_AREA_ST_SESSION_KEY not in st.session_state:
            st.session_state[DATA_TAB_LOG_AREA_ST_SESSION_KEY] = st.empty()

        if DATA_TAB_LOGGER_ST_SESSION_KEY not in st.session_state:
            log_area = st.session_state[DATA_TAB_LOG_AREA_ST_SESSION_KEY]
            data_tab_logger = initialize_streamlit_logger(
                log_area, DATA_TAB_LOGGER_NAME, debug=False
            )
            st.session_state[DATA_TAB_LOGGER_ST_SESSION_KEY] = data_tab_logger
            log_area.text("No experience loaded yet.")


def _handle_reference_experience_upload(exp_set: ExperienceSet):
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

            # Reinitialize data tab logger
            clear_streamlit_logger(DATA_TAB_LOGGER_NAME)
            log_area = st.session_state[DATA_TAB_LOG_AREA_ST_SESSION_KEY]
            data_tab_logger = initialize_streamlit_logger(
                log_area, DATA_TAB_LOGGER_NAME, debug=False
            )
            st.session_state[DATA_TAB_LOGGER_ST_SESSION_KEY] = data_tab_logger

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
                data_tab_logger.error(
                    MSG_ERR_LOADING_REF_EXP.format(error=e)
                )
            except Exception as e:
                data_tab_logger.error(
                     MSG_ERR_LOADING_REF_EXP.format(error=e)
                )


def _handle_additional_experience_upload(
    exp_set: ExperienceSet,
    reference_is_loaded: bool,
):
    st.write("### Load additional experiences")

    if not reference_is_loaded:
        st.file_uploader(
            "Upload zip file for additional experience",
            type="zip",
            key="zip_additional",
            disabled=True,
        )
        st.info("You must load a reference experience before adding additional experiences.")
        return

    zipped_data_add = st.file_uploader(
        "Upload zip file for additional experience",
        type="zip",
        key="zip_additional",
        disabled=False,
    )

    if zipped_data_add is None:
        return

    clear_streamlit_logger(DATA_TAB_LOGGER_NAME)
    log_area = st.session_state[DATA_TAB_LOG_AREA_ST_SESSION_KEY]
    data_tab_logger = initialize_streamlit_logger(
        log_area, DATA_TAB_LOGGER_NAME, debug=False
    )
    st.session_state[DATA_TAB_LOGGER_ST_SESSION_KEY] = data_tab_logger

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
        exp_set.add_experience(exp_add)
        data_tab_logger.info(MSG_INFO_ADD_EXP_ADDED.format(name=exp_name))


    except ExperienceLoadError as e:
        data_tab_logger.error(
            MSG_ERR_LOADING_ADD_EXP.format(name=exp_name, error=e)
        )
    except ValueError as e:
        data_tab_logger.error(
            MSG_ERR_LOADING_ADD_EXP.format(name=exp_name, error=e)
        )
    except Exception as e:
        data_tab_logger.error(
            MSG_ERR_LOADING_ADD_EXP.format(name=exp_name, error=e)
        )


def _render_time_range_and_metrics(exp: Experience, col_name_p: str, col_name_q: str):
    if exp.reference_data_df is None or col_name_p is None or col_name_q is None:
        return

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


def _render_experience_weight(exp: Experience):
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


def _render_reference_data(exp: Experience):
    if exp.reference_data_df is not None:
        ref_status_icon = "✅"
    else:
        ref_status_icon = "❌"
    ref_label = f"{ref_status_icon} P and Q reference data (reference_data.csv)"

    with st.expander(ref_label):
        if exp.reference_data_df is not None:
            st.write(exp.reference_data_df)
        else:
            st.write("Data have not been uploaded yet")


def _render_dynawo_file_expander(file_path: str, label: str):
    if file_path is not None:
        status_icon = "✅"
        uploaded_name = os.path.basename(file_path)
        full_label = f"{status_icon} {label}"
    else:
        status_icon = "❌"
        full_label = f"{status_icon} {label}"

    with st.expander(full_label):
        if file_path is not None:
            st.write(f"{label.split()[1]} file has been uploaded: " + uploaded_name)
        else:
            st.write(f"{label.split()[1]} file has not been uploaded yet")


def _render_experience_panel(exp: Experience, col_name_p: str, col_name_q: str):
    with st.expander(exp.name):
        _render_time_range_and_metrics(exp, col_name_p, col_name_q)
        _render_experience_weight(exp)
        _render_reference_data(exp)

        # jobs
        _render_dynawo_file_expander(exp.jobs_file, "Dynawo jobs file")
        # dyd
        _render_dynawo_file_expander(exp.dyd_file, "Dynawo dyd file")
        # par
        _render_dynawo_file_expander(exp.par_file, "Dynawo par file")
        # crv
        _render_dynawo_file_expander(exp.crv_file, "Dynawo crv file")


def create_data_tab():
    exp_set: ExperienceSet = st.session_state[EXPERIENCE_SET_ST_SESSION_KEY]

    col_1, col_2, col_3 = st.columns([1, 1, 2])

    # Col 3: logs
    _setup_experience_logs(col_3)

    # Reference experience upload
    with col_1:
        _handle_reference_experience_upload(exp_set)

    reference_is_loaded = exp_set.is_experience_ref_loaded()
    col_name_p, col_name_q = exp_set.get_col_names()

    # Additional experiences upload
    with col_2:
        _handle_additional_experience_upload(exp_set, reference_is_loaded)

    st.write("---")

    # List the information for each loaded experience
    for exp in exp_set.get_all_experiences():
        _render_experience_panel(exp, col_name_p, col_name_q)


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

    # Clear Streamlit loggers (by name)
    clear_streamlit_logger(DATA_TAB_LOGGER_NAME)
    clear_streamlit_logger(BASECASE_LOGGER_NAME)
    clear_streamlit_logger(SENSITIVITY_LOGGER_NAME)
    clear_streamlit_logger(AUTOMATIC_CALIBRATION_LOGGER_NAME)
    clear_streamlit_logger(CUSTOM_CALIBRATION_LOGGER_NAME)

    # Remove logger objects from session_state
    for key in [
        DATA_TAB_LOGGER_ST_SESSION_KEY,
        BASECASE_LOGGER_ST_SESSION_KEY,
        SENSITIVITY_LOGGER_ST_SESSION_KEY,
        AUTOMATIC_CALIBRATION_LOGGER_ST_SESSION_KEY,
        CUSTOM_CALIBRATION_LOGGER_ST_SESSION_KEY,
    ]:
        if key in st.session_state:
            del st.session_state[key]

    # P/Q columns must be re-inferred from the new reference
    exp_set.set_col_names(None, None)


def get_zip_filename_without_extension(zip_file):
    return os.path.splitext(zip_file.name)[0]
