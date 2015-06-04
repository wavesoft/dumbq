#!/bin/bash
#
# DumbQ Multi-Agent Binary
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# DumbQ location on cvmfs
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
DUMBQ_AGENT_BIN="${DUMBQ_DIR}/bootstraps/${BOOTSTRAP_NAME}"

# Where to put the swapfile
SWAPFILE="/mnt/.rw/swapfile"

# Apache server www root
WWW_ROOT="/var/www/html"

######################################
# 1) TTYs
######################################

# Override start-ttys.conf in order to start only tty1 and tty2
if [ ! -f /etc/init/start-ttys.override ]; then

	# Change the ACTIVE_CONSOLES line
	cat /etc/init/start-ttys.conf | sed -r 's%(ACTIVE_CONSOLES=/dev/tty)(.*)%\1[1-2]%' > cat /etc/init/start-ttys.override

	# We need a reboot for changes to take effect
	echo "WARNING: Rebooting in order to apply changes"
	reboot
	exit

fi

######################################
# 2) SWAP
######################################

# Make sure we have a swap sapce
SWAP_SIZE=$(free | grep -i swap | awk '{print $2}')
if [ $SWAP_SIZE -eq 0 ]; then

	# Create swapfile if missing
	if [ ! -f "${SWAPFILE}" ]; then

		# Create 1Gb swapfile
		mkdir -p $(dirname ${SWAPFILE})
		dd if=/dev/zero of=${SWAPFILE} bs=4096 count=262144

		# Fix permissions
		chown root:root ${SWAPFILE}
		chmod 0600 ${SWAPFILE}

		# Allocae swap
		mkswap ${SWAPFILE}

	fi

	# Activate swap
	swapon ${SWAPFILE}

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
wall "A scheduled daily reboot will begin promptly"
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

# Create www log directory
WWW_LOGS="${WWW_ROOT}/logs"
mkdir -p ${WWW_LOGS}
chmod a+xr ${WWW_LOGS}

# Get some metrics from our current environment
CPUS=$(cat /proc/cpuinfo | grep -c processor)
MEMORY=$(free -m | grep -i mem | awk '{print $2}')
DISK=$(df -m / 2>&1 | grep '/' | awk '{print $2}')

# Expose machine configuration
cat <<EOF > ${WWW_ROOT}/machine.json
{
	"vmid": "${HOST_UUID}",
	"info": {
		"cpus": "${CPUS}",
		"memory": "${MEMORY}",
		"disk": "${DISK}"
	},
	"layout": {
		"logs": "/logs",
		"index": "/index.json"
	}
}
EOF

# Start apache if not started
service httpd start

######################################
# 5) GO!
######################################

# Start the DumbQ Agent
while true; do
	
	# Start agent
	${DUMBQ_AGENT_BIN} --tty 3 2>${WWW_LOGS}/dumbq-agent.log >${WWW_LOGS}/dumbq-agent.log

	# If for any reason it failed, re-start in 60 seconds
	sleep 60

done
