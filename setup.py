# -*- coding: utf-8 -*-
"""
TextPress
========

TextPress is going to be an open source blog engine written in python, build on top of Werkzeug, Jinja and SQLAlchemy.

The `TextPress tip <http://dev.pocoo.org/hg/textpress-main/archive/tip.zip#egg=TextPress-dev>`_
is installable via `easy_install` with ``easy_install TextPress==dev``.
"""
import os
import ez_setup
ez_setup.use_setuptools()

from setuptools import setup, Feature

setup(
    name='TextPress',
    version='0.1',
    url='http://textpress.pocoo.org/',
    license='BSD',
    author='Armin Ronacher',
    author_email='armin.ronacher@active-4.com',
    description='A WSGI-based weblog engine in Python',
    long_description=__doc__,
    zip_safe=False,
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: News/Diary',
    ],
    packages=['textpress'],
    package_data={
        'textpress': ['shared/*', 'templates/*']
    },
    platforms='any',
    include_package_data=True,
    test_suite='tests.suite',
)
