#!/bin/bash
#
# DumbQ Multi-Agent Binary
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# DumbQ location on cvmfs
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
DUMBQ_CLIENT_BIN="${DUMBQ_DIR}/client/dumbq-client"
DUMBQ_BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/dumbq-agent"
DUMBQ_STATUS_BIN="${DUMBQ_BOOTSTRAP_DIR}/bin/dumbq-status"
DUMBQ_VERSION_FLAG="${DUMBQ_BOOTSTRAP_DIR}/version"
READ_FLOPPY_BIN="/cvmfs/sft.cern.ch/lcg/external/experimental/cernvm-copilot/usr/bin/readFloppy.pl"

# Configuration defaults
DUMBQ_CONFIG_FILE="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq/server/default.conf"

# Where to put the swapfile
SWAPFILE="/mnt/.rw/swapfile"

# Apache server www root
WWW_ROOT="/var/www/html"

# How much memory to allocate per core (Kb)
MEMORY_PERCORE_KB=2097152

# Get 1/2 of system memory for Z-RAM
ZRAM_FRACTION=2

# Which TTY to use for logging
LOG_TTY=1
LOG_TTY_DEV="/dev/tty${LOG_TTY}"

######################################
# Multiple executions guard
######################################

PIDFILE="/var/run/dumbq-agent-init.pid"
if [ -f "$PIDFILE" ] && kill -0 `cat $PIDFILE` 2>/dev/null; then
    echo "ERROR: Another instance of the init script is already running!"
    exit 1
fi  
echo $$ > $PIDFILE

# Place a banner on tty1 so people dont't wait for ever
clear > $LOG_TTY_DEV
echo -e "\nINFO: Initializing Worker Node" > $LOG_TTY_DEV

# Create www log directory
WWW_LOGS="${WWW_ROOT}/logs"
mkdir -p ${WWW_LOGS}
chmod a+xr ${WWW_LOGS}

# Copy website files
cp -r ${DUMBQ_BOOTSTRAP_DIR}/var/www/html/* "${WWW_ROOT}"

######################################
# Override command-line config
######################################

# Override config with first argument
[ ! -z "$1" ] && DUMBQ_CONFIG_FILE="$1"

######################################
# 1) TTYs
######################################

# Create a custom script for logging process
if [ ! -f /etc/init/dumbq-status.conf ]; then

	cat <<EOF > /etc/init/dumbq-status.conf
# dumbq-status - DumbQ Status TTY
#
# This service maintains a dumbq-status process on the specified console.
#
stop on runlevel [S016]
respawn
instance dumbq-status-\$CONSOLE
exec openvt -w -f -c \$CONSOLE -- ${DUMBQ_STATUS_BIN}
usage 'dumbq-status CONSOLE=X  - where X is console id'
EOF

fi

# Override start-ttys.conf in order to start only tty1 and tty2
if [ ! -f /etc/init/start-ttys.override ]; then

	# Stop all ttys (to avoid rebooting)
	for i in {0..9}; do
		initctl stop tty TTY=/dev/tty${i} 2>/dev/null >/dev/null
	done

	# Stop start-ttys
	initctl stop start-ttys 2>/dev/null >/dev/null

	# Change the ACTIVE_CONSOLES line
	cat <<EOF > /etc/init/start-ttys.override
start on stopped rc RUNLEVEL=[2345]
task
script
    . /etc/sysconfig/init
    initctl start tty TTY=/dev/tty1
    initctl start dumbq-status CONSOLE=2
end script
EOF

	# Start start-ttys
	initctl start start-ttys 2>/dev/null >/dev/null

fi

# Deploy cleanup scripts
if [ ! -f /etc/init.d/dumbq-cleanup ]; then

	# Copy cleanup bootstrap
	cp "${DUMBQ_BOOTSTRAP_DIR}/etc/init.d/dumbq-cleanup" /etc/init.d/dumbq-cleanup
	chmod +x /etc/init.d/dumbq-cleanup

	# Enable script
	chkconfig --add dumbq-cleanup
	chkconfig dumbq-cleanup on

	# Start it, so the stop script will work in this boot
	service dumbq-cleanup start

fi

######################################
# 2) SWAP & System features
######################################

# Get some metrics from our current environment
CPUS=$(cat /proc/cpuinfo | grep -c processor)
MEMORY_KB=$(grep MemTotal /proc/meminfo | grep -E --only-matching '[[:digit:]]+')
MEMORY_MB=$((MEMORY_KB / 1024))
DISK=$(df -m / 2>&1 | grep '/' | awk '{print $2}')

# Calculate how much memory is rezerved for z-ram
if [ ${ZRAM_FRACTION} -eq 0 ]; then

	# If ZRAM_FRACTION is zero, disable z-ram
	ZRAM_MEMORY_KB=0

else

	# How much memory to allocate for Z-RAM
	ZRAM_MEMORY_KB=$((MEMORY_KB / ZRAM_FRACTION))

	# Calculate how much Z-Ram to allocate per core
	ZRAM_MEMORY_PERCORE_KB=$((MEMORY_KB / CPUS))
	
	# Convert in bytes
	ZRAM_SIZE_BYTES=$((ZRAM_MEMORY_PERCORE_KB * 1024))

	# Log
	echo "INFO: Creating Z-RAM swap (${ZRAM_MEMORY_KB}Kb)" > $LOG_TTY_DEV

	# Allocate 1 zram device per core
    modprobe zram num_devices=$CPUS >/dev/null 2>/tmp/err.log
    if [ $? -ne 0 ]; then

    	# Error
    	echo "ERROR: Unable to load zram kernel module!" > $LOG_TTY_DEV
    	echo "# BEGIN STDERR"  > $LOG_TTY_DEV
    	cat /tmp/err.log  > $LOG_TTY_DEV
    	echo "# END STDERR" > $LOG_TTY_DEV

    else

	    # initialize the devices
	    CPUS_DECR=$((CPUS - 1))
	    for i in $(seq 0 $CPUS_DECR); do
		    echo ${ZRAM_SIZE_BYTES} > /sys/block/zram$i/disksize
	    done

	    # Creating swap filesystems
	    ERR=0; rm -f /tmp/err.log
	    for i in $(seq 0 $CPUS_DECR); do
		    mkswap /dev/zram$i >/dev/null 2>>/tmp/err.log
		    [ $? -ne 0 ] && let ERR++
	    done
	    if [ $ERR -ne 0 ]; then
	    	echo "ERROR: ${ERR} error(s) occured while allocating zram swap space!" > $LOG_TTY_DEV
	    	echo "# BEGIN STDERR" > $LOG_TTY_DEV
	    	cat /tmp/err.log > $LOG_TTY_DEV
	    	echo "# END STDERR" > $LOG_TTY_DEV
	    fi

	    # Switch the swaps on with high priority
	    ERR=0; rm -f /tmp/err.log
	    for i in $(seq 0 $CPUS_DECR); do
		    swapon -p 100 /dev/zram$i >/dev/null 2>>/tmp/err.log
		    [ $? -ne 0 ] && let ERR++
	    done
	    if [ $ERR -ne 0 ]; then
	    	echo "ERROR: ${ERR} error(s) occured while enabling swap space!" > $LOG_TTY_DEV
	    	echo "# BEGIN STDERR" > $LOG_TTY_DEV
	    	cat /tmp/err.log > $LOG_TTY_DEV
	    	echo "# END STDERR" > $LOG_TTY_DEV
	    fi


	fi

fi

# Calculate how much real memory do we have per core and how much
# swap will we need per core
MEMORY_REAL_PERCORE_KB=$(( (MEMORY_KB - ZRAM_MEMORY_KB) / CPUS ))
SWAP_PER_CORE_KB=$(( MEMORY_PERCORE_KB - MEMORY_REAL_PERCORE_KB ))

# If we need swap, allocate now
if [ ${SWAP_PER_CORE_KB} -gt 0 ]; then

	# Log
	echo "INFO: Creating Disk swap" > $LOG_TTY_DEV

	# Calculate required swap size
	SWAP_SIZE_KB=$((SWAP_PER_CORE_KB * CPUS))

	# Swap in multiplicants of 256 Mb
	SWAP_ROUND_KB=262144
	SWAP_SIZE_KB=$(( ((SWAP_SIZE_KB+SWAP_ROUND_KB-1)/SWAP_ROUND_KB) * SWAP_ROUND_KB ))

	# Check if we have a swapfile of a valid size
	if [ -f "${SWAPFILE}" ]; then
		
		# Get the size of the swapfile in KB
		SWAPFILE_SIZE=$(stat -c%s "$SWAPFILE")
		SWAPFILE_SIZE_KB=$((SWAPFILE_SIZE * 1024))

		# If the size is invalid, remove
		if [ $SWAPFILE_SIZE_KB -lt ${SWAP_SIZE_KB} ]; then
			rm "${SWAPFILE}"
		else
			SWAP_SIZE_KB=${SWAPFILE_SIZE_KB}
			echo "INFO: Swapfile size is sufficient (${SWAP_SIZE_KB}Kb)" > $LOG_TTY_DEV
		fi

	fi

	# If we still don't have a sapfile, allocate one
	if [ ! -f "${SWAPFILE}" ]; then

		# Log
		echo "INFO: Allocating swapfile (${SWAP_SIZE_KB}Kb)" > $LOG_TTY_DEV

		# Create parent folder
		mkdir -p $(dirname ${SWAPFILE})

		# Create swapfile in blocks of 64k
		SWAPFILE_BLOCKS=$((SWAP_SIZE_KB/64))
		rm -f /tmp/err.log
		dd if=/dev/zero of=${SWAPFILE} bs=65536 count=${SWAPFILE_BLOCKS} >/dev/null 2>/tmp/err.log
		if [ $? -ne 0 ]; then

			# Log error
			echo "ERROR: Unable to allocate swap space!" > $LOG_TTY_DEV
	    	echo "# BEGIN STDERR" > $LOG_TTY_DEV
	    	cat /tmp/err.log > $LOG_TTY_DEV
	    	echo "# END STDERR" > $LOG_TTY_DEV

		else

			# Fix permissions
			chown root:root ${SWAPFILE}
			chmod 0600 ${SWAPFILE}

			# Allocae swap
			mkswap "${SWAPFILE}" >/dev/null 2>/tmp/err.log
			if [ $? -ne 0 ]; then

				# Log error
				echo "ERROR: Unable to create swap filesystem!" > $LOG_TTY_DEV
		    	echo "# BEGIN STDERR" > $LOG_TTY_DEV
		    	cat /tmp/err.log > $LOG_TTY_DEV
		    	echo "# END STDERR" > $LOG_TTY_DEV

		    else 

				# Activate with low priority	
				swapon -p 50 "${SWAPFILE}" >/dev/null 2>/tmp/err.log
				if [ $? -ne 0 ]; then

					# Log error
					echo "ERROR: Unable to activate swap!" > $LOG_TTY_DEV
			    	echo "# BEGIN STDERR" > $LOG_TTY_DEV
			    	cat /tmp/err.log > $LOG_TTY_DEV
			    	echo "# END STDERR" > $LOG_TTY_DEV

				fi

		    fi

		fi

	fi

fi

# Make sure we reboot on kernel panic
if [ $(cat /proc/sys/kernel/panic) -eq 0 ]; then

	# Auto reboot on panic
	cat <<EOF >> /etc/sysctl.conf
kernel.panic = 5
EOF

    # Apply changes for the current session too
    /sbin/sysctl -w kernel.panic=5

fi

# Disable CVMFS permissions
if [ ! -f "/etc/cvmfs/default.local" ]; then

    # Patch to fix GENSER permissions
    cat <<EOF > /etc/cvmfs/default.local
CVMFS_CHECK_PERMISSIONS=no
EOF
	umount /cvmfs/sft.cern.ch

fi

# Make sure IP Forwarding is enabled in sysctl
#
# IMPORTANT: If not done like this, if a sysctl reload occurs
#            at any other time the ip forwarding will be disabled!
#
if [ $(grep -c 'net.ipv4.ip_forward = 1' /etc/sysctl.conf) -eq 0 ]; then
	# Enable IP Forwarding in the file
	sed -i.bak "s/net.ipv4.ip_forward = 0/net.ipv4.ip_forward = 1/g" /etc/sysctl.conf
	# Apply changes
	/sbin/sysctl -p /etc/sysctl.conf
fi

######################################
# 3) Scheduled reboots every day
######################################

# We should reboot our VM every 24h 
# in order to apply hotfixes through CVMFS
if [ ! -f /etc/cron.daily/reboot ]; then

	# Create reboot script
	cat <<EOF > /etc/cron.daily/reboot
#!/bin/bash

# Get the local version
LOCAL_VERSION=\$(cat /var/log/dumbq.version 2>/dev/null)
[ -z "\$LOCAL_VERSION" ] && LOCAL_VERSION=1

# Get the upstream version
UPSTREAM_VERSION=\$(cat ${DUMBQ_VERSION_FLAG} 2>/dev/null)
[ -z "\$UPSTREAM_VERSION" ] && UPSTREAM_VERSION=1

# Do not reboot if upstream is not newer
[ \${UPSTREAM_VERSION} -le \${LOCAL_VERSION} ] && exit 0
cp ${DUMBQ_VERSION_FLAG} /var/log/dumbq.version

# Reboot banner
wall "Rebooting to apply hotfixes"

# Stop status tty
initctl stop dumbq-status CONSOLE=2

# Kill all processes from CVMFS in order to avoid panics at reboot 
PID_DUMBQ_INIT=\$(ps aux | grep dumbq-agent/init.sh | grep -v grep | awk '{print \$2}')
PID_DUMBQ_CLIENT=\$(ps aux | grep dumbq-client | grep -v grep | awk '{print \$2}')
PID_DUMBQ_STATUS=\$(ps aux | grep dumbq-status | grep -v grep | awk '{print \$2}')
kill \${PID_DUMBQ_CLIENT} \${PID_DUMBQ_STATUS} \${PID_DUMBQ_INIT}

# Destroy all containers
for CONTAINER in \$(lxc-ls --active); do
	cernvm-fork \${CONTAINER} -D
done

# Reboot
reboot
EOF
	chmod +x /etc/cron.daily/reboot

fi

# We also have a mechanism to count how many hours the machine have been running
if [ ! -f /etc/cron.hourly/runhours ]; then

	# Create runhours script
	cat <<EOF > /etc/cron.hourly/runhours
#!/bin/bash
# Get current value
RUN_HOURS_FILE="/var/lib/dumbq/runhours"
RUN_HOURS=\$(cat \${RUN_HOURS_FILE} 2>/dev/null)
[ -z "\$RUN_HOURS" ] && RUN_HOURS=0
# Increment
let RUN_HOURS++
# Update
echo \${RUN_HOURS} > \${RUN_HOURS_FILE}
EOF
	chmod +x /etc/cron.hourly/runhours

fi

# Start cron if not started
service crond start

# Copy DumbQ version to prevent an initial reboot
cp ${DUMBQ_VERSION_FLAG} /var/log/dumbq.version

######################################
# 4) Web services
######################################

# -----------------------------------------
# Function shared with dumbq-client
# -----------------------------------------
# Calculate, get or generate a unique ID that identifies
# this machine ID and store it on HOST_UUID
function update_host_uuid {

    # Locate CERNVM_UUID if we are launched within CernVM
    local CERNVM_UUID=$(cat /etc/cernvm/default.conf | grep CERNVM_UUID | awk -F'=' '{print $2}')
    if [ ! -z "$CERNVM_UUID" ]; then
        export HOST_UUID=$CERNVM_UUID
        return
    fi

    # Not found? Use our own uinuqe ID
    if [ ! -f '/var/lib/uuid' ]; then
        uuidgen > /var/lib/uuid
    fi
    export HOST_UUID=$(cat /var/lib/uuid)

}
# -----------------------------------------

# Update and/or generate machine UUID
update_host_uuid

# Expose machine configuration
cat <<EOF > ${WWW_ROOT}/machine.json
{
	"vmid": "${HOST_UUID}",
	"info": {
		"cpus": "${CPUS}",
		"memory": "${MEMORY_MB}",
		"swap": "${SWAP_SIZE}",
		"disk": "${DISK}"
	},
	"layout": {
		"logs": "/logs",
		"index": "/index.json"
	}
}
EOF

# Create a blank index.json
cat <<EOF > ${WWW_ROOT}/index.json
{}
EOF

# Make sure we have CORS enabled
if [ ! -f /etc/httpd/conf.d/cors.conf ]; then

    # Prepare cross-origin requests for the webserver
    cat <<EOF > /etc/httpd/conf.d/cors.conf
<VirtualHost *:80>
    DocumentRoot /var/www/html
    Options Indexes
    Header set Access-Control-Allow-Origin "*"
	Header unset ETag
	Header set Cache-Control "max-age=0, no-cache, no-store, must-revalidate"
	Header set Pragma "no-cache"
	Header set Expires "Wed, 11 Jan 1984 05:00:00 GMT"
</VirtualHost>
EOF

fi

# Start apache if not started
service httpd start

# Start DNSMasq
service dnsmasq start

######################################
# 3) Extract BOINC details from user-data
######################################

# Reset metadata
echo "" > /var/lib/dumbq-meta

# If we have a floppy drive, fetch data from floppy
if [ -b /dev/fd0 ]; then

	# Expose floppy metadata to all containers
	${READ_FLOPPY_BIN} > /var/lib/dumbq-meta

else

	# Locate BOINC User & Host ID
	BOINC_USERID=$(cat /var/lib/amiconfig-online/2007-12-15/user-data 2>/dev/null | grep -i boinc_userid | awk -F'=' '{print $2}')
	BOINC_HOSTID=$(cat /var/lib/amiconfig-online/2007-12-15/user-data 2>/dev/null | grep -i boinc_hostid | awk -F'=' '{print $2}')
	if [ -z "$BOINC_USERID" ]; then
	  BOINC_USERID=$(cat /var/lib/amiconfig/2007-12-15/user-data 2>/dev/null | grep -i boinc_userid | awk -F'=' '{print $2}')
	  BOINC_HOSTID=$(cat /var/lib/amiconfig/2007-12-15/user-data 2>/dev/null | grep -i boinc_hostid | awk -F'=' '{print $2}')
	fi

	# Prepare dumbq-metadata if required
	if [ ! -z "$BOINC_USERID" ]; then
		# Populate shared metadata for BOINC
		echo "BOINC_USERID=${BOINC_USERID}" > /var/lib/dumbq-meta
		[ ! -z "$BOINC_HOSTID" ] && echo "BOINC_HOSTID=${BOINC_HOSTID}" >> /var/lib/dumbq-meta
	fi

fi

# Expose the vm_debug kernel command-line
if [ $(cat /proc/cmdline | grep -ic vm_debug=) -eq 1 ]; then
	DEBUG_ARGS=$(cat /proc/cmdline | sed -r 's/.*vm_debug=([^ ]+).*/\1/i')
	echo "DEBUG=${DEBUG_ARGS}" >> /var/lib/dumbq-meta
fi

######################################
# 5) GO!
######################################

# Banner on vt#1
chvt 1
clear > $LOG_TTY_DEV
echo "" > $LOG_TTY_DEV
echo "* * * * * * * * * * * * * * * * * * * * * * *" > $LOG_TTY_DEV
echo "* DumbQ VM v1.3 - Maintenance Console       *" > $LOG_TTY_DEV
echo "* Press enter to display the log-in prompt  *" > $LOG_TTY_DEV
echo "* * * * * * * * * * * * * * * * * * * * * * *" > $LOG_TTY_DEV
echo "" > $LOG_TTY_DEV

# Change to vt#2
chvt 2

# Start the DumbQ Agent
while true; do
	
	# Start agent
	echo "" > ${WWW_LOGS}/dumbq-agent.log
	${DUMBQ_CLIENT_BIN} -c "${DUMBQ_CONFIG_FILE}" --tty 3 2>>${WWW_LOGS}/dumbq-agent.log >>${WWW_LOGS}/dumbq-agent.log

	# If for any reason it failed, re-start in 60 seconds
	sleep 60

done
