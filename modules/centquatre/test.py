# -*- coding: utf-8 -*-

# Copyright(C) 2016      Phyks
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.


from weboob.tools.test import BackendTest


class CentQuatreTest(BackendTest):
    MODULE = 'centquatre'

    def test_centquatre(self):
        l = list(self.backend.list_events(None))
        assert len(l)
        event = self.backend.get_event(l[0].id)
        assert (event.id == l[0].id)
