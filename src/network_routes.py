# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 NetworkHub contributors
"""Discover active Windows IPv4 adapters with default gateways."""
from dataclasses import dataclass
import json
import subprocess


@dataclass(frozen=True)
class Network:
    name: str
    index: int
    address: str
    description: str = ""


def discover_networks():
    command = r"""$ErrorActionPreference = 'Stop'
$activeAdapters = @(Get-NetAdapter | Where-Object Status -eq 'Up')
Get-NetIPConfiguration | ForEach-Object {
    $networkConfig = $_
    $adapter = $activeAdapters | Where-Object ifIndex -eq $networkConfig.InterfaceIndex | Select-Object -First 1
    if ($adapter -and $networkConfig.IPv4DefaultGateway -and $networkConfig.IPv4Address) {
        [pscustomobject]@{
            name = [string]$networkConfig.InterfaceAlias
            index = [int]$networkConfig.InterfaceIndex
            address = [string]@($networkConfig.IPv4Address.IPAddress)[0]
            description = [string]$adapter.InterfaceDescription
        }
    }
} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("Could not read Windows network adapters: " + result.stderr.strip())
    data = json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(data, dict):
        data = [data]
    return [Network(**record) for record in data]
