# -*- coding: utf-8 -*-

"""
compat
~~~~~~~~~~~~~~~
This module handles import compatibility issues between Python 2 and
Python 3.

Copied from requests.
"""

import sys

__all__ = ['IS_PY2', 'IS_PY3', 'str', 'BytesIO']

# -------
# Pythons
# -------

# Syntax sugar.
_VER = sys.version_info

#: Python 2.x?
IS_PY2 = (_VER[0] == 2)

#: Python 3.x?
IS_PY3 = (_VER[0] == 3)

if IS_PY2:
    from StringIO import StringIO as BytesIO

    str = unicode  # pylint: disable=redefined-builtin,invalid-name

elif IS_PY3:
    from io import BytesIO

    str = str  # pylint: disable=redefined-builtin,invalid-name
