# setup.py
from setuptools import setup, find_packages

setup(
    name="robodogcli",
    version="0.1.0",
    description="robodog command-line interface",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.8",
    install_requires=[
        "langchain",
        "pydantic",
        # … any other deps …
    ],
    packages=find_packages(include=["robodog*"]),      # ← explicitly include your package(s)
    entry_points={
        "console_scripts": [
            "robodog=robodog.cli:main",
        ],
    },
)