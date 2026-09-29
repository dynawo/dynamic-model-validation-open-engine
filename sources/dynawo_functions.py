# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains the functions that enables to run dynawo and
to modify the parameter values of the inputs.
"""


import os
import shutil
import pandas as pd
import subprocess
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from experience import Experience
    from experience_set import ExperienceSet
from util_functions import remove_rows_with_same_index
from const import (
    DYNAWO_NS,
    DYNAWO_PAR_XPATH_TEMPLATE
)
from msg import (
    MSG_BASECASE_NOT_READY,
    MSG_CUSTOM_CALIBRATION_NOT_READY,
    MSG_NO_PARAMETERS_SELECTED_CUSTOM,
    MSG_DYNAWO_FAILED
)


class DynawoFailedException(Exception):
    pass


class SimulationPreconditionError(Exception):
    pass


class DynawoParam:
    def __init__(self, name, type, original_value):
        self._name = name
        self._type = type  # "INT", "DOUBLE", "STRING", ...
        self._original_value = original_value  # string
        self._value = original_value  # string
        self._calibrated_value = None
        if type == "DOUBLE":
            # if param = 4, we search in the range [-4, 40]
            # if param = -4, we search in the range [-40, 4]
            # in order to catch a sign error or an error in the order of magnitude
            # The larger the range the longer the computation time
            original_value = float(original_value)
            if original_value > 0:
                self._min_bound = -original_value
                self._max_bound = 10 * original_value
            elif original_value < 0:
                self._min_bound = 10 * original_value
                self._max_bound = -original_value
            else:
                # seems unnecessary, but prevents "-0.0" behaviours (not pretty on screen)
                self._min_bound = 0
                self._max_bound = 0
        # elif type == "BOOL":  # TODO
        #     self._min_bound = None
        #     self._max_bound = None
        else:
            self._min_bound = None
            self._max_bound = None

    def get_name(self):
        return self._name

    def get_type(self):
        return self._type

    def get_original_value(self):
        return self._original_value

    def get_value(self):
        return self._value

    def get_calibrated_value(self):
        return self._calibrated_value

    def get_min_bound(self):
        return self._min_bound

    def get_max_bound(self):
        return self._max_bound

    def set_name(self, value):
        self._name = value

    def set_type(self, value):
        self._type = value

    def set_original_value(self, value):
        self._original_value = value

    def set_value(self, value):
        self._value = value

    def set_calibrated_value(self, value):
        self._calibrated_value = value

    def set_min_bound(self, value):
        try:
            value = float(value)
            self._min_bound = value
        except ValueError:
            self._min_bound = None

    def set_max_bound(self, value):
        try:
            value = float(value)
            self._max_bound = value
        except ValueError:
            self._max_bound = None


def run_dynawo(dynawo_launcher: str, jobs_file: str, logger: Optional[logging.Logger] = None) -> pd.DataFrame:
    """
    The current version of this function calls dynawo via subprocess.
    In the future it might be rewritten by calling dynawo directly from pypowsybl.
    """
    init_wd = os.getcwd()
    input_wd = os.path.dirname(jobs_file)

    # With this implementation Dynawo should be called from the folder
    # which contains the input files.
    try:
        os.chdir(input_wd)

        cmd = [dynawo_launcher, "jobs", jobs_file]

        if logger is not None:
            logger.info("Running Dynawo: " + " ".join(cmd))
        t = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = t.communicate()
        return_code = t.returncode

        if return_code != 0:
            if logger is not None:
                logger.error(MSG_DYNAWO_FAILED)
                msg = stderr.decode("utf-8")
                logger.error(msg)
            raise DynawoFailedException

    finally:
        os.chdir(init_wd)

    simulation_data_df = get_simulation_data(jobs_file)
    return simulation_data_df


def modify_one_param_par_file(par_file, set_id, param_id, new_value):
    tree = ET.parse(par_file)
    root = tree.getroot()
    namespace = {"ns": DYNAWO_NS}
    for par in root.findall(DYNAWO_PAR_XPATH_TEMPLATE.format(set_id, param_id), namespace):
        par.set("value", str(new_value))
    ET.register_namespace("", DYNAWO_NS)
    modified_content = ET.tostring(root, encoding="unicode")
    with open(par_file, "w") as file:
        file.write(modified_content)


def modify_multiple_param_par_file(par_file, selected_sets):
    """
    selected_sets: dict(set_id, dict(param_id, DynawoParam))
    """
    tree = ET.parse(par_file)
    root = tree.getroot()
    namespace = {"ns": DYNAWO_NS}
    for set_id in selected_sets:
        for parameter_id in selected_sets[set_id]:
            parameter = selected_sets[set_id][parameter_id]
            new_value = parameter.get_value()
            xpath = DYNAWO_PAR_XPATH_TEMPLATE.format(set_id, parameter_id)
            for par in root.findall(xpath, namespace):
                par.set("value", str(new_value))
    ET.register_namespace("", DYNAWO_NS)
    modified_content = ET.tostring(root, encoding="unicode")
    with open(par_file, "w") as file:
        file.write(modified_content)


def modify_multiple_param_par_file_for_optim(par_file, x, index_to_param_map):
    # Time-consuming at the moment, but the xml approach should eventually be replaced
    # with a pypowsybl implementation
    tree = ET.parse(par_file)
    root = tree.getroot()
    namespace = {"ns": DYNAWO_NS}
    for i in range(len(index_to_param_map)):
        set_id, param_id = index_to_param_map[i]
        param_value = x[i]
        xpath = DYNAWO_PAR_XPATH_TEMPLATE.format(set_id, param_id)
        for par in root.findall(xpath, namespace):
            par.set("value", str(param_value))
    ET.register_namespace("", DYNAWO_NS)
    modified_content = ET.tostring(root, encoding="unicode")
    with open(par_file, "w") as file:
        file.write(modified_content)


def run_custom_dynawo(
    dynawo_launcher,
    jobs_file,
    par_file,
    selected_sets,
    logger=None,
):
    if logger is not None:
        for set_id in selected_sets:
            for parameter_id in selected_sets[set_id]:
                parameter = selected_sets[set_id][parameter_id]
                new_value = parameter.get_value()
                logger.info(
                    set_id
                    + "/"
                    + parameter.get_name()
                    + " - "
                    + "new_value: "
                    + str(new_value)
                )
    modify_multiple_param_par_file(par_file, selected_sets)
    simulation_data_df = run_dynawo(dynawo_launcher, jobs_file, logger)
    return simulation_data_df


def create_output_folder(output_folder=None):
    if output_folder is None:
        script_directory = os.path.dirname(os.path.abspath(__file__))
        output_folder = os.path.join(script_directory, "temp")
    if not os.path.isdir(output_folder):
        os.makedirs(output_folder)
    return output_folder


def get_simulation_data(jobs_file):
    tree = ET.parse(jobs_file)
    root = tree.getroot()
    out_csv = os.path.join(
        os.path.dirname(jobs_file),
        root.find("{*}job/{*}outputs").get("directory"),
        "curves",
        "curves.csv",
    )
    simulation_data_df = pd.read_csv(out_csv, delimiter=";")
    simulation_data_df.set_index("time", inplace=True)
    simulation_data_df = remove_rows_with_same_index(simulation_data_df)
    return simulation_data_df


def read_parameters_sets(par_file):
    tree = ET.parse(par_file)
    root = tree.getroot()
    parameters_sets: Dict[str, Dict[str, DynawoParam]] = {}
    for set_element in root:
        set_id = set_element.attrib["id"]
        parameters: Dict[str, DynawoParam] = {}
        for param_element in set_element:
            if param_element.tag.endswith("par"):
                param_name = param_element.attrib["name"]
                param_type = param_element.attrib["type"]
                param_value = param_element.attrib["value"]
                parameter = DynawoParam(param_name, param_type, param_value)
                parameters[param_name] = parameter
        parameters_sets[set_id] = parameters

    return parameters_sets


def _run_base_case_for_experience(
    dynawo_launcher: str,
    exp: "Experience",
    col_name_p: str,
    col_name_q: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Run Dynawo base case simulation for a single experience.
    """
    ok, msg = exp.check_ready_for_basecase_calculation()
    if not ok:
        if logger is not None:
            logger.warning(f"[{exp.name}] {msg}")
        exp.base_case_simulation_data_df = None
        exp.base_case_correlation_dict = None
        return

    jobs_file = exp.jobs_file

    try:
        if logger is not None:
            logger.info(f"[{exp.name}]")
            logger.info("Starting Dynawo base case simulation")

        base_case_simulation_data_df = run_dynawo(
            dynawo_launcher, jobs_file, logger
        )

        exp.base_case_simulation_data_df = base_case_simulation_data_df

        base_case_correlation_dict = exp.compute_correlation_dict(
            simulation_df=base_case_simulation_data_df,
            col_name_p=col_name_p,
            col_name_q=col_name_q,
        )
        exp.base_case_correlation_dict = base_case_correlation_dict

        if logger is not None:
            logger.info("Dynawo base case simulation completed.")

    except DynawoFailedException:
        if logger is not None:
            logger.error(MSG_DYNAWO_FAILED)
        exp.base_case_simulation_data_df = None
        exp.base_case_correlation_dict = None


def run_base_case_for_all(
    dynawo_launcher: str,
    exp_set: "ExperienceSet",
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Run Dynawo on the basecase for every experience in the set.
    """
    if not exp_set.can_run_base_case():
        raise SimulationPreconditionError(MSG_BASECASE_NOT_READY)

    col_name_p, col_name_q = exp_set.get_col_names()

    for exp in exp_set.get_all_experiences():
        _run_base_case_for_experience(
            dynawo_launcher,
            exp,
            col_name_p,
            col_name_q,
            logger,
        )


def _run_custom_calibration_for_experience(
    dynawo_launcher: str,
    exp: "Experience",
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    col_name_p: str,
    col_name_q: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Run custom calibration for a single experience.
    """
    ok, msg = exp.check_ready_for_custom_calibration()
    if not ok:
        if logger is not None:
            logger.warning(f"[{exp.name}] {msg}")
        exp.custom_simulation_data_df = None
        exp.custom_correlation_dict = None
        return

    if logger is not None:
        logger.info(f"[{exp.name}]")
        logger.info("Starting Dynawo custom calibration simulation...")

    temp_folder_custom_calibration = exp.temp_folder_custom_calibration
    for element in os.listdir(exp.temp_folder_base_case):
        src = os.path.join(exp.temp_folder_base_case, element)
        if os.path.isfile(src):
            shutil.copy(src, temp_folder_custom_calibration)

    jobs_file_calibration = exp.get_custom_calibration_jobs_file()
    par_file_calibration = exp.get_custom_calibration_par_file()

    try:
        custom_simulation_data_df = run_custom_dynawo(
            dynawo_launcher,
            jobs_file_calibration,
            par_file_calibration,
            selected_sets,
            logger=logger,
        )

        custom_correlation_dict = exp.compute_correlation_dict(
            simulation_df=custom_simulation_data_df,
            col_name_p=col_name_p,
            col_name_q=col_name_q,
        )

        exp.custom_simulation_data_df = custom_simulation_data_df
        exp.custom_correlation_dict = custom_correlation_dict

        if logger is not None:
            logger.info("Dynawo custom calibration simulation completed.")

    except DynawoFailedException:
        if logger is not None:
            logger.error("Dynawo custom calibration simulation failed.")
        exp.custom_simulation_data_df = None
        exp.custom_correlation_dict = None


def run_custom_calibration_for_all(
    dynawo_launcher: str,
    exp_set: "ExperienceSet",
    selected_sets: Dict[str, Dict[str, DynawoParam]],
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Run Dynawo with the custom parameters for every experience in the set.
    """
    if not exp_set.can_run_custom_calibration():
        raise SimulationPreconditionError(MSG_CUSTOM_CALIBRATION_NOT_READY)

    if not selected_sets:
        if logger is not None:
            logger.warning(MSG_NO_PARAMETERS_SELECTED_CUSTOM)
        return

    col_name_p, col_name_q = exp_set.get_col_names()

    for exp in exp_set.get_all_experiences():
        _run_custom_calibration_for_experience(
            dynawo_launcher,
            exp,
            selected_sets,
            col_name_p,
            col_name_q,
            logger,
        )
