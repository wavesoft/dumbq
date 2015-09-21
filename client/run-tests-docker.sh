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

##############################################
# Set up docker and test Dumbq within CernVM #
##############################################
./setup-docker.sh && \
	echo -e "\nBuild dumbq environment within CernVM\n"
	/usr/bin/docker build -t dumbq-client . && \
	echo -e "\nRun test suite...\n"
	/usr/bin/docker run --privileged \
		-v /var/lib/lxc/:/var/lib/lxc/ \
		-v /usr/share/lxc/:/usr/share/lxc \
		dumbq-client
