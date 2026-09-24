# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
The ExperienceSet class stores the data related to multiple experiences.

One of the experiences must be designated as the reference.
The reference is used to infer the names of col_name_p and col_name_q,
and to establish the list of dynamic parameters that can be calibrated.
Additional experiences must be consistent with this reference in terms of
col_name_p, col_name_q, and the associated dyd/par files.
"""


import pandas as pd
from typing import List, Optional, Dict, Any, Tuple

from experience import Experience, ExperienceLoadError


class ExperienceSet:
    def __init__(
        self,
        experience_ref: Optional[Experience] = None,
        additional_experiences: Optional[List[Experience]] = None,
        col_name_p: Optional[str] = None,
        col_name_q: Optional[str] = None,
        temp_dir: Optional[str] = None,
    ):
        self.experience_ref: Optional[Experience] = experience_ref
        self.additional_experiences: List[Experience] = additional_experiences or []

        self.col_name_p: Optional[str] = col_name_p
        self.col_name_q: Optional[str] = col_name_q

        self.temp_dir: Optional[str] = temp_dir

    def has_reference(self) -> bool:
        return self.experience_ref is not None

    def is_experience_ref_loaded(self) -> bool:
        if self.experience_ref is None:
            return False
        return (
            self.experience_ref.reference_data_df is not None
            and self.col_name_p is not None
            and self.col_name_q is not None
        )

    @staticmethod
    def _infer_col_names_from_df(reference_data_df: pd.DataFrame) -> Tuple[str, str]:
        columns = reference_data_df.columns

        candidates_p = [
            col for col in columns
            if col.endswith("PGenPu")
            or col.endswith("PGenNomPu")
            or col.endswith("P1_value")
            or col.endswith("P2_value")
        ]
        if not candidates_p:
            raise ValueError(
                "Unable to infer P column name from reference_data_df: "
                "no column ending with 'PGenPu', 'PGenNomPu', 'P1_value' or 'P2_value'."
            )

        candidates_q = [
            col for col in columns
            if col.endswith("QGenPu")
            or col.endswith("QGenNomPu")
            or col.endswith("Q1_value")
            or col.endswith("Q2_value")
        ]
        if not candidates_q:
            raise ValueError(
                "Unable to infer Q column name from reference_data_df: "
                "no column ending with 'QGenPu', 'QGenNomPu', 'Q1_value' or 'Q2_value'."
            )

        col_name_p = candidates_p[0]
        col_name_q = candidates_q[0]
        return col_name_p, col_name_q

    def initialize_col_names_from_exp_ref(self) -> None:
        if self.experience_ref is None:
            raise ValueError(
                "Cannot initialize P/Q column names: no reference experience is defined."
            )

        if self.experience_ref.reference_data_df is None:
            raise ValueError(
                "Cannot initialize P/Q column names: "
                "reference experience has no reference_data_df loaded."
            )

        col_name_p, col_name_q = self._infer_col_names_from_df(
            self.experience_ref.reference_data_df
        )
        self.set_col_names(col_name_p, col_name_q)

    def add_experience(self, exp: Experience) -> None:
        """
        If a reference experience has been loaded, it is possible to
        add a new experience in self.additional_experiences.
        """
        # Check the reference experience exists
        if self.experience_ref is None:
            raise ValueError(
                "Cannot add additional experience: no reference experience is defined."
            )

        # Each experience must be unique in the set (no duplicates)
        if exp.file_hash is not None:
            for existing_exp in self.get_all_experiences():
                if getattr(existing_exp, "file_hash", None) == exp.file_hash:
                    raise ValueError(
                        f"Cannot add additional experience '{exp.name}': "
                        "an experience with the same ZIP content is already present."
                    )

        # Consistency check around col_name_p and col_name_q
        if exp.reference_data_df is None:
            raise ValueError(
                f"Cannot add additional experience '{exp.name}': "
                "reference_data_df is not loaded."
            )
        col_name_p_exp, col_name_q_exp = self._infer_col_names_from_df(
            exp.reference_data_df
        )
        if col_name_p_exp != self.col_name_p or col_name_q_exp != self.col_name_q:
            raise ValueError(
                "Incompatible reference_data.csv columns for additional experience "
                f"'{exp.name}': expected P/Q columns "
                f"('{self.col_name_p}', '{self.col_name_q}'), but got "
                f"('{col_name_p_exp}', '{col_name_q_exp}')."
            )

        # All good
        self.additional_experiences.append(exp)

    def remove_experience(self, exp: Experience) -> None:
        try:
            self.additional_experiences.remove(exp)
        except ValueError:
            pass

    def get_all_experiences(self) -> List[Experience]:
        """
        Return all the experience (ref + all additional experiences)
        """
        experiences: List[Experience] = []
        if self.experience_ref is not None:
            experiences.append(self.experience_ref)
        experiences.extend(self.additional_experiences)
        return experiences


    def set_col_names(self, col_name_p: Optional[str], col_name_q: Optional[str]) -> None:
        self.col_name_p = col_name_p
        self.col_name_q = col_name_q

    def get_col_names(self) -> Tuple[Optional[str], Optional[str]]:
        return self.col_name_p, self.col_name_q

    def get_parameters_sets(self) -> Dict[str, Dict[str, Any]]:
        if self.experience_ref is None:
            raise ValueError(
                "Cannot get parameters_sets: no reference experience is defined."
            )
        return self.experience_ref.parameters_sets

    def compute_weighted_sensitivities(self) -> Dict[str, pd.DataFrame]:
        """
        Compute a weighted sensitivity (barycenter) over all experiences.

        For each set_id / parameter_id:
            weighted_sensitivity = sum(weight_exp * sensi_exp) / sum(weight_exp)

        Returns a dict:
            {
                set_id: DataFrame(index=parameter_id, columns=['sensitivity'])
            }
        where each DataFrame is sorted by descending absolute value of 'sensitivity'.
        """
        aggregated: Dict[str, Dict[str, Dict[str, float]]] = {}

        for exp in self.get_all_experiences():
            weight = exp.get_weight()

            if exp.sensitivities is None:
                continue

            for set_id, sensi_df in exp.sensitivities.items():
                if sensi_df is None or sensi_df.empty:
                    continue

                if set_id not in aggregated:
                    aggregated[set_id] = {}

                for parameter_id, row in sensi_df.iterrows():
                    sens_value = float(row["sensitivity"])

                    if parameter_id not in aggregated[set_id]:
                        aggregated[set_id][parameter_id] = {
                            "weighted_sum": 0.0,
                            "total_weight": 0.0,
                        }

                    aggregated[set_id][parameter_id]["weighted_sum"] += weight * sens_value
                    aggregated[set_id][parameter_id]["total_weight"] += weight

        # Conversion of the dict into a sorted Dataframe
        result: Dict[str, pd.DataFrame] = {}
        for set_id, params_dict in aggregated.items():
            sensi_values: Dict[str, float] = {}
            for parameter_id, acc in params_dict.items():
                total_weight = acc["total_weight"]
                if total_weight > 0.0:
                    sensi_values[parameter_id] = acc["weighted_sum"] / total_weight

            if not sensi_values:
                result[set_id] = pd.DataFrame(columns=["sensitivity"])
                continue

            df = pd.DataFrame.from_dict(
                sensi_values,
                orient="index",
                columns=["sensitivity"],
            )
            df = df.reindex(df["sensitivity"].abs().sort_values(ascending=False).index)
            result[set_id] = df

        return result

    def can_run_base_case(self) -> bool:
        if self.experience_ref is None:
            return False
        return (
            self.is_experience_ref_loaded() and
            self.experience_ref.has_dynawo_inputs()
        )

    def can_run_sensitivity(self) -> bool:
        if self.experience_ref is None:
            return False
        return self.experience_ref.is_base_case_calculated()

    def can_run_calibration(self) -> bool:
        if self.experience_ref is None:
            return False
        return self.experience_ref.is_base_case_calculated()

    def can_run_custom_calibration(self) -> bool:
        if self.experience_ref is None:
            return False
        return self.experience_ref.is_base_case_calculated()

    def load_reference_from_zip(
        self,
        temp_dir_exp: str,
        path_to_zip: str,
        exp_name: Optional[str] = None,
        logger: Optional[object] = None,
    ) -> Experience:
        """
        Load the reference experience from the zip file.
        Initialize col_name_p and col_name_q for the ExperienceSet.
        """
        if self.experience_ref is None:
            exp_ref = Experience(
                name=exp_name or "experience_ref",
                temp_dir_exp=temp_dir_exp,
                weight=1.0,
            )
            self.experience_ref = exp_ref
        else:
            exp_ref = self.experience_ref
            exp_ref.reset()
            if exp_name is not None:
                exp_ref.name = exp_name

        exp_ref.load_from_zip(path_to_zip, logger=logger)

        try:
            self.initialize_col_names_from_exp_ref()
        except ValueError as e:
            raise ExperienceLoadError(str(e)) from e

        if logger is not None:
            logger.info(f"Reference experience '{exp_ref.name}' loaded successfully.")
            logger.info(f"Reference P column: '{self.col_name_p}'.")
            logger.info(f"Reference Q column: '{self.col_name_q}'.")

        return exp_ref
