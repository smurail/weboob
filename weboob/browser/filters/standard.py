# -*- coding: utf-8 -*-

# Copyright(C) 2014 Romain Bignon
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

from __future__ import absolute_import

import datetime
from functools import wraps
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from itertools import islice
from collections import Iterator

from dateutil.parser import parse as parse_date
import lxml.html

from weboob.capabilities.base import empty
from weboob.capabilities.base import Currency as BaseCurrency
from weboob.tools.compat import basestring
from weboob.exceptions import ParseError
from weboob.browser.url import URL
from weboob.tools.log import getLogger, DEBUG_FILTERS


class NoDefault(object):
    def __repr__(self):
        return 'NO_DEFAULT'

_NO_DEFAULT = NoDefault()


__all__ = ['FilterError', 'ColumnNotFound', 'RegexpError', 'ItemNotFound',
           'Filter', 'Base', 'Env', 'TableCell', 'RawText',
           'CleanText', 'Lower', 'Upper', 'Capitalize', 'CleanDecimal',
           'Field', 'Regexp', 'Map', 'DateTime', 'Date', 'Time', 'DateGuesser',
           'Duration', 'MultiFilter', 'CombineDate', 'Format', 'Join', 'Type',
           'Eval', 'BrowserURL', 'Async', 'AsyncLoad']


class FilterError(ParseError):
    pass


class ColumnNotFound(FilterError):
    pass


class RegexpError(FilterError):
    pass


class ItemNotFound(FilterError):
    pass


class _Filter(object):
    _creation_counter = 0

    def __init__(self, default=_NO_DEFAULT):
        self._key = None
        self._obj = None
        self.default = default
        self._creation_counter = _Filter._creation_counter
        _Filter._creation_counter += 1

    def __or__(self, o):
        self.default = o
        return self

    def __and__(self, o):
        if isinstance(o, type) and issubclass(o, _Filter):
            o = o()
        o.selector = self
        return o

    def default_or_raise(self, exception):
        if self.default is not _NO_DEFAULT:
            return self.default
        else:
            raise exception

    def __str__(self):
        return self.__class__.__name__

    def highlight_el(self, el, item=None):
        obj = self._obj or item
        try:
            if not hasattr(obj, 'saved_attrib'):
                return
            if not obj.page.browser.highlight_el:
                return
        except AttributeError:
            return

        if el not in obj.saved_attrib:
            obj.saved_attrib[el] = dict(el.attrib)

        el.attrib['style'] = 'color: white !important; background: red !important;'
        if self._key:
            el.attrib['title'] = 'weboob field: %s' % self._key


def debug(*args):
    """
    A decorator function to provide some debug information
    in Filters.
    It prints by default the name of the Filter and the input value.
    """
    def wraper(function):
        @wraps(function)
        def print_debug(self, value):
            logger = getLogger('b2filters')
            result = ''
            outputvalue = value
            if isinstance(value, list):
                from lxml import etree
                outputvalue = ''
                first = True
                for element in value:
                    if first:
                        first = False
                    else:
                        outputvalue += ', '
                    if isinstance(element, etree.ElementBase):
                        outputvalue += "%s" % etree.tostring(element, encoding=unicode)
                    else:
                        outputvalue += "%r" % element
            if self._obj is not None:
                result += "%s" % self._obj._random_id
            if self._key is not None:
                result += ".%s" % self._key
            name = str(self)
            result += " %s(%r" % (name, outputvalue)
            for arg in self.__dict__:
                if arg.startswith('_') or arg == u"selector":
                    continue
                if arg == u'default' and getattr(self, arg) == _NO_DEFAULT:
                    continue
                result += ", %s=%r" % (arg, getattr(self, arg))
            result += u')'
            logger.log(DEBUG_FILTERS, result)
            res = function(self, value)
            return res
        return print_debug
    return wraper


class Filter(_Filter):
    """
    Class used to filter on a HTML element given as call parameter to return
    matching elements.

    Filters can be chained, so the parameter supplied to constructor can be
    either a xpath selector string, or an other filter called before.

    >>> from lxml.html import etree
    >>> f = CleanDecimal(CleanText('//p'), replace_dots=True)
    >>> f(etree.fromstring('<html><body><p>blah: <span>229,90</span></p></body></html>'))
    Decimal('229.90')
    """

    def __init__(self, selector=None, default=_NO_DEFAULT):
        super(Filter, self).__init__(default=default)
        self.selector = selector

    def select(self, selector, item):
        if isinstance(selector, basestring):
            ret = item.xpath(selector)
        elif isinstance(selector, _Filter):
            selector._key = self._key
            selector._obj = self._obj
            ret = selector(item)
        elif callable(selector):
            ret = selector(item)
        else:
            ret = selector

        if isinstance(ret, lxml.html.HtmlElement):
            self.highlight_el(ret, item)
        elif isinstance(ret, list):
            for el in ret:
                if isinstance(el, lxml.html.HtmlElement):
                    self.highlight_el(el, item)

        return ret

    def __call__(self, item):
        return self.filter(self.select(self.selector, item))

    @debug()
    def filter(self, value):
        """
        This method have to be overrided by children classes.
        """
        raise NotImplementedError()


class _Selector(Filter):
    def filter(self, elements):
        if elements is not None:
            return elements
        else:
            return self.default_or_raise(ParseError('Element %r not found' % self.selector))


class AsyncLoad(Filter):
    def __call__(self, item):
        link = self.select(self.selector, item)
        return item.page.browser.async_open(link) if link else None


class Async(Filter):
    def __init__(self, name, selector=None):
        super(Async, self).__init__()
        self.selector = selector
        self.name = name

    def __and__(self, o):
        if isinstance(o, type) and issubclass(o, _Filter):
            o = o()
        self.selector = o
        return self

    def __call__(self, item):
        if item.loaders[self.name] is None:
            return None

        return self.select(self.selector, self.loaded_page(item).doc)

    def filter(self, *args):
        raise AttributeError()

    def loaded_page(self, item):
        result = item.loaders[self.name].result()
        assert result.page is not None, 'The loaded url %s hasn\'t been matched by an URL object' % result.url
        return result.page


class Base(Filter):
    """
    Change the base element used in filters.

    >>> Base(Env('header'), CleanText('./h1'))  # doctest: +SKIP
    """

    def __call__(self, item):
        base = self.select(self.base, item)
        return self.select(self.selector, base)

    def __init__(self, base, selector=None, default=_NO_DEFAULT):
        super(Base, self).__init__(selector, default)
        self.base = base


class Decode(Filter):
    """
    Filter that aims to decode urlencoded strings

    >>> Decode(Env('_id'))  # doctest: +ELLIPSIS
    <weboob.browser.filters.standard.Decode object at 0x...>
    >>> from .html import Link
    >>> Decode(Link('./a'))  # doctest: +ELLIPSIS
    <weboob.browser.filters.standard.Decode object at 0x...>

    """
    def __call__(self, item):
        self.encoding = item.page.ENCODING if item.page.ENCODING else 'utf-8'
        return self.filter(self.select(self.selector, item))

    @debug()
    def filter(self, txt):
        from urllib import unquote
        try:
            txt = unquote(txt.encode('ascii')).decode(self.encoding)
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass

        return txt


class Env(_Filter):
    """
    Filter to get environment value of the item.

    It is used for example to get page parameters, or when there is a parse()
    method on ItemElement.
    """

    def __init__(self, name, default=_NO_DEFAULT):
        super(Env, self).__init__(default)
        self.name = name

    def __call__(self, item):
        try:
            return item.env[self.name]
        except KeyError:
            return self.default_or_raise(ParseError('Environment variable %s not found' % self.name))


class TableCell(_Filter):
    """
    Used with TableElement, it get the cell value from its name.

    For example:

    >>> from weboob.capabilities.bank import Transaction
    >>> from weboob.browser.elements import TableElement, ItemElement
    >>> class table(TableElement):
    ...     head_xpath = '//table/thead/th'
    ...     item_xpath = '//table/tbody/tr'
    ...     col_date =    u'Date'
    ...     col_label =   [u'Name', u'Label']
    ...     class item(ItemElement):
    ...         klass = Transaction
    ...         obj_date = Date(TableCell('date'))
    ...         obj_label = CleanText(TableCell('label'))
    ...
    """

    def __init__(self, *names, **kwargs):
        support_th = kwargs.pop('support_th', False)
        super(TableCell, self).__init__(**kwargs)
        self.names = names

        if support_th:
            self.td = '(./th | ./td)[%s]'
        else:
            self.td = './td[%s]'

    def __call__(self, item):
        for name in self.names:
            idx = item.parent.get_colnum(name)
            if idx is not None:
                ret = item.xpath(self.td % (idx + 1))
                for el in ret:
                    self.highlight_el(el, item)
                return ret

        return self.default_or_raise(ColumnNotFound('Unable to find column %s' % ' or '.join(self.names)))


class RawText(Filter):
    def __init__(self, selector=None, children=False, default=_NO_DEFAULT):
        super(RawText, self).__init__(selector, default=default)
        self.children = children

    @debug()
    def filter(self, el):
        if isinstance(el, (tuple, list)):
            return u' '.join([self.filter(e) for e in el])

        if self.children:
            text = el.text_content()
        else:
            text = el.text

        if text is None:
            result = self.default
        else:
            result = unicode(text)

        return result


class CleanText(Filter):
    """
    Get a cleaned text from an element.

    It first replaces all tabs and multiple spaces
    (including newlines if ``newlines`` is True)
    to one space and strips the result string.

    The result is coerced into unicode, and optionally normalized
    according to the ``normalize`` argument.

    Then it replaces all symbols given in the ``symbols`` argument.

    >>> CleanText().filter('coucou ')
    u'coucou'
    >>> CleanText().filter(u'coucou\xa0coucou')
    u'coucou coucou'
    >>> CleanText(newlines=True).filter(u'coucou\\r\\n coucou ')
    u'coucou coucou'
    >>> CleanText(newlines=False).filter(u'coucou\\r\\n coucou ')
    u'coucou\\ncoucou'
    """

    def __init__(self, selector=None, symbols='', replace=[], children=True, newlines=True, normalize='NFC', **kwargs):
        super(CleanText, self).__init__(selector, **kwargs)
        self.symbols = symbols
        self.toreplace = replace
        self.children = children
        self.newlines = newlines
        self.normalize = normalize

    @debug()
    def filter(self, txt):
        if isinstance(txt, (tuple, list)):
            txt = u' '.join([self.clean(item, children=self.children) for item in txt])

        txt = self.clean(txt, self.children, self.newlines, self.normalize)
        txt = self.remove(txt, self.symbols)
        txt = self.replace(txt, self.toreplace)
        # ensure it didn't become str by mistake
        return unicode(txt)

    @classmethod
    def clean(cls, txt, children=True, newlines=True, normalize='NFC'):
        if not isinstance(txt, basestring):
            if children:
                txt = [t.strip() for t in txt.itertext()]
            else:
                txt = [txt.text.strip()]
            txt = u' '.join(txt)  # 'foo   bar'
        if newlines:
            txt = re.compile(u'\s+', flags=re.UNICODE).sub(u' ', txt)  # 'foo bar'
        else:
            # normalize newlines and clean what is inside
            txt = '\n'.join([cls.clean(l) for l in txt.splitlines()])
        txt = txt.strip()
        # lxml under Python 2 returns str instead of unicode if it is pure ASCII
        txt = unicode(txt)
        # normalize to a standard Unicode form
        if normalize:
            txt = unicodedata.normalize(normalize, txt)
        return txt

    @classmethod
    def remove(cls, txt, symbols):
        for symbol in symbols:
            txt = txt.replace(symbol, '')
        return txt.strip()

    @classmethod
    def replace(cls, txt, replace):
        for before, after in replace:
            txt = txt.replace(before, after)
        return txt


class Lower(CleanText):
    @debug()
    def filter(self, txt):
        txt = super(Lower, self).filter(txt)
        return txt.lower()


class Upper(CleanText):
    @debug()
    def filter(self, txt):
        txt = super(Upper, self).filter(txt)
        return txt.upper()


class Capitalize(CleanText):
    @debug()
    def filter(self, txt):
        txt = super(Capitalize, self).filter(txt)
        return txt.title()


class Currency(CleanText):
    @debug()
    def filter(self, txt):
        txt = super(Currency, self).filter(txt)
        return BaseCurrency.get_currency(txt)


class CleanDecimal(CleanText):
    """
    Get a cleaned Decimal value from an element.

    replace_dots is False by default. A dot is interpreted as a decimal separator.

    If replace_dots is set to True, we remove all the dots. The ',' is used as decimal
    separator (often useful for French values)

    If replace_dots is a tuple, the first element will be used as the thousands separator,
    and the second as the decimal separator.

    See http://en.wikipedia.org/wiki/Thousands_separator#Examples_of_use

    For example, for the UK style (as in 1,234,567.89):

    >>> CleanDecimal('./td[1]', replace_dots=(',', '.'))  # doctest: +SKIP
    """

    def __init__(self, selector=None, replace_dots=False, sign=None, default=_NO_DEFAULT):
        super(CleanDecimal, self).__init__(selector, default=default)
        self.replace_dots = replace_dots
        self.sign = sign

    @debug()
    def filter(self, text):
        if type(text) in (float, int, long):
            text = str(text)

        if empty(text):
            return self.default_or_raise(ParseError('Unable to parse %r' % text))

        original_text = text = super(CleanDecimal, self).filter(text)
        if self.replace_dots:
            if type(self.replace_dots) is tuple:
                thousands_sep, decimal_sep = self.replace_dots
            else:
                thousands_sep, decimal_sep = '.', ','
            text = text.replace(thousands_sep, '').replace(decimal_sep, '.')
        try:
            v = Decimal(re.sub(r'[^\d\-\.]', '', text))
            if self.sign:
                v *= self.sign(original_text)
            return v
        except InvalidOperation as e:
            return self.default_or_raise(e)


class Slugify(Filter):
    @debug()
    def filter(self, label):
        label = re.sub(r'[^A-Za-z0-9]', ' ', label.lower()).strip()
        label = re.sub(r'\s+', '-', label)
        return label


class Type(Filter):
    """
    Get a cleaned value of any type from an element text.
    The type_func can be any callable (class, function, etc.).
    By default an empty string will not be parsed but it can be changed
    by specifying minlen=False. Otherwise, a minimal length can be specified.

    >>> Type(CleanText('./td[1]'), type=int)  # doctest: +SKIP

    >>> Type(type=int).filter('42')
    42
    >>> Type(type=int, default='NaN').filter('')
    'NaN'
    >>> Type(type=str, minlen=False, default='a').filter('')
    ''
    >>> Type(type=str, minlen=0, default='a').filter('')
    'a'
    """

    def __init__(self, selector=None, type=None, minlen=0, default=_NO_DEFAULT):
        super(Type, self).__init__(selector, default=default)
        self.type_func = type
        self.minlen = minlen

    @debug()
    def filter(self, txt):
        if empty(txt):
            return self.default_or_raise(ParseError('Unable to parse %r' % txt))
        if self.minlen is not False and len(txt) <= self.minlen:
            return self.default_or_raise(ParseError('Unable to parse %r' % txt))
        try:
            return self.type_func(txt)
        except ValueError as e:
            return self.default_or_raise(ParseError('Unable to parse %r: %s' % (txt, e)))


class Field(_Filter):
    """
    Get the attribute of object.
    """

    def __init__(self, name):
        super(Field, self).__init__()
        self.name = name

    def __call__(self, item):
        return item.use_selector(getattr(item, 'obj_%s' % self.name), key=self._key)


# Based on nth from https://docs.python.org/2/library/itertools.html
def nth(iterable, n, default=None):
    "Returns the nth item or a default value, n can be negative, or '*' for all"
    if n == '*':
        return iterable
    if n < 0:
        iterable = reversed(list(iterable))
        n = abs(n) - 1
    return next(islice(iterable, n, None), default)


def ordinal(n):
    "To have some readable debug information: '*' => all, 0 => 1st, 1 => 2nd..."
    if n == '*':
        return 'all'
    i = abs(n)
    n = n - 1 if n < 0 else n + 1
    return str(n) + ('th' if i > 2 else ['st', 'nd', 'rd'][i])


class Regexp(Filter):
    r"""
    Apply a regex.

    >>> from lxml.html import etree
    >>> doc = etree.fromstring('<html><body><p>Date: <span>13/08/1988</span></p></body></html>')
    >>> Regexp(CleanText('//p'), r'Date: (\d+)/(\d+)/(\d+)', '\\3-\\2-\\1')(doc)
    u'1988-08-13'

    >>> (Regexp(CleanText('//body'), r'(\d+)', nth=1))(doc)
    u'08'
    >>> (Regexp(CleanText('//body'), r'(\d+)', nth=-1))(doc)
    u'1988'
    >>> (Regexp(CleanText('//body'), r'(\d+)', template='[\\1]', nth='*'))(doc)
    [u'[13]', u'[08]', u'[1988]']
    """

    def __init__(self, selector=None, pattern=None, template=None, nth=0, flags=0, default=_NO_DEFAULT):
        super(Regexp, self).__init__(selector, default=default)
        assert pattern is not None
        self.pattern = pattern
        self._regex = re.compile(pattern, flags)
        self.template = template
        self.nth = nth

    def expand(self, m):
        if self.template is None:
            return next(g for g in m.groups() if g is not None)
        return self.template(m) if callable(self.template) else m.expand(self.template)

    @debug()
    def filter(self, txt):
        if isinstance(txt, (tuple, list)):
            txt = u' '.join([t.strip() for t in txt.itertext()])

        m = self._regex.search(txt) if self.nth == 0 else \
            nth(self._regex.finditer(txt), self.nth)
        if not m:
            msg = 'Unable to find %s %s in %r' % (ordinal(self.nth), self.pattern, txt)
            return self.default_or_raise(RegexpError(msg))

        if isinstance(m, Iterator):
            return map(self.expand, m)

        return self.expand(m)


class Map(Filter):

    def __init__(self, selector, map_dict, default=_NO_DEFAULT):
        super(Map, self).__init__(selector, default=default)
        self.map_dict = map_dict

    @debug()
    def filter(self, txt):
        try:
            return self.map_dict[txt]
        except KeyError:
            return self.default_or_raise(ItemNotFound('Unable to handle %r on %r' % (txt, self.map_dict)))


class DateTime(Filter):
    def __init__(self, selector=None, default=_NO_DEFAULT, dayfirst=False, translations=None,
                 parse_func=parse_date, fuzzy=False):
        super(DateTime, self).__init__(selector, default=default)
        self.dayfirst = dayfirst
        self.translations = translations
        self.parse_func = parse_func
        self.fuzzy = fuzzy

    @debug()
    def filter(self, txt):
        if empty(txt) or txt == '':
            return self.default_or_raise(ParseError('Unable to parse %r' % txt))
        try:
            if self.translations:
                for search, repl in self.translations:
                    txt = search.sub(repl, txt)
            return self.parse_func(txt, dayfirst=self.dayfirst, fuzzy=self.fuzzy)
        except (ValueError, TypeError) as e:
            return self.default_or_raise(ParseError('Unable to parse %r: %s' % (txt, e)))


class Date(DateTime):
    def __init__(self, selector=None, default=_NO_DEFAULT, dayfirst=False, translations=None,
                 parse_func=parse_date, fuzzy=False):
        super(Date, self).__init__(selector, default=default, dayfirst=dayfirst, translations=translations,
                                   parse_func=parse_func, fuzzy=fuzzy)

    @debug()
    def filter(self, txt):
        datetime = super(Date, self).filter(txt)
        if hasattr(datetime, 'date'):
            return datetime.date()
        else:
            return datetime


class DateGuesser(Filter):
    def __init__(self, selector, date_guesser, **kwargs):
        super(DateGuesser, self).__init__(selector)
        self.date_guesser = date_guesser
        self.kwargs = kwargs

    def __call__(self, item):
        values = self.select(self.selector, item)
        date_guesser = self.date_guesser
        # In case Env() is used to kive date_guesser.
        if isinstance(date_guesser, _Filter):
            date_guesser = self.select(date_guesser, item)

        if isinstance(values, basestring):
            values = re.split('[/-]', values)
        if len(values) == 2:
            day, month = map(int, values)
        else:
            raise ParseError('Unable to take (day, month) tuple from %r' % values)
        return date_guesser.guess_date(day, month, **self.kwargs)


class Time(Filter):
    klass = datetime.time
    _regexp = re.compile(r'(?P<hh>\d+)[:h]?(?P<mm>\d+)([:m](?P<ss>\d+))?')
    kwargs = {'hour': 'hh', 'minute': 'mm', 'second': 'ss'}

    def __init__(self, selector=None, default=_NO_DEFAULT):
        super(Time, self).__init__(selector, default=default)

    @debug()
    def filter(self, txt):
        m = self._regexp.search(txt)
        if m:
            kwargs = {}
            for key, index in self.kwargs.iteritems():
                kwargs[key] = int(m.groupdict()[index] or 0)
            return self.klass(**kwargs)

        return self.default_or_raise(ParseError('Unable to find time in %r' % txt))


class Duration(Time):
    klass = datetime.timedelta
    _regexp = re.compile(r'((?P<hh>\d+)[:;])?(?P<mm>\d+)[;:](?P<ss>\d+)')
    kwargs = {'hours': 'hh', 'minutes': 'mm', 'seconds': 'ss'}


class MultiFilter(Filter):
    def __init__(self, *args, **kwargs):
        default = kwargs.pop('default', _NO_DEFAULT)
        super(MultiFilter, self).__init__(args, default)

    def __call__(self, item):
        values = [self.select(selector, item) for selector in self.selector]
        return self.filter(tuple(values))

    def filter(self, values):
        raise NotImplementedError()


class CombineDate(MultiFilter):
    def __init__(self, date, time):
        super(CombineDate, self).__init__(date, time)

    @debug()
    def filter(self, values):
        return datetime.datetime.combine(values[0], values[1])


class Format(MultiFilter):
    def __init__(self, fmt, *args):
        super(Format, self).__init__(*args)
        self.fmt = fmt

    @debug()
    def filter(self, values):
        return self.fmt % values


class BrowserURL(MultiFilter):
    def __init__(self, url_name, **kwargs):
        super(BrowserURL, self).__init__(*kwargs.values())
        self.url_name = url_name
        self.keys = kwargs.keys()

    def __call__(self, item):
        values = super(BrowserURL, self).__call__(item)
        url = getattr(item.page.browser, self.url_name)
        assert isinstance(url, URL), "%s.%s must be an URL object" % (type(item.page.browser).__name__, self.url_name)
        return url.build(**dict(zip(self.keys, values)))

    @debug()
    def filter(self, values):
        return values


class Join(Filter):
    def __init__(self, pattern, selector=None, textCleaner=CleanText, newline=False, addBefore='', addAfter=''):
        super(Join, self).__init__(selector)
        self.pattern = pattern
        self.textCleaner = textCleaner
        self.newline = newline
        self.addBefore = addBefore
        self.addAfter = addAfter

    @debug()
    def filter(self, el):
        items = [self.textCleaner.clean(e) for e in el]
        items = [item for item in items if item]

        if self.newline:
            items = ['%s\r\n' % item for item in items]

        result = self.pattern.join(items)

        if self.addBefore:
            result = '%s%s' % (self.addBefore, result)

        if self.addAfter:
            result = '%s%s' % (result, self.addAfter)

        return result

class Eval(MultiFilter):
    """
    Evaluate a function with given 'deferred' arguments.

    >>> F = Field; Eval(lambda a, b, c: a * b + c, F('foo'), F('bar'), F('baz')) # doctest: +SKIP
    >>> Eval(lambda x, y: x * y + 1).filter([3, 7])
    22
    """
    def __init__(self, func, *args):
        super(Eval, self).__init__(*args)
        self.func = func

    @debug()
    def filter(self, values):
        return self.func(*values)


def test_CleanText():
    # This test works poorly under a doctest, or would be hard to read
    assert CleanText().filter(u' coucou  \n\théhé') == u'coucou héhé'
    assert CleanText().filter('coucou\xa0coucou') == CleanText().filter(u'coucou\xa0coucou') == u'coucou coucou'

    # Unicode normalization
    assert CleanText().filter(u'Éçã') == u'Éçã'
    assert CleanText(normalize='NFKC').filter(u'…') == u'...'
    assert CleanText().filter(u'…') == u'…'
    # Diacritical mark (dakuten)
    assert CleanText().filter(u'\u3053\u3099') == u'\u3054'
    assert CleanText(normalize='NFD').filter(u'\u3053\u3099') == u'\u3053\u3099'
    assert CleanText(normalize='NFD').filter(u'\u3054') == u'\u3053\u3099'
    assert CleanText(normalize=False).filter(u'\u3053\u3099') == u'\u3053\u3099'
