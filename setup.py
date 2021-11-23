from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in masar_cost/__init__.py
from masar_cost import __version__ as version

setup(
	name="masar_cost",
	version=version,
	description="Modifications on Moving Average Cost",
	author="KCSC",
	author_email="info@kcsc.com.jo",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
