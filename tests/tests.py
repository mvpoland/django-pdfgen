from builtins import str
from django.test import TestCase

from pdfgen.parser import XmlParser
from pdfgen.compat import PY3


class SimpleParserTest(TestCase):

    def setUp(self):
        self.xml_template = """
        <doc format="A4" title="Test" margin="0cm, 2cm, 0cm, 2cm">
            <style name="Normal" font-family="Helvetica" font-size="11pt" color="#666666"/>
            <div style="Normal">
               <p>Example document</p>
            </div>
        </doc>
        """.strip()

    def _convert_to_str(self, text):
        if PY3:
            return str(text, 'utf-8', 'ignore')
        return text

    def test_simple_test_xml_parser(self):
        document_parser = XmlParser()
        output = document_parser.parse(self.xml_template)
        self.assertIsNotNone(output)
        self.assertIn("%PDF-1.4", self._convert_to_str(output))
