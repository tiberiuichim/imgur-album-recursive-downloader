# import os
# import sys

from setuptools import find_packages, setup

version = '1.0'

setup(name='ImgurDownloader',
      version=version,
      description="Download and discover imgur albums",
      long_description="""Download Imgur albums, with optional discovery of
new albums based on image text descriptions.
""",
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Console',
          'Intended Audience :: End Users/Desktop',
          'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Topic :: Utilities',
      ],
      keywords='imgur, downloader, script',
      author='Tiberiu Ichim',
      author_email='tiberiu.ichim@gmail.com',
      url='https://play.pixelblaster.ro/',
      license='GPL3',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
          'awesome-slugify',
          'click',
          'requests',
          'xdg',
      ],
      entry_points="""
      [console_scripts]
      imgur = imgurdownloader:downloader
      """,
      )
