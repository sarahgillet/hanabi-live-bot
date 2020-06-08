import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...

setup(
    name = "hanabi_live_bot",
    version = "0.0.1",
    author = "Origin Zamiell, modified sarahgillet",
    description = ("An agent that connects to hanabi live and collects "
                                   "the game state."),
    packages=['hanabi_live_bot'],
    install_requires=[
   'python-dotenv',
   'requests',
   'websocket-client'
    ],
)