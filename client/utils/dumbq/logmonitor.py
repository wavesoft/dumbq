#!/usr/bin/python
#
# DumbQ - A lightweight job scheduler - Log Monitor Helper
# Copyright (C) 2014-2015  Ioannis Charalampidis, PH-SFT, CERN

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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

import os

# Log file directories
LOG_OUT="/tmp/job.out"
LOG_ERR="/tmp/job.err"

class LogMonitor:
	"""
	A class that provides a monitoring support on one or more log files
	and calls a parser logic in order to handle their status update.
	"""



class ParserLogic:

	

def check_logs_integrity(info=None):
	"""
	Return TRUE if the logfiles are accessible and if 'info'
	parameter is defined, also validated against their integrity.
	"""

	# Return false if any of the files are missing
	if not os.path.isfile(LOG_OUT) or not os.path.isfile(LOG_ERR):
		return False

	# Try to open and if error, return
	try:
		with open(LOG_OUT, 'r') as f:
			pass
	except Exception as e:
		return False
	try:
		with open(LOG_ERR, 'r') as f:
			pass
	except Exception as e:
		return False

	# We are good. Check if the files are symbolic links
	# and if yes, extract integrity information.
	integrity = [None, None]
	if os.path.islink(LOG_OUT):
		integrity[0] = os.readlink(LOG_OUT)
	if os.path.islink(LOG_ERR):
		integrity[0] = os.readlink(LOG_ERR)

	# If we have integrity information, validate
	if not info is None:
		if info[0] != integrity[0]:
			return False
		if info[1] != integrity[1]:
			return False

	# Return integrity information
	return integrity

def monitor_thread():
	"""
	A thread that monitors the current logs
	"""

	while logs_accessible():
