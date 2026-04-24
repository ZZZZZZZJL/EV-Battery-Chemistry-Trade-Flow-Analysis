from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    app_env: str
    runtime_root: Path
    runtime_releases_root: Path
    runtime_current_root: Path
    runtime_previous_root: Path
    app_data_root: Path
    output_versions_root: Path
    web_package_root: Path


def get_runtime_paths(project_root: Path | None = None) -> RuntimePaths:
    resolved_project_root = (project_root or Path(__file__).resolve().parents[3]).resolve()
    app_env = os.getenv('APP_ENV', 'dev').strip().lower() or 'dev'
    runtime_root = Path(os.getenv('RUNTIME_ROOT', str(resolved_project_root / 'instance' / 'runtime'))).resolve()
    runtime_current_root = runtime_root / 'current'
    runtime_previous_root = runtime_root / 'previous'
    app_data_root = Path(
        os.getenv(
            'BATTERY_SITE_APP_DATA_DIR',
            str(runtime_current_root / 'app_data'),
        )
    ).resolve()
    output_versions_root = Path(
        os.getenv(
            'BATTERY_SITE_OUTPUT_VERSIONS_DIR',
            str(runtime_current_root / 'output_versions'),
        )
    ).resolve()
    return RuntimePaths(
        project_root=resolved_project_root,
        app_env=app_env,
        runtime_root=runtime_root,
        runtime_releases_root=runtime_root / 'releases',
        runtime_current_root=runtime_current_root,
        runtime_previous_root=runtime_previous_root,
        app_data_root=app_data_root,
        output_versions_root=output_versions_root,
        web_package_root=(resolved_project_root / 'src' / 'trade_flow' / 'web').resolve(),
    )
