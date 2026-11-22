#!/usr/bin/env python3
from setuptools import setup

setup(
    name="iskra-me162",
    version="0.2.0",
    description="Publish Iskra ME162 meter readings to MQTT",
    license="GPLv3",
    author="Louis Lagendijk",
    url="https://github.com/xevxx/iskra-me162-MQTT",
    python_requires=">=3.8",
    install_requires=["pyserial>=3.4,<4", "paho-mqtt>=1.6,<3"],
    scripts=["iskra-me162"],
)
