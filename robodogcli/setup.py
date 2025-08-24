from setuptools import setup, find_packages

setup(
    name="robodog",
    version="0.1.0",
    author="Your Name",
    author_email="you@example.com",
    description="Combined MCP file‐server + Robodog CLI",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/youruser/robodog",
    license="MIT",
    packages=find_packages(exclude=["tests*",]),
    install_requires=[
        "PyYAML>=5.4",
        "openai>=0.27.0",
        "requests>=2.25",
        "playwright>=1.30",      # if you use Playwright
        # "pyppeteer",           # if you still need it
    ],
    entry_points={
        "console_scripts": [
            "robodog=robodog.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)