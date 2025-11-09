# Documentation Deployment Guide

Complete guide for deploying Strands CLI documentation to GitHub Pages with versioning.

## Overview

The documentation is built using **MkDocs + Material for MkDocs** and deployed to GitHub Pages with version management via **mike**.

- **Documentation site**: https://thomasrohde.github.io/strands-cli/
- **Source**: `manual/` directory
- **Configuration**: `mkdocs.yml`
- **CI/CD**: `.github/workflows/docs.yml`

## Quick Start

### Local Development

```powershell
# Start development server
.\scripts\docs.ps1 serve

# Build locally
.\scripts\docs.ps1 build

# Validate (strict mode)
.\scripts\docs.ps1 validate
```

Visit http://127.0.0.1:8000 to view your local docs.

## Deployment Options

### Option 1: Automatic (Recommended)

Push a git tag to trigger automatic deployment:

```bash
# Create and push tag
git tag v0.11.0
git push origin v0.11.0

# GitHub Actions will:
# 1. Build documentation with strict mode
# 2. Deploy to GitHub Pages as version v0.11
# 3. Set alias to "latest"
# 4. Update version switcher
```

### Option 2: Manual GitHub Actions

1. Go to **GitHub → Actions → Documentation**
2. Click **"Run workflow"**
3. Enter:
   - **Version**: `v0.11` (or `dev`, `preview`, etc.)
   - **Alias**: `latest` (or `stable`, `dev`, etc.)
4. Click **"Run workflow"**

### Option 3: Local Deployment

```powershell
# Deploy from local machine
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push

# Set default version
.\scripts\docs.ps1 set-default -Version latest -Push

# List all deployed versions
.\scripts\docs.ps1 list-versions
```

## Version Management with Mike

### Version Naming Convention

- **`v0.11`, `v0.12`, etc.**: Major/minor releases (e.g., v0.11.0 → v0.11)
- **`latest`**: Alias for the most recent stable release
- **`stable`**: Alias for the last stable LTS version (optional)
- **`dev`**: Development/preview version

### Version Aliases

Aliases provide user-friendly URLs:

```powershell
# Deploy v0.11 with "latest" alias
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push

# Users can visit:
# - https://thomasrohde.github.io/strands-cli/        (redirects to latest)
# - https://thomasrohde.github.io/strands-cli/latest/ (latest version)
# - https://thomasrohde.github.io/strands-cli/v0.11/  (specific version)
```

### Managing Versions

```powershell
# List all deployed versions
.\scripts\docs.ps1 list-versions

# Set default version (landing page)
.\scripts\docs.ps1 set-default -Version latest -Push

# Delete a version (via mike directly)
uv run mike delete v0.10
uv run mike deploy --push  # Push changes
```

## GitHub Pages Setup

### First-Time Configuration

1. **Enable GitHub Pages**:
   - Go to **Repository → Settings → Pages**
   - Source: **Deploy from a branch**
   - Branch: **gh-pages** / **root**
   - Save

2. **Configure Repository Permissions**:
   - Go to **Repository → Settings → Actions → General**
   - Workflow permissions: **Read and write permissions**
   - Allow GitHub Actions to create and approve pull requests: **Checked**
   - Save

3. **Verify Deployment**:
   - After first deployment, visit: https://thomasrohde.github.io/strands-cli/
   - Check that version switcher appears in top navigation

## Auto-Generated Documentation

The following documentation is automatically generated during builds:

### Schema Reference

- **File**: `manual/reference/schema.md`
- **Source**: `src/strands_cli/schema/strands-workflow.schema.json`
- **Generator**: `scripts/generate_schema_docs.py`
- **When**: Runs on every `serve` and `build`

### CLI Reference

- **File**: `manual/reference/cli.md`
- **Source**: Typer decorators in `src/strands_cli/__main__.py`
- **Generator**: `mkdocs-typer` plugin
- **When**: Runs during MkDocs build

### API Reference

- **Files**: `manual/reference/api/*.md`
- **Source**: Python docstrings in `src/strands_cli/`
- **Generator**: `mkdocstrings-python` plugin
- **When**: Runs during MkDocs build

## Quality Checks

Documentation includes automated quality gates:

### Markdownlint

Checks Markdown formatting and style:

```powershell
# Install
npm install -g markdownlint-cli2

# Run
markdownlint-cli2 "manual/**/*.md"

# Configuration
# See: .markdownlint-cli2.yaml
```

### Codespell

Checks for typos and spelling errors:

```powershell
# Install
pip install codespell

# Run
codespell manual/ README.md

# Configuration
# See: .codespellrc
```

### Strict Build Mode

Fails on warnings (broken links, missing references):

```powershell
# Build with strict mode
.\scripts\docs.ps1 build -Strict

# Or via uv directly
uv run mkdocs build --strict
```

### Pre-commit Hooks

Automatically run quality checks before commits:

```powershell
# Install
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files

# Configuration
# See: .pre-commit-config.yaml
```

## CI/CD Pipeline

Documentation is automatically validated and deployed via GitHub Actions.

### Workflow: `.github/workflows/docs.yml`

**Triggers**:
- Git tags matching `v*` pattern
- Manual workflow dispatch

**Jobs**:
1. **Build and Deploy**:
   - Install dependencies
   - Generate auto-generated docs
   - Build with strict mode
   - Deploy to GitHub Pages via mike
   - Update version aliases

2. **Validate** (manual dispatch only):
   - Build with strict mode
   - Check for broken links
   - Validate documentation quality

### Workflow: `.github/workflows/ci.yml`

Includes **Documentation Quality Checks** job on every PR:
- Markdownlint (Markdown style)
- Codespell (typo checking)
- Strict build (broken links)

## Troubleshooting

### Build Fails with "Config value: 'plugins'"

Ensure all plugins are installed:
```powershell
uv sync --dev
```

### Version Not Appearing in Switcher

Check that version was deployed with an alias:
```powershell
.\scripts\docs.ps1 list-versions
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push
```

### Broken Links in Build

Run strict mode to see details:
```powershell
.\scripts\docs.ps1 build -Strict
```

Fix broken links in source files, then rebuild.

### Schema Docs Not Updating

Regenerate schema docs:
```powershell
uv run python scripts/generate_schema_docs.py
```

Or run full generation:
```powershell
.\scripts\docs.ps1 generate
```

### GitHub Pages Not Updating

1. Check GitHub Actions logs: **Repository → Actions**
2. Verify gh-pages branch exists and has content
3. Check Pages settings: **Repository → Settings → Pages**
4. Wait 2-3 minutes for deployment to propagate

### Permission Denied on Deployment

Ensure GitHub Actions has write permissions:
- **Repository → Settings → Actions → General**
- Workflow permissions: **Read and write permissions**

## Best Practices

### Documentation Updates

1. **Edit locally**:
   ```powershell
   .\scripts\docs.ps1 serve
   # Edit files in manual/
   # Preview at http://127.0.0.1:8000
   ```

2. **Validate**:
   ```powershell
   .\scripts\docs.ps1 validate
   ```

3. **Commit and push**:
   ```bash
   git add manual/
   git commit -m "docs: update tutorial"
   git push
   ```

4. **Deploy** (for releases):
   ```bash
   git tag v0.11.0
   git push origin v0.11.0
   # Automatic deployment via GitHub Actions
   ```

### Version Deployment Strategy

- **Major/Minor Releases**: Deploy as `v0.11`, `v0.12` with `latest` alias
- **Patch Releases**: Update existing version (e.g., v0.11.1 updates v0.11)
- **Development**: Deploy as `dev` without `latest` alias
- **Legacy Versions**: Keep deployed for reference, use `stable` alias for LTS

### Writing Documentation

Follow the [Diátaxis framework](https://diataxis.fr/):

- **Tutorials** (`manual/tutorials/`): Learning-oriented, step-by-step
- **How-To** (`manual/howto/`): Task-oriented, problem-solving
- **Explanation** (`manual/explanation/`): Understanding-oriented, concepts
- **Reference** (`manual/reference/`): Information-oriented, specifications

## Resources

- **MkDocs**: https://www.mkdocs.org/
- **Material for MkDocs**: https://squidfunk.github.io/mkdocs-material/
- **mike (versioning)**: https://github.com/jimporter/mike
- **Diátaxis**: https://diataxis.fr/
- **mkdocstrings**: https://mkdocstrings.github.io/
- **mkdocs-typer**: https://github.com/bruce-szalwinski/mkdocs-typer

## See Also

- **Documentation Plan**: `docs/MANUAL.md` - Phased implementation guide
- **Scripts README**: `scripts/README.md` - Development scripts documentation
- **MkDocs Config**: `mkdocs.yml` - Site configuration
