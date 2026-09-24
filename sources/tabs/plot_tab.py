# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import streamlit as st
import pandas as pd

from experience_set import ExperienceSet

import plotly.graph_objs as go
from plotly.subplots import make_subplots


def create_correlation_df(correlation_dict: dict, index_label: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    corr_p = correlation_dict["corr_p"]
    m_alpha_p = correlation_dict["m_alpha_p"]
    a_beta_p = correlation_dict["a_beta_p"]
    rmse_p = correlation_dict["rmse_p"]

    corr_q = correlation_dict["corr_q"]
    m_alpha_q = correlation_dict["m_alpha_q"]
    a_beta_q = correlation_dict["a_beta_q"]
    rmse_q = correlation_dict["rmse_q"]

    rmse_pq = correlation_dict["rmse_pq"]

    similarity_p_df = pd.DataFrame(
        {
            "Correlation": [corr_p],
            "Mag metric": [m_alpha_p],
            "Ph metric": [a_beta_p],
            "RMSE": [rmse_p],
        },
        index=[index_label],
    )
    similarity_p_df.index.name = "P"

    similarity_q_df = pd.DataFrame(
        {
            "Correlation": [corr_q],
            "Mag metric": [m_alpha_q],
            "Ph metric": [a_beta_q],
            "RMSE": [rmse_q],
        },
        index=[index_label],
    )
    similarity_q_df.index.name = "Q"

    similarity_pq_df = pd.DataFrame(
        {
            "Correlation": [(corr_p + corr_q) / 2],
            "Mag metric": [(m_alpha_p + m_alpha_q) / 2],
            "Ph metric": [(a_beta_p + a_beta_q) / 2],
            "RMSE": [rmse_pq],
        },
        index=[index_label],
    )
    similarity_pq_df.index.name = "Mean P and Q"

    return similarity_p_df, similarity_q_df, similarity_pq_df


def compute_weighted_correlation(exp_set: ExperienceSet, attr_name: str):
    """
    Compute a barycentric (weighted) correlation over all experiences, where each experience
    is weighted by its weight, for a given case type (base_case, calibrated, custom).

    attr_name must be one of:
      - "base_case_correlation_dict"
      - "calibrated_correlation_dict"
      - "custom_correlation_dict"

    Returns a dict with the same keys as a correlation_dict, or None if there is
    no eligible experience.
    """
    keys = [
        "rmse_p", "rmse_q", "rmse_pq",
        "corr_p", "corr_q",
        "m_alpha_p", "m_alpha_q",
        "a_beta_p", "a_beta_q",
    ]
    sums = {k: 0.0 for k in keys}
    total_weight = 0.0

    for exp in exp_set.get_all_experiences():
        corr = getattr(exp, attr_name, None)
        w = exp.get_weight()

        if corr is None or w <= 0.0:
            continue

        total_weight += w
        for k in keys:
            if k in corr:
                sums[k] += w * corr[k]

    if total_weight == 0.0:
        return None

    return {k: sums[k] / total_weight for k in keys}


def create_correlation_panel(exp_set: ExperienceSet):
    """
    Display a panel of barycentric (weighted) correlations over all experiences:
      - base_case vs reference (weighted by the experience weights)
      - calibrated vs reference (weighted)
      - custom vs reference (weighted)
    """
    base_case_corr = compute_weighted_correlation(exp_set, "base_case_correlation_dict")
    calibrated_corr = compute_weighted_correlation(exp_set, "calibrated_correlation_dict")
    custom_corr = compute_weighted_correlation(exp_set, "custom_correlation_dict")

    if base_case_corr is None:
        return

    similarity_p_df, similarity_q_df, similarity_pq_df = create_correlation_df(
        base_case_corr, "base_case vs reference"
    )

    if calibrated_corr is not None:
        new_row_p_df, new_row_q_df, new_row_pq_df = create_correlation_df(
            calibrated_corr, "calibrated vs reference"
        )
        similarity_p_df = pd.concat([similarity_p_df, new_row_p_df])
        similarity_q_df = pd.concat([similarity_q_df, new_row_q_df])
        similarity_pq_df = pd.concat([similarity_pq_df, new_row_pq_df])

    if custom_corr is not None:
        new_row_p_df, new_row_q_df, new_row_pq_df = create_correlation_df(
            custom_corr, "custom vs reference"
        )
        similarity_p_df = pd.concat([similarity_p_df, new_row_p_df])
        similarity_q_df = pd.concat([similarity_q_df, new_row_q_df])
        similarity_pq_df = pd.concat([similarity_pq_df, new_row_pq_df])

    st.write("**Correlation indicators (weighted)**")

    col_1, col_2, col_3 = st.columns([1, 1, 1])
    with col_1:
        st.write(similarity_p_df)
    with col_2:
        st.write(similarity_q_df)
    with col_3:
        st.write(similarity_pq_df)


def create_plots(exp_set: ExperienceSet):
    """
    For each experience in the ExperienceSet, display a subplot (1 row, 2 columns):
      - left: P (reference, base_case, automatic calibration, custom calibration)
      - right: Q (reference, base_case, automatic calibration, custom calibration)
    """

    col_name_p, col_name_q = exp_set.get_col_names()

    for exp in exp_set.get_all_experiences():
        exp_name = exp.name

        if not exp.has_reference_values():
            st.write(f"Experience '{exp_name}': reference data are missing - plots skipped.")
            continue

        reference_data_df = exp.reference_data_df

        fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=(f"P - {exp_name}", f"Q - {exp_name}")
        )

        # Reference
        x_ref = reference_data_df.index
        y_ref_p = reference_data_df[col_name_p].values
        y_ref_q = reference_data_df[col_name_q].values

        fig.add_trace(
            go.Scatter(
                x=x_ref,
                y=y_ref_p,
                mode="lines",
                name="P_reference",
                line=dict(color="magenta", width=1.5),
            ),
            row=1, col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x_ref,
                y=y_ref_q,
                mode="lines",
                name="Q_reference",
                line=dict(color="magenta", width=1.5),
            ),
            row=1, col=2,
        )

        # Basecase
        if exp.is_base_case_calculated():
            base_case_simulation_data_df = exp.base_case_simulation_data_df
            x = base_case_simulation_data_df.index
            y_p = base_case_simulation_data_df[col_name_p].values
            y_q = base_case_simulation_data_df[col_name_q].values

            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_p,
                    mode="lines",
                    name="P_base_case",
                    line=dict(color="blue", width=1.5),
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_q,
                    mode="lines",
                    name="Q_base_case",
                    line=dict(color="blue", width=1.5),
                ),
                row=1, col=2,
            )

        # Automatic calibration
        if exp.is_calibrated_case_calculated():
            calibrated_simulation_data_df = exp.calibrated_simulation_data_df
            x = calibrated_simulation_data_df.index
            y_p = calibrated_simulation_data_df[col_name_p].values
            y_q = calibrated_simulation_data_df[col_name_q].values

            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_p,
                    mode="lines",
                    name="P_automatic_calibration",
                    line=dict(color="green", width=1.5),
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_q,
                    mode="lines",
                    name="Q_automatic_calibration",
                    line=dict(color="green", width=1.5),
                ),
                row=1, col=2,
            )

        # Custom calibration
        if exp.is_custom_case_calculated():
            custom_simulation_data_df = exp.custom_simulation_data_df
            x = custom_simulation_data_df.index
            y_p = custom_simulation_data_df[col_name_p].values
            y_q = custom_simulation_data_df[col_name_q].values

            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_p,
                    mode="lines",
                    name="P_custom_calibration",
                    line=dict(color="cyan", width=1.5),
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y_q,
                    mode="lines",
                    name="Q_custom_calibration",
                    line=dict(color="cyan", width=1.5),
                ),
                row=1, col=2,
            )

        st.write(f"**Experience '{exp_name}'**")
        st.plotly_chart(fig, width="stretch")


def create_plot_tab():
    exp_set: ExperienceSet = st.session_state["experience_set"]
    create_correlation_panel(exp_set)
    create_plots(exp_set)
