from typing import List, Optional

import surfactant.plugin
from surfactant.sbomtypes import SBOM, Relationship, Software


def has_required_fields(metadata) -> bool:
    return "" in metadata


@surfactant.plugin.hookimpl
def establish_relationships(
    sbom: SBOM, software: Software, metadata
) -> Optional[List[Relationship]]:
    if not has_required_fields(metadata):
        return None

    return None
