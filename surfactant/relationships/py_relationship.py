from pathlib import Path
from typing import List, Optional

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

            item_path_parts = Path(item.installPath[0]).with_suffix("").parts
            item_file_path = ".".join(item_path_parts)  # Used for case 2
            item_package_path = ".".join(item_path_parts[:-1])  # Used for case 1

            found_matching_file = item_file_path.endswith(package_name)

            if item_package_path.endswith(package_name):
                files_in_package.append(item)

            print("\t\t", item_package_path, package_name, found_matching_file)

            # Case 2: Check if all imported objects are defined in this module
            imported_obj_found_in_module = set(importedObjects).issubset(set(defined_objects))
            if found_matching_file and imported_obj_found_in_module:
                print("d", item.fileName, defined_objects)

                rel = Relationship(software.UUID, item.UUID, "Uses")
                if rel not in relationships:
                    relationships.append(rel)

                break

        # Case 1 & 3: Goes over the list of files/modules in the package in case a file match wasn't found
        print("\t", "Finding package match:")
        if not found_matching_file:
            print("\tff", [f.installPath for f in files_in_package])

            init_struct = next(
                (
                    item
                    for item in files_in_package
                    if any(path.endswith("__init__.py") for path in item.installPath)
                ),
                [],
            )
            print(init_struct)
            init_linked_objects = next(
                (m["pyLinkedObjects"] for m in init_struct.metadata if "pyLinkedObjects" in m), {}
            )

            for obj in importedObjects:
                print(obj)
                # Case 3
                imported_module = resolve_relative_import(obj, init_struct.installPath[0])
                if imported_module != Path("."):
                    for item in files_in_package:
                        if imported_module in [Path(i) for i in item.installPath]:
                            print("Matched case 3", obj, item.installPath)
                            break

                # Case 1
                if obj in init_linked_objects.keys():
                    file_for_linked_object = resolve_relative_import(
                        init_linked_objects[obj], init_struct.installPath[0]
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
                            print("Matched case 1", obj, item.installPath)
                            break

        print()

    return relationships
