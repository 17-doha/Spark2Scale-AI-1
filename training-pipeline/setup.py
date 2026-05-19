from setuptools import find_packages, setup

setup(
    name="spark2scale",
    version="1.0.0",
    description="Spark2Scale – ML pipeline for training, fine-tuning, and evaluating LLMs",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.1.0",
        "transformers==4.56.2",
        "datasets==4.3.0",
        "peft>=0.10.0",
        "pyyaml>=6.0",
    ],
)
