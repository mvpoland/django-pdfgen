from django.test import TestCase

from pdfgen.parser import XmlParser


class SimpleParserTest(TestCase):

    def _convert_to_str(self, text):
        return str(text, 'utf-8', 'ignore')

    def test_simple_test_xml_parser(self):
        xml_template = """
            <doc format="A4" title="Test" margin="0cm, 2cm, 0cm, 2cm">
                <style name="Normal" font-family="Helvetica" font-size="11pt" color="#666666"/>
                <div style="Normal">
                   <p>Example document</p>
                </div>
            </doc>
            """.strip()
        document_parser = XmlParser()

        output = document_parser.parse(xml_template)

        self.assertIsNotNone(output)
        self.assertIn("%PDF-1.4", self._convert_to_str(output))

    def test_xml_with_vector(self):
        xml_template = """
        <doc format="A4" title="Test" margin="0cm, 2cm, 0cm, 2cm">
            <style name="Normal" font-family="Helvetica" font-size="11pt" color="#666666"/>
            <div style="Normal">
                <table cols="9.9cm" align="center">
                    <tstyle padding="0"/>
                    <tr>
                        <td>
                            <vector src="sim_placeholder.svg" scale="0.8" width="9.9cm" height="5.8cm" search="!cardnumber!" replace="{{ cardnumber }}"/>
                        </td>
                    </tr>
                </table>
            </div>
        </doc>
        """.strip()
        document_parser = XmlParser()

        output = document_parser.parse(xml_template)

        self.assertIsNotNone(output)
        self.assertIn("%PDF-1.4", self._convert_to_str(output))

