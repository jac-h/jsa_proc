# Copyright (C) 2014 Science and Technology Facilities Council.
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



import sys
import logging
import argparse

from jsa_proc.statemachine import JSAProcStateMachine
from jsa_proc.config import get_database

description="""
This script will carry out simple state changes for JAC jobs in the
database configured in the JSAProc configuration file. It uses the
poll_jac_jobs method of the JSAProcStateMachine class which states:

"""+JSAProcStateMachine.poll_jac_jobs.__doc__

# Parse the arguments.
parser= argparse.ArgumentParser(description=description)
parser.add_argument('-v','--verbose', required=False, default=False,
                    action='store_true', help='Use DEBUG level of logging (otherwise uses INFO)')

args = parser.parse_args()

# Set up the logger.
logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

# Get the database specified in the config file.
db = get_database()

# Get the state machine.
sm = JSAProcStateMachine(db, None)

# Poll the JAC jobs.
status = sm.poll_jac_jobs()

# Return a status of 1 if status is not True.
if not status:
    sys.exit(1)
