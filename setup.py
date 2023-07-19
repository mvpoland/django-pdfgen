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
        "reportlab==4.0.4",
        "pypdf==3.10.0",
        "svglib==0.9.4",
    ],
    python_requires=">=3.8",
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Operating System :: OS Independent",
        "Environment :: Web Environment",
        "Topic :: Utilities",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 3.0",
        "Framework :: Django :: 3.1",
    ],
)
