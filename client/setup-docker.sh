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

######################################################
# Script to setup the docker environment with CernVM #
######################################################

IMAGE_FILE="cvm-docker.2.1-1.cernvm.x86_64.tar"
IMAGE_NAME="cernvm-test"
CERNVM_IMAGE_URL="http://cernvm.cern.ch/releases/testing/$IMAGE_FILE"

if [[ ! -f $IMAGE_FILE ]]; then
	echo "Downloading image..."
	curl -s $CERNVM_IMAGE_URL > $IMAGE_FILE
fi

if [[ $(docker images | grep $IMAGE_NAME) == "" ]]; then
	echo "Importing CernVM to your docker images..."
	cat $IMAGE_FILE | docker import - $IMAGE_NAME
fi

if [[ $? != 0 ]]; then
	echo -e "\nDocker couldn't import CernVM.\n"
	echo "Make sure you have the right permissions. Otherwise, run with sudo."
fi
