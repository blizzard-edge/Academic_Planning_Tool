$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

python -m PyInstaller --noconfirm --clean --onedir --console `
    --name SmartClassPlanningTool `
    --paths src `
    --add-data "data/Graduate_Study_Plans.xlsx:data" `
    --add-data "data/4_year_schedule.xlsx:data" `
    --add-data "data/cpsc_course_catalog.json:data" `
    src/Main.py

if ($LASTEXITCODE -ne 0) {
    throw "Executable build failed."
}

Write-Host "Build complete: dist\SmartClassPlanningTool"
