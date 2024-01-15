from setuptools import setup

setup(
    name='Flask-FastSpring',
    version='1.17',
    description='FastSpring API integration for Flask',
    py_modules=['flask_fastspring'],
    install_requires=[
        'Flask>=3.0',
        'SQLAlchemy>=1.0',
        'cryptography>=1.6',
        'requests>=2.12',
        'markupsafe>=1.0'
    ])
