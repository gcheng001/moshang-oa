"""Small cross-platform native dialogs used by the local desktop app."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def choose_directory(prompt: str) -> Path | None:
    if os.name == "nt":
        safe_prompt = prompt.replace("'", "''")
        script = f"""
Add-Type -AssemblyName System.Windows.Forms
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{safe_prompt}'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{ Write-Output $dialog.SelectedPath }}
"""
        command = ["powershell", "-NoProfile", "-STA", "-Command", script]
        stdin = None
    elif os.name == "posix":
        safe_prompt = prompt.replace("\\", "\\\\").replace('"', '\\"')
        script = f'''tell application "System Events" to activate
set folderPath to choose folder with prompt "{safe_prompt}"
return POSIX path of folderPath'''
        command = ["osascript", "-"]
        stdin = script
    else:
        return None

    try:
        proc = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_dir() else None
