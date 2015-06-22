
# Bootstraps for various projects

This directory contains the bootstrap scripts for the various dumbq projects. All of them are just an `init.sh` script that is executed upon creation of the worker environment.

## Current projects

<table>
    <tr>
        <th>Project</th>
        <th>Status</th>
        <th>Description</th>
    </tr>
    <tr>
        <td>autumn-challenge</td>
        <td><strong>Active</strong></td>
        <td>A Test4Theory version for the CERN Autumn/Summer challenge that uses DataBridge as a job queue.</td>
    </tr>
    <tr>
        <td>cern60-challenge</td>
        <td>Deprecated</td>
        <td>A Test4Theory version for the CERN 60 challenge that uses Co-Pilot as a job queue. It doesn't use the default MCPlots queue, but rather the VAS queue for populating the interpolation database.</td>
    </tr>
    <tr>
        <td>dumbq-agent</td>
        <td><strong>Active</strong></td>
        <td>A bootstrap for a dedicated VM that runs the DumbQ Client.</td>
    </tr>
    <tr>
        <td>test4theory-boinc</td>
        <td>Deprecated</td>
        <td>The production version of Test4Theory BOINC project, that uses the IT Co-Pilot infrastructure.</td>
    </tr>
    <tr>
        <td>test4theory-databridge</td>
        <td>In-Development</td>
        <td>A Beta version of the production Test4Theory BOINC project that uses DataBridge as the queue.</td>
    </tr>
    <tr>
        <td>vas-worker</td>
        <td>In-Development</td>
        <td>A Virtual-Atom-Smasher computing node. Upon starting it joins the global VAS queue.</td>
    </tr>
</table>

## Project Environment

The `init.sh` script of every project will be executed in a new container with only the network initialised. No services are started (such as `crond`). You will need to explicitly start the services your project needs.

### CVMFS

If your project uses one or more `cvmfs` mounts, you will need to define them in the server-side configuration script. It's not possible to mount any CVMFS directory inside the guest container after it's started!

### Environment Variables

The `dumbq-client` script defines some environment variables before starting the project's bootstrap. This is used for identifying the environment and/or provide additional run-time information.

These are:

<table>
    <tr>
        <th>Variable</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><code>DUMBQ_NAME</code></td>
        <td>The name of the project this container belongs to.</td>
    </tr>
    <tr>
        <td><code>DUMBQ_UUID</code></td>
        <td>The unique ID of the container instance. This is different for every instance.</td>
    </tr>
    <tr>
        <td><code>DUMBQ_VMID</code></td>
        <td>The unique ID of the host VM. This remains the same for every instance and is also accessible via the <code>index.json</code> metadata file.</td>
    </tr>
    <tr>
        <td><code>DUMBQ_METAFILE</code></td>
        <td>The full path to a metadata file shared with all containers. This metadata usually contains global run-time information.</td>
    </tr>
</table>

### Run-time Metadata

Each project __SHOULD__ expose some run-time information which is used by the front-ends to inform the users. This metadata file is expected to be located at `/var/www/html/metrics.json` and can be easily modified using the `dumbq-metrics` script.

### Utilities

There is a set of utilities provided along with dumbq in order to assist you with various dumbq-specific operations. 

Have a look at the README file in `client/utils` folder.

