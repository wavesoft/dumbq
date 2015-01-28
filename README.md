# DumbQ

A very simple service that starts multiple project agents inside a micro-cernvm distribution in isolated linux containers.

# Server-Side

The ONLY thing you need on the server is a text file served by a webserver in the following syntax:

    # Comments start with '#'
    # Each line defines a project in the following way:
    #  <project> : <start chance %> : <cvmfs>[,<cvmfs>...] : <bootstrap>
    #
    # Example:
    test-app:80:sft.cern.ch:sft.cern.ch/lcg/experimental/test-app-bootstrap.sh

The benefit from using this script instead of a proper job queue is that you can have **any** kind of job queue within the container, therefore allowing diverse projects to share the same resources.

_Note: Something to keep in mind is that the chances of all the projects should sum up to 100%._

# Client-Side

On the client side you have only the `dumbq-client.sh` script that should be run at the moment you want to start the containers (usually after system boot). No additional parameters are required.

The script will remain alive and monitor the status of the containers and if a container goes down it will try to re-start it (or the next available).

# Requirements

This script requires the following utilities to exist in the distribution:

 * `cernvm-fork` (available from https://github.com/wavesoft/cernvm-fork)

# License

DumbQ - A very simple project scheduler

Copyright (C) 2015  Ioannis Charalampidis, PH-SFT, CERN

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
