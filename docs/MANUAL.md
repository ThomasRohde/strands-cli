# Strands-CLI Documentation Manual - Phased Implementation Plan

## Overview
Build a production-ready documentation site using **MkDocs + Material for MkDocs**, following the **Diátaxis** framework (Tutorials, How-to, Explanation, Reference), with automated deployment to GitHub Pages.

## Tech Stack Decisions
- **Static Site**: MkDocs + Material for MkDocs
- **API Docs**: mkdocstrings-python with Griffe
- **CLI Docs**: mkdocs-typer (native Typer plugin)
- **Schema Docs**: jsonschema-markdown (auto-generated from JSON Schema)
- **Versioning**: mike (for version switcher)
- **Deployment**: GitHub Actions → GitHub Pages
- **Extras**: Mermaid diagrams, pymdown-extensions
- **PDF**: Not included (can add later)
- **Man Pages**: Not included (can add later)

---

## Phase 1: Foundation & Infrastructure

**Goal**: Set up MkDocs infrastructure and base configuration

- [x] Create `manual/` directory structure
- [x] Install MkDocs dependencies (add to `pyproject.toml` optional deps)
- [x] Create initial `mkdocs.yml` with Material theme
- [x] Set up basic navigation structure (Tutorials/How-to/Explanation/Reference)
- [x] Configure Material theme features (code copy, navigation tabs, TOC)
- [x] Add essential markdown extensions (admonition, superfences, tabbed, snippets)
- [x] Create placeholder `index.md` (landing page)
- [x] Test local build: `mkdocs serve`

**Deliverables**: Working MkDocs site with Material theme, builds locally

---

## Phase 2: Reference Documentation (Auto-Generated)

**Goal**: Automated reference docs from code, schema, and CLI

- [x] Configure **mkdocstrings-python** for API documentation
  - Create `manual/reference/api/index.md` with module stubs
  - Document key modules: `runtime`, `exec`, `loader`, `schema`, `telemetry`
- [x] Configure **mkdocs-typer** for CLI documentation
  - Create `manual/reference/cli.md`
  - Configure typer directive for `strands_cli.__main__:app`
- [x] Generate **schema documentation** from JSON Schema
  - Install `jsonschema-markdown` or `jsonschema2md`
  - Create automation script to generate `manual/reference/schema.md`
  - Document all workflow spec properties
- [x] Create **exit codes reference** from `exit_codes.py`
- [x] Create **environment variables reference** from `config.py`

**Deliverables**: Complete auto-generated reference docs (CLI, API, Schema, Exit Codes, Env Vars) ✅

---

## Phase 3: Tutorial Content

**Goal**: Step-by-step learning paths for new users

- [x] **Quickstart Tutorial (Ollama)**
  - Prerequisites checklist
  - Installation steps
  - First workflow execution
  - Validation and debugging
  - File: `manual/tutorials/quickstart-ollama.md`
- [x] **Quickstart Tutorial (AWS Bedrock)**
  - AWS setup and credentials
  - Model selection and regions
  - First Bedrock workflow
  - File: `manual/tutorials/quickstart-bedrock.md`
- [x] **Quickstart Tutorial (OpenAI)**
  - API key setup
  - First OpenAI workflow
  - File: `manual/tutorials/quickstart-openai.md`
- [x] **Building Your First Multi-Step Workflow**
  - Chain pattern walkthrough
  - Variable substitution
  - Context threading
  - File: `manual/tutorials/first-multi-step.md`

**Deliverables**: 4 tutorial documents covering all major providers and basic workflow patterns ✅

---

## Phase 4: How-To Guides

**Goal**: Task-oriented guides for common operations

- [x] **Workflow Validation**
  - Schema validation workflow
  - Common validation errors
  - File: `manual/howto/validate-workflows.md`
- [x] **Running Workflows**
  - Basic execution
  - Variable overrides
  - Output customization
  - File: `manual/howto/run-workflows.md`
- [x] **Working with Patterns**
  - Chain pattern guide
  - Workflow (DAG) pattern guide
  - Routing pattern guide
  - Parallel execution pattern
  - Evaluator-Optimizer pattern
  - Graph pattern (conditionals, loops)
  - Orchestrator-Workers pattern
  - File: `manual/howto/patterns/` (one file per pattern)
- [x] **Context Management**
  - Using presets (minimal/balanced/long_run/interactive)
  - Custom context policies
  - Notes and JIT tools
  - File: `manual/howto/context-management.md`
- [x] **Telemetry and Observability**
  - OpenTelemetry setup
  - Trace exports (OTLP, Console, Artifacts)
  - PII redaction
  - Debug mode
  - File: `manual/howto/telemetry.md`
- [x] **Working with Tools**
  - HTTP executors
  - Python tools (allowlist)
  - File operations (with consent)
  - File: `manual/howto/tools.md`
- [x] **Secrets and Environment Variables**
  - Using `source: env`
  - Best practices
  - File: `manual/howto/secrets.md`
- [x] **Budget Management**
  - Token budgets
  - Time limits
  - Cumulative tracking
  - File: `manual/howto/budgets.md`

**Deliverables**: 8+ how-to guides covering common tasks ✅

---

## Phase 5: Explanation Documentation

**Goal**: Conceptual understanding and architecture

- [x] **Architecture Overview**
  - System components diagram (Mermaid)
  - Data flow
  - Execution model
  - File: `manual/explanation/architecture.md`
- [x] **Pattern Philosophy**
  - Why patterns?
  - When to use each pattern
  - Pattern comparison matrix
  - File: `manual/explanation/patterns.md`
- [x] **Design Decisions**
  - Why YAML/JSON spec?
  - Why JSON Schema Draft 2020-12?
  - Provider abstraction design
  - Security model rationale
  - File: `manual/explanation/design-decisions.md`
- [x] **Performance Optimizations**
  - Agent caching
  - Model client pooling
  - Single event loop strategy
  - File: `manual/explanation/performance.md`
- [x] **Security Model**
  - Template sandboxing
  - SSRF prevention
  - Path traversal protection
  - File: `manual/explanation/security-model.md`

**Deliverables**: 5 explanation documents covering architecture, patterns, design, performance, security ✅

---

## Phase 6: Migration & Integration Guides

**Goal**: Help users migrate existing content and integrate with existing docs

- [x] **Migrate Existing Documentation**
  - Move `docs/strands-workflow-manual.md` content into Diátaxis structure
  - Break down `TOOL_DEVELOPMENT.md` into howto/explanation split
  - Integrate `troubleshooting.md` into reference
  - Integrate `security.md` into explanation + reference
  - Create index/navigation to existing content
- [x] **Examples Catalog**
  - Auto-generate example index from `examples/` folder
  - Add annotations and explanations
  - Link examples to relevant how-to guides
  - File: `manual/reference/examples.md`

**Deliverables**: All existing docs integrated into new structure, examples catalog ✅

---

## Phase 7: Polish & User Experience

**Goal**: Navigation, search, and discoverability improvements

- [ ] **Enhanced Navigation**
  - Add section-index plugin
  - Configure literate-nav for better structure
  - Add navigation tabs for main sections
- [ ] **Search Optimization**
  - Configure search plugin settings
  - Add keywords to frontmatter
  - Test search quality
- [ ] **Visual Enhancements**
  - Add Mermaid diagrams for workflows and architecture
  - Use pymdown-extensions for tabs, admonitions, details
  - Add code block annotations
- [ ] **Cross-Referencing**
  - Add internal links between related docs
  - Create "See Also" sections
  - Link tutorials → how-to → reference

**Deliverables**: Polished navigation, search, and visual enhancements

---

## Phase 8: Automation & CI/CD

**Goal**: Automated builds, versioning, and deployment

- [ ] **Build Automation Scripts**
  - Create script to generate CLI docs (mkdocs-typer)
  - Create script to generate schema docs (jsonschema-markdown)
  - Create script to generate API docs (mkdocstrings)
  - Add `make docs` or PowerShell equivalent
- [ ] **GitHub Actions Workflow**
  - Create `.github/workflows/docs.yml`
  - Trigger on tags (`v*`) and manual dispatch
  - Install all doc dependencies
  - Run generation scripts
  - Build site with `mkdocs build --strict`
  - Deploy with `mike deploy` for versioning
  - Configure GitHub Pages settings
- [ ] **Versioning Setup**
  - Configure mike for version aliases (latest, stable, v0.11, etc.)
  - Add version switcher to Material theme
  - Test version deployment locally
- [ ] **Quality Gates**
  - Add markdownlint-cli2 to pre-commit
  - Add codespell for typo checking
  - Add `mkdocs build --strict` to CI (fail on broken links)

**Deliverables**: Full CI/CD pipeline with versioned docs on GitHub Pages

---

## Phase 9: Maintenance & Iteration

**Goal**: Keep docs in sync with code changes

- [ ] **Documentation Standards**
  - Create CONTRIBUTING-DOCS.md with Diátaxis guidelines
  - Document when to update each section type
  - Add doc update checklist to PR template
- [ ] **Regular Updates**
  - Review and update examples quarterly
  - Update schema docs on spec changes
  - Refresh API docs on major releases
- [ ] **User Feedback Loop**
  - Add "Was this page helpful?" widget (optional)
  - Monitor GitHub issues for doc requests
  - Create "Improve this page" links

**Deliverables**: Documentation maintenance processes and standards

---

## Success Metrics

- [ ] All existing docs migrated to new structure
- [ ] 100% of CLI commands documented (auto-generated)
- [ ] 100% of schema properties documented (auto-generated)
- [ ] At least 3 tutorials for major use cases
- [ ] At least 8 how-to guides for common tasks
- [ ] Site builds with `--strict` (no warnings)
- [ ] Automated deployment to GitHub Pages working
- [ ] Version switcher functional with mike

---

## Estimated Timeline

- **Phase 1-2**: Foundation + Reference (1-2 days)
- **Phase 3**: Tutorials (2-3 days)
- **Phase 4**: How-To Guides (3-4 days)
- **Phase 5**: Explanation (2-3 days)
- **Phase 6**: Migration (1-2 days)
- **Phase 7**: Polish (1-2 days)
- **Phase 8**: Automation (1-2 days)
- **Phase 9**: Maintenance (ongoing)

**Total**: ~12-18 days of focused work, can be done incrementally

---

## Directory Structure

```
strands-cli/
├── manual/                           # New MkDocs site root
│   ├── index.md                     # Landing page
│   ├── tutorials/                   # Step-by-step learning
│   │   ├── quickstart-ollama.md
│   │   ├── quickstart-bedrock.md
│   │   ├── quickstart-openai.md
│   │   └── first-multi-step.md
│   ├── howto/                       # Task-oriented guides
│   │   ├── validate-workflows.md
│   │   ├── run-workflows.md
│   │   ├── context-management.md
│   │   ├── telemetry.md
│   │   ├── tools.md
│   │   ├── secrets.md
│   │   ├── budgets.md
│   │   └── patterns/
│   │       ├── chain.md
│   │       ├── workflow.md
│   │       ├── routing.md
│   │       ├── parallel.md
│   │       ├── evaluator-optimizer.md
│   │       ├── graph.md
│   │       └── orchestrator-workers.md
│   ├── explanation/                 # Conceptual docs
│   │   ├── architecture.md
│   │   ├── patterns.md
│   │   ├── design-decisions.md
│   │   ├── performance.md
│   │   └── security-model.md
│   └── reference/                   # Technical reference
│       ├── cli.md                   # Auto-generated from Typer
│       ├── schema.md                # Auto-generated from JSON Schema
│       ├── exit-codes.md
│       ├── environment.md
│       ├── examples.md              # Examples catalog
│       └── api/                     # Auto-generated API docs
│           ├── index.md
│           ├── runtime.md
│           ├── exec.md
│           ├── loader.md
│           ├── schema.md
│           └── telemetry.md
├── mkdocs.yml                       # MkDocs configuration
├── docs/                            # Existing docs (keep until migrated)
└── .github/workflows/docs.yml       # CI/CD for docs deployment
```

---

## Initial mkdocs.yml Template

```yaml
site_name: Strands CLI
site_url: https://thomasrohde.github.io/strands-cli/
site_description: Execute agentic workflows with strong observability and schema validation
site_author: Thomas Klok Rohde
repo_url: https://github.com/ThomasRohde/strands-cli
repo_name: ThomasRohde/strands-cli
edit_uri: edit/main/manual/

theme:
  name: material
  features:
    - content.code.copy
    - content.code.annotate
    - navigation.tabs
    - navigation.sections
    - navigation.expand
    - navigation.top
    - navigation.tracking
    - toc.follow
    - search.suggest
    - search.highlight
  palette:
    - scheme: default
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-7
        name: Switch to dark mode
    - scheme: slate
      primary: indigo
      accent: indigo
      toggle:
        icon: material/brightness-4
        name: Switch to light mode

nav:
  - Home: index.md
  - Tutorials:
      - Quickstart (Ollama): tutorials/quickstart-ollama.md
      - Quickstart (Bedrock): tutorials/quickstart-bedrock.md
      - Quickstart (OpenAI): tutorials/quickstart-openai.md
      - First Multi-Step Workflow: tutorials/first-multi-step.md
  - How-To:
      - Validate Workflows: howto/validate-workflows.md
      - Run Workflows: howto/run-workflows.md
      - Context Management: howto/context-management.md
      - Telemetry: howto/telemetry.md
      - Tools: howto/tools.md
      - Secrets: howto/secrets.md
      - Budgets: howto/budgets.md
      - Patterns:
          - Chain: howto/patterns/chain.md
          - Workflow: howto/patterns/workflow.md
          - Routing: howto/patterns/routing.md
          - Parallel: howto/patterns/parallel.md
          - Evaluator-Optimizer: howto/patterns/evaluator-optimizer.md
          - Graph: howto/patterns/graph.md
          - Orchestrator-Workers: howto/patterns/orchestrator-workers.md
  - Explanation:
      - Architecture: explanation/architecture.md
      - Patterns: explanation/patterns.md
      - Design Decisions: explanation/design-decisions.md
      - Performance: explanation/performance.md
      - Security Model: explanation/security-model.md
  - Reference:
      - CLI: reference/cli.md
      - Schema: reference/schema.md
      - Exit Codes: reference/exit-codes.md
      - Environment: reference/environment.md
      - Examples: reference/examples.md
      - API:
          - Overview: reference/api/index.md

plugins:
  - search:
      lang: en
  - mkdocstrings:
      handlers:
        python:
          options:
            docstring_style: google
            show_source: false
            show_root_heading: true
            show_root_toc_entry: false
            heading_level: 2
  - mkdocs-typer:
      module: strands_cli.__main__
      command: app
  - literate-nav:
      nav_file: SUMMARY.md
  - section-index
  - minify:
      minify_html: true

markdown_extensions:
  - admonition
  - attr_list
  - md_in_html
  - toc:
      permalink: true
      toc_depth: 3
  - pymdownx.details
  - pymdownx.superfences:
      custom_fences:
        - name: mermaid
          class: mermaid
          format: !!python/name:pymdownx.superfences.fence_code_format
  - pymdownx.tabbed:
      alternate_style: true
  - pymdownx.snippets:
      check_paths: true
  - pymdownx.highlight:
      anchor_linenums: true
      line_spans: __span
      pygments_lang_class: true
  - pymdownx.inlinehilite
  - pymdownx.emoji:
      emoji_index: !!python/name:material.extensions.emoji.twemoji
      emoji_generator: !!python/name:material.extensions.emoji.to_svg

extra:
  version:
    provider: mike
  social:
    - icon: fontawesome/brands/github
      link: https://github.com/ThomasRohde/strands-cli
```

---

## Notes

- Use Material for MkDocs best practices throughout
- Follow Diátaxis strictly - never mix tutorial/howto/explanation/reference
- Automate everything that can be automated (CLI, Schema, API docs)
- Keep existing docs in `docs/` until fully migrated, then archive
- Use Mermaid for all diagrams (built into Material)
- Test docs build on every PR after Phase 8
- Each phase can be completed independently and incrementally
- Prioritize phases 1-3 for immediate value (foundation + tutorials)
- Phases 4-9 can be done in parallel by multiple contributors

---

## Quick Start Commands

```bash
# Install doc dependencies
uv pip install -e ".[docs]"

# Serve docs locally
mkdocs serve

# Build docs
mkdocs build

# Build with strict mode (fail on warnings)
mkdocs build --strict

# Deploy with versioning (after Phase 8)
mike deploy --push --update-aliases v0.11 latest
```

---

## References

- [MkDocs Documentation](https://www.mkdocs.org/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [Diátaxis Framework](https://diataxis.fr/)
- [mkdocstrings](https://mkdocstrings.github.io/)
- [mkdocs-typer](https://github.com/bruce-szalwinski/mkdocs-typer)
- [mike (versioning)](https://github.com/jimporter/mike)
