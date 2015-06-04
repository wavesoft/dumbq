# DumbQ - Based Agent

This init script will start a DumbQ-Based multi-agent VM. 

## Configuration

This bootstrap will fetch the DumbQ configuration from CVMFS, as specified in the  `/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq/server/default.conf` file.

It will ensure the following:

 1. That only consoles 1-2 are in use for log-in
 2. That a swap file of 1Gb exists and is activated
 3. The machine reboots evert 24h (to apply hotfixes)
 4. The `dumbq-agent` process will remain alive


