#!/bin/bash
#
# CMS Job Execution For Webfest
# (C) Copyright 2015, Jorge Vicente Cantero, Ioannis Charalampidis, PH/SFT, CERN
#

# Configuration parameters
BOOTSTRAP_NAME="cms-webfest"
BOOTSTRAP_VER="1"

# Paths for executables
DUMBQ_DIR="/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq"
BOOTSTRAP_DIR="${DUMBQ_DIR}/bootstraps/${BOOTSTRAP_NAME}"
DUMBQ_UTILS_DIR="${DUMBQ_DIR}/client/utils"
DUMBQ_LOGCAT_BIN="${DUMBQ_UTILS_DIR}/dumbq-logcat"
DUMBQ_METRICS_BIN="${DUMBQ_UTILS_DIR}/dumbq-metrics"

# CMS Paths
CMS_PUBLIC_WWW_TGZ="/cvmfs/sft.cern.ch/lcg/external/experimental/t4t-webapp/t4t-webapp.tgz"
CMS_HOME="/cvmfs/cms.cern.ch/CMS@Home"
CMS_AGENT="${CMS_HOME}/agent"
CMS_WEBAPP="${CMS_HOME}/WebApp"
CMS_PUBLIC_WWW="${CMS_PUBLIC_WWW}"
CMS_PUBLIC_WWW_LOGDIR=${CMS_PUBLIC_WWW}/logs
CMS_PUBLIC_WWW_JOBDIR=${CMS_PUBLIC_WWW}/job
BOINC_PATH="/home/boinc/"
CMS_PATH="${BOINC_PATH}/CMSRun/"

# Log files names
STDOUT="stdout"
STDERR="stderr"
CMS_STDOUT_LOG="cmsRun-${STDOUT}.log"
CMS_STDERR_LOG="cmsRun-${STDERR}.log"
CMS_ANALYSIS_LOG="CMSRunAnalysisLog.txt"
BOINC_STDOUT_LOG="CMSJobAgent-${STDOUT}.log"
BOINC_STDERR_LOG="CMSJobAgent-${STDERR}.log"

# Log files
BOINC_STDOUT="${BOINC_PATH}/${STDOUT}"
BOINC_STDERR="${BOINC_PATH}/${STDERR}"
CMS_STDOUT="${CMS_PATH}/${CMS_STDOUT_LOG}"
CMS_STDERR="${CMS_PATH}/${CMS_STDERR_LOG}"


# 0) Redirect and start logcat 
# -----------------------------

# Create missing directories
mkdir -p ${CMS_PUBLIC_WWW_LOGDIR}
mkdir -p ${CMS_PUBLIC_WWW_JOBDIR}

(
   # Start logcat with all the interesting log files
   # This process will write everything in the public log files:
   #   - bootstrap-out.log
   #   - bootstrap-err.log
  ${DUMBQ_LOGCAT_BIN} \
    --prefix="[%d/%m/%y %H:%M:%S] " \
    ${CMS_PUBLIC_WWW_LOGDIR}/bootstrap-out[green] \
    ${CMS_PUBLIC_WWW_LOGDIR}/bootstrap-err.log[magenta] \
    ${BOINC_STDOUT}[green] \
    ${BOINC_STDERR}[red] \
    ${CMS_STDOUT}[green] \
    ${CMS_STDERR}[red] \
	${CMS_PATH}/${CMS_ANALYSIS_LOG}[white] \
	# There is only out, not err 
	"/tmp/mcplots-job.out"[cyan] 
)&

# Redirect stdout/err
exec 2>${CMS_PUBLIC_WWW_LOGDIR}/bootstrap-err.log >${CMS_PUBLIC_WWW_LOGDIR}/bootstrap-out.log

# 1) Installing CMS@Home app
# --------------------------

# Ensure the floppy drive is readable for a user
touch /dev/fd0
chmod +r /dev/fd0

# Writing BOINC credentials
echo "BOINC_USERID=35331" > /dev/fd0
echo "BOINC_AUTHENTICATOR=4c2ce9458a4750eafd589c9b4269fc2b" > /dev/fd0

# Copy certificates locally and install the BOINC CA
rm -f /etc/grid-security/certificates
cp -r /cvmfs/grid.cern.ch/etc/grid-security/certificates /etc/grid-security/
cp -r ${CMS_AGENT}/boinc-ca/* /etc/grid-security/certificates/

# Plugin globus commands
ln -sf /cvmfs/grid.cern.ch/glite/globus/bin/grid-proxy-init /usr/bin/
ln -sf /cvmfs/grid.cern.ch/glite/globus/bin/grid-proxy-info /usr/bin/

# Temp fix for contextulization issue
echo "export CMS_LOCAL_SITE=/etc/cms/SITECONF/BOINC" >> /etc/cvmfs/config.d/cms.cern.ch.local
cvmfs_config reload

# Manual SITECONF
mkdir -p /etc/cms/SITECONF/BOINC/{JobConfig,PhEDEx}
ln -sf /etc/cms/SITECONF/BOINC /etc/cms/SITECONF/local
ln -sf ${CMS_AGENT}/site-local-config.xml  /etc/cms/SITECONF/BOINC/JobConfig/site-local-config.xml
ln -sf ${CMS_AGENT}/storage.xml /etc/cms/SITECONF/BOINC/JobConfig/storage.xml

# Add index to the WWW public folder
cat ${CMS_WEBAPP}/index.html > ${CMS_PUBLIC_WWW}/index.html

# Put the bootlog to the Web logs
cat /var/log/boot.log > ${CMS_PUBLIC_WWW_LOGDIR}/boot.log

# Start the Web server (ported from CMS script)
# service httpd start -> It should not work. It's not tested, though


# 2) Add the T4T application
# --------------------------

# Unzip the t4t-webapp
/bin/tar zxvf $CMS_PUBLIC_WWW_TGZ -C $CMS_PUBLIC_WWW > /dev/null 2>&1


# 3) Start metrics monitor and CMS-Agent
# --------------------------------------

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

# Setup the CMS-Agent cron job
su - boinc -c "${CMS_AGENT}/CMSJobAgent.sh"
