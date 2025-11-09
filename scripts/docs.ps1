# Strands CLI - Documentation Build Script
# PowerShell automation for MkDocs documentation

param(
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter()]
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-DocsDependencies {
    Write-Header "Checking documentation dependencies..."
    
    try {
        $result = uv run python -c "import mkdocs; import material" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Documentation dependencies not installed." -ForegroundColor Yellow
            Write-Host "Run: uv sync --dev" -ForegroundColor Yellow
            return $false
        }
        Write-Host "Dependencies OK" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "Error checking dependencies: $_" -ForegroundColor Red
        return $false
    }
}

function Invoke-GenerateSchemaDocs {
    Write-Header "Generating schema documentation..."
    
    $scriptPath = Join-Path $PSScriptRoot "generate_schema_docs.py"
    if (-not (Test-Path $scriptPath)) {
        Write-Host "Error: generate_schema_docs.py not found at $scriptPath" -ForegroundColor Red
        exit 1
    }
    
    uv run python $scriptPath
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Schema docs generated successfully" -ForegroundColor Green
    } else {
        Write-Host "Failed to generate schema docs" -ForegroundColor Red
        exit 1
    }
}

function Invoke-GenerateAll {
    Write-Header "Generating all auto-generated documentation..."
    
    # Schema docs
    Invoke-GenerateSchemaDocs
    
    # Future: Add CLI docs generation if needed
    # Future: Add API docs generation if needed
    
    Write-Host ""
    Write-Host "All documentation generated successfully" -ForegroundColor Green
}

function Invoke-Serve {
    param([int]$Port = 8000)
    
    if (-not (Test-DocsDependencies)) {
        exit 1
    }
    
    Invoke-GenerateAll
    
    Write-Header "Starting MkDocs development server on port $Port..."
    Write-Host "Documentation will be available at: http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
    Write-Host ""
    
    uv run mkdocs serve --dev-addr "127.0.0.1:$Port"
}

function Invoke-Build {
    if (-not (Test-DocsDependencies)) {
        exit 1
    }
    
    Invoke-GenerateAll
    
    Write-Header "Building documentation site..."
    
    $buildArgs = @("build")
    if ($Strict) {
        Write-Host "Building with --strict mode (warnings as errors)" -ForegroundColor Yellow
        $buildArgs += "--strict"
    }
    
    uv run mkdocs @buildArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Documentation built successfully!" -ForegroundColor Green
        Write-Host "Output: site/" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Documentation build failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-Clean {
    Write-Header "Cleaning documentation build artifacts..."
    
    $pathsToRemove = @(
        "site",
        ".cache"
    )
    
    foreach ($path in $pathsToRemove) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "Removed: $path" -ForegroundColor Green
        }
    }
    
    Write-Host "Documentation artifacts cleaned" -ForegroundColor Green
}

function Invoke-Deploy {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Version,
        
        [string]$Alias = "latest",
        
        [switch]$Push
    )
    
    if (-not (Test-DocsDependencies)) {
        exit 1
    }
    
    Invoke-GenerateAll
    
    Write-Header "Deploying documentation version $Version (alias: $Alias)..."
    
    $deployArgs = @(
        "deploy",
        "--update-aliases",
        $Version,
        $Alias
    )
    
    if ($Push) {
        Write-Host "Will push to remote repository" -ForegroundColor Yellow
        $deployArgs += "--push"
    } else {
        Write-Host "Local deployment only (use -Push to deploy to remote)" -ForegroundColor Yellow
    }
    
    uv run mike @deployArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Documentation deployed successfully!" -ForegroundColor Green
        if (-not $Push) {
            Write-Host "To push to GitHub Pages, run: .\scripts\docs.ps1 deploy -Version $Version -Alias $Alias -Push" -ForegroundColor Yellow
        }
    } else {
        Write-Host ""
        Write-Host "Documentation deployment failed" -ForegroundColor Red
        exit 1
    }
}

function Invoke-SetDefault {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Version
    )
    
    Write-Header "Setting default version to $Version..."
    
    uv run mike set-default $Version
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Default version set successfully!" -ForegroundColor Green
    } else {
        Write-Host "Failed to set default version" -ForegroundColor Red
        exit 1
    }
}

function Invoke-ListVersions {
    Write-Header "Listing deployed documentation versions..."
    
    uv run mike list
}

function Invoke-Validate {
    Write-Header "Validating documentation..."
    
    # Check for broken links and build with strict mode
    Invoke-Build -Strict
    
    Write-Host ""
    Write-Host "Documentation validation complete" -ForegroundColor Green
}

function Show-Help {
    Write-Host @"

Strands CLI - Documentation Build Script

Usage: .\scripts\docs.ps1 <command> [options]

Commands:
  serve              Start MkDocs development server (default: http://127.0.0.1:8000)
  build              Build documentation site to site/
  build -Strict      Build with strict mode (warnings as errors)
  clean              Remove build artifacts (site/, .cache/)
  generate           Generate all auto-generated docs (schema, etc.)
  validate           Validate documentation (build with --strict)
  
  deploy             Deploy versioned documentation with mike
    -Version <ver>   Version identifier (e.g., "v0.11", "latest")
    -Alias <alias>   Version alias (default: "latest")
    -Push            Push to remote repository (GitHub Pages)
  
  set-default        Set default version for documentation
    -Version <ver>   Version to set as default
  
  list-versions      List all deployed documentation versions
  
  help               Show this help message

Examples:
  # Development workflow
  .\scripts\docs.ps1 serve                    # Start dev server
  .\scripts\docs.ps1 build                    # Build locally
  .\scripts\docs.ps1 build -Strict            # Build with strict mode
  .\scripts\docs.ps1 validate                 # Validate docs
  
  # Deployment workflow
  .\scripts\docs.ps1 deploy -Version v0.11 -Alias latest          # Deploy locally
  .\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push    # Deploy to GitHub Pages
  .\scripts\docs.ps1 set-default -Version latest                  # Set default version
  .\scripts\docs.ps1 list-versions                                # List versions

Notes:
  - Run 'uv sync --dev' to install documentation dependencies
  - Documentation source is in manual/
  - Built site output is in site/
  - MkDocs configuration is in mkdocs.yml
  - Auto-generated docs (schema) are regenerated on each build

"@ -ForegroundColor Yellow
}

# Main command dispatcher
switch ($Command.ToLower()) {
    "serve" {
        Invoke-Serve
    }
    "build" {
        Invoke-Build
    }
    "clean" {
        Invoke-Clean
    }
    "generate" {
        Invoke-GenerateAll
    }
    "validate" {
        Invoke-Validate
    }
    "deploy" {
        # Parse additional parameters from remaining args
        $version = $null
        $alias = "latest"
        $push = $false
        
        for ($i = 0; $i -lt $args.Count; $i++) {
            if ($args[$i] -eq "-Version" -and $i+1 -lt $args.Count) {
                $version = $args[$i+1]
                $i++
            } elseif ($args[$i] -eq "-Alias" -and $i+1 -lt $args.Count) {
                $alias = $args[$i+1]
                $i++
            } elseif ($args[$i] -eq "-Push") {
                $push = $true
            }
        }
        
        if (-not $version) {
            Write-Host "Error: -Version parameter required for deploy command" -ForegroundColor Red
            Write-Host "Example: .\scripts\docs.ps1 deploy -Version v0.11 -Alias latest" -ForegroundColor Yellow
            exit 1
        }
        
        if ($push) {
            Invoke-Deploy -Version $version -Alias $alias -Push
        } else {
            Invoke-Deploy -Version $version -Alias $alias
        }
    }
    "set-default" {
        $version = $null
        for ($i = 0; $i -lt $args.Count; $i++) {
            if ($args[$i] -eq "-Version" -and $i+1 -lt $args.Count) {
                $version = $args[$i+1]
                $i++
            }
        }
        
        if (-not $version) {
            Write-Host "Error: -Version parameter required for set-default command" -ForegroundColor Red
            Write-Host "Example: .\scripts\docs.ps1 set-default -Version latest" -ForegroundColor Yellow
            exit 1
        }
        
        Invoke-SetDefault -Version $version
    }
    "list-versions" {
        Invoke-ListVersions
    }
    "help" {
        Show-Help
    }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
