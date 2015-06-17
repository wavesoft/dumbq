#!/bin/bash
#
# Test4Theory Container Init Script
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# Configuration parameters
BOOTSTRAP_NAME="test4theory-databridge"

# Less important parameters
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
DUMBQ_LOGCAT="${DUMBQ_DIR}/client/utils/dumbq-logcat"
BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/${BOOTSTRAP_NAME}"

# Test4Theory WebApp
T4T_WEBAPP_TGZ="/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/share/t4t-webapp.tgz"
T4T_WEBAPP_DST="/var/www/html"

# Create missing directories
mkdir ${T4T_WEBAPP_DST}/logs
mkdir ${T4T_WEBAPP_DST}/job

# 0) Redirect and start logcat 
# ----------------------------------

(
  # Start logcat with all the interesting log files
  ${DUMBQ_LOGCAT} \
    --prefix="[%d/%m/%y %H:%M:%S] " \
    ${T4T_WEBAPP_DST}/logs/bootstrap-out.log[cyan] \
    ${T4T_WEBAPP_DST}/logs/bootstrap-err.log[magenta] \
    ${T4T_WEBAPP_DST}/logs/copilot-agent.log[cyan] \
    ${T4T_WEBAPP_DST}/logs/copilot-agent-err.log[cyan] \
    ${T4T_WEBAPP_DST}/job/out[green] \
    ${T4T_WEBAPP_DST}/job/err[red]
)&

# Redirect stdout/err
exec 2>${T4T_WEBAPP_DST}/logs/bootstrap-err.log >${T4T_WEBAPP_DST}/logs/bootstrap-out.log

# 1) Install the test4theory app
# ----------------------------------

# Unzip the t4t-webapp
/bin/tar zxvf $T4T_WEBAPP_TGZ -C $T4T_WEBAPP_DST > /dev/null 2>&1

# 2) Install required binaries
# ----------------------------------

# Copy the config and debug info scripts to /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-config /usr/bin
chmod a+rx /usr/bin/copilot-config

# 3) Start agent
# ----------------------------------

# Start databridge client
${BOOTSTRAP_DIR}/bin/databridge-client.sh "${DUMBQ_BOINC_ID}" "${DUMBQ_BOINC_AUTHENTICATOR}" \
	>${T4T_WEBAPP_DST}/logs/copilot-agent.log 2>${T4T_WEBAPP_DST}/logs/copilot-agent-err.log
