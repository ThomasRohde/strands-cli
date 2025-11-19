# Feature Migration Assistant

This prompt helps migrate uncommitted features from this repository to a parallel clone.

## Instructions for AI Coding Agent

You are tasked with creating a migration package for uncommitted changes in this repository. Follow these steps precisely:

### Step 1: Detect Uncommitted Changes

Use git to identify all changed files (both staged and unstaged):

```powershell
git status --porcelain
```

Parse the output to extract file paths. The format is:
- `M` = Modified
- `A` = Added (new file)
- `D` = Deleted
- `??` = Untracked

### Step 2: Prompt for Feature Name

Ask the user for a feature name to use for the migration directory. Use this format:
- Prompt: "What is the feature name for this migration?"
- Validate: Must be a valid directory name (no spaces, special chars except `-` and `_`)
- Default suggestion: Extract from current git branch name if not on `main`/`master`

### Step 3: Create Migration Directory Structure

Create the following directory structure:

```
./migrate/<feature_name>/
├── MIGRATE.md          # Integration instructions
├── files/              # All changed files (preserve directory structure)
│   └── <original_path> # Full path from repo root
└── context/            # Additional context files
    ├── git-status.txt  # Full git status output
    └── branch-info.txt # Current branch and commit info
```

### Step 4: Copy Changed Files

For each changed file from Step 1:

1. **Read the FULL current content** of the file (not the diff)
2. **Preserve the original directory structure** within `./migrate/<feature_name>/files/`
3. **Copy the entire file** to the migration directory

Example:
- Original: `src/strands_cli/api/__init__.py`
- Copy to: `./migrate/<feature_name>/files/src/strands_cli/api/__init__.py`

**CRITICAL**: Do NOT copy diffs or patches. Copy complete file contents.

### Step 5: Gather Context Information

Create `context/git-status.txt`:
```powershell
git status --porcelain > ./migrate/<feature_name>/context/git-status.txt
```

Create `context/branch-info.txt`:
```powershell
@"
Current Branch: $(git rev-parse --abbrev-ref HEAD)
Latest Commit: $(git rev-parse HEAD)
Latest Commit Message: $(git log -1 --pretty=%B)
Uncommitted Files: $(git status --short | Measure-Object -Line | Select-Object -ExpandProperty Lines)
Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ > ./migrate/<feature_name>/context/branch-info.txt
```

### Step 6: Generate MIGRATE.md

Create a comprehensive `MIGRATE.md` file with the following sections:

#### Template for MIGRATE.md:

```markdown
# Feature Migration: <FEATURE_NAME>

**Generated**: <TIMESTAMP>  
**Source Branch**: <BRANCH_NAME>  
**Source Commit**: <COMMIT_HASH>

## Overview

This migration package contains <N> changed files from the source repository.

### Changed Files Summary

<For each file, list:>
- `<file_path>` - <Status: new/modified/deleted>

## Integration Instructions

### Prerequisites

1. Ensure target repository is on a clean branch
2. Review all files in `files/` directory before applying
3. Back up target repository or create a new branch:
   ```bash
   git checkout -b integrate-<feature_name>
   ```

### File-by-File Integration

<For each file, create a subsection with:>

#### File: `<file_path>`

**Status**: <new/modified>

**Target Location**: `<file_path>` (same as source)

**Integration Steps**:

<If file is NEW:>
1. Create file at target location:
   ```bash
   New-Item -ItemType File -Path "<file_path>" -Force
   ```

2. Copy content from migration package:
   ```bash
   Copy-Item "./migrate/<feature_name>/files/<file_path>" "<file_path>" -Force
   ```

<If file is MODIFIED:>
1. **Review existing file** at `<file_path>` in target repo
2. **Key changes in this file**:
   <List the main changes - use AST/semantic analysis, NOT line-by-line diffs>
   
   <For Python files, identify:>
   - New imports added
   - New functions/methods added
   - Modified functions/methods (describe what changed functionally)
   - New classes added
   - Configuration changes
   
   <For YAML/JSON files, identify:>
   - New keys/sections added
   - Modified values
   - Removed keys
   
   <For Markdown files:>
   - New sections added
   - Updated sections (describe changes)

3. **Integration approach**:
   
   <Option A - Safe replacement (if file is new in target or minimal changes):>
   ```bash
   Copy-Item "./migrate/<feature_name>/files/<file_path>" "<file_path>" -Force
   ```
   
   <Option B - Manual merge (if target has diverged):>
   - Open both files side-by-side in editor
   - Apply changes listed above manually
   - Verify no functionality is lost from target version

4. **Verification**:
   <Provide specific verification steps, e.g.:>
   ```bash
   # For Python modules
   python -c "from <module> import <class>; print('Import successful')"
   
   # For CLI changes
   strands --help | Select-String "<new_feature>"
   
   # Run relevant tests
   pytest tests/<related_test_file.py> -v
   ```

<If file is DELETED:>
1. Verify file should be removed in target
2. Remove file:
   ```bash
   Remove-Item "<file_path>" -Force
   ```
3. Verify no dependencies remain:
   ```bash
   rg "<filename_without_ext>" --type py
   ```

### Code Changes Detail

<For each significantly modified file, provide:>

#### <file_path>

**Purpose**: <What this file does>

**Key Additions**:

<For each new function/class/method:>
##### `<function_name>` (New)

**Purpose**: <What it does>

**Signature**:
```python
<function signature with type hints>
```

**Usage Example**:
```python
<realistic usage example>
```

**Dependencies**: <List any new imports or dependencies this requires>

---

**Key Modifications**:

<For each modified function/class/method:>
##### `<function_name>` (Modified)

**What Changed**: <Describe the functional change, not line-by-line>

**Before** (conceptual):
```python
# OLD BEHAVIOR:
# <describe what it did before>
```

**After** (from migration):
```python
# NEW BEHAVIOR:
# <describe what it does now>
```

**Migration Notes**: <Any special considerations when applying this change>

---

### Dependencies & Configuration

<Check for new dependencies:>

**New Python Dependencies**:
<If pyproject.toml changed, list new packages>
```bash
# Add to target repo:
uv add <package_name>
```

**Configuration Changes**:
<If .env.example, config files, or pyproject.toml changed>
- <List changes needed>

### Testing Strategy

After integration, run the following tests:

1. **Unit Tests**:
   ```bash
   uv run pytest tests/ -v
   ```

2. **Type Checking**:
   ```bash
   uv run mypy src/
   ```

3. **Linting**:
   ```bash
   uv run ruff check .
   ```

4. **Feature-Specific Tests**:
   <List specific test commands for this feature>
   ```bash
   <commands>
   ```

### Rollback Procedure

If integration fails:

1. Discard changes:
   ```bash
   git checkout .
   git clean -fd
   ```

2. Or restore from backup branch:
   ```bash
   git checkout main
   git branch -D integrate-<feature_name>
   ```

## File Contents

All complete file contents are located in `./files/` subdirectory, preserving the original directory structure from the source repository.

To view a file:
```bash
Get-Content "./files/<file_path>"
```

## Notes

- This migration was auto-generated from uncommitted changes
- Review all changes carefully before applying to production
- Consider creating a PR in target repo for review
- Test thoroughly after integration

## Support

If you encounter issues during migration:
1. Check `context/git-status.txt` for original file states
2. Review `context/branch-info.txt` for source context
3. Compare files manually using diff tools:
   ```bash
   code --diff "./files/<file_path>" "<target_repo>/<file_path>"
   ```
```

### Step 7: Validation & Summary

After creating the migration package:

1. **Verify all files copied**:
   - Count files in `./migrate/<feature_name>/files/`
   - Compare with git status count

2. **Verify MIGRATE.md completeness**:
   - Every changed file has integration instructions
   - All code changes are documented with context
   - Testing strategy is provided

3. **Output summary**:
   ```
   Migration package created: ./migrate/<feature_name>/
   
   Files included:
   - <N> modified files
   - <N> new files  
   - <N> deleted files
   
   Next steps:
   1. Review MIGRATE.md
   2. Copy entire ./migrate/<feature_name>/ directory to target repo
   3. Follow integration instructions in MIGRATE.md
   4. Run tests and verify functionality
   ```

## Important Constraints

1. **DO NOT use git diff or patches** - Copy complete files only
2. **DO NOT truncate files** - Copy entire file contents
3. **DO preserve directory structure** - Keep original paths
4. **DO provide semantic analysis** - Describe what changed functionally, not line-by-line
5. **DO include verification steps** - For each file integration
6. **DO make instructions precise** - Use exact commands and paths
7. **DO handle edge cases**:
   - Binary files (note in MIGRATE.md, don't copy)
   - Very large files (>1MB, note and provide alternative)
   - Deleted files (document removal steps)

## Error Handling

If you encounter:
- **No uncommitted changes**: Inform user and exit gracefully
- **Binary files**: Note in MIGRATE.md but don't copy
- **Permission errors**: Report and skip file with warning
- **Invalid feature name**: Re-prompt user with validation rules

## Output Format

Provide a final summary in this format:

```
✓ Migration Package Created

Location: ./migrate/<feature_name>/

Contents:
  - MIGRATE.md (comprehensive integration guide)
  - files/ (<N> files copied with full directory structure)
  - context/ (git status and branch info)

Files Migrated:
  ✓ <file1> (modified)
  ✓ <file2> (new)
  ✓ <file3> (deleted - removal instructions in MIGRATE.md)

Ready to migrate to target repository.

Next Steps:
1. Copy ./migrate/<feature_name>/ to target repo
2. Open MIGRATE.md and follow integration instructions
3. Test thoroughly before committing
```

---

## Example Workflow

**User**: "Migrate my feature"

**Agent**:
1. Runs `git status --porcelain`
2. Finds 5 changed files
3. Prompts: "Feature name? (detected from branch: 'streamlit-support')"
4. User: "streamlit-integration"
5. Creates `./migrate/streamlit-integration/`
6. Copies all 5 complete files to `files/` subdirectory
7. Analyzes each file for semantic changes
8. Generates comprehensive MIGRATE.md with:
   - Exact integration steps for each file
   - Code snippets showing new functions/classes
   - Verification commands
   - Testing strategy
9. Saves context files
10. Outputs summary

**Result**: User can copy `./migrate/streamlit-integration/` to target repo and follow MIGRATE.md to integrate changes safely.
