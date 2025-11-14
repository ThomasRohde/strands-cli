# Copilot Code Review - Quick Start Guide

## ✅ Setup Complete!

All customization files have been created. GitHub Copilot is now configured to assist with systematic code reviews using REVIEW.md.

## 📁 Files Created

### Instructions (Auto-Applied)
- `.github/instructions/code-review.instructions.md` - Automatically applies to all `.py` files

### Prompt Files (On-Demand)
- `.github/prompts/review-layer.prompt.md` - Use: `/review-layer`
- `.github/prompts/review-unit.prompt.md` - Use: `/review-unit`
- `.github/prompts/review-checklist.prompt.md` - Use: `/review-checklist`
- `.github/prompts/review-comments.prompt.md` - Use: `/review-comments`

### Custom Agents (Specialized Reviewers)
- `.github/agents/security-reviewer.agent.md` - Use: `@security-reviewer`
- `.github/agents/performance-reviewer.agent.md` - Use: `@performance-reviewer`
- `.github/agents/comment-reviewer.agent.md` - Use: `@comment-reviewer`

### Tracking & Configuration
- `.github/REVIEW_PROGRESS.md` - Track review completion
- `.vscode/settings.json` - VS Code Copilot settings

## 🚀 How to Use

### 1. Review a Complete Layer
```
In Chat: /review-layer foundation
In Chat: /review-layer 5
In Chat: /review-layer execution
```

### 2. Review a Specific Unit
```
In Chat: /review-unit 1.1
In Chat: /review-unit 5.2
```

### 3. Quick File Review
Open a file, then:
```
In Chat: /review-checklist
```

### 4. Specialized Reviews
```
Switch to agent: @security-reviewer
Ask: Review src/strands_cli/exec/graph.py

Click "Review Performance" button (handoff)
Click "Review Comments" button (handoff)
```

### 5. Sequential Workflow (Recommended)
```
Step 1: /review-layer 1
Step 2: @security-reviewer: Review Layer 1 files
Step 3: Click "Review Performance" handoff
Step 4: Click "Review Comments" handoff
Step 5: Document findings in .github/REVIEW_PROGRESS.md
```

## 📊 Review Progress Tracking

Update `.github/REVIEW_PROGRESS.md` after each review session:
- Check off completed layers/units
- Document issues found (with severity: Critical/High/Medium/Low)
- Track metrics (time spent, coverage gaps, etc.)

## 🎯 Best Practices

### Always Reference REVIEW.md
The prompts automatically reference REVIEW.md, but you can be explicit:
```
Review types.py according to Layer 1.1 checklist in REVIEW.md
```

### Use Code Selection
Select code before running review prompts for focused analysis:
```
1. Select function or class
2. Run /review-checklist
```

### Leverage Handoffs
The agent handoff buttons create efficient review pipelines:
```
Security → Performance → Comments = Comprehensive coverage
```

### Document As You Go
After each review unit:
```
In Chat: Add these findings to .github/REVIEW_PROGRESS.md under Layer X.Y
```

## 🔧 Pre-Review Automation

Run these commands before starting a review session:

```powershell
# Generate coverage report
.\scripts\dev.ps1 test-cov
# Open: htmlcov/index.html

# Find TODOs to review
rg "TODO|FIXME|XXX|HACK" src/

# Find missing docstrings
rg "^(class|def|async def) " src/ | rg -v '"""'

# Find commented-out code
rg "^\s*#\s*(def|class|import|from)" src/

# Type check
uv run mypy src

# Full CI pipeline
.\scripts\dev.ps1 ci
```

## 📋 Review Checklist Template

For each review unit, check:
- ✓ **Comments & Docs**: Docstrings, inline comments, TODOs
- ✓ **Security**: Input validation, no code injection, secrets handling
- ✓ **Performance**: Agent caching, model pooling, async patterns
- ✓ **Error Handling**: Exit codes, exceptions, retry logic
- ✓ **Testing**: Coverage ≥85%, mocks, fixtures

## 🎨 Custom Agent Display Names

In the agent dropdown, you'll see:
- `@security-reviewer` (Security Reviewer)
- `@performance-reviewer` (Performance Reviewer)
- `@comment-reviewer` (Comment Reviewer)

## ⚙️ VS Code Settings Applied

The following settings are now active:
- ✅ Custom instructions enabled for Python files
- ✅ Prompt files enabled (use `/` to see available prompts)
- ✅ Prompt recommendations on chat start
- ✅ Review selection uses REVIEW.md
- ✅ Python cache files hidden from file explorer

## 🔄 Iterative Review Process

### Phase 1: Foundation (5-7 hours)
```
/review-layer 1  → @security-reviewer → handoff → handoff
/review-layer 2  → @security-reviewer → handoff → handoff
/review-layer 3  → @security-reviewer → handoff → handoff
```

### Phase 2: Runtime (6-8 hours)
```
/review-layer 4  → @security-reviewer → handoff → handoff
```

### Phase 3: Execution (8-10 hours)
```
/review-unit 5.1 → @security-reviewer → handoff → handoff
/review-unit 5.2 → @security-reviewer → handoff → handoff
... (repeat for all 5.x units)
```

### Phase 4-6: Continue through all layers
Follow the same pattern for Layers 6-9

## 📝 Example Review Session

```
1. Run: .\scripts\dev.ps1 test-cov
2. In Chat: /review-layer foundation
3. Review output, note issues
4. Switch to @security-reviewer
5. Ask: "Review the files from Layer 1 for security issues"
6. Click "Review Performance" button
7. Click "Review Comments" button
8. In Chat: "Add these findings to .github/REVIEW_PROGRESS.md"
9. Update progress tracker manually
10. Move to next layer
```

## ❓ Troubleshooting

### Prompts not appearing
- Check `.vscode/settings.json` has `"chat.promptFiles": true`
- Restart VS Code

### Agents not showing
- Agents should appear in the agent dropdown automatically
- Check files are in `.github/agents/` with `.agent.md` extension

### Instructions not applying
- Check `.vscode/settings.json` has `"github.copilot.chat.codeGeneration.useInstructionFiles": true`
- Verify file is in `.github/instructions/` with `.instructions.md` extension

### Handoffs not working
- Ensure target agent names match exactly (e.g., `performance-reviewer` not `Performance Reviewer`)
- Handoffs appear as buttons after agent completes response

## 📚 Resources

- **Review Plan**: `REVIEW.md` - Complete 9-layer review methodology
- **Setup Guide**: `.github/COPILOT_REVIEW_SETUP.md` - Detailed customization documentation
- **Progress Tracker**: `.github/REVIEW_PROGRESS.md` - Track your review completion
- **Project Standards**: `.github/copilot-instructions.md` - Existing project guidelines

## 🎉 Ready to Start!

You're all set! Begin with:
```
In Chat: /review-layer 1
```

Good luck with your code review! 🚀
