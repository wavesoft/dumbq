
# DumbQ Client

This is the client-side script of the DumbQ Scheduler. This script takes care of starting one or more projects in isolated containers, exposing the required metadata to end-users. 

If you want to create a dedicated VM that uses the DumbQ Scheduler to run any kind of jobs, have a look on the `bootstraps/dumbq-agent` bootstrap.

## Usage

The DumbQ Client has the following command-line syntax:

```
 dumbq-client [-c|--config <config>] [-t|--tty <base_tty>] [-p|--pref <source>]
              [-S|--share <guest_dir>] [-w|--webdir <htdocs>]
              [-b|--bind <path>[=<guest_path>]] [-m|--meta <file>[=<guest_path>]]
```

<table>
    <tr>
        <th>Flag</th>
        <th>Default</th>
        <th>Value</th>
    </tr>
    <tr>
        <td><code>-c</code>, <code>--config</code></td>
        <td>/cvmfs/sft.cern.ch/lcg/external/experimental/dumbq/server/default.conf</td>
        <td>Change the default path to the DumbQ scheduler configuration script.</td>
    </tr>
    <tr>
        <td><code>-t</code>, <code>--tty</code></td>
        <td>(None)</td>
        <td>Specify the tty number (ex. '2' for /dev/tty2) to use for displaying the project console. If more than one projects are started, the next ttys will be used.</td>
    </tr>
    <tr>
        <td><code>-p</code>, <code>--pref</code></td>
        <td>/var/lib/dumbq/preference.conf</td>
        <td>Specify the full path to the user-side preference override configuration. This file can be used in order to change the quotes allocated to the projects from the user's point of view.</td>
    </tr>
    <tr>
        <td><code>-s</code>, <code>--share</code></td>
        <td>/var/www/html=var/www/html</td>
        <td>Share that directory between the host and per-guest. This means that for every guest, a sub-directory called <code>inst-[uuid]</code> will be created in the host folder, bind-mounted to the guest directory.</td>
    </tr>
    <tr>
        <td><code>-w</code>, <code>--webdir</code></td>
        <td>/var/www/html</td>
        <td>The directory where to keep the <code>machine.json</code> and <code>index.json</code> files that expose the current state of the scheduler.</td>
    </tr>
    <tr>
        <td><code>-b</code>, <code>--bind</code></td>
        <td>(None)</td>
        <td>Specify one or more directories to blindly share between all guests. This means that no sub-directory will be created in the host folder, rather the same host folder will be shared with one or more guests.</td>
    </tr>
    <tr>
        <td><code>-m</code>, <code>--meta</code></td>
        <td>/var/lib/dumbq-meta</td>
        <td>Specify the metadata file to be shared between host and guest.</td>
    </tr>
</table>
