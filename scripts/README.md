# Development Scripts

PowerShell automation scripts for Strands CLI development and documentation.

## Quick Reference

### Development Tasks (`dev.ps1`)

```powershell
# Testing
.\scripts\dev.ps1 test              # Run all tests
.\scripts\dev.ps1 test-cov          # Run tests with coverage report

# Code Quality
.\scripts\dev.ps1 lint              # Run ruff linter
.\scripts\dev.ps1 format            # Format code with ruff
.\scripts\dev.ps1 typecheck         # Type check with mypy

# CI Pipeline
.\scripts\dev.ps1 ci                # Run full pipeline (lint + typecheck + test-cov)

# Validation
.\scripts\dev.ps1 validate-examples # Validate all YAML examples

# Build & Install
.\scripts\dev.ps1 build             # Build distribution package
.\scripts\dev.ps1 install           # Install in dev mode
.\scripts\dev.ps1 clean             # Clean build artifacts
```

### Documentation Tasks (`docs.ps1`)

```powershell
# Development
.\scripts\docs.ps1 serve            # Start dev server at http://127.0.0.1:8000
.\scripts\docs.ps1 build            # Build docs to site/
.\scripts\docs.ps1 build -Strict    # Build with strict mode (warnings as errors)
.\scripts\docs.ps1 validate         # Validate docs (strict build)

# Auto-generation
.\scripts\docs.ps1 generate         # Generate all auto-generated docs (schema, etc.)

# Deployment (GitHub Pages via mike)
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest          # Deploy locally
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push    # Deploy to GitHub Pages
.\scripts\docs.ps1 set-default -Version latest                  # Set default version
.\scripts\docs.ps1 list-versions                                # List all versions

# Cleanup
.\scripts\docs.ps1 clean            # Remove site/ and .cache/
```

## Documentation Workflow

### Local Development

1. **Install dependencies** (first time only):
   ```powershell
   uv sync --dev
   ```

2. **Start dev server**:
   ```powershell
   .\scripts\docs.ps1 serve
   ```
   - Opens at http://127.0.0.1:8000
   - Auto-reloads on file changes
   - Generates schema docs automatically

3. **Edit documentation**:
   - Source files in `manual/`
   - Configuration in `mkdocs.yml`
   - Follow [Diátaxis framework](https://diataxis.fr/) (Tutorials/How-To/Explanation/Reference)

4. **Validate changes**:
   ```powershell
   .\scripts\docs.ps1 validate
   ```

### Deployment to GitHub Pages

#### Automatic Deployment (via CI/CD)

When you push a git tag matching `v*` pattern, GitHub Actions will:

1. Build documentation with strict mode
2. Deploy to GitHub Pages with version based on tag
3. Set version alias to "latest"

```bash
# Example: Release v0.11.0
git tag v0.11.0
git push origin v0.11.0
# Documentation automatically deployed to https://thomasrohde.github.io/strands-cli/
```

You can also trigger manual deployment via GitHub Actions:

1. Go to GitHub repository → Actions → Documentation workflow
2. Click "Run workflow"
3. Enter version (e.g., `v0.11`) and alias (e.g., `latest`)
4. Click "Run workflow"

#### Manual Deployment (local)

1. **Build and test locally**:
   ```powershell
   .\scripts\docs.ps1 build -Strict
   ```

2. **Deploy version**:
   ```powershell
   # For new release v0.11
   .\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push
   
   # For development/preview
   .\scripts\docs.ps1 deploy -Version dev -Alias dev -Push
   ```

3. **Set default version** (optional):
   ```powershell
   .\scripts\docs.ps1 set-default -Version latest
   ```

4. **View deployed docs**:
   - Main site: https://thomasrohde.github.io/strands-cli/
   - Version switcher in top bar

## Auto-Generated Documentation

The following docs are generated automatically on each build:

- **Schema Reference** (`manual/reference/schema.md`):
  - Generated from `src/strands_cli/schema/strands-workflow.schema.json`
  - Script: `scripts/generate_schema_docs.py`
  - Auto-run on `serve` and `build`

- **CLI Reference** (`manual/reference/cli.md`):
  - Generated from Typer decorators in `src/strands_cli/__main__.py`
  - Uses `mkdocs-typer` plugin

- **API Reference** (`manual/reference/api/*.md`):
  - Generated from Python docstrings
  - Uses `mkdocstrings-python` plugin

## Documentation Structure

```
manual/
├── index.md                    # Landing page
├── tutorials/                  # Step-by-step learning paths
│   ├── quickstart-ollama.md
│   ├── quickstart-bedrock.md
│   ├── quickstart-openai.md
│   └── first-multi-step.md
├── howto/                      # Task-oriented guides
│   ├── validate-workflows.md
│   ├── run-workflows.md
│   ├── context-management.md
│   ├── telemetry.md
│   ├── tools.md
│   ├── secrets.md
│   ├── budgets.md
│   └── patterns/               # Pattern-specific guides
│       ├── chain.md
│       ├── workflow.md
│       ├── routing.md
│       ├── parallel.md
│       ├── evaluator-optimizer.md
│       ├── graph.md
│       └── orchestrator-workers.md
├── explanation/                # Conceptual documentation
│   ├── architecture.md
│   ├── patterns.md
│   ├── design-decisions.md
│   ├── performance.md
│   └── security-model.md
└── reference/                  # Technical reference
    ├── cli.md                  # Auto-generated
    ├── schema.md               # Auto-generated
    ├── exit-codes.md
    ├── environment.md
    ├── examples.md
    └── api/                    # Auto-generated
        ├── index.md
        ├── runtime.md
        ├── exec.md
        └── ...
```

## Tips & Best Practices

### Quality Gates

The project includes automated quality checks for documentation:

- **Markdownlint**: Checks Markdown style and formatting
  - Config: `.markdownlint-cli2.yaml`
  - Run: `markdownlint-cli2 "manual/**/*.md"`

- **Codespell**: Checks for typos and spelling errors
  - Config: `.codespellrc`
  - Run: `codespell manual/ README.md`

- **Strict Build**: Fails on warnings (broken links, missing references)
  - Run: `.\scripts\docs.ps1 build -Strict`

- **Pre-commit Hooks**: Automatic checks before commits
  - Install: `pip install pre-commit && pre-commit install`
  - Run manually: `pre-commit run --all-files`

All quality gates run automatically in CI on pull requests.

### When to Regenerate Docs

- **Schema changes**: Edit JSON Schema → run `.\scripts\docs.ps1 generate`
- **CLI changes**: Edit Typer commands → rebuild docs
- **API changes**: Edit docstrings → rebuild docs
- **Manual content**: Edit markdown in `manual/` → auto-reloads in dev server

### Writing Documentation

Follow the [Diátaxis framework](https://diataxis.fr/):

- **Tutorials**: Learning-oriented, step-by-step for beginners
- **How-To Guides**: Task-oriented, solve specific problems
- **Explanation**: Understanding-oriented, discuss concepts and architecture
- **Reference**: Information-oriented, technical specifications

### Testing Before Deployment

```powershell
# Full validation workflow
.\scripts\docs.ps1 clean
.\scripts\docs.ps1 build -Strict
.\scripts\docs.ps1 validate
```

## Troubleshooting

### Dependencies Not Installed
```powershell
uv sync --dev
```

### Schema Docs Not Updating
```powershell
.\scripts\docs.ps1 generate
```

### Build Warnings/Errors
```powershell
# See detailed output
.\scripts\docs.ps1 build -Strict
```

### Clear Cache
```powershell
.\scripts\docs.ps1 clean
```

## See Also

- **Documentation Plan**: `docs/MANUAL.md` - Full implementation phases
- **MkDocs Config**: `mkdocs.yml` - Site configuration
- **Schema Generator**: `scripts/generate_schema_docs.py` - Schema doc generation
- **Manual Source**: `manual/` - All documentation source files
