#!/usr/bin/python
#
# DumbQ - A lightweight job scheduler - Logging helper
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

import threading, Queue, subprocess
import time
import os
import sys

TTY_COLORS = {
	"black": 0,
	"red": 1,
	"green": 2,
	"yellow": 3,
	"blue": 4,
	"magenta": 5,
	"cyan": 6,
	"white": 7
}

def follow_thread(filename, queue):
	"""
	A thread that follows the contents of file 'filename'
	and feeds it the Queue given in the queue argument
	"""
	while True:

		# Wait until the file (re-)appears
		if not os.path.isfile(filename):
			time.sleep(0.5)
			continue

		# Tail file until the tail process dies for any reason
		p = subprocess.Popen(["tail", "-F", filename], stdout=subprocess.PIPE)
		while True:
			line = p.stdout.readline()
			queue.put(line.rstrip('\n'))
			if not line:
				break

def tty_color(message, fore="red", back=None, bold=False):
	"""
	Append ANSI colors on the given message and return
	"""
	# Get foreground color
	attr = [ str(30 + TTY_COLORS[fore.lower()]) ]
	# Get background color
	if back != None:
		attr.append(str(40 + TTY_COLORS[back.lower()]))
	# Check for bold
	if bold:
		attr.append('1')
	# Return ANSI Escape
	return "\x1b[%sm%s\x1b[0m" % (';'.join(attr), message)

class PrettyPrinter:

	def __init__(self):
		self.queues = []

	def add(self, filename, color="red", bold=False, suffix=""):
		"""
		Add a new file to monitor with the given color and font information
		"""

		# Create a new queue
		q = Queue.Queue(maxsize=10)

		# Start a new thread
		t = threading.Thread(target=follow_thread, args=(filename,q))

		# Put configuration in the queues array
		self.queues.append(( q, t, color, bold, suffix ))

	def suffix(self):
		"""
		Return global suffix
		"""
		return ""

	def start(self):
		"""
		Start threads and printing
		"""

		# Start threads
		for q in self.queues:
			q[1].start()

		# Iterate over all queues infinitely
		while True:

			# Protect against exceptions
			try:
				for q in self.queues:

					# Unpack queue record
					(q, t, color, bold, suffix) = q

					# Follow
					try:

						# Try to get a line
						line = q.get(False)

						# Compile suffixes and line color and print
						print tty_color("%s%s%s" % (self.suffix(), suffix, line), fore=color, bold=bold)

					except Queue.Empty:
						pass

				# Sleep a bit
				time.sleep(0.01)

			except KeyboardInterrupt:
				# Exit
				print "Interrupted"
				sys.exit(1)


# Create a PrettyPrinter
pp = PrettyPrinter()
pp.add("/var/log/messages")
pp.add("/tmp/test", color="green")
pp.start()
