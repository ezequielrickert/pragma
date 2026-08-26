# run_all.ps1
# Script to run the complete Pragma pipeline: crawl -> docs -> start servers

param (
    [string]$Url
)

# Enable UTF-8 encoding for PowerShell output
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $Url) {
    $Url = Read-Host "Enter the URL to crawl (e.g. https://www.empanad.app)"
}

if (-not $Url) {
    Write-Error "URL is required to run the pipeline."
    Exit 1
}

# Extract host/site slug from URL
try {
    $uri = [System.Uri]$Url
    $site_slug = $uri.Host
} catch {
    Write-Error "Invalid URL format."
    Exit 1
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "1. Running pragma crawl for $Url..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
python cli.py crawl $Url
if ($LASTEXITCODE -ne 0) {
    Write-Host "Crawl failed. Aborting." -ForegroundColor Red
    Exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "2. Generating documents for $site_slug..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
python cli.py docs $site_slug
if ($LASTEXITCODE -ne 0) {
    Write-Host "Document generation failed. Aborting." -ForegroundColor Red
    Exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "3. Starting Flask Interactive Server in a new window..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python cli.py interactive $site_slug"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "4. Starting Vite Dev Server in a new window..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd tools/graph-explorer; npm run dev"

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "All tasks launched successfully!" -ForegroundColor Green
Write-Host "The dashboard will be available at http://localhost:5173" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

# Wait a couple of seconds for servers to start and open browser
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"
