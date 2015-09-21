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

"""Port of DumbQ 1.0, originally written in Bash by Ioannis Charalampidis."""
__author__ = "Jorge Vicente Cantero <jorgevc@fastmail.es>"

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

# Do Monkey patch if using Python <= 2.6
import subprocess
if "check_output" not in dir(subprocess):
    from utils.utils import check_output as patch
    subprocess.check_output = patch

from subprocess import check_output, call

from utils.utils import create_dir_if_nonexistent, jsonify, DEVNULL
from utils.utils import ignored, error_and_exit, logged
from utils.utils import safe_read_from_file, safe_write_to_file

base_logger_class = logging.getLoggerClass()


class ConsoleLogger(base_logger_class):

    def __init__(self, name="DumbQ"):
        base_logger_class.__init__(self, name)
        self.setLevel(logging.DEBUG)

    def setup(self, config, hw_info, testing=False):
        """Set up the logger and show basic information."""
        if not testing:
            self.addHandler(logging.StreamHandler())
        else:
            test_filename = config["test_logfile"]
            self.addHandler(logging.FileHandler(test_filename))

        self.info("Dumbq Client version {0} started"
                  .format(config["version"]))

        self.info("Using configuration from {0}"
                  .format(config["config_source"]))

        self.info("Allocating {0} slot(s), with cpu={1}, "
                  "mem={2}Kb, swap={3}Kb"
                  .format(hw_info.number_cores,
                          hw_info.slot_cpu,
                          hw_info.total_memory,
                          hw_info.total_swap))

        if hw_info.tty_range:
            self.info("Reserving {0} for containers"
                      .format(hw_info.tty_range))

logging.setLoggerClass(ConsoleLogger)


class HardwareInfo:

    def __init__(self, config, feedback, logger):
        """Get cpu, memory and other info about host's hardware."""
        self.logger = logger
        self.feedback = feedback
        self.uuid_file = config["uuid_file"]
        self.local_cernvm_config = config["local_cernvm_config"]
        self.host_uuid = self.get_host_identifier()

        self.number_cores = multiprocessing.cpu_count()

        # Read total memory and swap from `free` in KB
        free_output = check_output(["free", "-k"]).split("\n")
        self.total_memory, self.total_swap = \
            self.get_memory_and_swap(free_output)

        # Calculate slots
        self.slot_cpu = 1
        self.slot_mem = self.total_memory / self.slot_cpu
        self.slot_swap = self.total_swap / self.slot_cpu

        # Calculate how many ttys need the projects
        self.base_tty = config["base_tty"]

        # Compute max tty and only initialise tty range if not expected
        if self.base_tty > 0 and self.number_cores == 1:
            self.max_tty = self.base_tty + self.number_cores
            self.tty_range = "tty{0}".format(self.base_tty)
        elif self.base_tty > 0:
            self.max_tty = self.base_tty + (self.number_cores - 1)
            self.tty_range = "tty[{0}-{1}]".format(self.base_tty, self.max_tty)
        else:
            self.max_tty = self.base_tty + self.number_cores
            self.tty_range = None

    def get_host_identifier(self):
        """Get UUID from CernVM, uuid file or create a new one."""
        def uuid_from_cernvm():
            lines = safe_read_from_file(
                self.local_cernvm_config, self.logger.warning, lines=True)
            for line in lines or []:
                key, value = line.split("=")
                if key == "CERNVM_UUID":
                    return value

        def uuid_from_file():
            return safe_read_from_file(self.uuid_file, self.logger.warning)

        def genwrite_uuid():
            # Generate a new UUID and save it
            new_uuid = str(uuid4())
            safe_write_to_file(self.uuid_file, new_uuid, self.logger.warning)
            return new_uuid

        return uuid_from_cernvm() or uuid_from_file() or genwrite_uuid()

    @staticmethod
    def get_memory_and_swap(free_output_lines):
        """Get memory and swap from the output of `free -k`."""
        regex = re.compile(r"^(Mem|Swap):[ \t]*(\d*)")

        def silent_match(l):
            match = re.match(regex, l)
            return match.groups() if match else (None, None)

        matches = map(silent_match, free_output_lines)
        memlines = filter(lambda m: m[0] == "Mem", matches)
        swaplines = filter(lambda m: m[0] == "Swap", matches)
        mem = int(memlines.pop()[1]) if memlines else 0
        swap = int(swaplines.pop()[1]) if swaplines else 0
        return mem, swap


class DumbqSetup:

    def __init__(self, hw_info, config, logger):
        self.config = config
        self.hw_info = hw_info
        self.logger = logger

        self.dumbq_dir = self.config["dumbq_dir"]
        self.www_dir = self.config["www_dir"]
        self.dumbq_folders = None

    def basic_setup(self):
        """Define Dumbq folders and update the config with their paths."""
        fs = ["run", "tty", "preference.conf", "runhours"]
        dumbq_paths = map(lambda f: os.path.join(self.dumbq_dir, f), fs)

        self.config["dumbq_rundir"] = dumbq_paths[0]
        self.config["dumbq_ttydir"] = dumbq_paths[1]
        self.config["preference_config_source"] = dumbq_paths[2]
        self.config["dumbq_runhours"] = dumbq_paths[3]

        self.dumbq_folders = (
            self.dumbq_dir, dumbq_paths[0], dumbq_paths[1]
        )

    def setup_dumbq_folders(self):
        """Make sure dumbq folders exist. Otherwise, create them."""
        map(create_dir_if_nonexistent, self.dumbq_folders)

    def setup_logger(self, testing=False):
        """Set up the logger and the handlers of the logs."""
        self.logger.setup(self.config, self.hw_info, testing)

    def setup_public_www(self):
        """Create public WWW folder and make it readable."""
        if self.config["www_dir"]:
            create_dir_if_nonexistent(self.www_dir, mode=0555)


class ProjectHub:

    def __init__(self, config, feedback, logger, *args, **kwargs):
        self.config = config
        self.logger = logger
        self.feedback = feedback

        # Default configuration sources
        self.config_source = config["config_source"]
        self.config_preference = config["preference_config_source"]
        self.shared_meta_file = config["shared_meta_file"]
        self.guest_meta_file = config["guest_meta_file"]

        self.config_lines = None

        # Regexps to validate the content of the config files
        self.there_are_comments = re.compile("^[ \t]*#|^[ \t]*$")
        self.valid_format = re.compile("^([^:]+):(\d+[,\d]*):([^:]*):(.+)$")
        self.escapes_from_cvmfs = re.compile("\.\.")

    def _read_config(self, config_file):
        """Read project configuration file striping out comment lines."""
        content_file = safe_read_from_file(
            config_file, self.logger.error
        ) or ""
        project_lines = self.there_are_comments.sub("", content_file)
        return project_lines.split("\n") if project_lines else []

    @staticmethod
    def _parse_chance(field):
        """Return a correct chance from the chance field."""
        return int(field.split(",")[0])

    def _parse_content_file(self, lines):
        """Parse configuration file and return validity of the content."""
        def project_parser(l):
            valid_format = self.valid_format.match(l)
            if valid_format and not self.escapes_from_cvmfs.search(l):
                spec = valid_format.groups()
                return (spec[0], self._parse_chance(spec[1]), spec[2], spec[3])
            return None

        self.valid_project_lines = filter(None, map(project_parser, lines))
        return len(self.valid_project_lines) > 0

    def _check_sum_chances_is_100(self):
        """Check the sum of all the valid project lines is 100."""
        sum_chances = sum(map(lambda p: p[1], self.valid_project_lines))
        return sum_chances == 100

    # TODO: Extend to fetch from SSL and FTPs besides local
    def fetch_config_file(self):
        """Get the content of the config local file."""
        self.config_lines = self._read_config(self.config_source)
        valid_file = (self.config_lines
                      and self._parse_content_file(self.config_lines)
                      and self._check_sum_chances_is_100())

        # Log and exit if configuration is invalid
        if not self.config_lines:
            error_and_exit(self.feedback["missing_config"], self.logger)
        if not valid_file:
            error_and_exit(feedback["invalid_config"], self.logger)

    def _check_preference_config(self):
        """Inform the user in case that a config preference exists."""
        if self.config_preference:
            self.logger.info(self.feedback["found_preference_file"]
                             .format(self.config_preference))
        return self.config_preference

    def fetch_preference_file(self):
        """Get preference config which overrides the chances of projects."""
        if self._check_preference_config():
            self.preference_lines = self._read_config(self.config_preference)
            self.preferred_chances = {}

            # Save the overriden chance for a given project
            for project in self.preference_lines:
                spec = project.split(":")
                project_name, new_chance = spec[0], self._parse_chance(spec[1])
                self.preferred_chances[project_name] = new_chance

    def preference_for(self, project):
        """Get a preferred chance for a project if it is defined."""
        preference_for_all = self.preferred_chances.get("*")
        preference_for_project = self.preferred_chances.get(project)
        best = preference_for_all or preference_for_project

        # Return the best assigned chance in case both exist
        if preference_for_all and preference_for_project:
            if preference_for_all > preference_for_project:
                best = preference_for_all
            else:
                best = preference_for_project
        return best

    def get_projects(self):
        """Return the content of the basic project configuration."""
        return self.valid_project_lines

    def parse_shared_and_guest_metadata_file(self):
        """Get both shared and guest metadata files from the option.

        The metadata file is used by several instances of VMs
        to have access to variables predefined by the client.
        """
        shared, guest = self.shared_meta_file, self.guest_meta_file
        fields = shared.split('=')
        if len(fields) > 1:
            shared, guest = fields[0], fields[1]

        # Strip first '/' to mount relatively
        guest = lstrip(guest, '/')

        if not os.path.exists(shared):
            shared, guest = "", ""

        self.shared_meta_file, self.guest_meta_file = shared, guest
        self.config["shared_meta_file"] = shared
        self.config["guest_meta_file"] = guest


class ProjectManager:

    def __init__(self, project_hub, hw_info, config, logger):
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

        self.get_vars_regexp = re.compile("^([^=]+)=(.*)")
        self.extract_id_tty = re.compile(".*tty(\d+)")

        self.envvars = []
        self.base_tty = self.hw_info.base_tty
        self.max_tty = self.hw_info.max_tty
        self.index_filepath = os.path.join(self.www_dir, "index.json")
        self.temp_index_filepath = os.path.join(self.www_dir, "index.new")
        self.version = config["version"]
        self.host_uuid = hw_info.host_uuid

    def pick_project(self):
        """Return a project randomly chosen."""
        winner = None
        sum_chance = 0
        found = False

        # Roll a dice
        choice = randint(0, 99)
        projects = self.project_hub.get_projects()

        # Iterate over ALL the projects
        for project in projects:
            project_name = project[0]
            project_chance = project[1]

            # Use a preferred chance in case it exists
            preferred_chance = self.project_hub.preference_for(project_name)
            if preferred_chance:
                self.logger.info(self.feedback["override_chance"]
                                 .format(project_chance, project_name))
                project_chance = preferred_chance

            # Recompute overall chance
            sum_chance += project_chance

            # Assign a winner when choice is below sum_chance
            if choice <= sum_chance and not found:
                winner = project
                found = True

        return winner

    def path_of_runfile(self, container_name):
        """Return absolute path of the container's runfile (flag)."""
        return os.path.join(self.run_dir, container_name)

    def open_tty(self, container_name):
        """Open a tty and return the success/failure of the operation."""
        def extract_tty_id(filename):
            match = self.extract_id_tty.match(filename)
            return match.group(0) if match else None

        def filepath_from_tty_id(tty_id):
            return os.path.join(self.tty_dir, "tty{0}".format(tty_id))

        def read_pid(tty_filepath):
            """Read PID from the tty info file."""
            return safe_read_from_file(
                tty_filepath, self.logger.warning
            ).split("\n")

        def is_alive(pid):
            """Return if a process with a PID is still alive."""
            with ignored(OSError):
                os.kill(pid, 0)
                return True
            return False

        def dump_info_to_file(tty_id, container_name):
            new_tty_fp = filepath_from_tty_id(tty_id)
            tty_info = "{0} {1}".format(os.getpid(), container_name)
            safe_write_to_file(new_tty_fp, tty_info, self.logger.error)

        def remove_tty_flag(tty_id):
            feedback = self.feedback["tty_file_removal"].format(tty_id)
            with logged(self.logger.error, feedback, (EnvironmentError,)):
                os.remove(filepath_from_tty_id(tty_id))
                return True
            return False

        def remove_flag_if_alive(tty_id):
            tty_fp = filepath_from_tty_id(tty_id)
            if not is_alive(read_pid(tty_fp)):
                return remove_tty_flag(tty_id)
            return False

        def start_console_daemon(tty_id, container_name):
            self.logger.info(self.feedback["reserving_tty"]
                             .format(tty_id, container_name))
            tty_device = "/dev/tty{0}".format(tty_id)
            tty = open(tty_device, "w")
            old_stdout = sys.stdout

            clear_command = ["clear"]
            openvt_command = [
                "openvt", "-w", "-f", "-c", str(tty_id), "--",
                self.cernvm_fork_bin, container_name, "-C"
            ]

            # Dump info to tty file and clear tty
            dump_info_to_file(tty_id, container_name)
            call(clear_command, stdout=tty)
            container_is_active = True

            while container_is_active:
                # Change stdout to tty and print feedback to tty
                sys.stdout = tty
                print(self.feedback["connecting_tty"].format(container_name))
                sys.stdout = old_stdout

                # Call openvt every 2 seconds unless container went away
                call(openvt_command)
                active_containers = self.get_active_containers()
                container_is_active = container_name in active_containers
                time.sleep(2)

            # Clear again and remove flag file
            call(clear_command, stdout=tty)
            remove_tty_flag(tty_id)
            return True

        # Get tty ids from existing tty flag files
        tty_ids = set(map(extract_tty_id, os.listdir(self.tty_dir)))
        tty_ids = filter(None, tty_ids)
        free_id = None

        # Find first free tty among the used ttys
        for tty_id in xrange(self.base_tty, self.max_tty + 1):
            if tty_id not in tty_ids or remove_flag_if_alive(tty_id):
                free_id = tty_id
                break

        # Log as error if no free tty is found
        if not free_id:
            message = self.feedback["no_free_tty"].format(container_name)
            self.logger.error(message)

        start_terminal = Process(target=start_console_daemon,
                                 args=(free_id, container_name))
        # Start tty daemon if free tty
        return free_id and start_terminal.start()

    def run_project(self):
        """Run a project and allocate the necessary resources."""
        def start_container():
            """Start CernVM fork with the proper context."""
            memory_option = "'lxc.cgroup.memory.limit_in_bytes = {0}K'"
            swap_option = "'lxc.cgroup.memory.memsw.limit_in_bytes = {0}K'"
            mount_entry_option = "'lxc.mount.entry = {0}'"
            metafile_option = "'DUMBQ_METAFILE = /{0}'"

            # Basic command configuration
            cernvm_fork_command = [
                self.cernvm_fork_bin, container_name,
                "-n", "-d", "-f",
                "--run={0}".format(container_run),
                "--cvmfs={0}".format(project_repos),
                "-o " + memory_option.format(quota_mem),
                "-o " + swap_option.format(quota_swap)
            ]

            # Mount shared mountpoint
            if mount_options:
                cernvm_fork_command.append(
                    "-o " + mount_entry_option.format(mount_options))

            # Share metadata file if exists
            if self.shared_meta_file:
                cernvm_fork_command.append(
                    ("-E " + metafile_option.format(self.guest_meta_file)))

            # Pass configuration environment variables
            for envvar in self.envvars:
                cernvm_fork_command.append(
                    "-E " + "'DUMBQ_{0}'".format(envvar))

            cernvm_fork_command.extend([
                "-E " + "'DUMBQ_NAME={0}'".format(project_name),
                "-E " + "'DUMBQ_UUID={0}'".format(container_uuid),
                "-E " + "'DUMBQ_VMID={0}'".format(self.host_uuid)
            ])

            # Append bind shares
            for bind_share in bind_shares:
                cernvm_fork_command.append(
                    "-o " + mount_entry_option.format(bind_share))

            # Return if container started correctly
            start_message = (self.feedback["starting_project"]
                             .format(container_name))
            self.logger.info(start_message)
            return call(cernvm_fork_command, stdout=DEVNULL) == 0

        def post_start_project():
            """Copy metadata, create runfile, update index and open tty."""
            if self.shared_meta_file:
                path_to_copy = (self.config["guest_mountpoint"]
                                .format(container_name, self.guest_meta_file))
                parent_path = re.sub("[^/]+$", "", path_to_copy)
                os.makedirs(parent_path)
                shutil.copy(self.shared_meta_file, path_to_copy)

            project_info = jsonify(
                uuid=container_uuid,
                wwwroot="/inst-{0}".format(container_name),
                project=project_name,
                memory=quota_mem,
                swap=quota_swap,
                cpus=quota_cpu
            )

            flag_filepath = os.path.join(self.run_dir, container_name)
            safe_write_to_file(flag_filepath, project_info, self.logger.error)

            if self.www_dir:
                self.update_project_stats()

            # Only open tty if the option is enabled
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

        container_uuid = str(uuid4())
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

        return project_name if is_success else ""

    def stop_project(self, container_name):
        """Destroy project's container and its allocated resources."""
        def destroy_container():
            action = [self.cernvm_fork_bin, container_name, "-D"]
            return call(action, stdout=DEVNULL) == 0

        # Check success of container destruction
        is_destroyed = destroy_container()
        if is_destroyed:
            # Remove run file and host shared mount
            run_filepath = self.path_of_runfile(container_name)
            with ignored(EnvironmentError):
                os.remove(run_filepath)
            instance_name = "inst-{0}".format(container_name)
            project_www_folder = os.path.join(self.www_dir, instance_name)
            shutil.rmtree(project_www_folder)
        else:
            self.logger.warning(self.feedback["destruction_error"])

        return is_destroyed

    def get_containers(self):
        """Get a set of containers - active and passive."""
        cs = check_output(["lxc-ls"]).split("\n")
        return set(map(string.strip, cs))

    def get_containers_in_run_dir(self):
        """Get a set of containers' folders in the run dir."""
        return set(os.listdir(self.run_dir))

    def get_active_containers(self):
        """Get a set of active containers."""
        cs = check_output(["lxc-ls", "--active"]).split("\n")
        return set(map(string.strip, cs))

    def free_space(self):
        """Check if another project can be run in the host."""
        containers = self.get_containers_in_run_dir()
        available_space = len(containers) < self.hw_info.number_cores

        if not available_space:
            active_containers = self.get_active_containers()

            # Check which containers are inactive
            for container_name in containers:
                if container_name not in active_containers:
                    self.logger.info(self.feedback["inactive_container"]
                                     .format(container_name))
                    if self.stop_project(container_name):
                        available_space = True
                        self.update_project_stats()
                        break

        return available_space

    def update_project_stats(self):
        """Thread-safe update of the index in the public WWW folder.

        Index represents the state, resources and logs of the projects.
        """
        def running_instances():
            """Get run dir and container name of every project."""
            for container_name in self.get_containers_in_run_dir():
                run_fp = self.path_of_runfile(container_name)
                lines = safe_read_from_file(
                    run_fp, self.logger.error, lines=True
                ) or [""]
                yield lines[0]

        def get_uptime():
            """Read uptime and replace spaces by commas."""
            seconds = safe_read_from_file("/proc/uptime", self.logger.error)[0]
            return seconds.translate(string.maketrans(' ', ',')) or None

        def get_load():
            """Get load from the uptime command."""
            return check_output(["uptime"]).split("load average: ")[1]

        def get_run_hours():
            """Get run hours of DumbQ."""
            runhours_fp = self.config["dumbq_runhours"]
            hours = safe_read_from_file(
                runhours_fp, self.logger.warning, lines=True)
            return hours[0] if hours else 0

        update_error_message = feedback["update_index_error"]
        now = str(time.time()).split(".")[0]

        # Get updated index from current values
        updated_index = jsonify(instances=list(running_instances()),
                                updated=now,
                                machine_uuid=self.host_uuid,
                                version=self.version,
                                uptime=get_uptime(),
                                load=get_load(),
                                runhours=get_run_hours())

        # Overwrite updated contents to tmp file and update old
        safe_write_to_file(self.temp_index_filepath,
                           updated_index, self.logger.warning)

        with logged(self.logger, update_error_message, (EnvironmentError,)):
            os.rename(self.temp_index_filepath, self.index_filepath)

    def cleanup_environment(self):
        """Clean up stale resources from inactive containers."""
        any_cleaned = False

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
                stopped = self.stop_project(stale_container_name)
                any_cleaned = any_cleaned or stopped

        if any_cleaned:
            self.update_project_stats()

    def read_environment_variables(self):
        """Read environment variables from floppy or default file."""
        def get_envvars(lines):
            # Return lines with 'key=value' format
            for line in lines:
                match = self.get_vars_regexp.match(line)
                yield match.groups() if match else None

        floppy_reader = self.config["floppy_reader_bin"]
        envvar_file = self.config["envvar_file"]

        # Update envars from floppy drive contents
        if os.path.exists(floppy_reader):
            floppy_out = check_output(floppy_reader, stderr=DEVNULL)
            floppy_vars = floppy_out.split("\n")
            self.envvars.extend(filter(None, get_envvars(floppy_vars)))

        # Update envars from standard file
        with ignored(OSError):
            envvars = safe_read_from_file(envvar_file, self.logger.warning,
                                          lines=True)
            self.envvars.extend(filter(None, get_envvars(envvars)))


# Use "" if an option is not enabled, not None.
dumbq_dir = "/var/lib/dumbq"
rep = "/cvmfs/sft.cern.ch/lcg/external"
config = {
    "config_ssl_certs":         "",
    "config_ssl_capath":        "",
    "config_ssl_capath":        "",
    "shared_mount":             "",
    "bind_mount":               "",
    "base_tty":                 0,
    "version":                  "2.0",
    "dumbq_dir":                dumbq_dir,
    "cernvm_fork_bin":          "/usr/bin/cernvm-fork",
    "default_env_file":         "/var/lib/user-data",
    "shared_meta_file":         "/var/lib/dumbq-meta",
    "guest_meta_file":          "/var/lib/dumbq-meta",
    "guest_shared_mount":       "/var/www/html",
    "www_dir":                  "/var/www/html",
    "uuid_file":                "/var/lib/uuid",
    "ennvar_file":              "/var/lib/user-data",
    "test_logfile":             dumbq_dir + "/testing.log",
    "guest_mountpoint":         "/mnt/.rw/containers/{0}/root/{1}",
    "local_cernvm_config":      "/etc/cernvm/default.conf",
    "preference_config_source": dumbq_dir + "/preference.conf",
    "floppy_reader_bin":        rep + "/cernvm-copilot/bin/readFloppy.pl",
    "config_source":            rep + "/experimental/dumbq/server/default.conf"
}

explanations = {
    "bind":     "Shared bind of the given file/directory from host "
                "to guest. The path after '=' defaults to <path>.",
    "config":   "Specify the source configuration file to use. "
                "The default value is {0}".format(config["config_source"]),
    "pref":     ("Preference override configuration file that "
                 "changes the project quotas. Default is {0}."
                 .format(config["preference_config_source"])),
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
    "found_preference_file":    "Overriding project preference using '{0}'",
    "clean_container":          "Cleaning up stale container '{0}'",
    "inactive_container":       "Found inactive container '{0}'",
    "no_free_tty":              "There is no free tty for container '{0}'!",
    "tty_file_removal":         "The tty flag of tty{0} could not be removed",
    "reserving_tty":            "Reserving tty{0} for container '{1}'",
    "connecting_tty":           "Connecting to '{0}'...",
    "override_chance":          "Preferred chance {0}% for project '{1}'",
    "starting_project":         "Starting project '{0}'",
    "update_index_error":       "The index file could not be updated",
    "cernvm_error":             "Unable to create a CernVM fork!",
    "free_slot":                "There is a free slot available",
    "invalid_config":           "Could not validate configuration information"
                                "\nEither the format is not valid or the sum"
                                "of the project chances is not 100.",
}

if __name__ == "__init__":
    authors = " and ".join(("Ioannis Charalampidis", "Jorge Vicente Cantero"))
    dumbq_headline = "Dumbq Client v2.0 - {0}, CERN".format(authors)

    parser = ArgumentParser(dumbq_headline)
    parser.add_argument("-b", "--bind", help=explanations["bind"],
                        dest="bind_mount", action="append")
    parser.add_argument("-c", "--config", help=explanations["config"],
                        dest="config_source")
    parser.add_argument("-p", "--pref", help=explanations["pref"],
                        dest="preference_config_source")
    parser.add_argument("-S", "--share", help=explanations["share"],
                        dest="guest_shared_mount")
    parser.add_argument("-t", "--tty", help=explanations["tty"],
                        dest="base_tty")
    parser.add_argument("-w", "--webdir", help=explanations["webdir"],
                        dest="www_dir")
    parser.add_argument("-m", "--meta", help=explanations["meta"],
                        dest="shared_meta_file")

    # Add default bind value and update config with user options
    parsed_args = vars(parser.parse_args())
    default_bind = config["bind_mount"]
    parsed_args["bind_mount"] = [default_bind] + parsed_args["bind_mount"]
    config.update(parsed_args)

    logger = ConsoleLogger()
    hw_info = HardwareInfo(config, feedback, logger)

    dumbq_setup = DumbqSetup(hw_info, config, logger)
    dumbq_setup.basic_setup()
    dumbq_setup.setup_dumbq_folders()
    dumbq_setup.setup_logger()
    dumbq_setup.setup_public_www()

    project_hub = ProjectHub(config, feedback, logger)
    project_hub.fetch_config_file()
    project_hub.fetch_preference_file()
    project_hub.parse_shared_and_guest_metadata_file()

    project_manager = ProjectManager(
        project_hub, hw_info, config, feedback, logger
    )

    project_manager.read_environment_variables()
    project_manager.cleanup_environment()
    project_manager.update_project_stats()

    while True:
        if project_manager.free_space():
            logger.info(feedback["free_slot"])
            project_manager.run_project()
            time.sleep(1)
        else:
            # Update index file to get current hw stats
            project_manager.update_project_stats()
            time.sleep(10)
