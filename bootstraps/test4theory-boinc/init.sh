#!/bin/bash
#
# Test4Theory Container Init Script
# (C) Copyright 2015, Ioannis Charalampidis, PH/SFT, CERN
#

# Configuration parameters
BOOTSTRAP_NAME="test4theory-boinc"
BOOTSTRAP_VER="8"

# Less important parameters
BOOTSTRAP_DIR="/cvmfs/sft.cern.ch/lcg/external/dumbq/bootstraps/${BOOTSTRAP_NAME}"
T4T_WEBAPP_TGZ="/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/share/t4t-webapp.tgz"

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

VERSION="7"

# Start cron
service cron start

# Unzip the t4t-webapp
T4T_WEBAPP_DST=/var/www/html
/bin/tar zxvf $T4T_WEBAPP_TGZ -C $T4T_WEBAPP_DST > /dev/null 2>&1

# Copy the config and debug info scripts to /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-debug-info /usr/bin
cp ${BOOTSTRAP_DIR}/bin/copilot-config /usr/bin
cp ${BOOTSTRAP_DIR}/bin/readFloppy.pl /usr/bin
chmod a+rx /usr/bin/copilot-debug-info
chmod a+rx /usr/bin/copilot-config
chmod a+rx /usr/bin/readFloppy.pl

# BOINC User ID Cache
BOINC_USER_ID_CACHE="/var/lib/copilot-agent-uuid-saved.$VERSION"
if [ -f $BOINC_USER_ID_CACHE ]; then
  . $BOINC_USER_ID_CACHE # 2>&1 >/dev/null
fi

if [ -z "$AGENT_JABBER_ID" ]; then
  # BOINC Config
  BOINC_SERVER=https://lhcathome2.cern.ch
  BOINC_PROJECT=test4theory

  DEV_BOINC_SERVER=https://boinc-dev.cern.ch
  DEV_BOINC_PROJECT=testing

  N_CPU=$(cat /proc/cpuinfo |grep processor|wc -l)
  REV="-g"

  USER_ID=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl | grep "^USER_ID" | awk -F'=' '{print $2}')
  if [ ! -z "${USER_ID}" ]; then

    # Use generic user ID
    USER_ID="g-${USER_ID}"

  else

    BOINC_AUTHENTICATOR=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl| grep BOINC_AUTHENTICATOR | awk '{split ($0, auth, "="); print auth[2]}')
    BOINC_USERID=$(/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/readFloppy.pl| grep BOINC_USERID | awk '{split ($0, auth, "="); print auth[2]}')

    #if [ -n "$BOINC_AUTHENTICATOR" -a -n "$BOINC_USERID" ]; then
    if [ -n $BOINC_AUTHENTICATOR ]; then
      USER_DATA=$(curl $BOINC_SERVER/$BOINC_PROJECT'/am_get_info.php?account_key='$BOINC_AUTHENTICATOR -k -s)
    fi
    get_user_id

    # (Dev server is not working)
    #if [ "$USER_ID" == "s-" ] ; then
    #  # Try the dev server
    #  if [ -n $BOINC_AUTHENTICATOR ]; then
    #    USER_DATA=$(curl $DEV_BOINC_SERVER/$DEV_BOINC_PROJECT'/am_get_info.php?account_key='$BOINC_AUTHENTICATOR -k -s)
    #  fi
    #  USER_ID=""
    #  get_user_id
    #
    #  #indicate that we tried the dev server
    #  USER_ID="d-""$USER_ID"
    #  BOINC_USERID="d-""$BOINC_USERID"
    #fi

  fi

  export AGENT_JABBER_ID="agent_""$USER_ID"_"$N_CPU"_"$VERSION"_"$(uuidgen)"_"$REV"
  echo "export AGENT_JABBER_ID=$AGENT_JABBER_ID" > $BOINC_USER_ID_CACHE

  chmod -w $BOINC_USER_ID_CACHE
fi


cp $BOINC_USER_ID_CACHE /var/www/html/logs
cp /var/log/start-perl-copilot.log /var/www/html/logs

/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-config --user-data 2>&1 >/dev/null # to create the ~/copilot-user-data file

#if  [ $[ ( $RANDOM % 2 ) ] == 0 ]; then
export COPILOT_CONFIG=/cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/etc/copilot
#else
#  export COPILOT_CONFIG=/cvmfs/sft.cern.ch/lcg/external/experimental/cernvm-copilot/etc/copilot.new
#fi

/bin/env PATH=$PATH LANG=C  perl -I /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/lib/perl5/site_perl/5.8.8/ /cvmfs/sft.cern.ch/lcg/external/cernvm-copilot/bin/copilot-agent
