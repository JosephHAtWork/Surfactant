import os
from dataclasses import asdict, dataclass, field
from sys import modules
from typing import Dict, List, Optional, Tuple

from isort.api import find_imports_in_file, place_module_with_reason
from isort.settings import Config
from loguru import logger

import surfactant.plugin
from surfactant import ContextEntry


@dataclass
class PyImportedModule:
    imported_objects: List[str]
    type: Tuple[str, str]


@dataclass
class Schema:
    pyImports: Dict[str, PyImportedModule] = field(default_factory=dict)


def supports_filetype(filetype: str) -> bool:
    return filetype in ("PYTHON",)


@surfactant.plugin.hookimpl
def extract_file_info(
    filename: str,
    filetype: str,
    current_context: Optional[ContextEntry],
) -> object:
    if "isort" not in modules:
        logger.warning("isort not installed - Skipped extracting Python file info.")
        return None

    if not supports_filetype(filetype):
        return None

    n_extract_paths = len(current_context.extractPaths)
    if n_extract_paths > 1:
        logger.warning(
            f"isort only supports 1 project root: {n_extract_paths} were given, using the first"
        )
    project_root = current_context.extractPaths[0]

    return extract_imports(filename, filetype, project_root)


def extract_imports(filename: str, filetype: str, project_root: str):
    schema = Schema()

    isortConfig = Config()
    isortConfig.project_root = os.path.abspath(
        project_root
    )  # Only search in the specimen config path

    imports = find_imports_in_file(filename)
    for i in imports:
        moduleName = i.module
        importName = i.attribute  # ie function, class
        if moduleName not in schema.pyImports:
            isortType = place_module_with_reason(moduleName)
            schema.pyImports[moduleName] = PyImportedModule(
                imported_objects=[importName], type=isortType
            )

    return asdict(schema)
