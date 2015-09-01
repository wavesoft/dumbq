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

from ..dumbq_client import config


class HardwareInfoTest(unittest.TestCase):

    """Test class to check that Dumbq gets hardware info correctly."""

    def setUp(self):
        """Set up the environment before the tests."""
        self.config = config

    def test(self):
        assert config is not None

    def tearDown(self):
        """Destroy environment."""
        self.config = None


if __name__ == '__main__':
    unittest.main()
