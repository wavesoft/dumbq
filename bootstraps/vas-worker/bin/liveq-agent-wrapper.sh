#!/bin/bash

# LiveQ CVMFS Directory
CVMFS_VAS_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/virtual-atom-smasher"
CVMFS_LIVEQ_DIR="${CVMFS_VAS_DIR}/liveq"

# CVMFS Binaries
AGENT_BIN="${CVMFS_LIVEQ_DIR}/liveq-agent/liveq-agent.py"
AGENT_CONFIG="/etc/liveq/liveq-agent.conf"

# Make sure we have log directory
[ ! -d /var/log/liveq ] && mkdir -p /var/log/liveq

# Log everything on the logfiles
exec >>/var/log/liveq/agent.err 2>>/var/log/liveq/agent.log

# Bootstrap
python ${AGENT_BIN} ${AGENT_CONFIG}
