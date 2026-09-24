# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
The Experience class stores the data related to a Dynawo simulation
and the reference data that the simulation attempts to reproduce.
"""


import os
from typing import Optional, Dict, List, IO
import pandas as pd
import shutil
import zipfile
from util_functions import get_reference_data, get_file_hash, sample_df, \
    rmse, pearson_corr, similarity_metrics, PowerToCalibrate, clean_directory
from dynawo_functions import read_parameters_sets


class ExperienceLoadError(Exception):
    """Error when loading the experience from a ZIP file."""
    pass


class Experience:
    def __init__(
        self,
        name: str,
        temp_dir_exp: str,
        weight: float = 1.0,
        zip_file: Optional[IO[bytes]] = None,
        logger: Optional[object] = None,
    ):
        """
        :param name: name of the experience (ex: 'experience_1').
        :param temp_dir_exp: root_folder for this experience (ex: .../temp/experience_1).
        :param weight: used for multi-experience configurations (float > 0).
        :param zip_file: binary file-like object pointing to the ZIP content.
        :param logger: logger.
        """
        self.name = name

        self.temp_dir_exp = temp_dir_exp
        self.temp_folder_base_case = os.path.join(self.temp_dir_exp, "base_case")
        self.temp_folder_sensitivity = os.path.join(self.temp_dir_exp, "sensitivity")
        self.temp_folder_calibration = os.path.join(self.temp_dir_exp, "calibration")
        self.temp_folder_custom_calibration = os.path.join(self.temp_dir_exp, "custom_calibration")
        for folder in [
            self.temp_dir_exp,
            self.temp_folder_base_case,
            self.temp_folder_sensitivity,
            self.temp_folder_calibration,
            self.temp_folder_custom_calibration,
        ]:
            os.makedirs(folder, exist_ok=True)

        self.set_weight(weight)

        # Hash
        # Used to avoid having redundant experiences in the experience set
        self.file_hash = None  # type: str | None

        # Dynawo files
        self.jobs_file = None
        self.dyd_file = None
        self.par_file = None
        self.crv_file = None
        # Dynawo dynamic parameters, from dyd file
        self.parameters_sets: Dict[str, Dict[str, object]] = {}

        # Reference data (for instance from PMU measurements or EMT simulation)
        self.reference_data_df: Optional[pd.DataFrame] = None

        # start time and end time
        # The calibration and sensitivity calculation will focus on this time window
        self._t_start: Optional[float] = None
        self._t_end: Optional[float] = None

        # Simulation outputs
        self.base_case_simulation_data_df: Optional[pd.DataFrame] = None
        self.base_case_correlation_dict: Optional[Dict[str, float]] = None

        self.calibrated_simulation_data_df: Optional[pd.DataFrame] = None
        self.calibrated_correlation_dict: Optional[Dict[str, float]] = None

        self.custom_simulation_data_df: Optional[pd.DataFrame] = None
        self.custom_correlation_dict: Optional[Dict[str, float]] = None

        # Sensitivities
        self.sensitivities: Optional[Dict[str, pd.DataFrame]] = None

        # If a zip
        if zip_file is not None:
            self.reset()
            self.load_from_zip(zip_file, logger=logger)

    def _extract_files_from_zip(self, zip_file: IO[bytes]) -> List[str]:
        """
        Extract all files from the ZIP into temp_folder_base_case.

        :param zip_file: binary file-like object opened in read mode.
        """
        temp_folder_base_case = self.temp_folder_base_case

        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            for zip_info in zip_ref.infolist():
                extracted_path = os.path.abspath(
                    os.path.join(temp_folder_base_case, zip_info.filename)
                )
                # Protection against path traversal: skip files whose extracted path
                # would end up outside the intended base_case directory
                if not extracted_path.startswith(os.path.abspath(temp_folder_base_case)):
                    continue

                os.makedirs(os.path.dirname(extracted_path), exist_ok=True)
                with zip_ref.open(zip_info) as source, open(extracted_path, "wb") as target:
                    shutil.copyfileobj(source, target)

        return os.listdir(temp_folder_base_case)

    @staticmethod
    def _validate_required_files(extracted_files: List[str]) -> None:
        """
        Check that the files extracted from the zip contain the expected inputs
        Check that there are no duplicates
        """
        required_files = [
            "reference_data.csv",
            ".crv",
            ".dyd",
            ".jobs",
            ".par",
        ]
        found_files = {key: [] for key in required_files}

        for f in extracted_files:
            filename = os.path.basename(f)
            if filename == "reference_data.csv":
                found_files["reference_data.csv"].append(f)
            elif filename.endswith(".crv"):
                found_files[".crv"].append(f)
            elif filename.endswith(".dyd"):
                found_files[".dyd"].append(f)
            elif filename.endswith(".jobs"):
                found_files[".jobs"].append(f)
            elif filename.endswith(".par"):
                found_files[".par"].append(f)

        errors = []
        for key in required_files:
            if len(found_files[key]) == 0:
                errors.append(f"Required file '{key}' missing from ZIP.")
            elif len(found_files[key]) > 1:
                errors.append(f"Several '{key}' files found in ZIP: {found_files[key]}")

        if errors:
            raise ExperienceLoadError(" ; ".join(errors))

    def load_from_zip(self, zip_file: IO[bytes], logger: Optional[object] = None) -> None:
        """
        Load the Dynawo inputs and reference data from a ZIP file-like object
        into this Experience.

        :param zip_file: binary file-like object pointing to the ZIP content.
        """
        # Compute and store the hash for this ZIP file
        try:
            self.file_hash = get_file_hash(zip_file)
        except Exception:
            self.file_hash = None

        if logger is not None:
            logger.info(f"[{self.name}]")

        # Extract ZIP content into temp_folder_base_case and validate it
        extracted_files = self._extract_files_from_zip(zip_file)
        self._validate_required_files(extracted_files)

        # Loading reference data
        try:
            uploaded_reference_file = [
                f for f in extracted_files
                if os.path.basename(f) == "reference_data.csv"
            ][0]

            uploaded_reference_file = os.path.join(self.temp_folder_base_case, uploaded_reference_file)
            reference_data_df = get_reference_data(uploaded_reference_file)

            self.reference_data_df = reference_data_df
            self.set_t_start(reference_data_df.index[0])
            self.set_t_end(reference_data_df.index[-1])
        except Exception as e:
            raise ExperienceLoadError(f"Error while loading reference data: {e}") from e

        # Loading Dynawo data
        try:
            uploaded_jobs = [f for f in extracted_files if f.endswith(".jobs")][0]
            uploaded_dyd = [f for f in extracted_files if f.endswith(".dyd")][0]
            uploaded_par = [f for f in extracted_files if f.endswith(".par")][0]
            uploaded_crv = [f for f in extracted_files if f.endswith(".crv")][0]
        except IndexError as e:
            raise ExperienceLoadError(
                "Missing one of .jobs, .dyd, .par or .crv files in ZIP."
            ) from e

        self.jobs_file = os.path.join(self.temp_folder_base_case, uploaded_jobs)
        self.dyd_file = os.path.join(self.temp_folder_base_case, uploaded_dyd)
        self.par_file = os.path.join(self.temp_folder_base_case, uploaded_par)
        self.crv_file = os.path.join(self.temp_folder_base_case, uploaded_crv)

        try:
            self.parameters_sets = read_parameters_sets(self.par_file)
        except Exception as e:
            raise ExperienceLoadError(
                f"Error while reading parameters sets from .par file: {e}"
            ) from e

        if logger is not None:
            logger.info("Dynawo input files loaded.")

    def get_weight(self) -> float:
        return self._weight

    def set_weight(self, value: float) -> None:
        """ Weight must be a float > 0. """
        try:
            w = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Experience weight must be a float, got {value!r}")

        if w <= 0.0:
            raise ValueError(f"Experience weight must be > 0.0, got {w}")

        self._weight = w

    def get_t_start(self):
        return self._t_start

    def set_t_start(self, value):
        if value is None:
            self._t_start = None
            return
        try:
            t = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"t_start must be a float or None, got {value!r}")
        self._t_start = t

    def get_t_end(self):
        return self._t_end

    def set_t_end(self, value):
        if value is None:
            self._t_end = None
            return
        try:
            t = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"t_end must be a float or None, got {value!r}")
        self._t_end = t

    def get_sensitivity_jobs_file(self) -> str:
        return os.path.join(
            self.temp_folder_sensitivity,
            os.path.basename(self.jobs_file),
        )

    def get_sensitivity_par_file(self) -> str:
        return os.path.join(
            self.temp_folder_sensitivity,
            os.path.basename(self.par_file),
        )

    def get_automatic_calibration_jobs_file(self) -> str:
        return os.path.join(
            self.temp_folder_calibration,
            os.path.basename(self.jobs_file),
        )

    def get_automatic_calibration_par_file(self) -> str:
        return os.path.join(
            self.temp_folder_calibration,
            os.path.basename(self.par_file),
        )

    def get_custom_calibration_jobs_file(self) -> str:
        return os.path.join(
            self.temp_folder_custom_calibration,
            os.path.basename(self.jobs_file),
        )

    def get_custom_calibration_par_file(self) -> str:
        return os.path.join(
            self.temp_folder_custom_calibration,
            os.path.basename(self.par_file),
        )

    def reset(self) -> None:
        clean_directory(self.temp_folder_base_case)
        clean_directory(self.temp_folder_sensitivity)
        clean_directory(self.temp_folder_calibration)
        clean_directory(self.temp_folder_custom_calibration)

        self.jobs_file = None
        self.dyd_file = None
        self.par_file = None
        self.crv_file = None

        self.parameters_sets = {}

        self.reference_data_df = None
        self._t_start = None
        self._t_end = None

        self.base_case_simulation_data_df = None
        self.base_case_correlation_dict = None

        self.calibrated_simulation_data_df = None
        self.calibrated_correlation_dict = None

        self.custom_simulation_data_df = None
        self.custom_correlation_dict = None

        self.sensitivities = None

    def has_reference_values(self) -> bool:
        return self.reference_data_df is not None

    def has_dynawo_inputs(self) -> bool:
        return (
            self.jobs_file is not None
            and self.dyd_file is not None
            and self.par_file is not None
            and self.crv_file is not None
        )

    def is_base_case_calculated(self) -> bool:
        return self.base_case_simulation_data_df is not None

    def is_calibrated_case_calculated(self) -> bool:
        return self.calibrated_simulation_data_df is not None

    def is_custom_case_calculated(self) -> bool:
        return self.custom_simulation_data_df is not None

    def compute_correlation_dict(
            self,
            simulation_df: pd.DataFrame,
            col_name_p: str,
            col_name_q: str,
    ) -> Dict[str, float]:
        if self.reference_data_df is None:
            raise ValueError("reference_data_df is not set in Experience.")
        if self.get_t_start() is None or self.get_t_end() is None:
            raise ValueError("t_start / t_end must be set in Experience.")

        t_start = self.get_t_start()
        t_end = self.get_t_end()

        sampled_simulation_df = sample_df(
            simulation_df,
            start_time=t_start,
            end_time=t_end,
        )

        sampled_reference_data_df = sample_df(
            self.reference_data_df,
            start_time=t_start,
            end_time=t_end,
        )

        sampled_simulated_p = sampled_simulation_df[col_name_p].values
        sampled_simulated_q = sampled_simulation_df[col_name_q].values
        sampled_reference_p = sampled_reference_data_df[col_name_p].values
        sampled_reference_q = sampled_reference_data_df[col_name_q].values

        correlation_dict: Dict[str, float] = {}

        correlation_dict["rmse_p"] = rmse(
            sampled_reference_p, sampled_reference_q,
            sampled_simulated_p, sampled_simulated_q,
            PowerToCalibrate.P,
        )
        correlation_dict["rmse_q"] = rmse(
            sampled_reference_p, sampled_reference_q,
            sampled_simulated_p, sampled_simulated_q,
            PowerToCalibrate.Q,
        )
        correlation_dict["rmse_pq"] = rmse(
            sampled_reference_p, sampled_reference_q,
            sampled_simulated_p, sampled_simulated_q,
            PowerToCalibrate.PQ,
        )

        corr_p = pearson_corr(sampled_reference_p, sampled_simulated_p)
        m_alpha_p, a_beta_p = similarity_metrics(sampled_reference_p, sampled_simulated_p)
        corr_q = pearson_corr(sampled_reference_q, sampled_simulated_q)
        m_alpha_q, a_beta_q = similarity_metrics(sampled_reference_q, sampled_simulated_q)

        correlation_dict["corr_p"] = corr_p
        correlation_dict["corr_q"] = corr_q
        correlation_dict["m_alpha_p"] = m_alpha_p
        correlation_dict["m_alpha_q"] = m_alpha_q
        correlation_dict["a_beta_p"] = a_beta_p
        correlation_dict["a_beta_q"] = a_beta_q

        return correlation_dict
