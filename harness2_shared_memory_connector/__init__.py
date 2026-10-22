# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""A memory connector for Harness².

It keeps the harness library in files and shares only the lessons through a
shared-memory server.
"""

from .connector import SharedMemoryConnector, make_connector

__all__ = ["SharedMemoryConnector", "make_connector"]

__version__ = "0.1.0"
