#!/bin/bash
#
# DumbQ Multi-Agent Binary
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# DumbQ location on cvmfs
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
DUMBQ_AGENT_BIN="${DUMBQ_DIR}/client/dumbq-client"
DUMBQ_BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/dumbq-agent"
DUMBQ_STATUS_BIN="${DUMBQ_BOOTSTRAP_DIR}/bin/dumbq-status"

# Where to put the swapfile
SWAPFILE="/mnt/.rw/swapfile"

# Apache server www root
WWW_ROOT="/var/www/html"

# Get some metrics from our current environment
CPUS=$(cat /proc/cpuinfo | grep -c processor)
MEMORY=$(free -m | grep -i mem | awk '{print $2}')
DISK=$(df -m / 2>&1 | grep '/' | awk '{print $2}')

######################################
# Multiple executions guard
######################################

PIDFILE="/var/run/dumbq-agent-init.pid"
if [ -f "$PIDFILE" ] && kill -0 `cat $PIDFILE` 2>/dev/null; then
    echo "ERROR: Another instance of the init script is already running!"
    exit 1
fi  
echo $$ > $PIDFILE

# Create www log directory
WWW_LOGS="${WWW_ROOT}/logs"
mkdir -p ${WWW_LOGS}
chmod a+xr ${WWW_LOGS}

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

	# We need a reboot for changes to take effect
	echo "WARNING: Rebooting in order to apply changes"
	reboot
	exit

fi

######################################
# 2) SWAP & System features
######################################

# Make sure we have a swap sapce
SWAP_SIZE=$(free | grep -i swap | awk '{print $2}')
if [ $SWAP_SIZE -eq 0 ]; then

	# Create swapfile if missing
	if [ ! -f "${SWAPFILE}" ]; then

		# Create 1Gb swapfile per core
		SWAP_SIZE=262144
		let SWAP_SIZE*=${CPUS}

		# Create swapfile
		mkdir -p $(dirname ${SWAPFILE})
		dd if=/dev/zero of=${SWAPFILE} bs=4096 count=${SWAP_SIZE}

		# Fix permissions
		chown root:root ${SWAPFILE}
		chmod 0600 ${SWAPFILE}

		# Allocae swap
		mkswap ${SWAPFILE}

		# Convert SWAP_SIZE metric to bytes
		let SWAP_SIZE*=4096

	fi

	# Activate swap
	swapon ${SWAPFILE}

fi

# Convert SWAP_SIZE metric to megabytes
let SWAP_SIZE/=1048576

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

######################################
# 3) Scheduled reboots every day
######################################

# We should reboot our VM every 24h 
# in order to apply hotfixes through CVMFS
if [ ! -f /etc/cron.daily/reboot ]; then

	# Create reboot script
	cat <<EOF > /etc/cron.daily/reboot
#!/bin/bash

# Reboot banner
wall "A scheduled daily reboot will begin promptly"

# Kill dumbq-client
PID_DUMBQ_INIT=\$(ps aux | grep dumbq-agent/init.sh | grep -v grep | awk '{print \$2}')
PID_DUMBQ_CLIENT=\$(ps aux | grep dumbq-client | grep -v grep | awk '{print \$2}')
kill \${PID_DUMBQ_CLIENT} \${PID_DUMBQ_INIT}

# Destroy all containers
for CONTAINER in \$(lxc-ls --active); do
	cernvm-fork \${CONTAINER} -D
done

# Reboot
reboot
EOF
	chmod +x /etc/cron.daily/reboot

fi

# Start cron if not started
service crond start

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
		"memory": "${MEMORY}",
		"swap": "${SWAP_SIZE}"
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

# Start apache if not started
service httpd start

######################################
# 5) GO!
######################################

# Change to vt#2
chvt 2

# Start the DumbQ Agent
while true; do
	
	# Start agent
	echo "" > ${WWW_LOGS}/dumbq-agent.log
	${DUMBQ_AGENT_BIN} --tty 3 2>>${WWW_LOGS}/dumbq-agent.log >>${WWW_LOGS}/dumbq-agent.log

	# If for any reason it failed, re-start in 60 seconds
	sleep 60

done
