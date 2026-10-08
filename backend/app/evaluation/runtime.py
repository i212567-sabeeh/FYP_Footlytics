"""Describe the evaluation machine without confusing scoring time with CV time."""

import importlib.metadata
import json
import os
import platform
from pathlib import Path


def environment(*, probe_torch: bool = False) -> dict:
    versions = {}
    for package in (
        "numpy",
        "scipy",
        "pandas",
        "motmetrics",
        "torch",
        "torchvision",
        "ultralytics-opencv-headless",
        "opencv-python-headless",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    cpu = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER")
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in cpuinfo.read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu,
        )
    result = {
        "os": platform.platform(),
        "wsl": "microsoft" in platform.release().lower(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "versions": versions,
        "cuda_available": None,
        "cuda_probe": "not requested",
        "evaluation_device": "cpu",
    }
    if probe_torch:
        try:
            import torch

            result.update(cuda_available=torch.cuda.is_available(), cuda_probe="passed")
        except (ImportError, OSError, RuntimeError) as error:
            result["cuda_probe"] = f"unavailable ({type(error).__name__})"
    return result


if __name__ == "__main__":
    print(json.dumps(environment(probe_torch=True), indent=2))
