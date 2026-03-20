from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .memory import list_process_modules
from .paths import HELLHADES_REFERENCE_DIR, RAID_EXECUTABLE, RAID_MANIFEST


def build_runtime_snapshot() -> Dict[str, Any]:
    processes = discover_processes(("Raid.exe", "PlariumPlay.NetHost.exe", "HellHades.ArtifactExtractor.exe"))
    raid_process = first_process(processes, "Raid.exe")
    nethost_process = first_process(processes, "PlariumPlay.NetHost.exe")
    hellhades_process = first_process(processes, "HellHades.ArtifactExtractor.exe")

    return {
        "raid_process": enrich_raid_process(raid_process),
        "plarium_nethost_process": enrich_nethost_process(nethost_process),
        "hellhades_process": hellhades_process,
        "raid_build": read_raid_build_info(),
        "reference_dlls": reference_inventory(),
    }


def discover_processes(names: Iterable[str]) -> List[Dict[str, Any]]:
    escaped_names = ",".join(f"'{name}'" for name in names)
    command = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.Name -in @({escaped_names}) }} | "
        "Select-Object ProcessId,Name,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Depth 3"
    )
    raw = run_powershell(command)
    if not raw.strip():
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else [data]


def run_powershell(command: str) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(stderr or f"PowerShell exited with code {completed.returncode}")
    return completed.stdout


def first_process(processes: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    for process in processes:
        if process.get("Name") == name:
            return process
    return None


def enrich_raid_process(process: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if process is None:
        return None

    command_line = str(process.get("CommandLine") or "")
    flags = parse_colon_flags(command_line)
    modules: List[Dict[str, Any]]
    module_error: Optional[str] = None

    try:
        modules = [
            module.as_dict()
            for module in list_process_modules(int(process["ProcessId"]))
            if module.name in {"Raid.exe", "GameAssembly.dll", "UnityPlayer.dll", "baselib.dll"}
        ]
    except Exception as exc:
        modules = []
        module_error = str(exc)

    return {
        "pid": process.get("ProcessId"),
        "name": process.get("Name"),
        "path": process.get("ExecutablePath"),
        "command_line": command_line,
        "flags": flags,
        "modules": modules,
        "module_error": module_error,
    }


def enrich_nethost_process(process: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if process is None:
        return None

    command_line = str(process.get("CommandLine") or "")
    return {
        "pid": process.get("ProcessId"),
        "name": process.get("Name"),
        "path": process.get("ExecutablePath"),
        "command_line": command_line,
        "flags": parse_quoted_pair_flags(command_line),
    }


def parse_colon_flags(command_line: str) -> Dict[str, str]:
    flags: Dict[str, str] = {}
    for match in re.finditer(r'-(?P<key>[A-Za-z0-9_-]+):(?P<value>"[^"]*"|\S+)', command_line):
        value = match.group("value").strip('"')
        flags[match.group("key")] = value
    for match in re.finditer(r'-(?P<key>[A-Za-z0-9_-]+)\s+(?P<value>"[^"]*"|\S+)', command_line):
        flags.setdefault(match.group("key"), match.group("value").strip('"'))
    return flags


def parse_quoted_pair_flags(command_line: str) -> Dict[str, str]:
    return {
        key.strip(): value.strip()
        for key, value in re.findall(r'"([^"]+?)\s+([^"]+)"', command_line)
    }


def read_raid_build_info() -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "raid_executable": str(RAID_EXECUTABLE),
        "manifest_path": str(RAID_MANIFEST),
        "product_version": None,
        "build_id": None,
        "content_version": None,
    }
    if RAID_EXECUTABLE.exists():
        summary["product_version"] = read_file_version(RAID_EXECUTABLE)
    if RAID_MANIFEST.exists():
        manifest = json.loads(RAID_MANIFEST.read_text(encoding="utf-8"))
        summary["build_id"] = manifest.get("options", {}).get("buildId")
        summary["content_version"] = detect_content_version(manifest)
    return summary


def read_file_version(path: Path) -> Optional[str]:
    command = f"(Get-Item '{path}').VersionInfo.ProductVersion | ConvertTo-Json"
    raw = run_powershell(command).strip()
    return json.loads(raw) if raw else None


def detect_content_version(manifest: Dict[str, Any]) -> Optional[str]:
    version_pattern = re.compile(r"/(\d+\.\d+\.\d+)/")
    for chunk in manifest.get("chunks", []):
        path = str(chunk.get("path", ""))
        match = version_pattern.search(path)
        if match:
            return match.group(1)
    return None


def reference_inventory() -> List[Dict[str, Any]]:
    if not HELLHADES_REFERENCE_DIR.exists():
        return []
    return [
        {
            "name": path.name,
            "path": str(path),
            "size": path.stat().st_size,
        }
        for path in sorted(HELLHADES_REFERENCE_DIR.iterdir())
        if path.is_file()
    ]
