import StringIO
from itertools import repeat

from pdfgen.parser import Parser, XmlParser, find
from PyPDF2 import PdfFileMerger, PdfFileReader

from django.http import HttpResponse, StreamingHttpResponse
from django.template.context import Context
from django.template.loader import render_to_string
from django.utils import translation


def get_parser(template_name):
    """
    Get the correct parser based on the file extension
    """
    import os

    if template_name[-4:] == '.xml':
        parser = XmlParser()
        # set the barcode file
        parser.barcode_library = find('common/pdf_img/barcode.ps')
        return parser
    else:
        return Parser()


def render_to_pdf_data(template_name, context, context_instance=None):
    """
    Parse the template into binary PDF data
    """
    context_instance = context_instance or Context()

    input = render_to_string(template_name, context, context_instance)
    parser = get_parser(template_name)

    return parser.parse(input)


def render_to_pdf_download(template_name, context, context_instance=None, filename=None):
    """
    Parse the template into a download
    """
    context_instance = context_instance or Context()

    response = HttpResponse()
    response['Content-Type'] = 'application/pdf'
    response['Content-Disposition'] = u'attachment; filename=%s' % (filename or u'document.pdf')

    input = render_to_string(template_name, context, context_instance)

    parser = get_parser(template_name)
    output = parser.parse(input)

    response.write(output)

    return response


def multiple_templates_to_pdf_download(template_names, context, context_instance=None, filename=None):
    """
    Render multiple templates with the same context into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        zip(repeat(context, len(template_names)), template_names),
        context_instance=context_instance,
        filename=filename
    )


def multiple_contexts_to_pdf_download(template_name, contexts, context_instance=None, filename=None):
    """
    Render a single template with multiple contexts into a single download
    """
    return multiple_contexts_and_templates_to_pdf_download(
        zip(contexts, repeat(template_name, len(contexts))),
        context_instance=context_instance,
        filename=filename
    )


def _merge_pdf(readers_list):
    merger = PdfFileMerger()
    for obj in readers_list:
        merger.append(obj)

    output = StringIO.StringIO()
    merger.write(output)
    output = output.getvalue()
    return output


def _get_chunked_pdf(contexts_templates, context_instance):
    """
    Stream merged PDF file
    """
    readers_list = []
    count = 0
    remainder = len(contexts_templates) % 10
    base = len(contexts_templates) - remainder

    for context, template_name in contexts_templates:
        count += 1
        parser = get_parser(template_name)
        if 'language' in context:
            translation.activate(context['language'])

        input_data = render_to_string(template_name, context, context_instance)
        outstream = StringIO.StringIO()
        outstream.write(parser.parse(input_data))
        reader = PdfFileReader(outstream)
        if reader not in readers_list:
            readers_list.append(reader)

        if count < base:
            if count % 10 == 0:
                yield _merge_pdf(readers_list)
            else:
                continue
        else:
            yield _merge_pdf(readers_list)


def multiple_contexts_and_templates_to_pdf_download(contexts_templates, context_instance=None, filename=None):
    """
    Render multiple templates with multiple contexts into a single download
    """
    context_instance = context_instance or Context()

    old_lang = translation.get_language()
    response = StreamingHttpResponse(
        _get_chunked_pdf(contexts_templates, context_instance),
        content_type="application/pdf"
    )
    response['Content-Disposition'] = u'attachment; filename=%s' % (filename or u'document.pdf')

    translation.activate(old_lang)
    return response
