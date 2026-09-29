# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.


"""
This file contains useful functions used by different streamlit tabs.
"""


from typing import Dict
from dynawo_functions import DynawoParam


def build_filtered_sets(
    parameters_sets: Dict[str, Dict[str, DynawoParam]],
    search_query: str,
) -> Dict[str, Dict[str, DynawoParam]]:
    """
    Filter parameters_sets by a search query on set_id and parameter_id.

    If search_query is empty, returns parameters_sets unchanged.
    Otherwise:
      - any set_id containing the query (case-insensitive) is kept with all its parameters;
      - any parameter_id containing the query (case-insensitive) is kept,
        even if the set_id does not match the query itself.

    Returns a dict with the same structure as parameters_sets but possibly
    with fewer sets and/or parameters.
    """
    if not search_query:
        # No filter from the search bar => return everything
        return parameters_sets

    filtered_sets: Dict[str, Dict[str, DynawoParam]] = {}
    query = search_query.lower()

    for set_id, params in parameters_sets.items():
        # Filter on set_id
        if query in set_id.lower():
            filtered_sets[set_id] = params
            continue

        # Filter on parameter_id
        filtered_params = {
            parameter_id: parameter
            for parameter_id, parameter in params.items()
            if query in parameter_id.lower()
        }
        if filtered_params:
            filtered_sets[set_id] = filtered_params

    return filtered_sets