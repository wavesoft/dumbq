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
import time

class LogMonitorLogic:
	"""
	Base class for writing log parsing logic
	"""

	def reset(self):
		"""
		Reset monitor (ex.) because the file was truncated
		"""
		pass

	def parse(self, line):
		"""
		Handle an incoming line
		"""
		pass

class LogMonitorEntry:
	"""
	An entry in the log monitor
	"""

	def __init__(self, fileName, logic):
		"""
		Initialize a log monitor entry
		"""
		self.fileName = fileName
		self.logic = logic

		# The name of last link (used for integrity check)
		self.lastLinkName = None
		# The current state
		self.open = False

		# The file descriptor
		self.fd = None

	def check_valid(self):
		"""
		Check if the file we are monitoring is valid
		"""

		# Return false if any of the files are missing
		if not os.path.isfile(self.fileName):
			return False

		# We are good. Check if the files are symbolic links
		# and if yes, extract integrity information.
		linkName = None
		if os.path.islink(self.fileName):
			linkName = os.readlink(self.fileName)

		# If we have last link name, verify
		if not self.lastLinkName is None:
			if self.lastLinkName != linkName:
				return False

		# Looks good
		return True

	def check_open(self):
		"""
		Return TRUE if the logfiles are accessible and if 'last'
		parameter is defined, also validated against their integrity.
		"""

		# Check if it's invalid
		if not self.check_valid():
			return None

		# Try to open and if error, return
		fd = None
		try:
			fd = open(self.fileName, 'r')
		except Exception as e:
			return None

		# We are good
		return fd

	def step(self):
		"""
		Execute one step in monitor probing and exit
		"""
		
		# If the file descriptor is closed, check if we can open it
		if not self.fd:

			# Try to open
			self.fd = check_open()

			# If we managed, reset logic
			if self.fd:
				self.logic.reset()
			else:
				return

		# If we have a file descriptor, check when it becomes invalid
		if self.fd and not self.check_valid():
				self.fd.close()
				self.fd = None
				return

		# Otherwise try to read the pending lines
		if self.fd:
			# While not EOF, read lines
			while self.fd.tell() != os.fstat(self.fd.fileno()).st_size:
				# Read line
				line = self.fd.readline()
				# Pass to logic
				self.logic.parse(line)

class LogMonitor:
	"""
	A class that provides a monitoring support on one or more log files
	and calls a parser logic in order to handle their status update.
	"""

	def __init__(self):
		"""
		Initialize the log monitor
		"""
		self.monitors = [ ]
		self.active = True

	def step(self):
		"""
		Iterate over the log lines
		"""
		
		# Run step of all entries
		for m in self.monitors:
			m.step()

	def stop(self):
		"""
		Stop the infinite loop in start method
		"""
		self.active = False

	def start(self):
		"""
		Infinite loop that monitors the log files
		"""

		# Loop until stop()
		self.active = True
		while self.active:
			# Run all steps
			self.step()
			# Sleep a bit
			time.sleep(0.5)

	def monitor(self, logFile, logParser):
		"""
		Monitor the specified log file with the specified log parser
		"""

		# Store a new monitor entry
		self.monitors.append(
				LogMonitorEntry(logFile, logParser)
			)
