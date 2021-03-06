# -*- coding: utf-8 -*-

# Copyright(C) 2016      Jean Walrave
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


import re

from datetime import datetime
from io import BytesIO

from weboob.browser.pages import LoggedPage, HTMLPage, JsonPage
from weboob.browser.filters.json import Dict
from weboob.browser.elements import DictElement, ItemElement, method
from weboob.browser.filters.standard import CleanText, CleanDecimal, Date, Regexp, Format, Eval
from weboob.capabilities.bank import Transaction, Account
from weboob.capabilities.profile import Profile
from weboob.tools.captcha.virtkeyboard import MappedVirtKeyboard, VirtKeyboardError
from weboob.capabilities import NotAvailable
from weboob.exceptions import ActionNeeded


class BNPVirtKeyboard(MappedVirtKeyboard):
    symbols = {'0': '91d2887b619ec825bb622c7770d4c2dc',
               '1': '9fe87bb481bde31b01c5ea434fbb391c',
               '2': '80c24c1586868830b8f578e41167996a',
               '3': 'dd4d989b1721506884914edbc1df3b91',
               '4': '38dd990feb7c40573e526fb69e2f17a9',
               '5': '579acb65bd5e98fcc413070192477528',
               '6': 'e133ed4e7c4c0028a2a0a7e9126751b4',
               '7': 'ae012ad7e1314571aef2343f40235d3c',
               '8': 'a619519f61da73124a2705544c45fb42',
               '9': 'fa625a1d4dc8357ec8eb87929bacd197',
               }

    color = (0, 0, 0)

    def __init__(self, page):
        img = page.doc.find('//img[@usemap="#gridpass_map_name"]')
        res = page.browser.open(img.attrib['src'])
        MappedVirtKeyboard.__init__(self, BytesIO(res.content), page.doc, img, self.color, convert='RGB')
        self.check_symbols(self.symbols, None)

    def check_color(self, pixel):
        return pixel[0] < 100

    def get_symbol_coords(self, coords):
        x1, y1, x2, y2 = coords

        return MappedVirtKeyboard.get_symbol_coords(self, (x1 + 6, y1 + 1, x2 - 6, y2 - 4))

    def get_symbol_code(self, md5sum):
        m = re.search('(\d+)', MappedVirtKeyboard.get_symbol_code(self, md5sum))
        if m:
            return m.group(1)


class LoginPage(HTMLPage):
    def get_password(self, password):
        vk_passwd = None

        try:
            vk = BNPVirtKeyboard(self)
            vk_passwd = vk.get_string_code(password)
        except VirtKeyboardError as e:
            self.logger.error(e)

        return vk_passwd


class AuthPage(HTMLPage):
    pass


class ActionNeededPage(HTMLPage):
    def on_load(self):
        raise ActionNeeded(CleanText('//p[@class="message"]')(self.doc))


class AccountsPage(LoggedPage, JsonPage):
    TYPES = {u'Compte chèque': Account.TYPE_CHECKING}

    @method
    class iter_accounts(DictElement):
        item_xpath = "tableauSoldes/listeGroupes/*/listeComptes"

        class item(ItemElement):
            klass = Account

            def obj_id(self):
                return CleanText(Dict('numeroCompte'))(self)[2:]

            obj_label = CleanText(Dict('libelleCompte'))
            obj_currency = CleanText(Dict('deviseTenue'))

            def obj_balance(self):
                return Eval(lambda x, y: x / 10**y, CleanDecimal(Dict('soldeComptable')), CleanDecimal(Dict('decSoldeComptable')))(self)

            def obj_coming(self):
                return Eval(lambda x, y: x / 10**y, CleanDecimal(Dict('soldePrevisionnel')), CleanDecimal(Dict('decSoldePrevisionnel')))(self)

            obj_iban = CleanText(Dict('numeroCompte', default=None), default=NotAvailable)

            def obj_type(self):
                return self.page.TYPES.get(Dict('libelleType')(self), Account.TYPE_UNKNOWN)


class AccountHistoryViewPage(LoggedPage, HTMLPage):
    @method
    class get_profile(ItemElement):
        klass = Profile

        obj_name = Regexp(CleanText('//table[@class="table_info_connecte"]//td'), '(.+?)\s-')


def fromtimestamp(page, dict):
    return datetime.fromtimestamp(float(dict(page) / 1000))


class AccountHistoryPage(LoggedPage, JsonPage):
    TYPES = {u'CARTE': Transaction.TYPE_CARD, # Cartes
             u'CHEQU': Transaction.TYPE_CHECK, # Chèques
             u'REMCB': Transaction.TYPE_CARD, # Remises cartes
             u'VIREM': Transaction.TYPE_TRANSFER, # Virements
             u'VIRIT': Transaction.TYPE_TRANSFER, # Virements internationaux
             u'VIRSP': Transaction.TYPE_TRANSFER, # Virements européens
             u'VIRTR': Transaction.TYPE_TRANSFER, # Virements de trésorerie
             u'VIRXX': Transaction.TYPE_TRANSFER, # Autres virements
             u'PRLVT': Transaction.TYPE_LOAN_PAYMENT, # Prélèvements, TIP et télérèglements
             u'AUTOP': Transaction.TYPE_UNKNOWN, # Autres opérations
            }

    COMING_TYPES = {u'0083': Transaction.TYPE_DEFERRED_CARD,
                    u'0813': Transaction.TYPE_LOAN_PAYMENT,
                    u'0568': Transaction.TYPE_TRANSFER,
                   }

    @method
    class iter_history(DictElement):
        item_xpath = "mouvementsBDDF"

        class item(ItemElement):
            klass = Transaction

            obj_original_currency = CleanText(Dict('montant/devise'))
            obj__coming = Dict('aVenir')

            def obj_raw(self):
                if CleanText(Dict('nature/libelle'))(self) and CleanText(Dict('libelle'))(self):
                    return "%s %s" % (CleanText(Dict('nature/libelle'))(self), CleanText(Dict('libelle'))(self))
                elif CleanText(Dict('libelle'))(self):
                    return CleanText(Dict('libelle'))(self)
                else:
                    return CleanText(Dict('nature/libelle'))(self)

            def obj_type(self):
                return self.page.TYPES.get(Dict('nature/codefamille')(self), Transaction.TYPE_UNKNOWN)

            def obj_date(self):
                return fromtimestamp(self, Dict('dateOperation'))

            def obj_rdate(self):
                return fromtimestamp(self, Dict('dateCreation'))

            def obj_vdate(self):
                return fromtimestamp(self, Dict('dateValeur'))

            def obj_amount(self):
                return Eval(lambda x, y: x / 10**y, CleanDecimal(Dict('montant/montant')), CleanDecimal(Dict('montant/nb_dec')))(self)

    @method
    class iter_coming(DictElement):
        item_xpath = "infoOperationsAvenir/operationsAvenir"

        class item(ItemElement):
            klass = Transaction

            obj_date = Date(Dict('dateOpeMvmt'))
            obj_rdate = Date(Dict('dateCreatMvmt'))
            obj_vdate = Date(Dict('dateValMvmt'))
            obj_original_currency = CleanText(Dict('montantMvmt/devise'))

            def obj_raw(self):
                if not Dict('natureLibelleMvt')(self):
                    return CleanText(Dict('libelle'))(self)
                return Format('%s %s', CleanText(Dict('natureLibelleMvt')), CleanText(Dict('libelle')))(self)

            def obj_type(self):
                return self.page.COMING_TYPES.get(Dict('codeMouvement')(self), Transaction.TYPE_UNKNOWN)

            def obj_amount(self):
                return Eval(lambda x, y: x / 10**y, CleanDecimal(Dict('montantMvmt/montant')), CleanDecimal(Dict('montantMvmt/nb_dec')))(self)
