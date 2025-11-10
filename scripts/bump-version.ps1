#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Bump version across all project files

.DESCRIPTION
    Updates version numbers in:
    - pyproject.toml
    - src/strands_cli/__init__.py
    - tests/test_version.py
    - README.md
    - manual/reference/cli.md
    - manual/howto/tools.md
    - .github/workflows/docs.yml

.PARAMETER Version
    The new version number (semantic version: X.Y.Z)

.PARAMETER Commit
    Create a git commit with the version bump

.PARAMETER Tag
    Create a git tag for the version

.PARAMETER Push
    Push the commit and tag to origin

.EXAMPLE
    .\scripts\bump-version.ps1 -Version 0.2.0

.EXAMPLE
    .\scripts\bump-version.ps1 -Version 0.2.0 -Commit -Tag -Push
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [Parameter(Mandatory = $false)]
    [switch]$Commit,

    [Parameter(Mandatory = $false)]
    [switch]$Tag,

    [Parameter(Mandatory = $false)]
    [switch]$Push
)

$ErrorActionPreference = 'Stop'

# Validate semantic version format
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Error "Version must be in semantic version format: X.Y.Z"
    exit 1
}

Write-Host "🔄 Bumping version to $Version" -ForegroundColor Cyan
Write-Host ""

# Get current version from pyproject.toml
$pyprojectPath = "pyproject.toml"
$pyprojectContent = Get-Content $pyprojectPath -Raw
if ($pyprojectContent -match 'version = "(\d+\.\d+\.\d+)"') {
    $currentVersion = $matches[1]
    Write-Host "Current version: $currentVersion" -ForegroundColor Yellow
    Write-Host "New version: $Version" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Error "Could not find current version in pyproject.toml"
    exit 1
}

# Files to update with simple version replacement
$filesToUpdate = @(
    @{
        Path = "pyproject.toml"
        Pattern = 'version = "\d+\.\d+\.\d+"'
        Replacement = "version = `"$Version`""
    },
    @{
        Path = "src\strands_cli\__init__.py"
        Pattern = '__version__ = "\d+\.\d+\.\d+"'
        Replacement = "__version__ = `"$Version`""
    },
    @{
        Path = "tests\test_version.py"
        Pattern = 'assert strands_cli\.__version__ == "\d+\.\d+\.\d+"'
        Replacement = "assert strands_cli.__version__ == `"$Version`""
    },
    @{
        Path = "README.md"
        Pattern = 'version-\d+\.\d+\.\d+-brightgreen'
        Replacement = "version-$Version-brightgreen"
    },
    @{
        Path = "README.md"
        Pattern = 'strands-cli version \d+\.\d+\.\d+'
        Replacement = "strands-cli version $Version"
    },
    @{
        Path = "README.md"
        Pattern = 'Current Version \(v\d+\.\d+\.\d+\)'
        Replacement = "Current Version (v$Version)"
    },
    @{
        Path = "manual\reference\cli.md"
        Pattern = '\(e\.g\., `\d+\.\d+\.\d+`\)'
        Replacement = "(e.g., ``$Version``)"
    },
    @{
        Path = ".github\workflows\docs.yml"
        Pattern = "default: 'v\d+\.\d+'"
        Replacement = "default: 'v$($Version -replace '\.\d+$', '')'"
    }
)

# Update each file
$updatedFiles = @()
foreach ($file in $filesToUpdate) {
    if (Test-Path $file.Path) {
        $content = Get-Content $file.Path -Raw
        $newContent = $content -replace $file.Pattern, $file.Replacement
        
        if ($content -ne $newContent) {
            Set-Content -Path $file.Path -Value $newContent -NoNewline
            Write-Host "✅ Updated $($file.Path)" -ForegroundColor Green
            $updatedFiles += $file.Path
        } else {
            Write-Host "⚠️  No changes needed in $($file.Path)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "⚠️  File not found: $($file.Path)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "✨ Version bump complete!" -ForegroundColor Green
Write-Host ""

# Git operations
if ($Commit -or $Tag -or $Push) {
    # Check if git is available
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Error "Git is not available. Cannot perform git operations."
        exit 1
    }

    # Check if there are changes to commit
    $gitStatus = git status --porcelain
    if (-not $gitStatus -and -not $Tag) {
        Write-Host "No changes to commit." -ForegroundColor Yellow
        exit 0
    }

    if ($Commit) {
        Write-Host "📝 Creating git commit..." -ForegroundColor Cyan
        foreach ($file in $updatedFiles) {
            git add $file
        }
        git commit -m "chore: bump version to $Version"
        Write-Host "✅ Committed version bump" -ForegroundColor Green
        Write-Host ""
    }

    if ($Tag) {
        Write-Host "🏷️  Creating git tag v$Version..." -ForegroundColor Cyan
        git tag "v$Version"
        Write-Host "✅ Created tag v$Version" -ForegroundColor Green
        Write-Host ""
    }

    if ($Push) {
        Write-Host "⬆️  Pushing to origin..." -ForegroundColor Cyan
        git push origin master
        if ($Tag) {
            git push origin "v$Version"
        }
        Write-Host "✅ Pushed to origin" -ForegroundColor Green
        Write-Host ""
    }
}

Write-Host "📋 Summary:" -ForegroundColor Cyan
Write-Host "  • Updated $($updatedFiles.Count) files" -ForegroundColor White
Write-Host "  • Version: $currentVersion → $Version" -ForegroundColor White

if ($Tag) {
    Write-Host ""
    Write-Host "🚀 Next steps:" -ForegroundColor Cyan
    Write-Host "  The tag v$Version will trigger the release workflow:" -ForegroundColor White
    Write-Host "  • GitHub Actions will run tests" -ForegroundColor Gray
    Write-Host "  • Build and publish to PyPI" -ForegroundColor Gray
    Write-Host "  • Create GitHub Release" -ForegroundColor Gray
}

Write-Host ""
