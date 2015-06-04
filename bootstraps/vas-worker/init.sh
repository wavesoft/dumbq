#!/bin/bash

# LiveQ CVMFS Directory
CVMFS_VAS_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/virtual-atom-smasher"
CVMFS_LIVEQ_DIR="${CVMFS_VAS_DIR}/liveq"

# CVMFS Binaries
AGENT_CHECK_BIN="${CVMFS_VAS_DIR}/liveq-agent-check.sh"
AGENT_LOG_BIN="${CVMFS_VAS_DIR}/liveq-agent-log.sh"

# One-time initialization
if [ ! -f /root/vas-initialized.flag ]; then

	# Read 'liveq_queue_id' from contextualization information
	QUEUE_ID_USER=$(cat /var/lib/amiconfig/2007-12-15/user-data | grep liveq_queue_id | awk -F'=' '{print $2}')
	QUEUE_ID_ONLINE=$(cat /var/lib/amiconfig-online/2007-12-15/user-data | grep liveq_queue_id | awk -F'=' '{print $2}')

	# Pick queue name the appropriate order
	JOIN_GROUP="global"
	[ ! -z "$QUEUE_ID_ONLINE" ] && JOIN_GROUP="${QUEUE_ID_ONLINE}"
	[ ! -z "$QUEUE_ID_USER" ] && JOIN_GROUP="${QUEUE_ID_USER}"

	# Ensure we have job directory
	JOB_DIR="/tmp/liveq-agent"
	mkdir -p ${JOB_DIR}

	# Create liveq configuration file
	mkdir -p /etc/liveq
	cat <<EOF > /etc/liveq/liveq-agent.conf
[general]
loglevel=info

[app]
class=liveq.classes.apps.mcplots
exec=./runRivet.sh boinc %(beam)s %(process)s %(energy)g %(params)s %(specific)s %(generator)s %(version)s %(tune)s %(events)i %(seed)i
work_dir=${JOB_DIR}
update_interval=10
tune=default

[external-bus]
class=liveq.classes.bus.xmppmsg
domain=t4t-xmpp.cern.ch
server=t4t-xmpp.cern.ch
username=jmliveq-agent
password=agentnode
resource=%(uuid)s

[agent]
slots=1
server=jmliveq-master@t4t-xmpp.cern.ch
group=${JOIN_GROUP}
EOF

    # Override start-ttys script
    cat <<EOF > /etc/init/start-ttys.override
start on stopped rc RUNLEVEL=[2345]
task
script
    . /etc/sysconfig/init
    openvt -f -c 1 -- ${AGENT_LOG_BIN}
    initctl start tty TTY=/dev/tty1
    initctl start tty TTY=/dev/tty2
    initctl start tty TTY=/dev/tty3
    initctl start tty TTY=/dev/tty4
    initctl start tty TTY=/dev/tty5
    initctl start tty TTY=/dev/tty6
end script
EOF

	# Ensure we have log directory
	mkdir -p /var/log/liveq

	# Install required python dependencies
	easy_install sleekxmpp pylzma
	rpm -y install numpy

	# Register crontab job
	crontab -l | (cat;echo "* * * * * ${AGENT_CHECK_BIN}") | crontab

	# We are now initialized
	touch /var/vas-initialized.flag

fi
