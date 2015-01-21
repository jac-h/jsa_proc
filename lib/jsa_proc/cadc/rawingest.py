# Copyright (C) 2015 Science and Technology Facilities Council.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, division, absolute_import

import os
import logging
import re
import shutil
import subprocess

from jsa_proc.admin.directories import get_misc_log_dir, make_misc_scratch_dir
from jsa_proc.error import JSAProcError
from jsa_proc.util import restore_signals

logger = logging.getLogger(__name__)

obsid_date = re.compile('_(\d{8})T')


def ingest_raw_observation(obsid, dry_run=False):
    """Perform raw ingestion of an observation."""

    logger.debug('Starting raw ingestion of OBSID %s', obsid)

    # Determine the date components which we can then use to create the
    # log directory.
    m = obsid_date.search(obsid)
    if not m:
        logger.error('Cannot parser OBSID %s to obtain date', obsid)
        raise JSAProcError('Cannot find date in OBSID {0}'.format(obsid))
    date = m.group(1)
    year = date[0:4]
    month = date[4:6]
    day = date[6:]
    logger.debug('Parsed OBSID, date: %s/%s/%s', month, day, year)

    # Prepare scratch directory.
    if not dry_run:
        scratch_dir = make_misc_scratch_dir('rawingest')
        logger.info('Working directory: %s', scratch_dir)
    else:
        scratch_dir = None

    # Prepare log directory and file name.
    if not dry_run:
        log_dir = os.path.join(get_misc_log_dir('rawingest'), year, month, day)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        logger.info('Log directory: %s', log_dir)
        log_file = os.path.join(log_dir, '{0}.log'.format(obsid))
        logger.debug('Log file: %s', log_file)
    else:
        log_file = 'DRY_RUN_MODE'

    # Attempt to run ingestion command.
    command = [
        'jsaraw',
        '--collection', 'JCMT',
        '--key', obsid,
        '--log', log_file + '.full',
        '--debug',
    ]

    try:
        if not dry_run:
            # Use context-manager to open a log file to store the (console)
            # output from the jsaraw program.
            with open(log_file, 'w') as log:
                logger.info('Running %s for OBSID %s', command[0], obsid)
                subprocess.check_call(
                    command,
                    shell=False,
                    cwd=scratch_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    preexec_fn=restore_signals)
        else:
            logger.info('Would have run: "%s" (DRY RUN)', ' '.join(command))

    except subprocess.CalledProcessError as e:
        logger.exception('Error during CAOM-2 ingestion')

    if not dry_run:
        logger.debug('Deleting scratch directory')
        shutil.rmtree(scratch_dir)
