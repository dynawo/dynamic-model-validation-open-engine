# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

import os
import sys
import unittest
import pandas as pd

# Add the sources directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sources")))

from experience_set import ExperienceSet


class DummyExperience:
    """Minimal dummy Experience-like object for testing ExperienceSet."""

    def __init__(
        self,
        name: str,
        reference_data_df: pd.DataFrame | None = None,
        weight: float = 1.0,
        file_hash: str | None = None,
        has_dynawo_inputs: bool = True,
        base_case_calculated: bool = False,
    ):
        self.name = name
        self.reference_data_df = reference_data_df
        self._weight = weight
        self.file_hash = file_hash

        # Flags for can_run_* tests
        self._has_dynawo_inputs = has_dynawo_inputs
        self._base_case_calculated = base_case_calculated

        # For get_parameters_sets tests
        self.parameters_sets = {}

        # For sensitivities tests
        self.sensitivities = None

    def get_weight(self) -> float:
        return self._weight

    def has_dynawo_inputs(self) -> bool:
        return self._has_dynawo_inputs

    def is_base_case_calculated(self) -> bool:
        return self._base_case_calculated


class TestExperienceSet(unittest.TestCase):

    def test_has_reference_and_is_experience_ref_loaded(self):
        # No reference
        exp_set = ExperienceSet()
        self.assertFalse(exp_set.has_reference())
        self.assertFalse(exp_set.is_experience_ref_loaded())

        # Reference without reference_data_df
        ref = DummyExperience(name="ref", reference_data_df=None)
        exp_set.experience_ref = ref
        exp_set.set_col_names("PGenPu", "QGenPu")
        self.assertTrue(exp_set.has_reference())
        self.assertFalse(exp_set.is_experience_ref_loaded())

        # Reference with reference_data_df but missing col names
        df = pd.DataFrame({"time": [0.0], "foo_PGenPu": [1.0], "foo_QGenPu": [2.0]})
        df.set_index("time", inplace=True)
        ref.reference_data_df = df
        exp_set.set_col_names(None, None)
        self.assertFalse(exp_set.is_experience_ref_loaded())

        # Reference fully loaded
        exp_set.set_col_names("foo_PGenPu", "foo_QGenPu")
        self.assertTrue(exp_set.is_experience_ref_loaded())

    def test_infer_col_names_from_df_success(self):
        df = pd.DataFrame(
            {
                "time": [0.0, 0.1],
                "foo_PGenPu": [1.0, 2.0],
                "bar_QGenPu": [3.0, 4.0],
            }
        ).set_index("time")

        col_name_p, col_name_q = ExperienceSet._infer_col_names_from_df(df)
        self.assertEqual(col_name_p, "foo_PGenPu")
        self.assertEqual(col_name_q, "bar_QGenPu")

    def test_infer_col_names_from_df_raises_if_missing_p_or_q(self):
        df_p_only = pd.DataFrame(
            {
                "time": [0.0],
                "foo_PGenPu": [1.0],
            }
        ).set_index("time")

        with self.assertRaises(ValueError):
            ExperienceSet._infer_col_names_from_df(df_p_only)

        df_q_only = pd.DataFrame(
            {
                "time": [0.0],
                "bar_QGenPu": [1.0],
            }
        ).set_index("time")

        with self.assertRaises(ValueError):
            ExperienceSet._infer_col_names_from_df(df_q_only)

    def test_initialize_col_names_from_exp_ref(self):
        exp_set = ExperienceSet()

        # No reference
        with self.assertRaises(ValueError):
            exp_set.initialize_col_names_from_exp_ref()

        # Reference without reference_data_df
        ref = DummyExperience("ref", reference_data_df=None)
        exp_set.experience_ref = ref
        with self.assertRaises(ValueError):
            exp_set.initialize_col_names_from_exp_ref()

        # Valid reference
        df = pd.DataFrame(
            {
                "time": [0.0],
                "foo_PGenPu": [1.0],
                "bar_QGenPu": [2.0],
            }
        ).set_index("time")
        ref.reference_data_df = df

        exp_set.initialize_col_names_from_exp_ref()
        self.assertEqual(exp_set.col_name_p, "foo_PGenPu")
        self.assertEqual(exp_set.col_name_q, "bar_QGenPu")

    def test_add_experience_errors_when_no_reference(self):
        exp_set = ExperienceSet(experience_ref=None)
        exp_add = DummyExperience("add", reference_data_df=None)

        with self.assertRaises(ValueError) as cm:
            exp_set.add_experience(exp_add)
        self.assertIn("no reference experience is defined", str(cm.exception))

    def test_add_experience_rejects_duplicate_hash(self):
        # Reference with a given hash
        ref = DummyExperience(
            "ref",
            reference_data_df=pd.DataFrame(
                {"time": [0.0], "foo_PGenPu": [1.0], "bar_QGenPu": [2.0]}
            ).set_index("time"),
            file_hash="hash_ref",
        )
        exp_set = ExperienceSet(experience_ref=ref)
        exp_set.set_col_names("foo_PGenPu", "bar_QGenPu")

        # Additional experience with same hash
        add = DummyExperience(
            "add",
            reference_data_df=ref.reference_data_df,
            file_hash="hash_ref",
        )

        with self.assertRaises(ValueError) as cm:
            exp_set.add_experience(add)
        self.assertIn("same ZIP content is already present", str(cm.exception))

    def test_add_experience_rejects_missing_reference_data(self):
        ref = DummyExperience(
            "ref",
            reference_data_df=pd.DataFrame(
                {"time": [0.0], "foo_PGenPu": [1.0], "bar_QGenPu": [2.0]}
            ).set_index("time"),
        )
        exp_set = ExperienceSet(experience_ref=ref)
        exp_set.set_col_names("foo_PGenPu", "bar_QGenPu")

        add = DummyExperience("add", reference_data_df=None)

        with self.assertRaises(ValueError) as cm:
            exp_set.add_experience(add)
        self.assertIn("reference_data_df is not loaded", str(cm.exception))

    def test_add_experience_rejects_incompatible_columns(self):
        ref_df = pd.DataFrame(
            {"time": [0.0], "ref_PGenPu": [1.0], "ref_QGenPu": [2.0]}
        ).set_index("time")
        ref = DummyExperience("ref", reference_data_df=ref_df)
        exp_set = ExperienceSet(experience_ref=ref)
        exp_set.set_col_names("ref_PGenPu", "ref_QGenPu")

        add_df = pd.DataFrame(
            {"time": [0.0], "other_PGenPu": [1.0], "other_QGenPu": [2.0]}
        ).set_index("time")
        add = DummyExperience("add", reference_data_df=add_df)

        with self.assertRaises(ValueError) as cm:
            exp_set.add_experience(add)
        self.assertIn("Incompatible reference_data.csv columns", str(cm.exception))

    def test_add_experience_success(self):
        ref_df = pd.DataFrame(
            {"time": [0.0], "ref_PGenPu": [1.0], "ref_QGenPu": [2.0]}
        ).set_index("time")
        ref = DummyExperience("ref", reference_data_df=ref_df)
        exp_set = ExperienceSet(experience_ref=ref)
        exp_set.set_col_names("ref_PGenPu", "ref_QGenPu")

        add_df = pd.DataFrame(
            {"time": [0.0], "ref_PGenPu": [3.0], "ref_QGenPu": [4.0]}
        ).set_index("time")
        add = DummyExperience("add", reference_data_df=add_df, file_hash="hash_add")

        exp_set.add_experience(add)
        self.assertIn(add, exp_set.additional_experiences)

    def test_remove_experience(self):
        ref = DummyExperience("ref")
        add1 = DummyExperience("add1")
        add2 = DummyExperience("add2")

        exp_set = ExperienceSet(
            experience_ref=ref,
            additional_experiences=[add1, add2],
        )

        exp_set.remove_experience(add1)
        self.assertNotIn(add1, exp_set.additional_experiences)
        self.assertIn(add2, exp_set.additional_experiences)

        # Removing a non-present experience should not raise
        exp_set.remove_experience(add1)

    def test_get_all_experiences(self):
        ref = DummyExperience("ref")
        add1 = DummyExperience("add1")
        add2 = DummyExperience("add2")

        exp_set = ExperienceSet(
            experience_ref=ref,
            additional_experiences=[add1, add2],
        )

        all_exps = exp_set.get_all_experiences()
        self.assertEqual(all_exps, [ref, add1, add2])

        # No reference: only additional
        exp_set_no_ref = ExperienceSet(
            experience_ref=None,
            additional_experiences=[add1, add2],
        )
        all_exps_no_ref = exp_set_no_ref.get_all_experiences()
        self.assertEqual(all_exps_no_ref, [add1, add2])

    def test_set_and_get_col_names(self):
        exp_set = ExperienceSet()
        exp_set.set_col_names("P_col", "Q_col")
        p, q = exp_set.get_col_names()
        self.assertEqual(p, "P_col")
        self.assertEqual(q, "Q_col")

    def test_get_parameters_sets(self):
        ref = DummyExperience("ref")
        ref.parameters_sets = {"SET1": {"param": 1.0}}
        exp_set = ExperienceSet(experience_ref=ref)

        params = exp_set.get_parameters_sets()
        self.assertEqual(params, {"SET1": {"param": 1.0}})

        exp_set_no_ref = ExperienceSet(experience_ref=None)
        with self.assertRaises(ValueError):
            exp_set_no_ref.get_parameters_sets()

    def test_compute_weighted_sensitivities(self):
        # Two experiences with sensitivities on the same set/parameters
        df1 = pd.DataFrame(
            {"sensitivity": [1.0, -2.0]},
            index=["param1", "param2"],
        )
        df2 = pd.DataFrame(
            {"sensitivity": [3.0, 4.0]},
            index=["param1", "param2"],
        )

        exp1 = DummyExperience("exp1", weight=1.0)
        exp1.sensitivities = {"SET": df1}

        exp2 = DummyExperience("exp2", weight=3.0)
        exp2.sensitivities = {"SET": df2}

        exp_set = ExperienceSet(experience_ref=exp1, additional_experiences=[exp2])

        result = exp_set.compute_weighted_sensitivities()
        self.assertIn("SET", result)

        sens_df = result["SET"]

        # Weighted sensitivity:
        # param1: (1*1.0 + 3*3.0) / (1+3) = (1 + 9) / 4 = 2.5
        # param2: (1*(-2.0) + 3*4.0) / 4 = (-2 + 12) / 4 = 2.5
        self.assertAlmostEqual(sens_df.loc["param1", "sensitivity"], 2.5, places=6)
        self.assertAlmostEqual(sens_df.loc["param2", "sensitivity"], 2.5, places=6)

        # DataFrame is sorted by absolute sensitivity descending
        self.assertListEqual(
            sens_df.index.tolist(),
            ["param1", "param2"],  # same abs value, original order preserved by sort_index
        )

    def test_can_run_base_case(self):
        df = pd.DataFrame(
            {"time": [0.0], "PGenPu": [1.0], "QGenPu": [2.0]}
        ).set_index("time")
        ref = DummyExperience("ref", reference_data_df=df, has_dynawo_inputs=True)
        exp_set = ExperienceSet(experience_ref=ref)
        exp_set.set_col_names("PGenPu", "QGenPu")

        # Reference loaded + has inputs -> True
        self.assertTrue(exp_set.can_run_base_case())

        # No reference
        exp_set_no_ref = ExperienceSet(experience_ref=None)
        self.assertFalse(exp_set_no_ref.can_run_base_case())

    def test_can_run_sensitivity_calibration_custom(self):
        ref = DummyExperience(
            "ref",
            reference_data_df=None,
            has_dynawo_inputs=True,
            base_case_calculated=False,
        )
        exp_set = ExperienceSet(experience_ref=ref)

        self.assertFalse(exp_set.can_run_sensitivity())
        self.assertFalse(exp_set.can_run_calibration())
        self.assertFalse(exp_set.can_run_custom_calibration())

        ref._base_case_calculated = True
        self.assertTrue(exp_set.can_run_sensitivity())
        self.assertTrue(exp_set.can_run_calibration())
        self.assertTrue(exp_set.can_run_custom_calibration())


if __name__ == "__main__":
    unittest.main()