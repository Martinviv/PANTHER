from setuptools import setup, find_packages
import codecs
import os
import platform

# Get the long description from the README file
here = os.path.abspath(os.path.dirname(__file__))
try:
  with codecs.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
      long_description = f.read()
except:
  # This happens when running tests
  long_description = None

# TODO test if good

setup(name='panther',
      version='0.1',
      description='panther',
      long_description=long_description,
      url='https://github.com/ElNiak/PANTHER',
      author='ElNiak from UCLouvain',
      author_email='nomail@uclouvain.com',
      license='MIT', 
      packages=find_packages(), 
      setup_requires=['wheel'], # "importlib-metadata", ,"importlib_metadata"
      install_requires=[
          'docker',
          'click',
          'termcolor',
          'terminal_banner',
          "paramiko",
          "mkgendocs == 0.9.2",
          "mkdocs-material == 9.1.15",
          "mkdocs == 1.5.0",
          "PyYAML == 6.0.1"
          ],

      zip_safe=False)
