from distutils.core import setup, Command
import glob
import sys
import os


setup(name = "rbldnspy",
    version = '0.0.1',
    description = "RBLDNS server",
    author = "O. Schacher",
    author_email = "oli@fuglu.org",
    package_dir={'':'src'},
    packages = ['rbldnspy'],
    scripts = ["src/rbldnsd.py",],
    long_description = """RBLDNSD in python """ ,
)


        
        
        
