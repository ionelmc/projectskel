from setuptools import setup, find_packages

import os

setup(
    name = "project",
    version = "0.1.0",
    url = '',
    download_url = '',
    license = 'BSD',
    description = "",
    author = 'Ionel Cristian Maries',
    author_email = 'contact@ionelmc.ro',
    packages = find_packages('src'),
    package_dir = {'':'src'},
    include_package_data = True,
    zip_safe = False,
    classifiers = [
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP',
    ]
)
