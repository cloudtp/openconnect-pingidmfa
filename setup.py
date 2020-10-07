import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pingmfa",
    author="Adam Barrett",
    author_email="adam.barrett@hpe.com",
    version="0.0.1",
    description="HPE VPN with PingID MFA using Openconnect",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/utahcon/pingmfa",
    install_requires=[
        "pyyaml",
        "selenium",
        "pykeepass",
        "elevate",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
