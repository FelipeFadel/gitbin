from setuptools import setup, find_packages

setup(
    name="gitbin",
    version="0.1.0",
    description="Versionamento diferencial de arquivos GLB baseado em Btrfs CoW",
    author="Felipe da Silva Fadel",
    packages=find_packages(),
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "gitbin=gitbin.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
    ],
)