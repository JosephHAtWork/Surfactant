from pathlib import Path

import surfactant.plugin
from surfactant.sbomtypes import SBOM, Software


def supports_filetype(filetype: str) -> bool:
    return filetype in ("PYTHON",)


def supports_filename(filename: str) -> bool:
    return Path(filename).name in ("pyproject.toml",)


@surfactant.plugin.hookimpl
def extract_file_info(sbom: SBOM, software: Software, filename: str, filetype: str) -> object:
    if not supports_filename(filename) and not supports_filetype(filetype):
        return None

    return extract_python_info(filename, filetype)


def extract_python_info(filename: str, filetype: str):
    pass
