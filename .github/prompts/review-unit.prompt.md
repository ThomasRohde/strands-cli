---
name: review-unit
description: Review a specific review unit (e.g., Layer 1.1, Layer 5.2)
argument-hint: "unit ID (e.g., '1.1', '5.2') from REVIEW.md"
agent: agent
tools: ['edit', 'runNotebooks', 'search', 'new', 'runCommands', 'runTasks', 'Context7/*', 'Ref tools/*', 'usages', 'vscodeAPI', 'problems', 'changes', 'testFailure', 'openSimpleBrowser', 'fetch', 'githubRepo', 'extensions', 'todos', 'runSubagent', 'runTests']
---

# Review Unit: ${input:unit}

Review the specific unit **${input:unit}** from [REVIEW.md](../../REVIEW.md).

## Process:

1. **Locate Unit in REVIEW.md**
   - Find the unit definition (e.g., "1.1 Type System & Models")
   - Read the "Review Focus" checklist
   - Note the "Red Flags" to watch for

2. **Read Source Files**
   - Read all files listed in the unit
   - Read corresponding test files

3. **Execute Checklist**
   - Go through each item in "Review Focus"
   - Mark each as ✓ (pass), ✗ (fail), or ⚠ (needs attention)

4. **Check Red Flags**
   - Specifically look for each red flag mentioned
   - Document any found with severity

5. **Cross-Cutting Review**
   - Apply comment quality checklist
   - Apply security checklist
   - Apply performance checklist
   - Apply error handling checklist
   - Apply testing checklist

6. **Generate Findings**
   Format output using the template from REVIEW.md section "Review Output Template"

## Focus on Actionable Output
- Specific line numbers for issues
- Severity ratings (Critical/High/Medium/Low)
- Clear recommendations for fixes
- Priority rankings (P0/P1/P2)
