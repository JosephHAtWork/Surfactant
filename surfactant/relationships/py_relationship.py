from pathlib import Path
from typing import List, Optional

from loguru import logger

import surfactant.plugin
from surfactant.sbomtypes import SBOM, Relationship, Software


def has_required_fields(metadata) -> bool:
    return "pyImports" in metadata


def resolve_relative_import(module: str, file_path: str) -> Path:
    split_module_path = module.split(".")
    directories_to_move_up = (
        next((i for i, x in enumerate(split_module_path) if x != ""), len(split_module_path)) - 1
    )  # "from ..module import object" -> moves up 1 directory

    print("\tf ", file_path)
    directory = Path(file_path).parent
    if directories_to_move_up > 0:
        directory = directory.parents[directories_to_move_up]

    for f in directory.iterdir():
        if f.stem == split_module_path[directories_to_move_up + 1] and f.suffix == ".py":
            return f

    return Path()


@surfactant.plugin.hookimpl
def establish_relationships(
    sbom: SBOM, software: Software, metadata
) -> Optional[List[Relationship]]:
    if not has_required_fields(metadata):
        return None

    print(">>>>>>>", software.installPath)
    relationships: List[Relationship] = []

    for package_name, data in metadata["pyImports"].items():
        if data["type"][0] != "FIRSTPARTY":
            continue  # Only parse imports in the

        print(package_name, data)
        importedObjects = data["imported_objects"]

        # Iterates through all other python files to build relationships
        # Import cases:
        #     1. Imports symbol from a package / namespace (also includes importing * symbols, use definitions and __all__ in __init__.py from packages) (eg 'from surfactant.sbomtypes import SBOM, Relationship, Software')
        #     2. Imports symbols from a file/module (eg 'from surfactant.relationships._internal.posix_utils import posix_normpath')
        #     3. Imports file/module from package (eg 'from surfactant.plugin import hookspecs')

        print("\t", "Finding file match:")
        found_matching_file = False
        files_in_package = []
        for item in sbom.software:
            defined_objects = next(
                (d["pyDefinedObjects"] for d in item.metadata if "pyDefinedObjects" in d), None
            )
            if defined_objects is None or item.UUID == software.UUID or defined_objects == []:
                continue  # Skip non-python files and self

            for p in item.installPath:
                item_path = Path(p)
                item_path_parts = item_path.with_suffix("").parts
                item_file_path = ".".join(item_path_parts)  # Used for case 2
                item_package_path = ".".join(item_path_parts[:-1])  # Used for case 1

                found_matching_file = found_matching_file or item_file_path.endswith(package_name)

                if item_package_path.endswith(package_name):
                    files_in_package.append(item)

                # print("\t\t", item_package_path, package_name, found_matching_file)

                # Case 2: Check if all imported objects are defined in this module
                imported_obj_found_in_module = set(importedObjects).issubset(set(defined_objects))
                if found_matching_file and imported_obj_found_in_module and importedObjects != []:
                    print("Matched case 2", item.fileName, defined_objects)

                    rel = Relationship(software.UUID, item.UUID, "Uses")
                    if rel not in relationships:
                        relationships.append(rel)
                    break

            else:
                continue
            break  # Break out of outer sbom.software loop

        if not found_matching_file and not files_in_package:
            logger.warning(
                f"Unable to establish relationship between UUID {software.UUID} and Python path {package_name} {data}"
            )
            continue

        # Case 1 & 3: Goes over the list of files/modules in the package in case a file match wasn't found
        print("\t", "Finding package match:")
        if not found_matching_file:
            print("\tff", [f.installPath for f in files_in_package])

            install_path_root = Path(files_in_package[0].installPath[0]).resolve().parent

            init_struct = next(
                (
                    item
                    for item in sbom.software
                    if any(
                        Path(p).resolve() == (install_path_root / "__init__.py")
                        for p in item.installPath
                    )
                ),
                [],
            )
            print()
            print("IS", init_struct)
            init_linked_objects = next(
                (m["pyLinkedObjects"] for m in init_struct.metadata if "pyLinkedObjects" in m), {}
            )

            init_defined_objects = next(
                (m["pyDefinedObjects"] for m in init_struct.metadata if "pyDefinedObjects" in m), {}
            )

            init_imports = next(
                (m["pyImports"] for m in init_struct.metadata if "pyImports" in m), {}
            )

            for obj in importedObjects:
                # print(obj)
                # Case 3
                for p in init_struct.installPath:
                    imported_module = resolve_relative_import(obj, p)
                    if imported_module != Path("."):
                        for item in files_in_package:
                            if imported_module in [Path(i) for i in item.installPath]:
                                print("Matched case 3", obj, item.installPath)

                                rel = Relationship(software.UUID, item.UUID, "Uses")
                                if rel not in relationships:
                                    relationships.append(rel)
                                break
                        else:
                            continue
                        break  # Break out of outer init_struct.installPath loop

                # Case 1 (import * from ___)
                if obj in init_linked_objects.keys():
                    for p in init_struct.installPath:
                        file_for_linked_object = resolve_relative_import(
                            init_linked_objects[obj], p
                        )

                        for item in files_in_package:
                            defined_objects = next(
                                (
                                    d["pyDefinedObjects"]
                                    for d in item.metadata
                                    if "pyDefinedObjects" in d
                                ),
                                None,
                            )
                            if (
                                file_for_linked_object in [Path(i) for i in item.installPath]
                                and obj in defined_objects
                            ):
                                print("Matched case 1 (import *)", obj, item.installPath)

                                rel = Relationship(software.UUID, item.UUID, "Uses")
                                if rel not in relationships:
                                    relationships.append(rel)

                                break
                        else:
                            continue
                        break  # Break out of outer init_struct.installPath loop

                # Case 1 (imports a symbol defined in __init__.py, eg parse_relationships() in 'surfactant/relationships/__init__.py')
                if obj in init_defined_objects:
                    print(
                        "Matched case 1 (sym defined in __init__.py)", obj, init_struct.installPath
                    )

                    rel = Relationship(software.UUID, init_struct.UUID, "Uses")
                    if rel not in relationships:
                        relationships.append(rel)

                    break

                # Case 1 (module references an imported symbol)
                module_with_obj = next(
                    (
                        module_name
                        for module_name, data in init_imports.items()
                        if obj in data.get("imported_objects", [])
                    ),
                    None,
                )
                if module_with_obj is not None:
                    pass

        print()

    return relationships
