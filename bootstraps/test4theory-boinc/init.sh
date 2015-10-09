#!/bin/bash
#
# Test4Theory Container Init Script
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# Configuration parameters
BOOTSTRAP_NAME="test4theory-boinc"
BOOTSTRAP_VER="8"
JID_VER="-g"

# Less important parameters
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/${BOOTSTRAP_NAME}"
DUMBQ_UTILS_DIR="${DUMBQ_DIR}/client/utils"
DUMBQ_LOGCAT_BIN="${DUMBQ_UTILS_DIR}/dumbq-logcat"
DUMBQ_METRICS_BIN="${DUMBQ_UTILS_DIR}/dumbq-metrics"

# Test4Theory WebApp
T4T_WEBAPP_TGZ="/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/share/t4t-webapp.tgz"
T4T_WEBAPP_DST="/var/www/html"

#
# Parses the USER_DATA value and retrieves the USER_ID.
# Compares the USER_ID with BOINC_ID to see it matches.
#
# In case of a problem sets the value of USER_ID to 'U'
#
###########################################################
get_user_id()
###########################################################
{
  if [[ $USER_DATA =~ '<am_get_info_reply>.*<success/>.*<id>(.*)</id>.*</am_get_info_reply>' ]]; then
    [ $? -eq 0 ] && USER_ID=${BASH_REMATCH[1]}
  fi

  #if [ "$DUMBQ_BOINC_ID" != "$USER_ID" ]; then
  #  echo "Error: BOINC User ID from the wrapper does not match."
    echo "Got from wrapper: $DUMBQ_BOINC_ID"
    echo "Got from server: $USER_ID"
    echo "Server response: $USER_DATA"
    USER_ID="s-$USER_ID"
  #fi
}

# 0) Redirect and start logcat 
# ----------------------------------

(
  # Start logcat with all the interesting log files
  ${DUMBQ_LOGCAT_BIN} \
    --prefix="[%d/%m/%y %H:%M:%S] " \
    /var/www/html/logs/bootstrap-out.log[cyan] \
    /var/www/html/logs/bootstrap-err.log[magenta] \
    /var/www/html/logs/copilot-agent.log[cyan] \
    /tmp/mcplots-job.out[green] \
    /tmp/mcplots-job.err[red]
)&

# Redirect stdout/err
exec 2>${$T4T_WEBAPP_DST}/logs/bootstrap-err.log >${$T4T_WEBAPP_DST}/logs/bootstrap-out.log

# 1) Start required services
# ----------------------------------

# Start cron
service cron start

# 2) Install the test4theory app
# ----------------------------------

# Unzip the t4t-webapp
/bin/tar zxvf $T4T_WEBAPP_TGZ -C $T4T_WEBAPP_DST > /dev/null 2>&1

# Create missing directories
mkdir ${T4T_WEBAPP_DST}/logs
mkdir ${T4T_WEBAPP_DST}/job
mkdir ${T4T_WEBAPP_DST}/copilot

# 3) Install required binaries
# ----------------------------------

# Copy the config and debug info scripts to /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-debug-info /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-config /usr/bin
chmod a+rx /usr/bin/copilot-debug-info
chmod a+rx /usr/bin/copilot-config

# 4) Cache and prepare Jabber ID
# ----------------------------------

# Log dumb metadata for debug purposes
if [ -f /var/lib/dumbq-meta ]; then
  echo "--[ Global Metadata ]-------------------------"
  cat /var/lib/dumbq-meta
  echo "----------------------------------------------"
fi

# BOINC User ID Cache
BOINC_USER_ID_CACHE="/var/lib/copilot-agent-uuid-saved.$BOOTSTRAP_VER"
if [ -f $BOINC_USER_ID_CACHE ]; then
  . $BOINC_USER_ID_CACHE # 2>&1 >/dev/null
fi

# If we don't have a cached jabber ID, calculate one
if [ -z "$AGENT_JABBER_ID" ]; then

  # BOINC Config
  BOINC_SERVER=https://lhcathome2.cern.ch
  BOINC_PROJECT=vLHCathome

  # Count number of CPUS
  N_CPU=$(cat /proc/cpuinfo |grep processor|wc -l)

  # Read UserID from DumbQ environment
  USER_ID="${DUMBQ_USER_ID}"

  # If we have a USERID field (challenge mode), use the one provided
  if [ ! -z "${USER_ID}" ]; then

    # Use specified UserID
    USER_ID="g-${USER_ID}"

    # Log
    echo "INFO: Challenge mode using ID: ${USER_ID}"

  else

    # Check for BOINC_AUTHENTICATOR from the shared metadata
    BOINC_AUTHENTICATOR=$(cat /var/lib/dumbq-meta | grep BOINC_AUTHENTICATOR)

    # If we have a BOINC authenticator, get USER_ID from there
    if [ -n $BOINC_AUTHENTICATOR ]; then
      USER_DATA=$(curl $BOINC_SERVER/$BOINC_PROJECT'/am_get_info.php?account_key='$BOINC_AUTHENTICATOR -k -s)
    fi
    get_user_id

    # Log
    echo "INFO: BOINC mode using ID: ${USER_ID}"

  fi

  # Setup jabber ID and place on cache
  export AGENT_JABBER_ID="agent_""$USER_ID"_"$N_CPU"_"$BOOTSTRAP_VER"_"$(uuidgen)"_"$JID_VER"
  echo "export AGENT_JABBER_ID=$AGENT_JABBER_ID" > $BOINC_USER_ID_CACHE
  chmod -w $BOINC_USER_ID_CACHE

  # Log
  echo "INFO: Using Jabber ID ${AGENT_JABBER_ID}"

fi

# 5) Prepare user interface
# ----------------------------------

cp $BOINC_USER_ID_CACHE /var/www/html/logs
cp /var/log/start-perl-copilot.log /var/www/html/logs

# 6) Prepare DumbQ-Compatible environment
# ----------------------------------

# Start the log-monitoring agent that will update the dumbq metrics file
python ${BOOTSTRAP_DIR}/bin/mcprod-monitor&

# Include DUMBQ binary dir in environment
export PATH="${PATH}:${DUMBQ_UTILS_DIR}"

# Set dumbq status in order to activate instance
${DUMBQ_METRICS_BIN} --set status=initializing

# 7) Start Co-Pilot from CVMFS
# ----------------------------------

# Create the ~/copilot-user-data file
/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-config --user-data 2>&1 >/dev/null 

# Select configuration and start co-pilot
export COPILOT_CONFIG=${BOOTSTRAP_DIR}/etc/copilot
/bin/env PATH=$PATH LANG=C  perl -I /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/lib/perl5/site_perl/5.8.8/ /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-agent

