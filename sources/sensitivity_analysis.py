# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
This file contains the necessary functions for the sensitivity analysis.

Sensitivity analysis should help identifying the parameters whose modification
has the greatest impact on RMSE.
"""

import pandas as pd
from util_functions import sample_df, rmse, get_col_name_p_q
from dynawo_functions import run_dynawo, modify_one_param_par_file, DynawoFailedException


def run_sensitivity_analysis(
        dynawo_launcher,
        jobs_file,
        par_file,
        selected_sets,
        sampled_measured_p,
        sampled_measured_q,
        base_case_rmse,
        streamlit_logger=None,
        epsilon=0.1
):
    sensitivities = dict()
    for set_id in selected_sets:
        sensitivity = dict()
        for parameter_id in selected_sets[set_id]:
            parameter = selected_sets[set_id][parameter_id]
            reference_value = parameter.get_reference_value()
            type = parameter.get_type()
            if type == "DOUBLE":
                reference_value = float(reference_value)
            else:
                if streamlit_logger is not None:
                    streamlit_logger.error(set_id + "/" + parameter_id + " - " + "Skipped")
                continue
            modified_param_value = reference_value * (1 + epsilon)
            modify_one_param_par_file(par_file, set_id, parameter_id, modified_param_value)

            try:
                sensitivity_simulation_data_df = run_dynawo(dynawo_launcher, jobs_file)
                sensitivity_simulation_data_df = sample_df(sensitivity_simulation_data_df)
                col_name_p, col_name_q = get_col_name_p_q()
                simulated_sensitivity_p = sensitivity_simulation_data_df[col_name_p].values
                simulated_sensitivity_q = sensitivity_simulation_data_df[col_name_q].values
                rmse_for_param = rmse(sampled_measured_p, sampled_measured_q, simulated_sensitivity_p, simulated_sensitivity_q)
                sensitivity[parameter_id] = round(rmse_for_param - base_case_rmse, 4)
                if streamlit_logger is not None:
                    streamlit_logger.info(set_id + "/" + parameter_id + " - " + "Done")
            except DynawoFailedException:
                if streamlit_logger is not None:
                    streamlit_logger.info(set_id + "/" + parameter_id + " - " + "Simulation failed!")
            finally:
                modify_one_param_par_file(par_file, set_id, parameter_id, reference_value)

        sensitivities[set_id] = sensitivity

    for set_id in sensitivities:
        sensitivity_dict = sensitivities[set_id]
        sensitivity_df = pd.DataFrame.from_dict(sensitivity_dict, orient='index', columns=['sensitivity'])
        sensitivity_df = sensitivity_df.reindex(sensitivity_df['sensitivity'].abs().sort_values(ascending=False).index)
        sensitivities[set_id] = sensitivity_df

    return sensitivities
