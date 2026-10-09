$ErrorActionPreference = "Stop"
$target = "$HOME\.gemini\config\plugins\agy-porter"
$parentDir = Split-Path $target
if (-not (Test-Path $parentDir)) {
    New-Item -ItemType Directory -Force -Path $parentDir | Out-Null
}

if (Test-Path "$target\.git") {
    Write-Host "[agy-porter] Updating existing installation..." -ForegroundColor Cyan
    git -C "$target" pull --quiet
} else {
    if (Test-Path $target) {
        Remove-Item -Recurse -Force $target
    }
    Write-Host "[agy-porter] Installing agy-porter into $target..." -ForegroundColor Cyan
    git clone --quiet https://github.com/Dxrmy/agy-porter.git "$target"
}

Write-Host "[agy-porter] Successfully installed!" -ForegroundColor Green
Write-Host "You can now use /export and /import in Antigravity Desktop and the agy CLI." -ForegroundColor Green
