# Complete Playwright installation script
# Run from grok-harness directory with venv activated

param(
    [switch]$Force
)

Write-Host "Playwright Installation Script" -ForegroundColor Cyan
Write-Host ("=" * 50)

# Uninstall and reinstall
Write-Host "`nUninstalling existing packages..."
pip uninstall playwright -y 2>$null
pip uninstall pyee -y 2>$null

# Clear cached installations
$cachePath = "$env:USERPROFILE\AppData\Local\ms-playwright"
if (Test-Path $cachePath) {
    Write-Host "Clearing cache: $cachePath"
    Remove-Item -Recurse -Force $cachePath -ErrorAction SilentlyContinue
}

# Install fresh
Write-Host "`nInstalling playwright>=1.40.0..."
pip install "playwright>=1.40.0"

# Install browsers
Write-Host "`nInstalling Chromium (this may take a minute)..."
if ($Force) {
    python -m playwright install chromium --force --verbose
} else {
    python -m playwright install chromium --verbose
}

Write-Host "`nDone. Run: python scripts/test_playwright.py" -ForegroundColor Green
