from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import tomllib
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parent


def _pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())


def _project_metadata() -> dict:
    return _pyproject()["project"]


def _distribution_name() -> str:
    return _project_metadata()["name"].replace("-", "_")


def _version() -> str:
    return _project_metadata()["version"]


def _dist_info_dir() -> str:
    return f"{_distribution_name()}-{_version()}.dist-info"


def _wheel_filename() -> str:
    return f"{_distribution_name()}-{_version()}-py3-none-any.whl"


def _metadata_text() -> str:
    project = _project_metadata()
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {project['name']}",
        f"Version: {project['version']}",
        f"Summary: {project.get('description', '')}",
        f"Requires-Python: {project.get('requires-python', '')}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _wheel_text() -> str:
    return "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: local_backend",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
        ]
    ) + "\n"


def _entry_points_text() -> str:
    scripts = _project_metadata().get("scripts", {})
    lines = ["[console_scripts]"]
    lines.extend(f"{name} = {target}" for name, target in scripts.items())
    return "\n".join(lines).rstrip() + "\n"


def _top_level_text() -> str:
    return "tax_pipeline\n"


def _hash_bytes(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _record_text(files: dict[str, bytes], record_path: str) -> str:
    lines: list[str] = []
    for path, data in files.items():
        lines.append(f"{path},sha256={_hash_bytes(data)},{len(data)}")
    lines.append(f"{record_path},,")
    return "\n".join(lines).rstrip() + "\n"


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)


def _build_common_dist_info() -> dict[str, bytes]:
    dist_info = _dist_info_dir()
    return {
        f"{dist_info}/METADATA": _metadata_text().encode(),
        f"{dist_info}/WHEEL": _wheel_text().encode(),
        f"{dist_info}/entry_points.txt": _entry_points_text().encode(),
        f"{dist_info}/top_level.txt": _top_level_text().encode(),
    }


def _editable_files() -> dict[str, bytes]:
    files = _build_common_dist_info()
    files[f"{_distribution_name()}.pth"] = (str(PROJECT_ROOT) + os.linesep).encode()
    return files


def _wheel_files() -> dict[str, bytes]:
    files = _build_common_dist_info()
    for path in _iter_files(PROJECT_ROOT / "tax_pipeline"):
        files[path.relative_to(PROJECT_ROOT).as_posix()] = path.read_bytes()
    for path in _iter_files(PROJECT_ROOT / "years" / "demo-2025"):
        files[path.relative_to(PROJECT_ROOT).as_posix()] = path.read_bytes()
    files["README.md"] = (PROJECT_ROOT / "README.md").read_bytes()
    return files


def _write_metadata_directory(metadata_directory: str) -> str:
    dist_info = Path(metadata_directory) / _dist_info_dir()
    dist_info.mkdir(parents=True, exist_ok=True)
    common = _build_common_dist_info()
    for path, content in common.items():
        target = Path(metadata_directory) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return _dist_info_dir()


def _build_archive(wheel_directory: str, files: dict[str, bytes]) -> str:
    wheel_directory_path = Path(wheel_directory)
    wheel_directory_path.mkdir(parents=True, exist_ok=True)
    filename = _wheel_filename()
    dist_info = _dist_info_dir()
    record_path = f"{dist_info}/RECORD"
    files = dict(files)
    files[record_path] = _record_text(files, record_path).encode()
    wheel_path = wheel_directory_path / filename
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path, content in files.items():
            handle.writestr(path, content)
    return filename


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _build_archive(wheel_directory, _wheel_files())


def build_editable(wheel_directory: str, config_settings=None, metadata_directory=None) -> str:
    return _build_archive(wheel_directory, _editable_files())


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    return _write_metadata_directory(metadata_directory)


def prepare_metadata_for_build_editable(metadata_directory: str, config_settings=None) -> str:
    return _write_metadata_directory(metadata_directory)


def get_requires_for_build_wheel(config_settings=None) -> list[str]:
    return []


def get_requires_for_build_editable(config_settings=None) -> list[str]:
    return []
