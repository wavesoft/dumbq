#!/usr/bin/python
#
# DumbQ - A lightweight job scheduler - Metrics Library
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

import fcntl
import json
import sys
import os

#: The path to the database
_db_path = "/var/www/html/metrics.json"

#: The database file descriptor
_db_fd = None

#: The database contents
_db = None

#: If we should automatically commit changes
_autocommit = True

def configure(database=None, autocommit=None):
	"""
	Global function to configure module
	"""
	global _db_path
	global _autocommit

	# Update database if specified
	if not database is None:
		_db_path = database

	# Update autocommit flag if specified
	if not autocommit is None:
		_autocommit = autocommit

def load():
	"""
	Load database from disk
	"""
	global _db
	global _db_fd

	# If we have an open file descriptor, save
	if not _db_fd is None:
		commit()

	# Load database from file
	_db = { }
	if os.path.exists(_db_path):

		# Open file
		try:
			# Open file
			_db_fd = open(_db_path, 'r+')
			# Get exclusive lock on the entire file
			#fcntl.lockf(_db_fd, fcntl.LOCK_EX)
		except Exception as e:
			raise IOError("ERROR: Unable to open database file %s for reading! (%s)\n" % (_db_path, str(e)))

		# Try to read file
		try:
			_db = json.loads(_db_fd.read())
		except IOError as e:
			# Close database
			_db_fd.close()
			_db_fd = None
			raise IOError("ERROR: Unable to read database file %s (%s)!\n" % (_db_path, str(e)))

		except ValueError as e:
			sys.stderr.write("WARNING: Syntax error wile reading database file %s!\n" % _db_path)
			_db = { }


def commit():
	"""
	Save database to disk
	"""
	global _db
	global _db_fd

	# If _db is none, replace with {}
	if _db is None:
		_db = { }

	# If we have a missing _db_fd, open file now
	if _db_fd is None:
		try:
			# Open file
			_db_fd = open(_db_path, 'w')
			# Get exclusive lock on the entire file
			fcntl.lockf(_db_fd, fcntl.LOCK_EX)
		except Exception as e:
			raise IOError("ERROR: Unable to open database file %s for writing!\n" % _db_path)

	# Update database
	succeed = True
	try:
		# Replace file contents
		_db_fd.seek(0)
		_db_fd.write(json.dumps(_db))
		# And if new object is smaller, truncate
		# remaining file size
		_db_fd.truncate()
	except Exception as e:
		# Close FDs
		_db_fd.close()
		_db_fd = None
		raise IOError("ERROR: Unable to update database file %s! (%s)\n" % (_db_path, str(e)))

	# Release lock and close
	_db_fd.close()
	_db_fd = None

def set(key, value):
	"""
	Set a property to a value
	"""
	global _db

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	_db[key] = value

	# Commit database if autocommit
	if _autocommit:
		save()

def add(key, value):
	"""
	Add value to the specified key
	"""
	global _db

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	if '.' in value:
		if not key in _db:
			_db[key] = float(value)
		else:
			_db[key] = float(_db[key]) + float(value)
	else:
		if not key in _db:
			_db[key] = int(value)
		else:
			_db[key] = int(_db[key]) + int(value)

	# Commit database if autocommit
	if _autocommit:
		save()

def multiply(key, value):
	"""
	Multiply database value with given value
	"""
	global _db

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	if '.' in value:
		if not key in _db:
			_db[key] = float(value)
		else:
			_db[key] = float(_db[key]) * float(value)
	else:
		if not key in _db:
			_db[key] = int(value)
		else:
			_db[key] = int(_db[key]) * int(value)

	# Commit database if autocommit
	if _autocommit:
		save()

def average(key, value, ring=20):
	"""
	Average values in the database, using up to 'ring' values stored in it
	"""
	global _db

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Operate on float or int
	if '.' in value:
		value = float(value)
	else:
		value = int(value)

	# If we don't have average values, create them now
	if not '%s_values' % key in _db:
		_db['%s_values' % key] = []

	# Append and rotate values
	_db['%s_values' % key].append( value )
	while len(_db['%s_values' % key]) > ring:
		del _db['%s_values' % key][0]

	# Store values & Update average
	_db[key] = sum( _db['%s_values' % key] ) / float(len( _db['%s_values' % key] ))

	# Commit database if autocommit
	if _autocommit:
		save()

