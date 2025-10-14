# ============================
# Prometheus + Grafana Playground Helper (Windows)
# ============================

param (
  [Parameter(Position = 0)]
  [ValidateSet("start", "start-with-logs", "stop", "restart", "rebuild", "reset", "logs", "status", "stop-clean", "clean", "help")]
  [string]$action = "help"
)

Write-Host "== Prometheus Playground Manager ==" -ForegroundColor Cyan

switch ($action) {
  "start" {
    Write-Host ">  Starting all containers..." -ForegroundColor Green
    docker-compose up -d
  }

  "start-with-logs" {
    Write-Host ">  Starting all containers and tailing per-service logs..." -ForegroundColor Green
    docker-compose up -d --build

    # ensure logs directory exists at repo root
    $logsDir = Join-Path (Get-Location) 'logs'
    if (-not (Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }

    # list of container names matching docker-compose service names or container_name in compose
    $services = @('prometheus', 'grafana', 'mock_server')

    foreach ($s in $services) {
      # start a background job to follow docker logs and append to a file
      Start-Job -Name "log_$s" -ScriptBlock {
        param($svc, $outdir)
        $outfile = Join-Path $outdir "$svc.log"
        # follow logs - include stderr; this will run until job is stopped
        docker logs -f $svc 2>&1 | ForEach-Object { $_ | Out-File -FilePath $outfile -Encoding utf8 -Append }
      } -ArgumentList $s, $logsDir | Out-Null
      Write-Host "Started background log job for $s -> $logsDir\$s.log"
    }
  }

  "stop" {
    Write-Host "⏹️  Stopping all containers..." -ForegroundColor Yellow
    docker-compose down
    # stop any background log jobs started by start-with-logs
    Get-Job -Name 'log_*' -State 'Running' -ErrorAction SilentlyContinue | ForEach-Object { Stop-Job $_; Remove-Job $_ }
  }

  "restart" {
    Write-Host "🔁  Restarting containers..." -ForegroundColor Yellow
    docker-compose restart
  }

  "rebuild" {
    Write-Host "🔨  Rebuilding mock server..." -ForegroundColor Cyan
    docker-compose build mock_server
    docker-compose up -d mock_server
  }

  "reset" {
    Write-Host "🧹  Cleaning up EVERYTHING (containers, volumes, images)..." -ForegroundColor Red
    docker-compose down -v --rmi all
    Write-Host "✅ Cleaned. Rebuilding fresh setup..."
    docker-compose up -d --build
  }

  "logs" {
    Write-Host "📜  Showing logs (Ctrl+C to stop viewing)" -ForegroundColor Cyan
    docker-compose logs -f
  }

  "status" {
    Write-Host "📊  Current container status:" -ForegroundColor Cyan
    docker ps --filter "name=prometheus" --filter "name=grafana" --filter "name=mock_server"
  }

  "stop-clean" {
    docker-compose down -v all
    Write-Host "🧹  Cleaning logs, pycache, and docker images..." -ForegroundColor Red

    # Remove all log files in ./logs
    $logsDir = Join-Path (Get-Location) 'logs'
    if (Test-Path $logsDir) {
      Get-ChildItem -Path $logsDir -File | Remove-Item -Force -ErrorAction SilentlyContinue
      Write-Host "Deleted all log files in $logsDir"
    }

    # Remove all __pycache__ folders and .pyc files recursively
    Get-ChildItem -Path (Get-Location) -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Get-Location) -Recurse -File -Include '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Deleted all __pycache__ folders and .pyc files"

    # Remove docker images created by docker-compose (removes all images for this project)
    $composeProject = (Get-Content .\docker-compose.yml | Select-String -Pattern 'container_name: (.+)' | ForEach-Object { $_.Matches[0].Groups[1].Value })
    foreach ($img in $composeProject) {
      $imageId = docker images --format '{{.ID}}' --filter reference="$img"
      if ($imageId) {
        docker rmi -f $imageId | Out-Null
        Write-Host "Removed docker image for $img"
      }
    }
    Write-Host "Clean complete."
  }

  default {
    Write-Host @"
Usage:
  .\run.ps1 start            # Start all containers
  .\run.ps1 start-with-logs  # Start all containers and tail logs
  .\run.ps1 stop             # Stop everything
  .\run.ps1 restart          # Restart all containers
  .\run.ps1 rebuild          # Rebuild only mock server
  .\run.ps1 reset            # Clean everything and rebuild fresh
  .\run.ps1 logs             # Tail all container logs
  .\run.ps1 status           # Show running containers
  .\run.ps1 clean            # Clean up logs, pycache, and docker images
  .\run.ps1 stop-clean       # Stop all containers and clean up
"@
  }
}
