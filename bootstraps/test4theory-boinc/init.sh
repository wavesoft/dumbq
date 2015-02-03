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
BOOTSTRAP_DIR="/cvmfs/sft.cern.ch/lcg/external/dumbq/bootstraps/${BOOTSTRAP_NAME}"
T4T_WEBAPP_TGZ="/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/share/t4t-webapp.tgz"
DUMBQ_LOG_BIN="/cvmfs/sft.cern.ch/lcg/external/dumbq/bin/dumbq-log"

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

  #if [ "$BOINC_USERID" != "$USER_ID" ]; then
  #  echo "Error: BOINC User ID from the wrapper does not match."
    echo "Got from wrapper: $BOINC_USERID"
    echo "Got from server: $USER_ID"
    echo "Server response: $USER_DATA"
    USER_ID="s-$USER_ID"
  #fi
}

# 1) Start required services
# ----------------------------------

# Start cron
service cron start

# 2) Install the test4theory app
# ----------------------------------

# Unzip the t4t-webapp
T4T_WEBAPP_DST=/var/www/html
/bin/tar zxvf $T4T_WEBAPP_TGZ -C $T4T_WEBAPP_DST > /dev/null 2>&1

# 3) Install required binaries
# ----------------------------------

# Copy the config and debug info scripts to /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-debug-info /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-config /usr/bin
cp ${BOOTSTRAP_DIR}/bin/readFloppy.pl /usr/bin
chmod a+rx /usr/bin/copilot-debug-info
chmod a+rx /usr/bin/copilot-config
chmod a+rx /usr/bin/readFloppy.pl

# 4) Cache and prepare Jabber ID
# ----------------------------------

# BOINC User ID Cache
BOINC_USER_ID_CACHE="/var/lib/copilot-agent-uuid-saved.$BOOTSTRAP_VER"
if [ -f $BOINC_USER_ID_CACHE ]; then
  . $BOINC_USER_ID_CACHE # 2>&1 >/dev/null
fi

# If we don't have a cached jabber ID, calculate one
if [ -z "$AGENT_JABBER_ID" ]; then

  # BOINC Config
  BOINC_SERVER=https://lhcathome2.cern.ch
  BOINC_PROJECT=test4theory

  # Count number of CPUS
  N_CPU=$(cat /proc/cpuinfo |grep processor|wc -l)

  # Read UserID from floppy
  USER_ID=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl | grep "^USER_ID" | awk -F'=' '{print $2}')

  # If we have a USERID field (challenge mode), use the one provided
  if [ ! -z "${USER_ID}" ]; then

    # Use specified UserID
    USER_ID="g-${USER_ID}"

  else

    # Otherwise extract BOINC_AUTHENTICATOR and BOINC_USER_ID
    BOINC_AUTHENTICATOR=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl| grep BOINC_AUTHENTICATOR | awk '{split ($0, auth, "="); print auth[2]}')
    BOINC_USERID=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl| grep BOINC_USERID | awk '{split ($0, auth, "="); print auth[2]}')

    # If we have a BOINC authenticator, get USER_ID from there
    if [ -n $BOINC_AUTHENTICATOR ]; then
      USER_DATA=$(curl $BOINC_SERVER/$BOINC_PROJECT'/am_get_info.php?account_key='$BOINC_AUTHENTICATOR -k -s)
    fi
    get_user_id

  fi

  # Setup jabber ID and place on cache
  export AGENT_JABBER_ID="agent_""$USER_ID"_"$N_CPU"_"$BOOTSTRAP_VER"_"$(uuidgen)"_"$JID_VER"
  echo "export AGENT_JABBER_ID=$AGENT_JABBER_ID" > $BOINC_USER_ID_CACHE
  chmod -w $BOINC_USER_ID_CACHE

fi

# 5) Prepare user interface
# ----------------------------------

cp $BOINC_USER_ID_CACHE /var/www/html/logs
cp /var/log/start-perl-copilot.log /var/www/html/logs

# 6) Start multicolored log
# ----------------------------------

${DUMBQ_LOG_BIN} \
  /var/log/start-perl-copilot.log[green] \
  /var/log/messages[red] \
  /var/log/copilot-config[red] \
  > /dev/tty1

# 7) Start Co-Pilot from CVMFS
# ----------------------------------

# Create the ~/copilot-user-data file
/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-config --user-data 2>&1 >/dev/null 

# Select configuration and start co-pilot
export COPILOT_CONFIG=/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/etc/copilot
/bin/env PATH=$PATH LANG=C  perl -I /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/lib/perl5/site_perl/5.8.8/ /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-agent

