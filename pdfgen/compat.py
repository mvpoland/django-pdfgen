# lxml etree if it's available, otherwise find in any known place
try:
    from lxml import etree
except ImportError:
    try:
        # Python 3.x
        import xml.etree.ElementTree as etree
    except ImportError:
        print("Failed to import ElementTree from any known place")
