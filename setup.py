from setuptools import setup, find_packages

from pdfgen import __version__


setup(
    name="django-pdfgen",
    version=__version__,
    url="https://github.com/mvpoland/django-pdfgen",
    license="BSD",
    description="Generation of PDF documents",
    long_description=open("README.rst", "r").read(),
    author="Jef Geskens, City Live nv",
    packages=find_packages("."),
    install_requires=[
        "reportlab==3.5.23",
        "PyPDF2==1.19",
        "svglib==0.9.1",
    ],
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Operating System :: OS Independent",
        "Environment :: Web Environment",
        "Topic :: Utilities",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 1.9",
    ],
)
