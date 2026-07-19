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
    extras_require={
        # Terminal Mode (Claude Code-style agentic coding terminal).
        "terminal": ["rich>=13", "prompt_toolkit>=3", "requests>=2.25"],
    },
    packages=find_packages(include=["robodog*"]),      # ← explicitly include your package(s)
    entry_points={
        "console_scripts": [
            # `robodog` routes `terminal` to Terminal Mode without the heavy
            # server imports; everything else goes to the original CLI.
            "robodog=robodog.entry:main",
            # Direct first-class launcher for Terminal Mode.
            "robodog-terminal=robodog.terminal.app:main",
        ],
    },
)