"""ABI workflow support — catalogs, execution, manifests, validation, and figures.

# Usage / 用法
    from abi.workflow import (
        ResourceManifest,
        generate_resource_manifest,
        write_resource_manifest,
        WorkflowValidator,
        check_required_artifacts,
        load_figure_specs,
        validate_figure_specs,
    )

# Modules / 模块
- ``catalog.py``: Declarative workflow preset loading and resolution.
- ``execution.py``: Transport-neutral preparation and runtime selection.
- ``manifest.py``: Resource manifest generation and checksumming.
- ``validation.py``: Workflow artifact validation for CI/linting.
- ``figure_specs.py``: Figure spec loading with cross-validation against
  standard table schemas.
"""

from abi.workflow.catalog import (
    WorkflowCatalog,
    WorkflowCatalogError,
    WorkflowPreset,
    WorkflowPresetError,
)
from abi.workflow.execution import PreparedWorkflow, WorkflowCoordinator
from abi.workflow.figure_specs import load_figure_specs, validate_figure_specs
from abi.workflow.manifest import (
    ResourceManifest,
    checksum_file,
    generate_resource_manifest,
    write_resource_manifest,
)
from abi.workflow.validation import WorkflowValidator, check_required_artifacts

__all__ = [
    "ResourceManifest",
    "PreparedWorkflow",
    "WorkflowCatalog",
    "WorkflowCatalogError",
    "WorkflowCoordinator",
    "WorkflowPreset",
    "WorkflowPresetError",
    "WorkflowValidator",
    "check_required_artifacts",
    "checksum_file",
    "generate_resource_manifest",
    "load_figure_specs",
    "validate_figure_specs",
    "write_resource_manifest",
]
