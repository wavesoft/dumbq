#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import logging
import multiprocessing
import os
import re
import shutil
import time
import string
import sys

from argparse import ArgumentParser
from string import lstrip
from multiprocessing import Process
from uuid import uuid4
from random import randint
from subprocess import check_output, call, CalledProcessError

from utils.utils \
    import error_and_exit, create_dir_if_nonexistent, jsonify, DEVNULL
from utils.utils import ignored, logged

"""Port of DumbQ 1.0, originally written in Bash by Ioannis Charalampidis."""

__author__ = "Jorge Vicente Cantero <jorgevc@fastmail.es>"


class ConsoleLogger(logging.getLoggerClass()):

    def __init__(self):
        logging.getLoggerClass().__init__("DumbQ")

    def setup(self, config, hw_info):
        """Set up the logger and show basic information."""
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
                         .format(hw_info.tty_range))


class HardwareInfo:

    def __init__(self, config):
        """Get cpu, memory and other info about host's hardware."""
        self.host_uuid = self.get_host_identifier()
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

        # Calculate how many ttys need the projects
        self.base_tty = self.config["base_tty"]

        if self.base_tty > 0 and hw_info.number_cores == 1:
            self.max_tty = self.base_tty + self.number_cores
            self.tty_range = "tty" + str(self.base_tty)
        elif self.base_tty > 0:
            self.max_tty = self.base_tty + self.number_cores - 1
            self.tty_range = "tty[{0}-{1}]".format(self.base_tty,
                                                   self.max_tty)

    def get_host_identifier(self):
        """Get UUID from CernVM/standard file or create one."""
        def uuid_from_cernvm():
            with ignored(IOError):
                with open(self.local_cernvm_config, "r") as c:
                    for line in c.readlines():
                        if "CERNVM_UUID" in line:
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

        return uuid_from_cernvm() or uuid_from_file()

    @staticmethod
    def _total_value_from_row(row_to_parse):
        return int(row_to_parse.split()[1])


class DumbqSetup:

    def __init__(self, hw_info, config, logger):
        self.config = config
        self.hw_info = hw_info
        self.logger = logger

        # Dumbq-related variables
        self.dumbq_dir = self.config["dumbq_dir"]
        self.www_dir = self.config["www_dir"]
        self.dumbq_folders = None

    def setup_config(self):
        """Define Dumbq folders and update the config with their paths."""
        extensions = ["run", "tty", "preference.conf"]
        dumbq_paths = os.path.join(self.dumbq_dir, extensions)

        self.config["dumbq_rundir"] = dumbq_paths[0]
        self.config["dumbq_ttydir"] = dumbq_paths[1]
        self.config["dumbq_preference_file"] = dumbq_paths[2]

        self.dumbq_folders = (
            self.dumbq_dir, dumbq_paths[0], dumbq_paths[1]
        )

    def setup_dumbq_folders(self):
        """Make sure dumbq folders exist. Otherwise, create them."""
        map(create_dir_if_nonexistent, self.dumbq_folders)

    def setup_logger(self):
        """Set up the logger and the handlers of the logs."""
        self.logger.setup(self.config, self.hw_info)

    def setup_public_www(self):
        """Create public WWW folder and make it readable."""
        if self.config["www_dir"]:
            create_dir_if_nonexistent(self.www_dir, mode=0555)


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
        self.config_content = self._read_config(self.config_file)

        # If the configuration file is invalid, log and exit
        valid_file = (self.config_content and
                      self._validate_content_file(self.config_content))

        if not valid_file:
            error_and_exit(self.feedback["missing_config"], self.logger)

    def check_config_preference(self):
        """Inform the user in case that a config preference exists."""
        if self.config_preference:
            self.logger.info(self.feedback["found_preference_file"]
                             .format(self.config_preference))

    def fetch_preference_file(self):
        """Get the content of the preference config file which
        overrides the chances of the projects defined in the
        main config file.
        """
        self.preference_file = self._read_config(self.config_preference)
        self.preferred_chances = {}

        # If exists, save the overriden chance for a given project
        if self.preference_file:
            for project in self.preference_file:
                project_name, new_chance = tuple(project.split(":")[0:2])
                self.preferred_chances[project_name] = new_chance

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

    def parse_shared_and_guest_metadata_file(self):
        self.shared_metadata_file, self.guest_metadata_file = \
            self._parse_metadata_option(config["shared_metadata_option"])
        self.config["shared_metadata_file"] = self.shared_metadata_file
        self.config["guest_metadata_file"] = self.guest_metadata_file

    def _read_config(self, config_file):
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
        """Get both shared and guest metadata files from the option.

        The metadata file is used by several instances of VMs
        to have access to variables predefined by the client.
        """
        shared, guest = None, None

        if self.shared_option:
            # Get options and strip first '/' to mount relatively
            shared, guest = self.shared_option.split('=')
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

        valid_projects = filter(project_parser, lines)
        return valid_projects > 0


class ProjectManager:

    def __init__(self, hw_info, config, logger):
        self.project_hub = project_hub
        self.hw_info = hw_info
        self.config = config
        self.feedback = feedback
        self.logger = logger

        self.dumbq_dir = config["dumbq_dir"]
        self.run_dir = config["dumbq_rundir"]
        self.tty_dir = config["dumbq_ttydir"]
        self.www_dir = config["www_dir"]
        self.cernvm_fork_bin = config["cernvm_fork_bin"]
        self.shared_meta_file = config["shared_meta_file"]
        self.guest_meta_file = config["guest_meta_file"]
        self.bind_mount = config["bind_mount"]
        self.envvars = []

        self.base_tty = self.hw_info.base_tty
        self.max_tty = self.hw_info.max_tty

        # Project information
        self.index_filename = os.path.join(self.www_dir, "index.json")
        self.temp_index_filename = os.path.join(self.www_dir, "index.new")
        self.version = config["version"]
        self.host_uuid = hw_info.host_uuid

        # Regexp to get envars
        self.get_vars_regexp = re.compile("^[^=]+=(.*)")
        self.extract_id_tty = re.compile(".*tty([0-9]+)")

    def pick_project(self):
        """Pick a project by rolling a dice and checking the chances
        of being selected. Return the specification of the project."""
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

            # If preference chance, use it
            preferred_chance = self.project_hub.preference_for(project_name)
            if preferred_chance:
                self.logger.info(self.feedback["override_chance"]
                                 .format(project_chance, project_name))
                project_chance = preferred_chance

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
        return os.path.join(self.run_dir, container_name)

    def open_tty(self, container_name):
        """Find a free tty for the given container. Return boolean."""
        def extract_tty_id(filename):
            match = self.extract_id_tty.match(filename)
            return match if not match else match.group(0)

        def filepath_from_tty_id(tty_id):
            return os.path.join(self.tty_dir, "tty" + tty_id)

        def read_pid(tty_filepath):
            with open(tty_filepath, "r") as f:
                return f.readline().split()[0]

        def is_alive(pid):
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            else:
                return True

        def write_content_to_tty_file(tty_id, container_name):
            new_tty_fp = filepath_from_tty_id(tty_id)
            with open(new_tty_fp, "w") as f:
                f.write("{0} {1}".format(os.getpid(), container_name))

        def remove_tty_flag(tty_id):
            try:
                os.remove(filepath_from_tty_id(tty_id))
            except (OSError, IOError):
                self.logger.error(self.feedback["tty_file_removal"]
                                  .format(tty_id))
                return False
            else:
                return True

        def remove_flag_if_alive(tty_id):
            tty_fp = filepath_from_tty_id(tty_id)
            if not is_alive(read_pid(tty_fp)):
                return remove_tty_flag(tty_id)
            return False

        def start_console_daemon(tty_id, container_name):
            self.logger.info(self.feedback["reserving_tty"]
                             .format(tty_id, container_name))

            openvt_command = ["openvt", "-w", "-f", "-c", tty_id, "--",
                              self.cernvm_fork_bin, container_name, "-C"]
            clear_command = ["clear"]
            tty_device = "/dev/tty{}".format(tty_id)
            tty = open(tty_device, "w")

            # Write content info to tty file and clear tty
            write_content_to_tty_file(tty_id, container_name)
            call(clear_command, stdout=tty)
            container_is_active = True

            while container_is_active:
                # Change stdout to tty and print feedback
                sys.stdout = tty
                print(self.feedback["connecting_tty"].format(container_name))

                # Call openvt every 2 seconds unless container went away
                call(openvt_command)
                active_containers = self.get_active_containers()
                container_is_active = container_name in active_containers()
                time.sleep(2)

            # Clear again and remove flag file
            call(clear_command, stdout=tty)
            remove_tty_flag()

        # Get tty ids from existing tty flag files
        tty_files = os.listdir(self.tty_dir)
        tty_ids = set(map(extract_tty_id, tty_files))
        free_id = None

        # Find first free tty among the used ttys
        for tty_id in xrange(self.base_tty, self.max_tty + 1):
            if tty_id not in tty_ids or remove_flag_if_alive(tty_id):
                free_id = tty_id
                break

        if not free_id:
            message = self.feedback["no_free_tty"].format(container_name)
            self.logger.error(message)

        start_terminal = Process(target=start_console_daemon,
                                 args=(free_id, container_name))

        return free_id and start_terminal.start()

    def run_project(self):
        def start_container():
            """Start CernVM fork with the proper context."""
            memory_option = "\'lxc.group.memory.limit_in_bytes = {}K\'"
            swap_option = "\'lxc.group.memory.memsw.limit_in_bytes = {}K\'"
            mount_entry_option = "\'lxc.mount.entry = {}\'"
            metafile_option = "\'DUMBQ_METAFILE = /{}\'"

            # Basic command configuration
            cernvm_fork_command = [
                self.cernvm_fork_bin, container_name,
                "-n", "-d", "-f",
                "--run={}".format(container_run),
                "--cvmfs={}".format(project_repos),
                "-o", memory_option.format(quota_mem),
                "-o", swap_option.format(quota_swap)
            ]

            # Mount shared mountpoint
            if mount_options:
                cernvm_fork_command.append(
                    "-o", mount_entry_option.format(mount_options))

            # Share metadata file if exists
            if self.shared_meta_file:
                cernvm_fork_command.append(
                    ("-E", metafile_option.format(self.guest_meta_file)))

            # Pass configuration environment variables
            for envvar in self.envars:
                cernvm_fork_command.append(
                    "-E", "'DUMBQ_{}'".format(envvar))

            cernvm_fork_command.extend([
                "-E", "'DUMBQ_NAME={}'".format(project_name),
                "-E", "'DUMBQ_UUID={}'".format(container_uuid),
                "-E", "'DUMBQ_VMID={}'".format(self.host_uuid)
            ])

            # Append bind shares
            for bind_share in bind_shares:
                cernvm_fork_command.append(
                    "-o", mount_entry_option.format(bind_share))

            # Start container and log actions
            start_message = (self.feedback["starting_container"]
                             .format(container_name))
            self.logger.info(start_message)

            try:
                check_output(cernvm_fork_command, stdout=DEVNULL)
            except CalledProcessError:
                return False
            else:
                return True

        def post_start_project():
            # Copy metadata file to guest
            if self.shared_meta_file:
                path_to_copy = ("/mnt/.rw/containers/{}/root/{}"
                                .format(container_name, self.guest_meta_file))
                shutil.copy(self.shared_meta_file, path_to_copy)

            # Create run file for project and update projects info
            run_file_contents = jsonify(
                uuid=container_uuid,
                wwwroot="/inst-{}".format(container_name),
                project=project_name,
                memory=quota_mem,
                swap=quota_swap,
                cpus=quota_cpu
            )

            flag_filepath = "{}/{}".format(self.run_dir, container_name)
            with open(flag_filepath, "w") as f:
                f.write(run_file_contents)

            if self.www_dir:
                self.update_projects_info()

            # Open tty console for project
            if self.base_tty > 0:
                self.open_tty(container_name)

        # Get project to run, quotas and container conf
        project = self.pick_project()
        project_name = project[0]
        project_repos = project[2].split(",")
        project_script = project[3]

        quota_cpu = self.hw_info.slot_cpu
        quota_mem = self.hw_info.slot_mem
        quota_swap = self.hw_info.slot_swap + self.hw_info.slot_mem

        container_uuid = uuid4()
        container_name = "{0}-{1}".format(project_name, container_uuid)
        container_run = "/cvmfs/{0}".format(project_script)

        # Mount WWW dir
        if self.www_dir:
            mountpoint = "{0}/inst-{1}".format(self.www_dir, container_name)
            create_dir_if_nonexistent(mountpoint, mode=0555)
            guest_shared_mount = self.config["guest_shared_mount"]
            mount_options = ("{0} {1} none defaults,bind,user 0 0"
                             .format(mountpoint, guest_shared_mount))

        # Aggregate bind shares with mount options
        bind_shares = []
        for bind_share in self.bind_mount:
            # Get `host, guest` or `host, host`
            hg = bind_share.split("=")
            dir_host = hg[0]
            hg.append(dir_host)
            dir_guest = hg[1]

            rel_path = re.sub("^/?", "", dir_guest)
            mount_options = ("{0} {1} none defaults,bind 0 0"
                             .format(mountpoint, rel_path))
            bind_shares.append(mount_options)

        # Start container, post_start and log any error
        if start_container():
            is_success = post_start_project()
        else:
            cernvm_error = self.feedback["cernvm_error"]
            self.logger.error(cernvm_error)
            is_success = False

        return is_success

    def stop_project(self, container_name):
        """Destroy project's container and its assigned resources."""
        def destroy_container():
            action = [self.cernvm_fork_bin, container_name, "-D"]
            return call(action, stdout=DEVNULL)

        # Check success of container destruction
        if destroy_container() == 0:
            is_success = True

            # Remove run file
            run_filepath = self.path_of_runfile(container_name)
            os.remove(run_filepath)

            # Remove host shared mount directory
            instance_name = "inst-{0}".format(container_name)
            project_www_folder = os.path.join(self.www_dir, instance_name)
            shutil.rmtree(project_www_folder, ignore_errors=True)
        else:
            is_success = False
            self.logger.warning(self.feedback["destruction_error"])

        return is_success

    def get_containers(self):
        """Get a set of containers - active and passive."""
        return set(check_output(["lxc-ls"]).split("\n"))

    def get_containers_in_run_dir(self):
        """Get a set of containers' folders in the run dir."""
        return set(os.listdir(self.run_dir))

    def get_active_containers(self):
        """Get a set of active containers."""
        return set(check_output(["lxc-ls", "--active"]).split("\n"))

    def has_free_space(self):
        """Check the resources to run another project."""
        active_containers = self.get_active_containers()
        needs_update = False

        # Check which containers are inactive
        for container_name in self.get_containers_in_run_dir():
            if container_name not in active_containers:
                self.logger.info(self.feedback["inactive_container"]
                                 .format(container_name))

                # Stop and free resources, update index if success
                destroyed = self.stop_project(container_name)
                needs_update = needs_update or destroyed

        # Update only if needed
        if needs_update:
            self.update_projects_info()

        return needs_update

    def update_projects_info(self):
        """Thread-safe update of the index in the public WWW folder.

        Index represents the state, resources and logs of the projects."""
        def running_instances():
            for container_name in self.get_containers_in_run_dir():
                filepath = self.path_of_runfile(container_name)

                # Get project description & remove newlines
                with open(filepath, "r") as f:
                    content = f.read()
                    yield content.translate(None, "\n")

        def get_uptime():
            # Read uptime and replace spaces by commas
            with open("/proc/uptime", "r") as f:
                seconds = f.readline()
                return seconds.translate(string.maketrans(' ', ','))
            return None

        def get_load():
            return check_output(["uptime"]).split("load average: ")[1]

        def get_run_hours():
            with open(self.dumbq_dir + "/runhours") as f:
                hours = f.readline()
                if not hours:
                    hours = 0

        now = str(time.time()).split(".")[0]

        # Get updated index from current values
        updated_index = jsonify(instances=running_instances(),
                                updated=now,
                                machine_uuid=self.host_uuid,
                                version=self.version,
                                uptime=get_uptime(),
                                load=get_load(),
                                runhours=get_run_hours())

        # Overwrite updated contents to new file and update old
        with open(self.temp_index_filename, "w") as f:
            f.write(updated_index)
        os.rename(self.temp_index_filename, self.index_filename)

    def cleanup_environment(self):
        """Clean up stale resources from inactive containers."""
        needs_update = False

        # Get flags of containers in the running folder
        containers_in_run_dir = self.get_containers_in_run_dir()

        # Get inactive containers
        total_containers = self.get_containers()
        active_containers = self.get_active_containers()
        inactive_containers = total_containers - active_containers

        # Iterate over all the stale containers
        if containers_in_run_dir and inactive_containers:
            stale_containers = (containers_in_run_dir & inactive_containers)

            # Stop, clean them and update index if it's a success
            for stale_container_name in stale_containers:
                self.logger.info(self.feedback["clean_container"]
                                 .format(stale_container_name))

                # Stop project and check for update
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

        # Update envars from floppy drive contents
        if os.path.exists(floppy_reader):
            floppy_out = check_output(floppy_reader, stderr=DEVNULL)
            floppy_vars = floppy_out.split("\n")
            self.envvars.extend(get_envvars(floppy_vars))

        # Update envars from standard file
        with ignored(IOError):
            with open(envvar_file, "r") as f:
                content = f.readlines()
                self.envvars.extend(get_envvars(content))


config = {
    "config_ssl_certs":     "",
    "config_ssl_capath":    "",
    "config_preference":    "",
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
    "connecting_tty":           "Connecting to {0}...",
    "override_chance":          "Overriding chance to {0}% for project {1}",
    "incomplete_overall_chance": "The sum of the project chances is not 100!",
    "starting_project":         "Starting project \'{}\'",
    "cernvm_error":             "Unable to create a CernVM fork!",
    "free_slot":                "There is a free slot available"
}

if __name__ == "__init__":
    authors = " and ".join(("Ioannis Charalampidis", "Jorge Vicente Cantero"))
    dumbq_headline = "Dumbq Client v2.0 - {}, CERN".format(authors)

    # Set up Command Line Interface and update config with values from CLI
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
    config.update(vars(parser.parse_args()))

    logger = ConsoleLogger()
    hw_info = HardwareInfo()

    dumbq_setup = DumbqSetup(hw_info, config, logger)
    dumbq_setup.setup_config()
    dumbq_setup.setup_dumbq_folders()
    dumbq_setup.setup_logger()
    dumbq_setup.setup_public_www()

    project_hub = ProjectHub(config, feedback, logger)
    project_hub.fetch_config_file()
    project_hub.check_config_preference()
    project_hub.fetch_preference_file()
    project_hub.parse_shared_and_guest_metadata_file()

    project_manager = ProjectManager(project_hub, hw_info,
                                     config, feedback, logger)
    project_manager.read_environment_variables()
    project_manager.cleanup_environment()
    project_manager.update_projects_info()

    # Main logic of the program
    while True:
        if project_manager.has_free_space():
            logger.info(feedback["free_slot"])
            project_manager.run_project()
            time.sleep(1)
        else:
            # Update index file to get current hw stats
            project_manager.update_projects_info()
            time.sleep(10)
