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
import datetime
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

def tty_color(message, fore=None, back=None, bold=None):
	"""
	Append ANSI colors on the given message and return
	"""

	# Prepare attributes
	attr = []
	# Get foreground color
	if fore != None:
		attr = [ str(30 + TTY_COLORS[fore.lower()]) ]
	# Get background color
	if back != None:
		attr.append(str(40 + TTY_COLORS[back.lower()]))
	# Check for bold
	if bold == True:
		attr.append('1')

	# If we have no attributes, don't use ANSI encoding
	if len(attr) == 0:
		return message
	else:
		# Return ANSI Escape
		return "\x1b[%sm%s\x1b[0m" % (';'.join(attr), message)

class TailMonitor(threading.Thread):

	def __init__(self, filename, fore, back, bold, prefix):
		threading.Thread.__init__(self)

		# Keep variables
		self.filename = filename
		self.fore = fore
		self.back = back
		self.bold = bold
		self.prefix = prefix

		# Allocate new queue
		self.queue = Queue.Queue(maxsize=10)

		# Local properties
		self.active = True
		self.p = None

	def stop(self):
		"""
		Interrupt thread by stopping the forked Popen
		and resetting the active flag
		"""

		# Disable
		self.active = False

		# Kill sub process
		if self.p != None:
			self.p.terminate()


	def run(self):
		"""
		A thread that follows the contents of file 'filename'
		and feeds it the Queue given in the queue argument
		"""
		while self.active:

			# Wait until the file (re-)appears
			if not os.path.isfile(self.filename):
				time.sleep(0.5)

				# Stop when interrupted
				if not self.active:
					return
				continue

			# Tail file until the tail process dies for any reason
			self.p = subprocess.Popen(["tail", "-F", self.filename], stdout=subprocess.PIPE)
			while True:
				line = self.p.stdout.readline()
				self.queue.put(line.rstrip('\n'))
				if not line:
					break

			# Reset p value
			self.p = None


class TailList:

	def __init__(self):
		self.monitors = []
		self.prefix_str = ""

	def add(self, filename, col_fore=None, col_back=None, bold=None, prefix=None):
		"""
		Add a new file to monitor with the given color and font information
		"""

		# Put a new monitor in the list
		self.monitors.append( 
				TailMonitor(filename, col_fore, col_back, bold, prefix )
			)

	def prefix(self, name):
		"""
		Return global prefix
		"""

		# Replace optional '%n'
		prefix = self.prefix_str.replace("%n", name)

		# Return prefix only if we have one
		if not prefix:
			return ""
		else:
			return datetime.datetime.now().strftime(prefix)

	def start(self):
		"""
		Start threads and printing
		"""

		# Start threads
		for q in self.monitors:
			q.start()

		# Iterate over all queues infinitely
		while True:

			# Protect against exceptions
			try:
				for mon in self.monitors:

					# Follow
					try:

						# Try to get a line
						line = mon.queue.get(False)

						# Combine prefixes, line color and print
						print tty_color(
								"%s%s%s" % (self.prefix(os.path.basename(mon.filename)), mon.prefix, line), 
								fore=mon.fore, back=mon.back, bold=mon.bold
							)

					except Queue.Empty:
						# No new line, that's ok...
						pass

				# Sleep a bit
				time.sleep(0.01)

			except KeyboardInterrupt:
				# Exit
				print "Interrupted"

				# Interrupt all tail subprocesses
				for mon in self.monitors:
					mon.stop()

				# And exit with error
				sys.exit(1)


# Create a TailList
pp = TailList()

# Display error message one various help/wrong questions
if (len(sys.argv) == 1) or ('--help' in sys.argv) or ('help' in sys.argv) or ('-h' in sys.argv):
	print "DumbQ Logging Helper"
	print "Usage:"
	print ""
	print " dumbq-log [--prefix=""] <filename>[<attr>,...]"
	print ""
	print "The accepted options are:"
	print ""
	print " --prefix : Specify the prefix for every line (check strftime python"
	print "            function reference for accepted parameters."
	print "            Additionally \%n expands to file basename."
	print ""
	print "Attr can be one or more of:"
	print ""
	print "    color : The color to use on the lines of this log file."
	print "     bold : Where to use bold letters for this font."
	print ""
	print "Example:"
	print ""
	print " dumbq-log \\"
	print "   /var/log/messages[red] \\"
	print "   /var/log/boot.log[cyan,bold]"
	print ""
	sys.exit(0)

# Handle commands
for f in sys.argv[1:]:

	# === OPTION ==========

	# Check if this is an option
	if f[0] == "-":

		# Check for prefix
		if f[0:9] == "--prefix=":
			pp.prefix_str = f[9:]

		# Otherwise that's an invalid option
		else:
			print "ERROR: Unrecognized option '%s'" % f
			sys.exit(1)

		# Continue loop
		continue

	# === FILE ============

	# Split file/attribute
	parts = f.split("[")
	if (len(parts) == 1):
		print "ERROR: Missing attribute for '%s'" % f
		sys.exit(1)

	# Get file
	f_name = parts[0]

	# Validate attribute
	if parts[1][-1] != ']':
		print "ERROR: Missing attribute terminator in '%s'" % f
		sys.exit(1)

	# Get attributes
	f_attr = parts[1][:-1].split(",")

	# Parse attributes
	a_fore = None
	a_back = None
	a_bold = None
	for attr in f_attr:
		attr = attr.lower()

		# Check for color
		if attr in TTY_COLORS:
			a_fore = attr

		# Check for background-color
		elif (attr[0:2] == "b-") and (attr[2:] in TTY_COLORS):
			a_back = attr[2:]

		# Check for bold
		elif attr == "bold":
			a_bold = True

		# Otherwise that's an error
		else:
			print "ERROR: Invalid attribute '%s' in '%s'" % (attr, f)
			sys.exit(1)

	# Add file
	pp.add(f_name, a_fore, a_back, a_bold)

# Start tracing the logs specified
pp.start()
