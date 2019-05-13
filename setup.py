import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="hitch-databank-migration",
    version="0.0.1",
    author="Data Republic <support@datarepublic.com>",
    author_email="support@datarepublic.com",
    description="Hitch Databank Migration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://datarepublic.com.au",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Senate Matching License",
        "Operating System :: OS Independent",
    ],
)
