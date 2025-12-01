# Copyright (c) 2022-2025, RTE (http://www.rte-france.com)
# See AUTHORS.md
# All rights reserved.
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of the dynamic-model-validation-engine project.

"""
Utility function for the loggers.
"""

import logging
import logging.handlers


def initialize_streamlit_logger(st_log_area, logger_name, debug=False):
    """ The content of this logger is displayed in the web browser.
    This content is expected to be short and its purpose is to keep track
     of the computation progress """
    streamlit_logger = logging.getLogger(logger_name)
    log_level = logging.DEBUG if debug else logging.INFO
    if not streamlit_logger.hasHandlers():
        streamlit_logger.setLevel(log_level)
        streamlit_handler = StreamlitLoggerHandler(st_log_area)
        streamlit_logger.addHandler(streamlit_handler)
    else:
        clear_streamlit_logger(streamlit_logger)
    return streamlit_logger


class StreamlitLoggerHandler(logging.Handler):
    """ Custom logging handler to send logs to a Streamlit text area """
    def __init__(self, log_area):
        super().__init__()
        self.log_area = log_area
        self.logs = ""

    def emit(self, record):
        log_entry = self.format(record)
        self.logs += log_entry + "\n"
        self.log_area.code(self.logs)

    def get_logs(self):
        return self.logs

    def clean(self):
        self.logs = ""
        self.log_area.text("")


def clear_streamlit_logger(streamlit_logger):
    """
    streamlit_logger can be either a logger or a string
    """
    if isinstance(streamlit_logger, str):
        streamlit_logger = logging.getLogger(streamlit_logger)

    if streamlit_logger is not None:
        for handler in streamlit_logger.handlers:
            if isinstance(handler, StreamlitLoggerHandler):
                handler.clean()


def get_streamlit_logs(streamlit_logger):
    for handler in streamlit_logger.handlers:
        if isinstance(handler, StreamlitLoggerHandler):
            return handler.get_logs()
