from __future__ import print_function
from builtins import str
from builtins import range
from builtins import object
import logging
import xml.dom.minidom

from ast import literal_eval

from django.conf import settings
from django.contrib.staticfiles.finders import find
from django.utils.encoding import force_str

from reportlab.lib import pagesizes, colors
from reportlab.lib.units import cm, mm, toLength
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, Spacer, Image, PageBreak
from reportlab.platypus.doctemplate import SimpleDocTemplate
from svglib.svglib import SvgRenderer

from pdfgen.compat import etree, StringIO, BytesIO, PY3
from pdfgen.barcode import Barcode


logger = logging.getLogger(__name__)


CSS_DICT = {
    'padding-left': 'LEFTPADDING',
    'padding-right': 'RIGHTPADDING',
    'padding-top': 'TOPPADDING',
    'padding-bottom': 'BOTTOMPADDING',
    'border-left': 'LINEBEFORE',
    'border-right': 'LINEAFTER',
    'border-top': 'LINEABOVE',
    'border-bottom': 'LINEBELOW',
    'text-align': 'alignment',
    'font-family': 'fontName',
    'font-size': 'fontSize',
    'color': 'textColor',
    'left': TA_LEFT,
    'right': TA_RIGHT,
    'center': TA_CENTER,
    'justify': TA_JUSTIFY,
}

PAGE_SIZE_MAPPING = {
    'A0': pagesizes.A0,
    'A1': pagesizes.A1,
    'A2': pagesizes.A2,
    'A3': pagesizes.A3,
    'A4': pagesizes.A4,
    'A5': pagesizes.A5,
    'A6': pagesizes.A6,

    'B0': pagesizes.B0,
    'B1': pagesizes.B1,
    'B2': pagesizes.B2,
    'B3': pagesizes.B3,
    'B4': pagesizes.B4,
    'B5': pagesizes.B5,
    'B6': pagesizes.B6,

    'LETTER': pagesizes.LETTER,
    'LEGAL': pagesizes.LEGAL,
    'ELEVENSEVENTEEN': pagesizes.ELEVENSEVENTEEN,
}


def _new_draw(self):
    self.canv.setLineWidth(0.2 * mm)
    self.drawPara(self.debug)


def patch_reportlab():
    setattr(Paragraph, 'draw', _new_draw)


patch_reportlab()


def debug_print(text):
    if settings.DEBUG:
        logger.debug(text)


def split_ignore(haystack, needle, ignore_start=None, ignore_end=None):
    parts = []
    ignore_start = ignore_start or '<![CDATA['
    ignore_end = ignore_end or ']]>'
    haystack_len = len(haystack)
    needle_len = len(needle)
    ignore_start_len = len(ignore_start)
    ignore_end_len = len(ignore_end)
    ignore = False
    i = 0
    pi = -1
    unignored = False
    while i < haystack_len:
        unignored = False
        if ignore and i+ignore_end_len <= haystack_len and haystack[i:i+ignore_end_len] == ignore_end:
            ignore = False
            unignored = True
        if not ignore and i+needle_len <= haystack_len and haystack[i:i+needle_len] == needle:
            part = haystack[pi+1:i].replace(ignore_start, '').replace(ignore_end, '')
            i += needle_len-1
            pi = i
            parts.append(part)
        if not ignore and not unignored and i+ignore_start_len <= haystack_len and haystack[i:i+ignore_start_len] == ignore_start:
            ignore = True
        i += 1
    parts.append(haystack[pi+1:].replace(ignore_start, '').replace(ignore_end, ''))
    return parts


class Parser(object):
    styles = None
    out_buffer = None
    doc = None
    unit = cm
    parts = None
    parts_buffer_dict = {}
    parts_buffer = None
    fonts = {}

    style_stack = []
    svg_dict = {}
    img_dict = {}

    def import_pdf_font(self, base_name, face_name):
        if self.fonts.get(face_name) is None:
            afm = find(base_name + '.afm')
            pfb = find(base_name + '.pfb')

            try:
                face = pdfmetrics.EmbeddedType1Face(afm, pfb)

                pdfmetrics.registerTypeFace(face)
                font = pdfmetrics.Font(face_name, face_name, 'WinAnsiEncoding')
                pdfmetrics.registerFont(font)
            except:
                pass
        else:
            self.fonts[face_name] = True

    def reset_table(self):
        self.table_data = []
        self.table_row = []
        self.table_cols = []
        self.table_styles = []
        self.table_align = 'CENTER'

    def append_to_parts(self, item):
        if self.parts_buffer is not None:
            self.parts_buffer_dict[self.parts_buffer].append(item)
            debug_print('Added part to %s' % self.parts_buffer)
        else:
            self.parts.append(item)
            debug_print('Added part to root parts')

    @staticmethod
    def default_out_buffer():
        if PY3:
            return BytesIO()
        return StringIO()

    def parse_parts(self, buffer):
        # prepare ReportLab
        self.styles = getSampleStyleSheet()
        self.style_stack.append(self.styles['Normal'])
        if self.out_buffer is None:
            self.out_buffer = self.default_out_buffer()
        self.parts = []

        # prepare for parsing
        i = 0
        buffer_len = len(buffer)
        # Possible modes: 0 = normal, 1 = table row, 2 = insert object
        mode = 0
        new_line = True
        new_para = True
        cue = 0
        content = ''
        raw_table_data = ''
        self.reset_table()
        obj = None

        style_stack = self.style_stack

        paragraphs = split_ignore(buffer, '\n\n', '[[[block', ']]]')

        for p in paragraphs:
            lines = p.split('\n')
            content = ''
            for line in lines:
                c = line[:1]
                if c == '#':
                    debug_print('[comment]')
                elif c == '$':
                    self.parse_paragraph_style(line[1:])
                elif c == '~':
                    debug_print('[document element %s]' % line[1])
                    elem = line[1]
                    endpos = line.find(']', 2)
                    if elem == 'D':
                        self.handle_document_properties(line[3:endpos], line[endpos+1:])
                    elif elem == 'T':
                        if line[2] == '$':
                            # table style
                            raw_style = line[3:]
                            style = self.parse_table_style(raw_style)
                            self.table_styles.append(style)
                        else:
                            self.table_cols = list(float(n) * self.unit for n in line[3:endpos].split('|'))
                            align = line[endpos+1:endpos+2]
                            if align == '<':
                                self.table_align = 'LEFT'
                            elif align == '>':
                                self.table_align = 'RIGHT'
                    elif elem == 'B':
                        self.append_to_parts(PageBreak())
                    elif elem == 'S':
                        self.append_to_parts(Spacer(1, toLength(line[2:])))
                    elif elem == 'V':
                        svg_info_raw = line[3:endpos]
                        svg_info = svg_info_raw.split(';')[:7]
                        if len(svg_info) == 1:
                            mode = 2
                            obj = self.svg_dict[svg_info[0]]
                        else:
                            if len(svg_info) == 7:
                                svg_name, svg_scale, svg_w, svg_h, svg_path, svg_find, svg_replace = svg_info
                            else:
                                svg_name, svg_scale, svg_w, svg_h, svg_path = svg_info

                            svg_file = open(find(svg_path), 'rb')
                            svg_data = svg_file.read()
                            svg_file.close()

                            if len(svg_info) == 7:
                                svg_data = svg_data.replace(svg_find, svg_replace)

                            svg = xml.dom.minidom.parseString(svg_data).documentElement

                            svgRenderer = SvgRenderer(None)
                            svgRenderer.render(svg)
                            svg_obj = svgRenderer.finish()

                            #svg_obj = svg2rlg(settings.MEDIA_ROOT + svg_path)
                            svg_obj.scale(float(svg_scale), float(svg_scale))
                            svg_obj.asDrawing(float(svg_w) * self.unit, float(svg_h) * self.unit)
                            self.svg_dict[svg_name] = svg_obj
                    elif elem == 'I':
                        img_info_raw = line[3:endpos]
                        img_info = img_info_raw.split(';')[:4]
                        if len(img_info) == 1:
                            mode = 2
                            obj = self.img_dict[img_info[0]]
                        else:
                            img_name, img_w, img_h, img_path = img_info
                            img_obj = Image(
                                find(img_path),
                                width=self.unit * float(img_w),
                                height=self.unit * float(img_h)
                            )
                            align = line[endpos+1:endpos+2]
                            if align == '<':
                                img_obj.hAlign = 'LEFT'
                            elif align == '>':
                                img_obj.hAlign = 'RIGHT'
                            self.img_dict[img_name] = img_obj
                    elif elem == 'C':
                        barcode_info_raw = line[3:endpos]
                        barcode_info = barcode_info_raw.split(';')[:6]
                        if len(barcode_info) == 1:
                            mode = 2
                            obj = self.img_dict[barcode_info[0]]
                        else:
                            barcode_name, barcode_type, barcode_scale, barcode_w, barcode_h, barcode_data = barcode_info
                            barcode_obj = Barcode(
                                library=find('common/pdf_img/barcode.ps'),
                                width=self.unit * float(barcode_w),
                                height=self.unit * float(barcode_h),
                                data=barcode_data,
                                scale=float(barcode_scale),
                                type=barcode_type
                            )
                            align = line[endpos+1:endpos+2]
                            if align == '<':
                                barcode_obj.hAlign = 'LEFT'
                            elif align == '>':
                                barcode_obj.hAlign = 'RIGHT'
                            self.img_dict[barcode_name] = barcode_obj
                    elif elem == 'F':
                        font_info_raw = line[3:endpos]
                        font_info = font_info_raw.split(';')[:2]
                        self.import_pdf_font(font_info[1], font_info[0])
                    elif elem == 'P':
                        if '[' in line:
                            self.parts_buffer = line[3:endpos]
                            self.parts_buffer_dict[self.parts_buffer] = []
                        else:
                            self.parts_buffer = None
                elif c == '[':
                    mode = 1
                    raw_table_data += line + '\n'
                elif c == '\n':
                    pass
                else:
                    if mode == 0:
                        content += line + '\n'
                    elif mode == 1:
                        raw_table_data += line + '\n'

            if mode == 0:
                if content != '':
                    self.append_to_parts(Paragraph(content, self.style_stack[-1] if len(self.style_stack) > 0 else self.styles['Normal']))
                content = ''

            if mode == 1:
                td = raw_table_data
                td_len = len(td)
                i = 0
                while i < td_len:
                    c = td[i]
                    c_1 = td[i-1:i]
                    if c == '[' and c_1 != '\\':
                        cue = i + 1
                    if (c == '|' or c == ']') and c_1 != '\\':
                        cell_content = td[cue:i]
                        pop_after_cell = False
                        if cell_content[:1] == '$':
                            if ' ' in cell_content:
                                style, cell_content = cell_content.split(None, 1)
                                style = style[1:]
                            else:
                                style = ''
                                cell_content = cell_content[1:]
                            self.parse_paragraph_style(style)
                        if cell_content[-1:] == '$':
                            cell_content = cell_content[:-1]
                            pop_after_cell = True
                        if cell_content[:2] == '~V':
                            svg_name = cell_content[2:]
                            self.table_row.append(self.svg_dict[svg_name])
                        elif cell_content[:2] == '~I':
                            img_name = cell_content[2:]
                            self.table_row.append(self.img_dict[img_name])
                        elif cell_content[:2] == '~P':
                            self.table_row.append(self.parts_buffer_dict[cell_content[2:]])
                        else:
                            self.table_row.append(Paragraph(cell_content, self.style_stack[-1] if len(self.style_stack) > 0 else self.styles['Normal']))

                        if pop_after_cell:
                            self.parse_paragraph_style('')

                        cue = i + 1
                        if c == ']':
                            self.table_data.append(self.table_row)
                            self.table_row = []

                    i += 1
                if len(self.table_data) > 0:
                    self.append_to_parts(Table(self.table_data, self.table_cols, hAlign=self.table_align, style=self.table_styles))
                self.reset_table()
                raw_table_data = ''

            if mode == 2:
                if obj is not None:
                    self.append_to_parts(obj)
                    obj = None

            mode = 0

        return self.parts

    def merge_parts(self, parts):
        if self.doc is not None:
            self.doc.build(parts)
            output_data = self.out_buffer.getvalue()
            self.out_buffer.close()

            return output_data
        else:
            print('Error: missing document instance')
            return None

    def parse(self, buffer):
        parts = self.parse_parts(buffer)
        return self.merge_parts(parts)

    def handle_document_properties(self, raw_properties, title):
        __, raw_unit, raw_margins = raw_properties.split(';')
        doc_format = pagesizes.A4
        unit = toLength('1%s' % raw_unit)
        self.unit = unit
        top_margin, right_margin, bottom_margin, left_margin = (float(i) for i in raw_margins.split(','))

        if self.doc is not None:
            return

        def make_canvas(*args, **kwargs):
            canvas = Canvas(*args, **kwargs)
            canvas.setLineWidth(0.25)
            return canvas

        self.doc = SimpleDocTemplate(
            self.out_buffer,
            pagesize=doc_format,
            title=title,
            topMargin=top_margin * unit,
            leftMargin=left_margin * unit,
            rightMargin=right_margin * unit,
            bottomMargin=bottom_margin * unit,
            canvasmaker=make_canvas,
        )

    def parse_table_style(self, raw_style):
        parts = raw_style.split('$')
        topleft, bottomright = (list(int(q) for q in p.split(',')) for p in parts[0].split(':'))
        top = topleft[0]
        left = topleft[-1]
        bottom = bottomright[0]
        right = bottomright[-1]
        cells = [(top, left), (bottom, right)]
        desc = CSS_DICT.get(parts[1], parts[1].upper())
        params = parts[2:]

        for i in range(len(params)):
            param = params[i]
            if param[0] == '#':
                params[i] = colors.HexColor(int('0x' + param[1:]))
            elif param[-1] == 'u':
                params[i] = float(param[:-1])*self.unit
            else:
                try:
                    floatval = float(param)
                    params[i] = floatval
                except ValueError:
                    params[i] = param.upper()

        style = [desc] + cells + params
        return style

    def parse_paragraph_style(self, raw_style):
        if '=' in raw_style:
            # define
            name, definition = (i.strip() for i in raw_style.split('=', 1))
            if '+' in definition:
                source_name, definition = (i.strip() for i in definition.split('+', 1))
            else:
                source_name = None

            def_dict = literal_eval(definition)
            new_dict = {}
            for k in list(def_dict.keys()):
                v = def_dict[k]
                nk = CSS_DICT.get(k, k)
                # translate v
                v = CSS_DICT.get(v, v)
                if nk == 'fontSize' or nk == 'leading':
                    v = toLength(v)
                elif nk == 'color':
                    v = colors.HexColor(int('0x' + v[1:], 0))
                new_dict[nk] = v

            if 'leading' not in new_dict and 'fontSize' in new_dict:
                new_dict['leading'] = new_dict['fontSize'] + 2.0

            if source_name is not None:
                source_dict = self.styles[source_name].__dict__.copy()
                source_dict.update(new_dict)
                new_dict = source_dict

            new_dict.update({'name': name})

            if name in self.styles:
                self.styles[name].__dict__.update(new_dict)
            else:
                self.styles.add(ParagraphStyle(**new_dict))

        else:
            name = raw_style.strip()
            if name == 'end' or name == '':
                self.style_stack.pop()
            elif name in self.styles:
                style = self.styles[name]
                self.style_stack.append(style)


def inner_xml(e):
    return etree.tostring(e).strip()[len(e.tag)+2:-len(e.tag)-3]


class XmlParser(object):
    """
    Management command to create a pdf
    """

    document = None
    styles = None
    out_buffer = None
    style_stack = None
    barcode_library = ''
    fonts = {}
    #: the Django MEDIA_URL
    media_url = ''
    #: the Django STATIC_URL
    static_url = ''

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.out_buffer = self.default_out_buffer()
        self.style_stack = []
        self.media_url = getattr(settings, 'MEDIA_URL', '')
        self.static_url = getattr(settings, 'STATIC_URL', '')

    @staticmethod
    def default_out_buffer():
        if PY3:
            return BytesIO()
        return StringIO()

    def get_from_url(self, url):
        """
        For a given URL, return the matching path to the directory.

        Support MEDIA_URL and STATIC_URL
        """
        if self.static_url and url.startswith(self.static_url):
            url = url.replace(self.static_url, '', 1)
        elif self.media_url and url.startswith(self.media_url):
            url = url.replace(self.media_url, '', 1)

        return find(url)

    def merge_parts(self, parts):
        if self.document is not None:
            self.document.build(parts)
            output_data = self.out_buffer.getvalue()
            self.out_buffer.close()

            return output_data
        else:
            return None

    def parse(self, buffer):
        parts = self.parse_parts(buffer)
        return self.merge_parts(parts)

    def parse_parts(self, buffer):
        xdoc = etree.fromstring(force_str(buffer))
        return list(self.parse_element(xdoc))

    def parse_element(self, e):
        method = getattr(self, str(e.tag), self.parse_children)
        for i in method(e):
            yield i

    def parse_children(self, e):
        for c in e:
            for i in self.parse_element(c):
                yield i

    def doc(self, e):
        doc_format = e.get('format', 'A4')
        raw_margins = e.get('margin', '2cm, 2cm, 2cm, 2cm')
        title = e.get('title')

        if ',' in doc_format:
            w, h = (toLength(i.strip()) for i in doc_format.split(','))
            doc_format = (w, h)
        else:
            doc_format = PAGE_SIZE_MAPPING.get(doc_format.upper(), pagesizes.A4)

        top_margin, right_margin, bottom_margin, left_margin = (toLength(i.strip()) for i in raw_margins.split(','))

        def make_canvas(*args, **kwargs):
            canvas = Canvas(*args, **kwargs)
            canvas.setLineWidth(0.25)
            return canvas

        if self.document is None:
            self.document = SimpleDocTemplate(
                self.out_buffer,
                pagesize=doc_format,
                title=title,
                topMargin=top_margin,
                leftMargin=left_margin,
                rightMargin=right_margin,
                bottomMargin=bottom_margin,
                canvasmaker=make_canvas
            )

        for i in self.parse_children(e):
            yield i

    def style(self, e):
        name = e.get('name')
        source_name = e.get('base', None)
        def_dict = dict(e.attrib)

        del def_dict['name']
        if 'base' in def_dict:
            del def_dict['base']

        new_dict = {}
        for k in list(def_dict.keys()):
            v = def_dict[k]
            nk = CSS_DICT.get(k, k)
            # translate v
            v = CSS_DICT.get(v, v)
            if nk == 'fontSize' or nk == 'leading':
                v = toLength(v)
            elif nk == 'color':
                v = colors.HexColor(int('0x' + v[1:], 0))
            new_dict[nk] = v

        if 'leading' not in new_dict and 'fontSize' in new_dict:
            new_dict['leading'] = new_dict['fontSize'] + 2.0

        if source_name is not None:
            source_dict = self.styles[source_name].__dict__.copy()
            source_dict.update(new_dict)
            new_dict = source_dict

        new_dict.update({'name': name})

        if name in self.styles:
            self.styles[name].__dict__.update(new_dict)
        else:
            self.styles.add(ParagraphStyle(**new_dict))

        # make this function an empty generator
        yield

    def font(self, e):
        name = e.get('name')
        path = e.get('src')
        self.import_pdf_font(path, name)

        # make this function an empty generator
        yield

    def div(self, e):
        style = e.get('style', None)

        if style is not None:
            self.style_stack.append(self.styles[style])

        parts = list(self.parse_children(e))

        if style is not None:
            self.style_stack.pop()

        for i in parts:
            yield i

    def p(self, e):
        data = inner_xml(e)
        para = Paragraph(data, self.style_stack[-1] if len(self.style_stack) > 0 else self.styles['Normal'])
        yield para

    def tstyle(self, e):
        area = e.get('area', '0:-1')

        topleft, bottomright = (list(int(q) for q in p.split(',')) for p in area.split(':'))
        top = topleft[0]
        left = topleft[-1]
        bottom = bottomright[0]
        right = bottomright[-1]
        cells = [(top, left), (bottom, right)]

        tstyle_dict = dict(e.attrib)
        if 'area' in tstyle_dict:
            del tstyle_dict['area']

        if 'border' in tstyle_dict:
            border = tstyle_dict['border']
            tstyle_dict.update({
                'border-left': border,
                'border-right': border,
                'border-top': border,
                'border-bottom': border
            })
            del tstyle_dict['border']

        if 'padding' in tstyle_dict:
            padding = tstyle_dict['padding']
            tstyle_dict.update({
                'padding-left': padding,
                'padding-right': padding,
                'padding-top': padding,
                'padding-bottom': padding
            })
            del tstyle_dict['padding']

        for key in list(tstyle_dict.keys()):
            value = tstyle_dict[key]
            desc = CSS_DICT.get(key, key.upper())
            params = value.split(',')

            for i in range(len(params)):
                param = params[i].strip()
                if param[0] == '#':
                    params[i] = colors.HexColor(int('0x' + param[1:], 0))
                else:
                    try:
                        floatval = toLength(param)
                        params[i] = floatval
                    except ValueError:
                        params[i] = param.upper()

            yield [desc] + cells + params

    def tr(self, e):
        for c in e:
            if c.tag == 'td':
                yield list(self.parse_children(c)) if len(c) else None

    def table(self, e):
        cols = [toLength(i.strip()) for i in e.get('cols').split(',')]

        height = e.get('height')
        if height and len(height.split(',')) > 1:
            height = [toLength(i.strip()) for i in height.split(',')]
        elif height:
            height = toLength(height)

        align = e.get('align', 'left').upper()

        tstyles = []
        rows = []

        for c in e:
            if c.tag == 'tstyle':
                tstyles += list(self.tstyle(c))
            else:
                rows.append(list(self.parse_element(c)))

        table_obj = Table(rows, cols, rowHeights=height, hAlign=align, style=tstyles)
        yield table_obj

    def pagebreak(self, e):
        yield PageBreak()

    def sign(self, e):
        text = e.get('text')
        scale = float(e.get('scale', '1.0'))
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))

        template = """
        <table cols="9.9cm, 1.9cm" align="right">
            <tstyle padding="0" />
            <tstyle area="0,0:-1,-1" padding-left="0.5cm"/>
            <tr>
                <td>
                    <p>................................................................</p>
                    <p><font size="8pt">{text}</font></p>
                </td>
                <td>
                    <vector src="common/pdf_img/left-pointing-arrow.svg" scale="{scale}" width="{width}" height="{height}" />
                </td>
            </tr>
        </table>
        """.format(
            text=text,
            scale=scale,
            width=width,
            height=height,
        )
        element = self.parse_parts(template)
        for i in element:
            yield i

    def spacer(self, e):
        width = toLength(e.get('width', '1pt'))
        height = toLength(e.get('height'))
        yield Spacer(width, height)

    def vector(self, e):
        scale = float(e.get('scale', '1.0'))
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        path = e.get('src')
        search = e.get('search', None)
        replace = e.get('replace', None)

        with open(self.get_from_url(path), 'rb') as fh:
            data = fh.read()
            if search is not None:
                data = data.replace(search.encode(), replace.encode())

        svg = etree.fromstring(data)
        renderer = SvgRenderer(None)
        drawing = renderer.render(svg)
        drawing.scale(scale, scale)
        drawing.asDrawing(width, height)

        yield drawing

    def img(self, e):
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        path = e.get('src')
        align = e.get('align', 'left').upper()

        img_obj = Image(self.get_from_url(path), width=width, height=height)
        img_obj.hAlign = align

        yield img_obj

    def barcode(self, e):
        scale = float(e.get('scale', '1.0'))
        width = toLength(e.get('width'))
        height = toLength(e.get('height'))
        value = e.get('value')
        align = e.get('align', 'left').upper()
        barcode_type = e.get('type', 'datamatrix')

        barcode_obj = Barcode(
            library=self.barcode_library,
            width=width,
            height=height,
            data=value,
            scale=scale,
            type=barcode_type,
            align=align.lower()
        )

        barcode_obj.hAlign = align

        yield barcode_obj

    def import_pdf_font(self, base_name, face_name):
        if self.fonts.get(face_name, None) is None:
            afm = find(base_name + '.afm')
            pfb = find(base_name + '.pfb')
            ttf = find(base_name + '.ttf')

            if afm:
                try:
                    face = pdfmetrics.EmbeddedType1Face(afm, pfb)

                    pdfmetrics.registerTypeFace(face)
                    font = pdfmetrics.Font(face_name, face_name, 'WinAnsiEncoding')
                    pdfmetrics.registerFont(font)
                except:
                    pass
            elif ttf:
                pdfmetrics.registerFont(TTFont(face_name, ttf))
            else:
                raise Exception('Cannot find font %s (tried .afm, .pfb and .ttf)' % base_name)
        else:
            self.fonts[face_name] = True
