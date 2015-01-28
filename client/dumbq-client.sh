#!/bin/sh
#
# CernVM Environment Fork Utility 
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

# Global configuration
CONFIG_SOURCE=http://t4tc-mcplots-web.cern.ch/dumbq.conf
CERNVM_FORK_BIN=/usr/bin/cernvm-fork

# Local configuration
DUMBQ_LIBDIR=/var/lib/dumbq
DUMBQ_RUNDIR=${DUMBQ_LIBDIR}/run
CONFIG_PREFERENCE=${DUMBQ_LIBDIR}/preference.conf
CONFIG_CACHE=${DUMBQ_LIBDIR}/config.conf

# Lookup some general metrics in the system
CPU_COUNT=$(cat /proc/cpuinfo | grep -c processor)
MEMORY_KB=$(free -k | grep 'Mem' | awk '{ print $2 }')
SWAP_KB=$(free -k | grep 'Swap' | awk '{ print $2 }')

# Calculate how much memory do we need per container
let SLOT_CPU=1
let SLOT_MEM_KB=${MEMORY_KB}/${SLOT_CPU}
let SLOT_SWAP_KB=${SWAP_KB}/${SLOT_CPU}

# Validate the configuration file
function is_config_invalid {

	local NUM_PRJECTS=0
	local CFG=""

	# Iterate over the project configuration
	while read CFG; do

		# Skip comment lines
		[ $(echo "$CFG" | grep -cE '^[ \t]*#|^[ \t]*$') -ne 0 ] && continue

		# Check if we have a valid format in the line
		[ $(echo "$CFG" | grep -cE '^[^:]+:[^:]+:[^:]*:.*$') -eq 0 ] && return 0

		# Make sure people do not attempt to escape from the cvmfs jail
		[ $(echo "$CFG" | grep -c '\.\.') -ne 0 ] && return 0

		# That looks good
		let NUM_PRJECTS++

	done <${CONFIG_CACHE}

	# It's valid only if num_projets is bigger than 0
	[ ${NUM_PRJECTS} -le 0 ]

}

# Roll the dice and pick a container
function pick_project {

	# Project config with the biggest chances
	local BEST_CHANCE_CONFIG=""
	local BEST_CHANCE_VALUE=0
	local P_OPTIONS=""
	local P_SCRIPT=""
	local O_CHANCE=""
	local P_NAME=""
	local CFG=""

	# Create a random number between 0 and 100
	local SUM_CHANCE=0
	local R_SCORE=$RANDOM
	let R_SCORE%=100

	# Iterate over the project configuration
	while read CFG; do

		# Skip comment lines
		[ $(echo "$CFG" | grep -cE '^[ \t]*#|^[ \t]*$') -ne 0 ] && continue

		# ----------------------

		# Split parts
		P_NAME=$(echo "$CFG" | awk -F':' '{print $1}')
		P_OPTIONS=$(echo "$CFG" | awk -F':' '{print $2}')

		# Split options
		O_CHANCE=$(echo "$P_OPTIONS" | awk -F',' '{print $1}')

		# Check for overriden chance to this project
		if [ ! -z "${CONFIG_PREFERENCE}" -a -f "${CONFIG_PREFERENCE}" ]; then

			# Get preferred chance (use wildcard '*' for all projects if specified)
			PREF_CHANCE=$(cat "${CONFIG_PREFERENCE}" | grep -E "(\*|${P_NAME}):" | sort | tail -n1 | awk -F':' '{ print $2 }')

			# If we have no value, keep it as-is
			if [ ! -z "$PREF_CHANCE" ]; then

				# Change preference
				echo "INFO: Overriding preference to ${PREF_CHANCE}% for project ${P_NAME}"
				O_CHANCE=${PREF_CHANCE}

			fi

		fi

		# Calculate the current commulative weight
		let SUM_CHANCE+=${O_CHANCE}

		# ----------------------
		
		# Make sure we have a fail-over if nothing was checked
		if [ $O_CHANCE -gt $BEST_CHANCE_VALUE ]; then
			BEST_CHANCE_CONFIG="$CFG"
			BEST_CHANCE_VALUE=$O_CHANCE
		fi

		# Check our chances
		if [ $R_SCORE -le $SUM_CHANCE ]; then
			echo $CFG
			return
		fi

	done <${CONFIG_CACHE}

	# Nothing found? Echo default
	echo $BEST_CHANCE_CONFIG

}

# Internal logic to start a container
function start_container {

	# Pick a project
	local PROJECT_CFG=$(pick_project)

	# Get name/script
	local P_NAME=$(echo "$PROJECT_CFG" | awk -F':' '{ print $1 }')
	local P_REPOS=$(echo "$PROJECT_CFG" | awk -F':' '{ print $3 }')
	local P_SCRIPT=$(echo "$PROJECT_CFG" | awk -F':' '{ print $4 }')

	# Get quota
	local P_QUOTA_MEM=${SLOT_MEM_KB}
	local P_QUOTA_SWAP=${SLOT_SWAP_KB}
	local P_QUOTA_CPU=${SLOT_CPU}
	let P_QUOTA_SWAP+=${P_QUOTA_MEM}

	# Get a project name
	local CONTAINER_NAME="${P_NAME}-$(uuidgen)"
	local CONTAIENR_RUN="/cvmfs/${P_SCRIPT}"

	# Log
	echo "INFO: Starting project '${P_NAME}'"

	# Start container
	${CERNVM_FORK_BIN} ${CONTAINER_NAME} -n -d -f \
		--run=${CONTAIENR_RUN} \
		--cvmfs=${P_REPOS} \
		-o "lxc.cgroup.memory.limit_in_bytes = ${P_QUOTA_MEM}K" \
		-o "lxc.cgroup.memory.memsw.limit_in_bytes = ${P_QUOTA_SWAP}K" > /dev/null

	# Check for errors
	[ $? -ne 0 ] && echo "ERROR: Unable to create a CernVM fork!" && return

	# Mark as running
	touch ${DUMBQ_RUNDIR}/${CONTAINER_NAME}

}

# Check if there are free slots
function has_free_slot {
	local RUN_FILE=""
	local RUN_NAME=""
	local RUNNING_CONTAINERS=0

	# Get list of active containers
	local ACTIVE_CONTAINERS=$(lxc-ls --active)

	# Check if the containers we manage are running
	for RUN_FILE in ${DUMBQ_RUNDIR}/*; do

		# Empty directory? Exit loop
		[ "$RUN_FILE" == "${DUMBQ_RUNDIR}/*" ] && break

		# Get base name
		RUN_NAME=$(basename ${RUN_FILE})

		# Check if container is inactive
		if [ $(echo "$ACTIVE_CONTAINERS" | grep -c "$RUN_NAME") -eq 0 ]; then

			# Log
			echo "INFO: Found inactive container '${RUN_NAME}'"

			# Destroy inactive container
			${CERNVM_FORK_BIN} ${RUN_NAME} -D > /dev/null
			[ $? -ne 0 ] && echo "WARN: Unable to destroy the container!" && return

			# Remove run flag
			rm $RUN_FILE

			# We have a free slot!
			return 0

		fi

		# Increment counter
		let RUNNING_CONTAINERS++

	done

	# Return positive response if the running containers
	# are less than the free CPUs
	[ ${RUNNING_CONTAINERS} -lt ${CPU_COUNT} ]

}

# Banner
echo "DumbQ Client v0.1 - Ioannis Charalampidis, PH-SFT, CERN"
echo ""
echo "INFO: Using configuration from ${CONFIG_SOURCE}"

# Make sure lib directory exists
[ ! -d ${DUMBQ_LIBDIR} ] && mkdir -p $DUMBQ_LIBDIR
[ ! -d ${DUMBQ_RUNDIR} ] && mkdir -p $DUMBQ_RUNDIR

# Check for overriden user preference file
[ ! -f ${CONFIG_PREFERENCE} ] && CONFIG_PREFERENCE=""

# Refresh cache
curl -s -o "${CONFIG_CACHE}" "${CONFIG_SOURCE}"
[ $? -ne 0 ] && echo "ERROR: Could not fetch DumbQ configuration information!" && exit 2
is_config_invalid && echo "ERROR: Could not validate configuration information!" && exit 2

# Main project loop
while :; do

	# Do we have a free slot?
	if has_free_slot; then

		# Start container
		# (Blocking until completion)
		echo "INFO: There is a free slot available"
		start_container

		# Wait for a while
		sleep 1

	else

		# Sleep for a while and test again
		sleep 10

	fi

done