# Strands CLI - Development Automation Script
# PowerShell wrapper for common development tasks

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Dev {
    Write-Header "Running tests..."
    uv run pytest -v
}

function Test-Coverage {
    Write-Header "Running tests with coverage..."
    uv run pytest --cov=src --cov-report=term-missing --cov-report=html
    Write-Host ""
    Write-Host "Coverage report generated in htmlcov/index.html" -ForegroundColor Green
}

function Invoke-Lint {
    Write-Header "Running linter (ruff check)..."
    uv run ruff check .
}

function Invoke-Format {
    Write-Header "Formatting code (ruff format)..."
    uv run ruff format .
}

function Invoke-TypeCheck {
    Write-Header "Type checking with mypy..."
    uv run mypy src
}

function Invoke-Clean {
    Write-Header "Cleaning build artifacts..."
    
    $pathsToRemove = @(
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "htmlcov",
        ".coverage",
        "dist",
        "build",
        "*.egg-info"
    )
    
    foreach ($path in $pathsToRemove) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "Removed: $path"
        }
    }
    
    # Remove __pycache__ directories
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Write-Host "Removed all __pycache__ directories"
}

function Invoke-Build {
    Write-Header "Building distribution..."
    uv build
}

function Invoke-Install {
    Write-Header "Installing package in dev mode..."
    uv pip install -e .
}

function Invoke-ValidateExamples {
    Write-Header "Validating all example specs..."
    
    $examplesDir = "examples"
    $specs = Get-ChildItem -Path $examplesDir -Filter "*.yaml"
    $failed = 0
    
    foreach ($spec in $specs) {
        Write-Host "Validating $($spec.Name)..." -NoNewline
        try {
            $result = uv run strands validate $spec.FullName 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host " OK" -ForegroundColor Green
            } else {
                Write-Host " FAILED" -ForegroundColor Red
                Write-Host $result
                $failed++
            }
        } catch {
            Write-Host " ERROR" -ForegroundColor Red
            Write-Host $_.Exception.Message
            $failed++
        }
    }
    
    if ($failed -gt 0) {
        Write-Host ""
        Write-Host "FAILED: $failed specs failed validation" -ForegroundColor Red
        exit 1
    } else {
        Write-Host ""
        Write-Host "SUCCESS: All specs validated" -ForegroundColor Green
    }
}

function Invoke-CI {
    Write-Header "Running full CI pipeline..."
    
    try {
        Invoke-Lint
        Invoke-TypeCheck
        Test-Coverage
        
        Write-Host ""
        Write-Host "==> CI Pipeline Complete" -ForegroundColor Green
        Write-Host "All checks passed!" -ForegroundColor Green
    } catch {
        Write-Host ""
        Write-Host "==> CI Pipeline Failed" -ForegroundColor Red
        Write-Host $_.Exception.Message
        exit 1
    }
}

function Show-Help {
    Write-Host @"

Strands CLI - Development Automation

Usage: .\scripts\dev.ps1 <command>

Commands:
  test              Run tests with pytest
  test-cov          Run tests with coverage report
  lint              Run linter (ruff check)
  format            Format code (ruff format)
  typecheck         Type check with mypy
  clean             Clean build artifacts and caches
  build             Build distribution package
  install           Install package in dev mode
  validate-examples Validate all example specs
  ci                Run full CI pipeline (lint + typecheck + test-cov)
  help              Show this help message

Documentation:
  For documentation build/serve/deploy commands, use:
    .\scripts\docs.ps1 help

Examples:
  .\scripts\dev.ps1 test
  .\scripts\dev.ps1 ci
  .\scripts\dev.ps1 validate-examples
  .\scripts\docs.ps1 serve              # Start docs dev server

"@ -ForegroundColor Yellow
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "test" { Test-Dev }
    "test-cov" { Test-Coverage }
    "lint" { Invoke-Lint }
    "format" { Invoke-Format }
    "typecheck" { Invoke-TypeCheck }
    "clean" { Invoke-Clean }
    "build" { Invoke-Build }
    "install" { Invoke-Install }
    "validate-examples" { Invoke-ValidateExamples }
    "ci" { Invoke-CI }
    "help" { Show-Help }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
