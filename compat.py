# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import os
import sys
import six
import pipes


if six.PY2:
    from pipes import quote
elif six.PY3:
    try: # Python > 3.2
        from shlex import quote
    except ImportError: # Python 3.2
        from pipes import quote


def to_unicode(data):
    if isinstance(data, six.text_type):
        return to_str(data.encode('utf-8', 'surrogateescape'))

    if isinstance(data, six.binary_type):
        return data.decode('utf-8', 'ignore')

    raise ValueError('unrecognized type: {0}'.format(type(data)))


# This version of "which" comes directly from the sources for Python 3.6. It's
# included here for users of Python 3.2 or older.
def compat_which(cmd, mode=os.F_OK | os.X_OK, path=None):
    def _access_check(fn, _mode):
        return (os.path.exists(fn) and os.access(fn, _mode)
                and not os.path.isdir(fn))

    if os.path.dirname(cmd):
        if _access_check(cmd, mode):
            return cmd
        return None

    if path is None:
        path = os.environ.get("PATH", os.defpath)
    if not path:
        return None
    path = path.split(os.pathsep)

    if sys.platform == "win32":
        if os.curdir not in path:
            path.insert(0, os.curdir)

        pathext = os.environ.get("PATHEXT", "").split(os.pathsep)
        if any(cmd.lower().endswith(ext.lower()) for ext in pathext):
            files = [cmd]
        else:
            files = [cmd + ext for ext in pathext]
    else:
        files = [cmd]

    seen = set()
    for _dir in path:
        normdir = os.path.normcase(_dir)
        if normdir not in seen:
            seen.add(normdir)
            for thefile in files:
                name = os.path.join(_dir, thefile)
                if _access_check(name, mode):
                    return name
    return None

try:
    from shutil import which
except ImportError:
    which = compat_which

