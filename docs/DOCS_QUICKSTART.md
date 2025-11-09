# Documentation Quick Start Guide

## 🎯 TL;DR

```powershell
# Start documentation server
.\scripts\docs.ps1 serve

# Open browser to: http://127.0.0.1:8000/strands-cli/
```

---

## 📋 All Available Commands

```powershell
# Development
.\scripts\docs.ps1 serve              # Start dev server
.\scripts\docs.ps1 build              # Build docs
.\scripts\docs.ps1 build -Strict      # Build with strict mode
.\scripts\docs.ps1 validate           # Validate docs
.\scripts\docs.ps1 generate           # Generate auto-docs
.\scripts\docs.ps1 clean              # Clean artifacts

# Deployment
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest          # Local deploy
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push    # Deploy to GitHub
.\scripts\docs.ps1 set-default -Version latest                  # Set default
.\scripts\docs.ps1 list-versions                                # List versions

# Help
.\scripts\docs.ps1 help               # Show full help
```

---

## 🗂️ File Organization

```
strands-cli/
├── scripts/
│   ├── docs.ps1                  ⭐ Documentation build script
│   ├── dev.ps1                   ⭐ Development automation script
│   ├── generate_schema_docs.py   ⭐ Schema doc generator
│   └── README.md                 📖 Scripts documentation
├── manual/                       📝 Documentation source files
│   ├── index.md
│   ├── tutorials/
│   ├── howto/
│   ├── explanation/
│   └── reference/
├── mkdocs.yml                    ⚙️ MkDocs configuration
├── site/                         🏗️ Built documentation (generated)
├── docs/                         📁 Legacy docs (to be migrated)
├── DOCS_BUILD_SUMMARY.md         📊 This summary
└── pyproject.toml                📦 Dependencies (includes [docs])
```

---

## 🔧 Common Workflows

### First Time Setup

```powershell
# Install all dependencies
uv sync --dev

# Start server
.\scripts\docs.ps1 serve
```

### Edit Documentation

```powershell
# 1. Start dev server (auto-reloads on changes)
.\scripts\docs.ps1 serve

# 2. Edit files in manual/
#    - manual/tutorials/*.md
#    - manual/howto/*.md
#    - manual/explanation/*.md
#    - manual/reference/*.md

# 3. See changes immediately in browser
#    http://127.0.0.1:8000/strands-cli/

# 4. Validate before committing
.\scripts\docs.ps1 validate
```

### Build for Review

```powershell
# Build static site
.\scripts\docs.ps1 build

# Open site/index.html in browser
# Or use a local server:
python -m http.server --directory site 9000
```

### Deploy to GitHub Pages

```powershell
# Step 1: Test locally
.\scripts\docs.ps1 build -Strict

# Step 2: Deploy (requires git permissions)
.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push

# Step 3: Visit docs
# https://thomasrohde.github.io/strands-cli/
```

---

## 📊 Documentation Structure

```
Diátaxis Framework
├── 📘 Tutorials (Learning-oriented)
│   ├── quickstart-ollama.md
│   ├── quickstart-bedrock.md
│   ├── quickstart-openai.md
│   └── first-multi-step.md
├── 🔧 How-To Guides (Task-oriented)
│   ├── validate-workflows.md
│   ├── run-workflows.md
│   ├── context-management.md
│   ├── telemetry.md
│   ├── tools.md
│   ├── secrets.md
│   ├── budgets.md
│   └── patterns/
│       ├── chain.md
│       ├── workflow.md
│       ├── routing.md
│       ├── parallel.md
│       ├── evaluator-optimizer.md
│       ├── graph.md
│       └── orchestrator-workers.md
├── 💡 Explanation (Understanding-oriented) [TODO]
│   ├── architecture.md
│   ├── patterns.md
│   ├── design-decisions.md
│   ├── performance.md
│   └── security-model.md
└── 📚 Reference (Information-oriented)
    ├── cli.md (auto-generated)
    ├── schema.md (auto-generated)
    ├── exit-codes.md
    ├── environment.md
    ├── examples.md
    └── api/ (auto-generated)
```

---

## 🎨 What Gets Auto-Generated

| File | Source | Generator |
|------|--------|-----------|
| `reference/schema.md` | `src/strands_cli/schema/*.json` | `scripts/generate_schema_docs.py` |
| `reference/cli.md` | `src/strands_cli/__main__.py` | mkdocs-typer plugin |
| `reference/api/*.md` | Python docstrings | mkdocstrings-python plugin |

**Note**: Auto-generated docs are rebuilt on every `serve` and `build` command.

---

## ⚡ Quick Tips

### Speed Up Development
```powershell
# Leave server running, edit files, see changes instantly
.\scripts\docs.ps1 serve
# Then edit manual/*.md files
```

### Fix Broken Links
```powershell
# Build with strict mode to catch all issues
.\scripts\docs.ps1 build -Strict
```

### Clean Start
```powershell
# Remove all generated files
.\scripts\docs.ps1 clean

# Fresh build
.\scripts\docs.ps1 build
```

### Update Schema Docs
```powershell
# Edit: src/strands_cli/schema/strands-workflow.schema.json
# Then regenerate:
.\scripts\docs.ps1 generate
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Module not found: mkdocs" | Run `uv sync --dev` |
| Server won't start | Run `.\scripts\docs.ps1 clean` then retry |
| Schema docs outdated | Run `.\scripts\docs.ps1 generate` |
| Build warnings | Fix missing links or use `-Strict` to fail fast |
| Port 8000 in use | Kill process or use different port |

---

## 📖 Learn More

- **Full Documentation**: See `scripts/README.md`
- **Build Summary**: See `DOCS_BUILD_SUMMARY.md`
- **Implementation Plan**: See `docs/MANUAL.md`
- **MkDocs Config**: See `mkdocs.yml`
- **Diátaxis Framework**: https://diataxis.fr/

---

## 🎯 Next Actions

1. ✅ **Start the server**: `.\scripts\docs.ps1 serve`
2. ✅ **Open browser**: http://127.0.0.1:8000/strands-cli/
3. ✅ **Edit docs**: Files in `manual/`
4. ✅ **Validate**: `.\scripts\docs.ps1 validate`
5. ✅ **Deploy**: `.\scripts\docs.ps1 deploy -Version v0.11 -Alias latest -Push`

---

**Happy documenting! 📝**
