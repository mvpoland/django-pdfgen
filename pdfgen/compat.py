from __future__ import print_function
from future import standard_library
standard_library.install_aliases()
import sys


# cStringIO only if it's available, otherwise StringIO
try:
    from cStringIO import StringIO
    from io import BytesIO
except ImportError:
    from io import StringIO, BytesIO


# lxml etree if it's available, otherwise find in any known place
try:
    from lxml import etree
except ImportError:
    try:
        # Python 2.5
        import xml.etree.cElementTree as etree
    except ImportError:
        try:
            # Python 3.x
            import xml.etree.ElementTree as etree
        except ImportError:
            print("Failed to import ElementTree from any known place")


# Python versions
PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
