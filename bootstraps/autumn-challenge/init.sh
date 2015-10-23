#!/bin/bash
#
# Test4Theory For Autumn Challenge Bootstrap
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# Configuration parameters
BOOTSTRAP_NAME="autumn-challenge"
BOOTSTRAP_VER="1"

# Less important parameters
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/${BOOTSTRAP_NAME}"
DUMBQ_UTILS_DIR="${DUMBQ_DIR}/client/utils"
DUMBQ_LOGCAT_BIN="${DUMBQ_UTILS_DIR}/dumbq-logcat"
DUMBQ_METRICS_BIN="${DUMBQ_UTILS_DIR}/dumbq-metrics"

# Databridge client bin
DATABRIDGE_AGENT_BIN="/cvmfs/sft.cern.ch/lcg/external/experimental/databridge-interface/client/bin/databridge-agent"
DATABRIDGE_DOMAIN="t4t-data-bridge.cern.ch"

# Test4Theory WebApp
T4T_WEBAPP_TGZ="/cvmfs/sft.cern.ch/lcg/external/experimental/t4t-webapp/t4t-webapp.tgz"
T4T_WEBAPP_DST="/var/www/html"
T4T_WEBAPP_LOGDIR=${T4T_WEBAPP_DST}/logs

# 0) Redirect and start logcat 
# ----------------------------------

# Create missing directories
mkdir -p ${T4T_WEBAPP_DST}/logs
mkdir -p ${T4T_WEBAPP_DST}/job

(
  # Start logcat with all the interesting log files
  ${DUMBQ_LOGCAT_BIN} \
    --prefix="[%d/%m/%y %H:%M:%S] " \
    ${T4T_WEBAPP_LOGDIR}/bootstrap-out.log[cyan] \
    ${T4T_WEBAPP_LOGDIR}/bootstrap-err.log[magenta] \
    ${T4T_WEBAPP_LOGDIR}/databridge-client.log[yellow] \
    /tmp/mcplots-job.out[green] \
    /tmp/mcplots-job.err[red]
)&

# Redirect stdout/err
exec 2>${T4T_WEBAPP_LOGDIR}/bootstrap-err.log >${T4T_WEBAPP_LOGDIR}/bootstrap-out.log

# 1) Install the test4theory app
# ----------------------------------

# Unzip the t4t-webapp
/bin/tar zxvf $T4T_WEBAPP_TGZ -C $T4T_WEBAPP_DST > /dev/null 2>&1

# 2) Patch binaries queried by jobs
# ----------------------------------

# Copy the config and debug info scripts to /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-debug-info /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-config /usr/bin
chmod a+rx /usr/bin/copilot-debug-info
chmod a+rx /usr/bin/copilot-config

# 3) Hack to use gateway as our DNS
# ----------------------------------

GW_IP=$(cat /etc/sysconfig/network-scripts/ifcfg-eth0 | grep GATEWAY= | awk -F'=' '{print $2}')
echo "nameserver ${GW_IP}" > /etc/resolv.conf

# 4) Start databridge-client
# ----------------------------------

# Log dumb metadata for debug purposes
if [ -f /var/lib/dumbq-meta ]; then
	echo "--[ Global Metadata ]-------------------------"
	cat /var/lib/dumbq-meta
	echo "----------------------------------------------"
fi

# Start the log-monitoring agent that will update the dumbq metrics file
python ${BOOTSTRAP_DIR}/bin/mcprod-monitor&

# Include DUMBQ binary dir in environment
export PATH="${PATH}:${DUMBQ_UTILS_DIR}"

# Check if we should add debug arguments to the databridge client
DEBUG_ARGS=""
[ -f /var/lib/dumbq-meta ] && [ $(cat /var/lib/dumbq-meta | grep DEBUG= | awk -F'=' '{print $2}' | grep -c 'databridge') -eq 1 ] && DEBUG_ARGS="--debug"

# Start databridge agent
echo "" > ${T4T_WEBAPP_LOGDIR}/databridge-client.log
${DATABRIDGE_AGENT_BIN} "35331" "4c2ce9458a4750eafd589c9b4269fc2b" "${DATABRIDGE_DOMAIN}" ${DEBUG_ARGS} 2>>${T4T_WEBAPP_LOGDIR}/databridge-client.log >>${T4T_WEBAPP_LOGDIR}/databridge-client.log
