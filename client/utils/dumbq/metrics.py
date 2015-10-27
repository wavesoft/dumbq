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

##########################################################
# Configuration Function
##########################################################

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

##########################################################
# Low level database operations
##########################################################

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

	# Open file
	isnew = False
	try:
		# Open file
		if os.path.exists(_db_path):
			_db_fd = open(_db_path, 'r+')
		else:
			_db_fd = open(_db_path, 'w+')
			isnew = True
		# Get exclusive lock on the entire file
		fcntl.lockf(_db_fd, fcntl.LOCK_EX)
	except Exception as e:
		raise IOError("ERROR: Unable to open database file %s for reading! (%s)\n" % (_db_path, str(e)))

	# Try to read file
	if not isnew:
		try:
			_db_fd.seek(0)
			_db = json.loads(_db_fd.read())
		except IOError as e:
			# Close database
			_db_fd.close()
			_db_fd = None
			raise IOError("ERROR: Unable to read database file %s (%s)!\n" % (_db_path, str(e)))
		except ValueError as e:
			_db = { }
			sys.stderr.write("WARNING: Invalid contents of database %s!\n" % _db_path)

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

def getKey(key, default=None):
	"""
	Return a key from the datbase
	"""

	# Get path components
	path = key.split("/")

	# Walk through
	cdict = _db
	while len(path) > 0:
		p = path.pop(0)
		if not (p in cdict) or (not isinstance(cdict[p], dict) and (len(path)>0)):
			return default
		cdict = cdict[p]

	# Return value
	return cdict

def setKey(key, value):
	"""
	Set a value to a key in the database
	"""
	global _db

	# Get path components
	path = key.split("/")

	# Walk through
	cdict = _db
	while len(path) > 0:
		p = path.pop(0)
		if len(path) == 0:
			# Reached the leaf
			cdict[p] = value
		else:
			# Walk and allocate missing paths and destroy non-dicts
			if not (p in cdict) or not isinstance(cdict[p], dict):
				cdict[p] = { }
			cdict = cdict[p]

def hasKey(key):
	"""
	Check if key exists in the database
	"""

	# Get path components
	path = key.split("/")

	# Walk through
	cdict = _db
	while len(path) > 0:
		p = path.pop(0)
		if not (p in cdict) or (not isinstance(cdict[p], dict) and (len(path)>0)):
			return False
		cdict = cdict[p]

	# Return true
	return True

def delKey(key):
	"""
	Delete a particular key
	"""
	global _db

	# Get path components
	path = key.split("/")

	# Walk through
	cdict = _db
	while len(path) > 0:
		p = path.pop(0)
		if len(path) == 0:
			# Reached the leaf
			if p in cdict:
				del cdict[p]
		else:
			# Walk and allocate missing paths and destroy non-dicts
			if not (p in cdict) or not isinstance(cdict[p], dict):
				cdict[p] = { }
			cdict = cdict[p]


##########################################################
# High level interface functions
##########################################################

def set(key, value):
	"""
	Set a property to a value
	"""

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	setKey(key, value)

	# Commit database if autocommit
	if _autocommit:
		commit()

def delete(key):
	"""
	Delete a property in the database
	"""

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Delete key
	delKey(key)

	# Commit database if autocommit
	if _autocommit:
		commit()

def add(key, value):
	"""
	Add value to the specified key
	"""

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	if '.' in str(value):
		if not hasKey(key):
			setKey( key, float(value) )
		else:
			setKey( key, float(getKey(key)) + float(value) )
	else:
		if not hasKey(key):
			setKey( key, int(value) )
		else:
			setKey( key, int(getKey(key)) + int(value) )

	# Commit database if autocommit
	if _autocommit:
		commit()

def multiply(key, value):
	"""
	Multiply database value with given value
	"""

	# Load database if missing
	if (_db is None) or (_autocommit):
		load()

	# Update database
	if '.' in value:
		if not hasKey(key):
			setKey( key, float(value) )
		else:
			setKey( key, float(getKey(key)) * float(value) )
	else:
		if not hasKey(key):
			setKey( key, int(value) )
		else:
			setKey( key, int(getKey(key)) * int(value) )

	# Commit database if autocommit
	if _autocommit:
		commit()

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

	# Append and rotate values
	vals = getKey('%s_values' % key, default=[])
	vals.append( value )
	setKey( '%s_values' % key, vals )

	# Trim ring
	while len(vals) > ring:
		del vals[0]

	# Store values & Update average
	setKey( key, sum( vals ) / float(len( vals )) )

	# Commit database if autocommit
	if _autocommit:
		commit()

