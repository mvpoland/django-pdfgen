from io import StringIO
from itertools import repeat

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import translation

from pdfgen.parser import Parser, XmlParser, find

from pypdf import PdfMerger, PdfReader


def get_parser(template_name):
    """
    Get the correct parser based on the file extension
    """
    if template_name[-4:] == '.xml':
        parser = XmlParser()
        # set the barcode file
        parser.barcode_library = find('common/pdf_img/barcode.ps')
        return parser
    else:
        return Parser()


def render_to_pdf_data(template_name, context, request=None):
    """
    Parse the template into binary PDF data
    """

    input = render_to_string(template_name, context, request=request)
    parser = get_parser(template_name)

    return parser.parse(input)


def render_to_pdf_download(template_name, context, request=None, filename=None):
    """
    Parse the template into a download
    """

    response = HttpResponse()
    response['Content-Type'] = 'application/pdf'
    response['Content-Disposition'] = u'attachment; filename=%s' % (filename or u'document.pdf')

    input = render_to_string(template_name, context, request=request)

    parser = get_parser(template_name)
    output = parser.parse(input)

    response.write(output)

    return response


def multiple_templates_to_pdf_download(template_names, context, request=None, filename=None):
    """
    Render multiple templates with the same context into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        list(zip(repeat(context, len(template_names)), template_names)),
        request=request,
        filename=filename
    )


def multiple_contexts_to_pdf_download(template_name, contexts, request=None, filename=None):
    """
    Render a single template with multiple contexts into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        list(zip(contexts, repeat(template_name, len(contexts)))),
        request=request,
        filename=filename
    )


def multiple_contexts_and_templates_to_pdf_download(contexts_templates, request=None, filename=None):
    """
    Render multiple templates with multiple contexts into a single download
    """

    response = HttpResponse()
    response['Content-Type'] = 'application/pdf'
    response['Content-Disposition'] = u'attachment; filename=%s' % (filename or u'document.pdf')

    merger = PdfMerger()

    old_lang = translation.get_language()

    for context, template_name in contexts_templates:
        parser = get_parser(template_name)
        if 'language' in context:
            translation.activate(context['language'])
        input = render_to_string(template_name, context, request=request)

        outstream = StringIO()
        outstream.write(parser.parse(input))
        reader = PdfReader(outstream)
        merger.append(reader)

    translation.activate(old_lang)

    output = StringIO()
    merger.write(output)
    output = output.getvalue()

    response.write(output)

    return response
