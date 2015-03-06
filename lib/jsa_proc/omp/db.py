# Copyright (C) 2014-2015 Science and Technology Facilities Council.
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

from collections import namedtuple
from datetime import datetime
from keyword import iskeyword

import Sybase
from pytz import UTC

from jsa_proc.config import get_config
from omp.siteconfig import get_omp_siteconfig

from omp.db.backend.sybase import OMPSybaseLock
from jsa_proc.error import NoRowsError, ExcessRowsError


class OMPDB:
    """OMP and JCMT database access class.
    """

    CommonInfo = None

    def __init__(self, write_access=None):
        """Construct new OMP and JCMT database object.

        Connects to the JAC Sybase server.

        Write access can either be None (the default), "omp"
        or "jcmt".  Read-only and OMP credentials come from
        the OMP siteconfig file.  JCMT database write permissions
        come from the JSA Proc configuration system.
        """

        # Connect using the "hdr_database" set of credentials, which is
        # the "staff" user (supposed to be read only) at the time of
        # writing, unless the write_access option is specified.
        if write_access is None:
            config = get_omp_siteconfig()
            credentials = 'hdr_database'
        elif write_access == 'omp':
            config = get_omp_siteconfig()
            credentials = 'database'
        elif write_access == 'jcmt':
            config = get_config()
            credentials = 'database_jcmt'
        else:
            raise JSAProcError('Unknown write_access request {0}'
                               .format(write_access))

        conn = Sybase.connect(
            config.get(credentials, 'server'),
            config.get(credentials, 'user'),
            config.get(credentials, 'password'),
            auto_commit=0)

        self.db = OMPSybaseLock(conn)

    def get_obsid_common(self, obsid):
        """Retrieve information for a given obsid from the COMMON table.
        """

        query = 'SELECT * FROM COMMON WHERE obsid=@o'
        args = {'@o': obsid}

        with self.db as c:
            c.execute('USE jcmt')
            c.execute(query, args)

            rows = c.fetchall()
            cols = c.description

        if not rows:
            raise NoRowsError('COMMON', query, args)

        elif len(rows) > 1:
            raise ExcessRowsError('COMMON', query, args)

        if self.CommonInfo is None:
            self.CommonInfo = namedtuple(
                'CommonInfo',
                ['{0}_'.format(x[0]) if iskeyword(x[0]) else x[0]
                 for x in cols])

        return self.CommonInfo(*rows[0])

    def get_obsid_status(self, obsid):
        """Retrieve the last comment status for a given obsid.

        Returns None if no status was found.
        """

        query = 'SELECT commentstatus FROM ompobslog ' \
                'WHERE obslogid = ' \
                '(SELECT MAX(obslogid) FROM ompobslog ' \
                'WHERE obsid=@o AND obsactive=1)'
        args = {'@o': obsid}

        with self.db as c:
            c.execute('USE omp')
            c.execute(query, args)

            rows = c.fetchall()

        if not rows:
            return None

        if len(rows) > 1:
            raise ExcessRowsError('omp', query, args)

        return rows[0][0]

    def parse_datetime(self, dt):
        """Parse a datetime value returned by Sybase and return a
        datetime object.
        """

        return UTC.localize(datetime.strptime(str(dt), '%b %d %Y %I:%M%p'))

    def find_obs_for_ingestion(self, utdate_start, utdate_end=None,
                               no_status_check=False):
        """Find (raw) observations which are due for ingestion into CAOM-2.

        This method searches for observations matching these criteria:

            1. utdate within the given range
            2. date_obs at least 4 hours ago
            3. last_caom_mod NULL or older than last comment
            4. no files still in the process of being transferred

        Arguments:
            utdate_start: start date (observation's UT date must be >= this)
                          as a "YYYYMMDD" integer.  Can also be None to remove
                          the restriction, but this is not advisable for the
                          start date.
            utdate_end:   similar to utdate_end but for the end of the date
                          range (default: None).
            no_status_check: disable criterion 3, and instead only look for
                             observations with NULL last_caom_mod

        Returns:
            A list of OBSID strings.
        """

        where = []
        args = {}

        # Consider date range limits.
        if utdate_start is not None:
            args['@us'] = utdate_start
            where.append('(utdate >= @us)')
        if utdate_end is not None:
            args['@ue'] = utdate_end
            where.append('(utdate <= @ue)')

        # Check the observation is finished.  (Started >= 4 hours ago.)
        where.append('(DATEDIFF(hh, date_obs, GETUTCDATE()) >= 4)')

        # Look for last_caom_mod NULL or (optionally) comment newer than
        # last_caom_mod.
        if no_status_check:
            where.append('(last_caom_mod IS NULL)')
        else:
            where.append('((last_caom_mod IS NULL)'
                            ' OR (last_caom_mod < (SELECT MAX(commentdate)'
                                ' FROM omp..ompobslog'
                                ' WHERE omp..ompobslog.obsid=COMMON.obsid)))')

        # Check that all files have been transferred.
        where.append('(SELECT COUNT(*) FROM FILES'
                        ' JOIN transfer ON FILES.file_id=transfer.file_id'
                        ' WHERE FILES.obsid=COMMON.obsid'
                            ' AND transfer.status NOT IN ("t", "d", "D", "z"))'
                        ' = 0')

        query = 'SELECT obsid FROM COMMON WHERE ' + ' AND '.join(where)
        result = []

        with self.db as c:
            c.execute('use jcmt')
            c.execute(query, args)

            while True:
                row = c.fetchone()
                if row is None:
                    break

                result.append(row[0])

        return result

    def set_last_caom_mod(self, obsid, set_null=False):
        """Set the "COMMON.last_caom_mod" column to the current date
        and time for the given observation.

        This is to be used to mark an observation as successfully ingested
        into CAOM-2 (raw data only).

        If the set_null option is given then last_caom_mod is nulled rather
        than being set to the current date and time.
        """

        query = 'UPDATE COMMON SET last_caom_mod = ' + \
            ('NULL' if set_null else 'GETUTCDATE()') + \
            ' WHERE obsid=@o'
        args = {'@o': obsid}

        with self.db as c:
            try:
                c.execute('USE jcmt')
                c.execute(query, args)

                # Check that exactly one row was updated.
                # TODO: reinstate this check if/when we migrate to a
                # database where rowcount works.
                # if c.rowcount == 0:
                #     raise NoRowsError('COMMON', query, args)
                # elif c.rowcount > 1:
                #     raise ExcessRowsError('COMMON', query, args)

                # The Sybase DB lock object (JSAProcSybaseLock) was designed
                # for read-only access.  Since this is the only case (so far)
                # where we need to write to the database, handle commit and
                # rollback explicitly here for now.
                self.db._conn.commit()
            except:
                self.db._conn.rollback()
                raise
