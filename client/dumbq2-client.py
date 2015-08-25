#!/bin/bash
#
# DumbQ 2.0 - A lightweight job scheduler
# Copyright (C) 2015-2016  Ioannis Charalampidis, Jorge Vicente Cantero, CERN

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA
#

import logging
import multiprocessing
import os
import re
import shutil
import time
import string
import json

from argparse import ArgumentParser
from subprocess import check_output, call, DEVNULL
from string import lstrip
from uuid import uuid4
from random import randint

from utils.utils import error_and_exit, ignored, create_dir_if_nonexistent


class ConsoleLogger(logging.getLoggerClass()):

    def __init__(self):
        # Initialise standard logger class
        logging.getLoggerClass().__init__("Dumbq")

    def setup(self, config, hw_info):
        """Set up the logger and show basic information."""

        # Log information about dumbq and hardware
        self.logger.info("Dumbq Client version {0} started"
                         .format(self.config["version"]))
        self.logger.info("Using configuration from {0}"
                         .format(self.config["config_source"]))
        self.logger.info("Allocating {0} slot(s), with cpu={1}, "
                         "mem={2}Kb, swap=${3}Kb"
                         .format(hw_info.number_cores,
                                 hw_info.slot_cpu,
                                 hw_info.total_memory,
                                 hw_info.total_swap))

        self.logger.info("Reserving {0} for containers"
                         .format(hw_info.reserved_ttys))


class HardwareInfo:

    def __init__(self, config):
        """Get cpu, memory and other info about host's hardware."""
        self.host_uuid = self._get_host_identifier()
        self.uuid_file = config["uuid_file"]
        self.local_cernvm_config = config["local_cernvm_config"]

        self.number_cores = multiprocessing.cpu_count()

        # Read total memory and swap from `free` in KB
        free_output = check_output(["free", "-k"]).split("\n")
        self.total_memory = self._total_value_from_row(free_output[1])
        self.total_swap = self._total_value_from_row(free_output[2])

        # Calculate slots
        self.slot_cpu = 1
        self.slot_mem = self.total_memory / self.slot_cpu
        self.slot_swap = self.total_swap / self.slot_cpu

        self.base_tty = self.config["base_tty"]

        # Calculate how many ttys need the projects
        if self.base_tty > 0:
            if hw_info.number_cores == 1:
                self.reserved_ttys = "tty" + str(self.base_tty)
            else:
                self.max_tty = self.base_tty + self.number_cores - 1
                self.reserved_ttys = ("tty[{0}-{1}]"
                                      .format(self.base_tty, self.max_tty))
        else:
            self.max_tty = self.base_tty + self.number_cores

    def _get_host_identifier(self):
        """Get UUID from CernVM/standard file or create one."""
        def uuid_from_cernvm():
            # Get value of uuid from CERNVM file
            with ignored(IOError):
                with open(self.local_cernvm_config, "r") as c:
                    for line in c.readlines():
                        if "CERNVM_UUID" in line:
                            # UUID value found
                            return line.split("=")[1]

        def uuid_from_file():
            with ignored(IOError):
                if not os.path.exists(self.uuid_file):
                    # Generate a new UUID and save it
                    new_uuid = uuid4()
                    with open(self.uuid_file, "w") as f:
                        f.write(new_uuid)

                    return str(new_uuid)
                else:
                    # Get UUID from the existing file
                    with open(self.uuid_file, "r") as f:
                        return f.readline()

        return uuid_from_cernvm() or uuid_from_file() or None

    @staticmethod
    def _total_value_from_row(row_to_parse):
        # Total value is in the second column
        return int(row_to_parse.split()[1])


class DumbqSetup:

    def __init__(self, config, hw_info, logger):
        self.logger = logger

        # Dumbq-related variables
        self.dumbq_dir = self.config["dumbq_dir"]
        self.www_dir = self.config["www_dir"]
        self.dumbq_folders = None

        # Get hardware details
        self.hw_info = hw_info

    def setup_config(self):
        # Define Dumbq folder
        extensions = ["run", "tty", "preference.conf"]
        dumbq_paths = os.path.join(self.dumbq_dir, extensions)

        # Update config with Dumbq folders
        config["dumbq_rundir"] = dumbq_paths[0]
        config["dumbq_ttydir"] = dumbq_paths[1]
        config["dumbq_preference_file"] = dumbq_paths[2]

        # Register dumbq folders for setup
        self.dumbq_folders = (
            self.dumbq_dir, dumbq_paths[0], dumbq_paths[1]
        )

    def setup_dumbq_folders(self):
        """Make sure dumbq folders exist. Otherwise, create them."""
        # Apply the function to each folder
        map(create_dir_if_nonexistent, self.dumbq_folders)

    def setup_logger(self):
        """Set up the logger and the handlers of the logs."""
        self.logger.setup(self.config, self.hw_info)

    def setup_public_www(self):
        """Create public WWW folder and make it readable."""
        create_dir_if_nonexistent(self.www_dir, mode=0555)

    def setup(self):
        """Set up all the environment.

        This is a key step and the order of the operations matter."""
        self.setup_config()
        self.setup_dumbq_folders()
        self.setup_logger()
        self.setup_public_www()


class ProjectHub:

    def __init__(self, config, feedback, logger, *args, **kwargs):
        self.logger = logger
        self.feedback = feedback

        # Default configuration sources
        self.config_source = config["config_source"]
        self.config_file = config["config_file"]
        self.config_preference = config["config_preference"]

        # Regexps to validate the content of the config files
        self.there_are_comments = re.compile("^[ \t]*#|^[ \t]*$")
        self.valid_format = re.compile("^[^:]+:[^:]+:[^:]*:.*$")
        self.escapes_from_cvmfs = re.compile("\.\.")

        # Vars needed by setup()
        self.config_content = None
        self.shared_metadata_file = None
        self.guest_metadata_file = None

    def fetch_config_file(self):
        """Get the content of the config local file."""
        # Assume config_source is local
        # TODO: Extend to fetch from SSL and FTPs
        self.config_file = self.config_source
        self.config_content = self._read_config_file(self.config_file)
        valid_file = True

        # Check if the configuration file is valid
        if self.config_content:
            valid_file = self._validate_content_file(self.config_content)

        # If error, log and exit
        if not self.config_content or valid_file:
            error_and_exit(self.feedback["missing_config"], self.logger)

    def check_config_preference(self):
        """Inform the user in case that a config preference exists."""
        if self.config_preference:
            self.logger.info(self.feedback["found_preference_file"]
                             .format(self.config_preference))

    def fetch_preference_file(self):
        """
        Get the content of the preference config file which
        overrides the chances of the projects defined in the
        main config file.
        """
        self.preference_file = self._read_config_file(self.config_preference)
        self.preferred_chances = {}

        if self.preference_file:
            for project in self.preference_file:
                # Extract options from project line
                specification = project.split(":")

                # Save the overriden chance for a given project
                self.preferred_chances[specification[0]] = specification[1]

    def preference_for(self, project):
        """Get a preferred chance for a project if it is defined."""
        preference_for_all = self.preferred_chances["*"]
        preference_for_project = self.preferred_chances[project]
        best = preference_for_all or preference_for_project

        # In case both exist, get the best assigned chance
        if preference_for_all and preference_for_project:
            if preference_for_all > preference_for_project:
                best = preference_for_all
            else:
                best = preference_for_project

        return best

    def get_projects(self):
        """Return the content of the basic project configuration."""
        return self.config_content

    def setup(self):
        """Execution flow of the ProjectHub."""
        self.fetch_config_file()
        self.check_config_preference()
        self.fetch_preference_file()

        # Get shared and guest metadata filepaths and save in config
        self.shared_metadata_file, self.guest_metadata_file = \
            self._parse_metadata_option(config["shared_metadata_option"])
        self.config["shared_metadata_file"] = self.shared_metadata_file
        self.config["guest_metadata_file"] = self.guest_metadata_file

    def _read_config_file(self, config_file):
        existing_file = None

        with ignored(IOError):
            with open(config_file, "r") as fp:
                existing_file = fp.readlines()
                without_comments = []

                # Remove comments from the content
                for line in existing_file:
                    if not self.there_are_comments.match(line):
                        without_comments.append(line)

                existing_file = without_comments

        return existing_file

    def _parse_metadata_option(self, shared_option):
        """Parse and get both shared and guest metadata files.

        The metadata file is used by several instances of VMs
        to have access to variables predefined by the client.
        """
        shared, guest = None, None

        if self.shared_option:
            shared, guest = self.shared_option.split('=')

            # Strip heading '/' to mount relatively to the path
            guest = lstrip(guest, '/')

            # If the shared file does not exists, disable options
            if not os.path.exists(shared):
                shared, guest = None, None

        return shared, guest

    def _validate_content_file(self, lines):
        def project_parser(l):
            return (not self.there_are_comments.match(l) and
                    self.valid_format.match(l) or
                    not self.escapes_from_cvmfs.match(l))

        # Check validity of every project
        valid_projects = filter(project_parser, lines)
        return valid_projects > 0


class ProjectManager:

    def __init__(self, hw_info, config, logger):
        self.hw_info = hw_info
        self.config = config
        self.logger = logger
        self.dumbq_dir = config["dumbq_dir"]
        self.run_dir = config["dumbq_rundir"]
        self.tty_dir = config["dumbq_ttydir"]
        self.base_tty = config["base_tty"]
        self.www_dir = config["www_dir"]
        self.envvars = []

        # Project information
        self.index_filename = self.www_dir + os.sep + "index.json"
        self.temp_index_filename = self.www_dir + os.sep + "index.new"
        self.version = config["version"]
        self.host_uuid = hw_info.host_uuid

        # Regexp to get envars
        self.get_vars_regexp = re.compile("^[^=]+=(.*)")
        self.extract_id_tty = re.compile("")

        # Get configuration of projects
        self.project_hub = ProjectHub()
        self.project_hub.setup()

    def pick_project(self):
        """
        Pick a project by rolling a dice and checking the chances
        of being selected. Return the specification of the project.
        """
        winner = None
        sum_chance = 0
        found = False

        # Roll a dice
        choice = randint(0, 99)
        projects = self.project_hub.get_projects()

        # Iterate over ALL the projects
        for project in projects:
            # Get project information
            specification = project.split(":")
            project_name = specification[0]
            options = specification[1]
            project_chance = options.split(",")[0]

            # Reassign if the there is a preference for the project
            if self.project_hub.preference_for(project_name):
                self.logger.info(self.feedback["override_chance"]
                                 .format(project_chance, project_name))
            sum_chance += project_chance

            # Assign a winner when choice is below sum_chance
            if choice <= sum_chance and not found:
                winner = specification
                found = True

        # Check that all the chances add up to 100
        if sum_chance != 100:
            self.logger.error(self.feedback["incomplete_overall_chance"])

        return winner

    def path_of_runfile(self, container_name):
        """Return abspath of the run file (flag) of a given container."""
        return self.run_dir + os.sep + container_name

    def open_tty(self, container_name):
        """Find a free tty for the given container. Return boolean."""

        def extract_tty_id(filename):
            match = self.extract_id_tty.match(filename)
            return match if not match else match.group(0)

        def filepath_from_tty_id(tty_id):
            return self.tty_dir + os.sep + "tty" + tty_id

        def read_tty_pid(tty_filepath):
            with ignored(IOError):
                with open(tty_filepath, "r") as f:
                    return f.readline().split()[0]
            return None

        def is_alive(pid):
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True

        def remove_tty_file(filepath):
            try:
                os.remove(filepath)
            except (OSError, IOError):
                self.logger(self.feedback["tty_file_removal"]
                            .format(tty_id))

        def start_console_daemon(tty_id):
            self.logger.info(self.feedback["reserving_tty"]
                             .format(tty_id, container_name))
            new_tty_filepath = filepath_from_tty_id(tty_id)
            # TODO Finish start_console_daemon

        # Get existing tty files
        tty_files = os.listdir(self.tty_dir)

        # Extract id from filenames
        tty_ids = map(extract_tty_id, tty_files)

        # Check if there are ttys in use
        sorted_tty_ids = sorted(tty_ids)
        next_id = None

        # Find free tty among the used ttys
        for tty_id in sorted_tty_ids:
            # If don't match, free tty
            if next_id and tty_id != next_id:
                next_id = tty_id
                break

            tty_filepath = filepath_from_tty_id(tty_id)

            # If container is dead, reuse that tty
            if not is_alive(read_tty_pid(tty_filepath)):
                remove_tty_file(tty_filepath)
                break

            next_id = tty_id + 1

        if not next_id:
            next_id = 0

        # Check if it's out of the allowed tty range
        if next_id > self.hw_info.max_tty:
            self.logger.error(self.feedback["no_free_tty"]
                              .format(container_name))
            allocated_tty = False
        else:
            allocated_tty = start_console_daemon(next_id)

        return allocated_tty

    def run_project(self):
        def start_container(project_config):
            # Basic command configuration
            cernvm_fork_command = [
                self.config["cernvm_fork_bin"],
                container_name, "-n", "-d", "-f",
                "--run={}".format(container_run),
                "--cvmfs={}".format(project_repos),
                "-o", ("'lxc.cgroup.memory.limit_in_bytes = {}K'"
                       .format(quota_mem)),
                "-o", ("'lxc.cgroup.memory.memsw.limit_in_bytes = {}K'"
                       .format(quota_swap)),
            ]

            # Mount shared guest mountpoint
            if mount_options:
                cernvm_fork_command.append(
                    "-o", "'lxc.mount.entry = {}'".format(mount_options),
                )

            # Share metadata file if exists
            if self.config["shared_meta_file"]:
                guest_meta_file = self.config["guest_meta_file"]
                cernvm_fork_command.append(
                    "-E", "'DUMBQ_METAFILE=/{}'".format(guest_meta_file)
                )

            # Pass configuration environment variables
            for envvar in self.envars:
                cernvm_fork_command.append(
                    "-E", "'DUMBQ_{}'".format(envvar)
                )

            cernvm_fork_command.extend([
                "-E", "'DUMBQ_NAME={}'".format(project_name),
                "-E", "'DUMBQ_UUID={}'".format(random_uuid),
                "-E", "'DUMBQ_VMID={}'".format(self.host_uuid)
            ])

            # Start container
            check_output(cernvm_fork_command)

        # Get project to run
        project = self.pick_project()
        project_name = project[0]
        project_repos = project[2].split(",")
        project_script = project[3]

        # Quotas of every project
        quota_cpu = self.hw_info.slot_cpu
        quota_mem = self.hw_info.slot_mem
        quota_swap = self.hw_info.slot_swap + self.hw_info.slot_mem

        # Container configuration
        random_uuid = uuid4()
        container_name = "{0}-{1}".format(project_name, random_uuid)
        container_run = "/cvmfs/{0}".format(project_script)

        # Mount WWW dir
        if self.www_dir:
            mountpoint = "{0}/inst-{1}".format(self.www_dir, container_name)
            create_dir_if_nonexistent(mountpoint, mode=0555)
            guest_shared_mount = self.config["guest_shared_mount"]
            mount_options = ("{0} {1} none defaults,bind,user 0 0"
                             .format(mountpoint, guest_shared_mount))

    def stop_project(self, container_name):
        """Destroy project's container and its assigned resources."""
        def destroy_container():
            # Destroy container and return exit code
            action = [self.cernvm_fork_bin, container_name, "-D"]
            return call(action, stdout=DEVNULL)

        is_success = False

        # Check success of container destruction
        if destroy_container() == 0:
            is_success = True

            # Remove run file
            run_filepath = self.path_of_runfile(container_name)
            os.remove(run_filepath)

            # Remove host shared mount directory
            project_www_folder = (self.www_dir + os.sep +
                                  "inst-{0}".format(container_name))
            shutil.rmtree(project_www_folder, ignore_errors=True)

        else:
            self.logger.warning(self.feedback["destruction_error"])

        return is_success

    def get_containers(self):
        """Get containers - active and passive."""
        return check_output(["lxc-ls"]).split("\n")

    def get_containers_in_run_dir(self):
        """Get containers folders in the run dir."""
        return os.listdir(self.run_dir)

    def get_active_containers(self):
        """Get active containers."""
        return check_output(["lxc-ls", "--active"]).split("\n")

    def has_free_space(self):
        """Check the resources to run another project."""
        active_containers = self.get_active_containers()
        needs_update = False

        # Iterate over any managed container
        for container_name in self.get_containers_in_run_dir():
            if container_name not in active_containers:
                # Found inactive container
                self.logger.info(self.feedback["inactive_container"]
                                 .format(container_name))

                # Stop and clean container to free resources
                destroyed = self.stop_project(container_name)

                # Index needs update if destroyed
                needs_update = needs_update or destroyed

        if needs_update:
            self.update_projects_info()

        # Any space has been freed?
        return needs_update

    def update_projects_info(self):
        """Thread-safe update the index in the public WWW folder.

        The index file represents the current state of
        the projects and points to its resources and logs.
        """

        # Time of update
        now = str(time.time()).split(".")[0]

        def jsonify(**vars):
            return json.dumps(vars)

        def running_instances():
            for container_name in self.get_containers_in_run_dir():
                # The run file is named as the container
                filepath = self.path_of_runfile(container_name)

                with open(filepath, "r") as f:
                    # Get project description
                    content = f.read()
                    # Return and remove newlines
                    yield content.translate(None, "\n")

        def get_uptime():
            uptime = None

            # Read uptime and replace spaces by commas
            with open("/proc/uptime", "r") as f:
                uptime_seconds = f.readline()
                uptime = uptime_seconds.translate(string.maketrans(' ', ','))

            return uptime

        def get_load():
            return check_output(["uptime"]).split("load average: ")[1]

        def get_run_hours():
            with open(self.dumbq_dir + "/runhours") as f:
                hours = f.readline()
                if not hours:
                    hours = 0

        # Get updated index from current values
        updated_index = jsonify(instances=running_instances(),
                                updated=now,
                                machine_uuid=self.host_uuid,
                                version=self.version,
                                uptime=get_uptime(),
                                load=get_load(),
                                runhours=get_run_hours())

        # Write updated contents to new file (truncating)
        with open(self.temp_index_filename, "w+") as f:
            f.write(updated_index)

        # Update old file with new file
        os.rename(self.temp_index_filename, self.index_filename)

    def cleanup_environment(self):
        """Clean up stale resources from inactive containers."""
        needs_update = False

        # Get flags of containers in the running folder
        containers_in_run_dir = set(self.get_containers_in_run_dir())

        # Get inactive containers
        total_containers = set(self.get_containers())
        active_containers = set(self.get_active_containers())
        inactive_containers = total_containers - active_containers

        # Iterate over all the stale containers
        if containers_in_run_dir and inactive_containers:
            stale_containers = (containers_in_run_dir & inactive_containers)

            # Stop, clean them and update index if it's a success
            for stale_container_name in stale_containers:
                self.logger.info(self.feedback["clean_container"]
                                 .format(stale_container_name))

                stopped = self.stop_project(stale_container_name)
                needs_update = needs_update or stopped

        if needs_update:
            self.update_projects_info()

    def read_environment_variables(self):
        """Read environment variables from floppy or default file."""
        def get_envvars(lines):
            # Return lines with 'key=value' format
            for line in lines:
                match = self.get_vars_regexp.match(line)
                if match:
                    yield match.group()

        floppy_reader = self.config["floppy_reader_bin"]
        envvar_file = self.config["envvar_file"]

        # Read from floppy drive
        if os.path.exists(floppy_reader):
            floppy_out = check_output(floppy_reader, stderr=DEVNULL)
            floppy_vars = floppy_out.split("\n")
            self.envvars.extend(get_envvars(floppy_vars))

        # Read from standard storage of envvars
        with ignored(IOError):
            with open(envvar_file, "r") as f:
                content = f.readlines()
                self.envvars.extend(get_envvars(content))


# Config initialised with default values
config = {
    "config_ssl_certs":     "",
    "config_ssl_capath":    "",
    "shared_mount":         "",
    "bind_mount":           "",
    "base_tty":             0,
    "version":              "2.0",
    "dumbq_dir":            "/var/lib/dumbq",
    "cernvm_fork_bin":      "/usr/bin/cernvm-fork",
    "default_env_file":     "/var/lib/user-data",
    "shared_meta_file":     "/var/lib/dumbq-meta",
    "guest_meta_file":      "/var/lib/dumbq-meta",
    "guest_shared_mount":   "/var/www/html",
    "www_dir":              "/var/www/html",
    "uuid_file":            "/var/lib/uuid",
    "local_cervm_config":   "/etc/cernvm/default.conf",
    "config_source":        "/cvmfs/sft.cern.ch/lcg/external/"
                            "experimental/dumbq/server/default.conf",
    "floppy_reader_bin":    "/cvmfs/sft.cern.ch/lcg/external/"
                            "cernvm-copilot/bin/readFloppy.pl"
}

explanations = {
    "bind":     "Shared bind of the given file/directory from host "
                "to guest. The path after '=' defaults to <path>.",
    "config":   "Specify the source configuration file to use. "
                "The default value is {0}".format(config["config_source"]),
    "prefix":   ("Preference override configuration file that "
                 "changes the project quotas. Default is {0}."
                 .format(config["config_preference"])),
    "share":    ("Expose the directory guest_dir from the guest on "
                 "the web directory in order to expose project-specific "
                 "information to the user. Default is {0}."
                 .format(config["guest_shared_mount"])),
    "tty":      "Display container's tty on a real tty starting from "
                "base_tty up to base_tty+cpu_count.",
    "webdir":   ("The directory where to expose run-time invormation "
                 "that can be served over a webserver in order to reach "
                 "the end-user. The default value is ${0}."
                 .format(config["www_dir"])),
    "meta":     "A metadata file shared with all guests. Useful for passing "
                "arbitrary information that should be included alon every job."
}

feedback = {
    "destruction_error":        "Unable to destroy the container!",
    "missing_config":           "Could not fetch configuration file!",
    "found_preference_file":    "Overriding project preference using {}",
    "clean_container":          "Cleaning up stale container {}",
    "inactive_container":       "Found inactive container {}",
    "no_free_tty":              "There is no free tty for container {}!",
    "reserving_tty":            "Reserving tty{0} for container{1}",
    "override_chance":          "Overriding chance to {0}% for project {1}",
    "incomplete_overall_chance": "The sum of the project chances is not 100!"
}

if __name__ == "__init__":
    authors = " and ".join(("Ioannis Charalampidis", "Jorge Vicente Cantero"))
    dumbq_headline = "Dumbq Client v2.0 - {}, CERN".format(authors)

    # Set up Command Line Interface
    parser = ArgumentParser(dumbq_headline)
    parser.add_argument("-b", "--bind", help=explanations["bind"],
                        default=config["bind_mount"])
    parser.add_argument("-c", "--config", help=explanations["config"],
                        default=config["config_source"])
    parser.add_argument("-p", "--pref", help=explanations["prefix"],
                        default=0)
    parser.add_argument("-S", "--share", help=explanations["share"],
                        default=config["guest_shared_mount"])
    parser.add_argument("-t", "--tty", help=explanations["tty"],
                        default=config["base_tty"])
    parser.add_argument("-w", "--webdir", help=explanations["webdir"],
                        default=config["host_web_dir"])
    parser.add_argument("-m", "--meta", help=explanations["meta"],
                        default=config["shared_meta_file"])

    # TODO Review argument parse, missing options as store

    # Update config with values from CLI
    config.update(vars(parser.parse_args()))

    # --------------------------------------------
    # Start the real execution flow of the program
    # --------------------------------------------

    logger = ConsoleLogger()
    hw_info = HardwareInfo()
    dumbq_setup = DumbqSetup(config, hw_info, logger)

    # Setup all the DumbQ environment
    dumbq_setup.setup()

    # TODO Continue the flow of the program with ProjectHub and ProjectManager
