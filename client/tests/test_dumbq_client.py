# -*- coding: utf-8 -*-

# DumbQ 2.0 - A lightweight job scheduler
# Copyright (C) 2015-2016  Jorge Vicente Cantero, CERN

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA

import os
import sys
import unittest
import multiprocessing

from ..dumbq_client import config
from ..dumbq_client import HardwareInfo


class BaseDumbqTest(unittest.TestCase):

    """Test class to check that Dumbq gets hardware info correctly."""

    def setUp(self):
        """Set up the environment before the tests."""
        self.hardware_info = HardwareInfo()
        self.config = config

    def tearDown(self):
        """Destroy environment."""
        self.hardware_info = None
        self.config = None


class HardwareInfoTest(BaseDumbqTest):

    """Test class to check that Dumbq gets hardware info correctly."""

    def test_cpu_count(self):
        assert self.hardware_info.number_cores == multiprocessing.cpu_count()


if __name__ == '__main__':
    unittest.main()
