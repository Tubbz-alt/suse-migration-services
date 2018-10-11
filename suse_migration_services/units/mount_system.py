# Copyright (c) 2018 SUSE Linux LLC.  All rights reserved.
#
# This file is part of suse-migration-services.
#
# suse-migration-services is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# suse-migration-services is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with suse-migration-services. If not, see <http://www.gnu.org/licenses/>
#
import os

# project
from suse_migration_services.command import Command
from suse_migration_services.defaults import Defaults
from suse_migration_services.fstab import Fstab
from suse_migration_services.path import Path

from suse_migration_services.exceptions import (
    DistMigrationSystemNotFoundException,
    DistMigrationSystemMountException
)


def main():
    """
    DistMigration mount system to upgrade

    Searches on all partitions for a fstab file. The first
    fstab file found is used as the system to upgrade.
    Filesystems relevant for an upgrade process are read from
    that fstab in order and mounted such that the system roofs
    is available for a zypper based migration process.
    """
    root_path = Defaults.get_system_root_path()
    Path.create(root_path)

    mountpoint_call = Command.run(
        ['mountpoint', '-q', root_path], raise_on_error=False
    )
    if mountpoint_call.returncode == 0:
        # root_path is already a mount point, better not continue
        # The condition is not handled as an error because the
        # existing mount point under this service created root_path
        # is considered to represent the system to upgrade and
        # not something else. Thus if already mounted, let's use
        # what is there.
        return

    fstab = None
    lsblk_call = Command.run(
        ['lsblk', '-p', '-n', '-r', '-o', 'NAME,TYPE']
    )
    for entry in lsblk_call.output.split(os.linesep):
        block_record = entry.split()
        if block_record and block_record[1] == 'part':
            try:
                Command.run(
                    ['mount', block_record[0], root_path],
                    raise_on_error=False
                )
                fstab_file = os.sep.join([root_path, 'etc', 'fstab'])
                if os.path.exists(fstab_file):
                    fstab = Fstab(fstab_file)
                    break
            finally:
                Command.run(
                    ['umount', root_path],
                    raise_on_error=False
                )

    if not fstab:
        raise DistMigrationSystemNotFoundException(
            'Could not find system with fstab on {0}'.format(
                lsblk_call.output
            )
        )

    mount_system(root_path, fstab)


def mount_system(root_path, fstab):
    mount_list = []
    for fstab_entry in fstab.get_devices():
        if fstab_entry.mountpoint != 'swap':
            try:
                mountpoint = ''.join(
                    [root_path, fstab_entry.mountpoint]
                )
                Command.run(
                    [
                        'mount', '-o', fstab_entry.options,
                        fstab_entry.device, mountpoint
                    ]
                )
                mount_list.append(mountpoint)
            except Exception as issue:
                for mountpoint in reversed(mount_list):
                    Command.run(['umount', mountpoint])
                raise DistMigrationSystemMountException(
                    'Mounting system for upgrade failed with {0}'.format(issue)
                )