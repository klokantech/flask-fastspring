from setuptools import setup

setup(
    name='Flask-FastSpring',
    version='1.19',
    description='FastSpring API integration for Flask',
    py_modules=['flask_fastspring'],
    install_requires=[
        'Flask>=2.0',
        'SQLAlchemy>=1.0',
        'cryptography>=1.6',
        'requests>=2.12',
        'markupsafe>=2.0'
    ])
