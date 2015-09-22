#!/bin/bash -
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

###############################
# Execute tests within CernVM #
###############################

dir=$(dirname `readlink -f $0 || realpath $0`)
floppy="/dev/fd0"
stepid=0

echo "Step $stepid : Add directory to PYTHONPATH (if necessary)"
c=$(echo $PYTHONPATH | tr ':' '\n' | grep -x -c $dir)
[[ $c == "0" ]] && \
	export PYTHONPATH="$PYTHONPATH:$dir" 
stepid=$(($stepid + 1))

echo "Step $stepid : Create floppy drive"
[[ ! -z "/dev/fd0" ]] \
	&& install -m 666 /dev/null $floppy \
	|| sudo install -m 666 /dev/null $floppy

stepid=$(($stepid + 1))


# Use Python 2.6 (the installed version in CernVM)
echo "Step $stepid : Execute tests"
/usr/bin/python2 "$dir/tests/test_dumbq_client.py"
