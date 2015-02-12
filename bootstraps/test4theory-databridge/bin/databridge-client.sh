#!/bin/bash

DB_URL="https://t4t-data-bridge.cern.ch"
DB_QUEUE_URL="${DB_URL}/boinc-client/get-job.cgi"
DB_INPUT_URL="${DB_URL}/myfed/t4t-boinc/input"
DB_OUTPUT_URL="${DB_URL}/myfed/t4t-boinc/output"

BOINC_USER="$1"
BOINC_AUTHENTICATOR="$2"

[ -z "$BOINC_USER" ] && echo "ERROR: Please specify the BOINC ID of the user!" && exit 2
[ -z "$BOINC_AUTHENTICATOR" ] && echo "ERROR: Please specify the BOINC Authenticator of the user!" && exit 2

function get_jobfile {
        local JOBDIR=$1

        # Get a job ID from the queue
        local JOB_ID=$(curl -u "${BOINC_USER}:${BOINC_AUTHENTICATOR}" -k -s "${DB_QUEUE_URL}" 2>/dev/null)
        # If queue is not empty, return
        [ -z "$JOB_ID" ] && return 1

        # Download job file
        local JOB_FILE="${JOBDIR}/job.sh"
        curl -o ${JOB_FILE} -u "${BOINC_USER}:${BOINC_AUTHENTICATOR}" -k -L -s "${DB_INPUT_URL}/${JOB_ID}" 2>/dev/null
        [ $? -ne 0 ] && return 1

        # Got file
        echo $JOB_ID
        return 0
}

function upload_jobdir {
        local JOBDIR=$1
        local JOB_ID=$2
        local USER_DATA=$3

        # Archive job directory
        local ARCHIVE_FILE="$(mktemp -u).tgz"
        ( cd ${JOBDIR}; tar -zcf ${ARCHIVE_FILE} ./* )

        # Upload archive directory
        curl -X PUT --upload "${ARCHIVE_FILE}" -u "${BOINC_USER}:${BOINC_AUTHENTICATOR}" -k -L -s "${DB_OUTPUT_URL}/${JOB_ID}.tgz?userdata=${USER_DATA}" 2>/dev/null

        # Remove archive file
        rm "${ARCHIVE_FILE}"
}

function cleanup {
        # Remove directory
        [ -d ${WORKDIR} -a ${#WORKDIR} -gt 1 ] && rm -rf ${WORKDIR}
        # Exit
        exit 0
}

# Trap cleanup
trap cleanup SIGINT

# Main program loop
while true; do

        # Create a temporary directory for the project
        WORKDIR=$(mktemp -d)

        # Download job file
        JOB_ID=""
        echo "INFO: Fetching next job in queue"
        while [ -z "$JOB_ID" ]; do
                JOB_ID=$(get_jobfile "${WORKDIR}")
                if [ -z "$JOB_ID" ]; then
                        echo "INFO: Queue is empty. Waiting 1 min before checking again"
                        sleep 60
                fi
        done

        # Run job
        echo "INFO: Starting job ${JOB_ID}"
        ( cd "${WORKDIR}"; chmod +x job.sh; exec ./job.sh ) >${WORKDIR}/job.stdout 2>${WORKDIR}/job.stderr

        # Get exit code
        EXIT_CODE=$?
        echo "exitcode=${EXIT_CODE}" >> ${WORKDIR}/jobdata

        # Upload results
        echo "INFO: Uploading results"
        upload_jobdir ${WORKDIR} ${JOB_ID} "exitcode=$EXIT_CODE"

        # Cleanup
        echo "INFO: Cleaning-up workdir"
        rm -rf "${WORKDIR}"

        # Sleep a bit
        sleep 10

done
