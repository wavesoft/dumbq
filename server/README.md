
# DumbQ Server-Side

As you might have figured out, there is no server logic in the DumbQ Scheduler. The only server-side file is a static configuration that points to the appropriate bootstrap files.

## Configuration File

The ONLY thing you need on the server is a text file served by a webserver in the following syntax:

    # Comments start with '#'
    # Each line defines a project in the following way:
    #  <project> : <start chance %> : <cvmfs>[,<cvmfs>...] : <bootstrap>
    #
    # Example:
    test-app:80:sft.cern.ch:sft.cern.ch/lcg/experimental/test-app-bootstrap.sh

Each colon-seprated parameter has the following meaning:

 * `<project>` : A short name for the project
 * `<start chance %>` : The chance this project has to be selected (0 = never, 100 = always)
 * `<cvmfs>[,<cvmfs>...]` : A  comma-separated list of cvmfs repositories this project requires to be mounted
 * `<bootstrap>` : A bootstrap application to be executed within the container. Whatever you enter in this field is *already* prefixed with `/cvmfs/`. Therefore `sft.cern.ch/lcg/experimental/test.sh` will be translated to `/cvmfs/sft.cern.ch/lcg/experimental/test.sh`.

The benefit from using this script instead of a proper job queue is that you can have **any** kind of job queue within the container, therefore allowing diverse projects to share the same resources.

_Note: Something to keep in mind is that the chances of all the projects should sum up to 100%._
