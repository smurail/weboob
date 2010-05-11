# -*- coding: utf-8 -*-

"""
Copyright(C) 2010  Romain Bignon

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

"""

from __future__ import with_statement

import logging
import sys

from weboob.tools.application import PromptApplication
from weboob.capabilities.dating import ICapDating


__all__ = ['HaveSex']


class HaveSex(PromptApplication):
    APPNAME = 'havesex'
    VERSION = '1.0'
    COPYRIGHT = 'Copyright(C) 2010 Romain Bignon'
    STORAGE_FILENAME = 'dating.storage'

    def main(self, argv):
        self.load_config()
        self.load_backends(ICapDating, storage=self.create_storage(self.STORAGE_FILENAME))

        return self.loop()

    def split_id(self, id):
        try:
            bname, id = id.split('.', 1)
        except ValueError:
            return None, None

        return self.weboob.backends.get(bname, None), id

    @PromptApplication.command("exit program")
    def command_exit(self):
        print 'Returning in real-life...'
        self.weboob.want_stop()

    @PromptApplication.command("show a profile")
    def command_profile(self, id):
        backend, _id = self.split_id(id)
        if not backend:
            print 'Invalid ID: %s' % id
            return False
        with backend:
            profile = backend.get_profile(_id)
            if not profile:
                print 'Profile not found'

            print profile.get_profile_text()
        return True

    def service(self, action, function):
        sys.stdout.write('%s:' % action)
        for backend, result in self.weboob.do(function):
            sys.stdout.write(' ' + backend.name)
            sys.stdout.flush()
        sys.stdout.write('.\n')

    @PromptApplication.command("start profiles walker")
    def command_walker(self, action):
        if action == 'start':
            self.service('Starting walker', 'start_profiles_walker')
        elif action == 'stop':
            self.service('Stopping walker', 'stop_profiles_walker')
        else:
            logging.error(u'Syntax: walker (start|stop)')
