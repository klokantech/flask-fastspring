from setuptools import setup

setup(
    name='Flask-FastSpring',
    version='1.2',
    description='FastSpring API integration for Flask',
    py_modules=['flask_fastspring'],
    install_requires=[
        'Flask>=0.11',
        'requests>=2.12',
    ])
