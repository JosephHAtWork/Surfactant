import ast
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
    pyDefinedObjects: List[str] = field(default_factory=list)
    pyLinkedObjects: Dict[str, str] = field(
        default_factory=dict
    )  # Symbols what were previously imported or also referenced in __all__ (typically found in __init__.py files)


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

    schema = Schema()

    extract_imports(schema, filename, project_root)
    extract_ast_objects(schema, filename)

    return asdict(schema)


def extract_imports(schema: Schema, filename: str, project_root: str):
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
                imported_objects=([importName] if importName is not None else []), type=isortType
            )
        else:
            schema.pyImports[moduleName].imported_objects.append(importName)


def extract_ast_objects(schema: Schema, filename: str):
    with open(filename, "r") as f:
        content = f.read()

        tree = ast.parse(content)

        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                schema.pyDefinedObjects.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        schema.pyDefinedObjects.append(target.id)

                        # Gets linked symbols defined in __all__
                        if target.id == "__all__":
                            if isinstance(node.value, ast.List):
                                # Caveat: this only works for constant values/strings.
                                #   If a function returns a name (like __all__ = [ "myVar", ret_myVar2() ]), it won't be detected
                                #   Only by loading the file will values like those be able to be extracted
                                all_const_values = [
                                    elt.s
                                    for elt in node.value.elts
                                    if isinstance(elt, ast.Constant)
                                ]
                                for name in all_const_values:
                                    for pkg, value in schema.pyImports.items():
                                        if name in value.imported_objects:
                                            schema.pyLinkedObjects[name] = pkg

                    elif isinstance(target, ast.Tuple):  # eg a, b = (1, 2)
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                schema.pyDefinedObjects.append(elt.id)
