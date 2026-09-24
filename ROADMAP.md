<!-- 
    # Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
    # See AUTHORS.md
    # All rights reserved.
    # This Source Code Form is subject to the terms of the Mozilla Public
    # License, v. 2.0. If a copy of the MPL was not distributed with this
    # file, you can obtain one at http://mozilla.org/MPL/2.0/.
    # SPDX-License-Identifier: MPL-2.0
    # This file is part of the dynamic-model-validation-engine project.
-->

# ROADMAP

* Adapt the optimization engine in order to deal with binary variables
* Add a button to force the stop of the optimization process if it
takes too much time.
* Revisit the call to dynawo, for instance using pypowsybl.
* Take advantage of parallel computing?
* With streamlit it is near imposible to remove an experience because of the behaviour of the st.file_uploader
==> Refactor everything using another library than streamlit
* SonarQube