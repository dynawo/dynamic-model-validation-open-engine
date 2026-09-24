# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
This file contains various methods to work on the data.
"""

import os
import shutil
import hashlib
import pandas as pd
import numpy as np
import math
from enum import Enum
from scipy.fft import fft
from scipy.stats import pearsonr


class PowerToCalibrate(Enum):
    PQ = "PQ"
    P = "P"
    Q = "Q"


def get_reference_data(csv_path: str) -> pd.DataFrame:
    reference_data_df = pd.read_csv(csv_path, delimiter=",")
    reference_data_df.set_index("time", inplace=True)
    reference_data_df = remove_rows_with_same_index(reference_data_df)
    reference_data_df = reference_data_df.apply(pd.to_numeric, errors='coerce')
    return reference_data_df


def remove_rows_with_same_index(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df.index.duplicated(keep='first')]


def sample_df(
        df: pd.DataFrame,
        start_time: float | None = None, end_time: float | None = None,
        sampling_frequency=100
) -> pd.DataFrame:

    df = df.sort_index()

    if start_time is None:
        start_time = df.index[0]
    else:
        if start_time < df.index[0]:
            raise ValueError(f"start_time {start_time} is before the minimum index in df ({df.index[0]})")
    if end_time is None:
        end_time = df.index[-1]
    else:
        if end_time > df.index[-1]:
            raise ValueError(f"end_time {end_time} is after the maximum index in df ({df.index[-1]})")

    timestep = 1 / sampling_frequency
    sampled_time_indices = np.linspace(start_time, end_time, num=int(np.round((end_time - start_time) / timestep)) + 1)
    sampled_time_indices = np.round(sampled_time_indices, 10)

    sampled_df = pd.DataFrame(index=sampled_time_indices, columns=df.columns)
    for sampled_time_index in sampled_time_indices:
        if sampled_time_index in df.index:
            sampled_df.loc[sampled_time_index] = df.loc[sampled_time_index]
        else:
            lower_index = max(df.index[df.index < sampled_time_index])
            upper_index = min(df.index[df.index > sampled_time_index])
            position = (sampled_time_index - lower_index) / (upper_index - lower_index)
            interpolated_row = (1 - position) * df.loc[lower_index] + position * df.loc[upper_index]
            sampled_df.loc[sampled_time_index] = interpolated_row
    return sampled_df


def pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    correlation, _ = pearsonr(x, y)
    return correlation


def similarity_metrics(x, y):
    """
    Metric proposed in
    "An alternative approach to measure similarity between two deterministic transient signals",
    Kihong Shin

    x and y are numpy Arrays of same length
    """
    alpha = 20
    beta = 1
    fft_x = fft(x)
    fft_y = fft(y)
    h = [fft_x[i] / fft_y[i] for i in range(len(fft_x))]
    mag_h = np.absolute(h)
    phi_h = np.angle(h)
    db = np.absolute(20 * np.log10(mag_h) / alpha)
    angle_ratio = np.absolute(phi_h / (2 * math.pi * beta))
    m_alpha = 1 - np.mean(np.tanh(np.log(3) / 2 * db))
    a_beta = 1 - np.mean(np.tanh(np.log(3) / 2 * angle_ratio))
    return m_alpha, a_beta


def rmse(
    reference_p: np.ndarray,
    reference_q: np.ndarray,
    simulated_p: np.ndarray,
    simulated_q: np.ndarray,
    power_to_calibrate: PowerToCalibrate = PowerToCalibrate.PQ,
) -> float:
    """
    reference_p, reference_q, simulated_p, simulated_q are numpy Arrays of same length
    (i.e. after sampling)
    """
    if power_to_calibrate == PowerToCalibrate.P:
        errors = np.square(reference_p - simulated_p)
    elif power_to_calibrate == PowerToCalibrate.Q:
        errors = np.square(reference_q - simulated_q)
    else:
        errors = np.square(reference_p - simulated_p) + np.square(reference_q - simulated_q)

    mean_error = np.mean(errors)
    rmse = np.sqrt(mean_error)
    return rmse


def get_file_hash(file):
    file.seek(0)
    file_hash = hashlib.sha256(file.read()).hexdigest()
    file.seek(0)
    return file_hash


def clean_directory(folder_path: str) -> None:
    if not os.path.isdir(folder_path):
        return
    for file_object in os.listdir(folder_path):
        file_object_path = os.path.join(folder_path, file_object)
        if os.path.isfile(file_object_path) or os.path.islink(file_object_path):
            os.unlink(file_object_path)
        else:
            shutil.rmtree(file_object_path)
