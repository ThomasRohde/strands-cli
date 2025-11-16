# Skills - Progressive Knowledge Loading

Skills enable agents to dynamically load specialized instructions and domain knowledge on-demand, similar to Claude Code's skill system. Instead of front-loading all context into the initial prompt, skills are discovered and loaded only when needed, improving efficiency and reducing token usage.

## What are Skills?

Skills are self-contained bundles of domain-specific knowledge stored in directories containing:

- **SKILL.md**: Main skill documentation with instructions, guidelines, and best practices
- **Supporting files**: Reference code, examples, or assets the skill references
- **LICENSE.txt**: Optional licensing information

When an agent encounters a task requiring specialized expertise (PDF manipulation, spreadsheet creation, document processing, etc.), it can load the relevant skill to access detailed instructions.

## How Skills Work

### 1. Progressive Loading

Skills use a two-phase approach inspired by Claude Code:

**Phase 1 - Discovery**: The agent's system prompt includes a lightweight list of available skills with short descriptions. This awareness allows the agent to identify which skill might be relevant.

**Phase 2 - Loading**: When the agent determines a skill is needed, it calls `Skill("skill_id")` to load the full content from `SKILL.md`. This detailed content then guides the agent's execution.

### 2. Skill Structure

Each skill directory follows this pattern:

```
skills/
├── xlsx/
│   ├── SKILL.md          # Main instructions (loaded on-demand)
│   ├── LICENSE.txt       # Optional licensing
│   └── recalc.py         # Reference code/examples
├── pdf/
│   ├── SKILL.md
│   └── ...
└── docx/
    ├── SKILL.md
    └── ...
```

The `SKILL.md` file contains:

- Frontmatter with name, description, and license
- Requirements and standards
- Best practices and guidelines
- Code patterns and examples
- Common pitfalls to avoid

## Configuring Skills

### Basic Configuration

Add skills to your workflow spec:

```yaml
skills:
  - id: xlsx
    path: ./skills/xlsx
    description: Comprehensive spreadsheet creation and analysis
  
  - id: pdf
    path: ./skills/pdf
    description: PDF manipulation toolkit for extraction and creation
```

### Skill Properties

| Property | Required | Description |
|----------|----------|-------------|
| `id` | ✅ | Unique identifier for the skill |
| `path` | ✅ | Path to skill directory (relative to spec file) |
| `description` | ❌ | Brief description (auto-extracted from SKILL.md if omitted) |
| `preload_metadata` | ❌ | If true, loads metadata at startup (default: false) |

### Path Resolution

Skill paths are resolved relative to the workflow spec file:

```yaml
# If spec is at: /project/workflows/main.yaml
skills:
  - id: xlsx
    path: ../skills/xlsx  # Resolves to /project/skills/xlsx
```

## Using Skills in Workflows

### Agent Setup

No special agent configuration is required. When skills are defined at the workflow level, the skill loader tool is automatically injected:

```yaml
skills:
  - id: xlsx
    path: ./skills/xlsx

agents:
  data-processor:
    prompt: |
      You are a data processing assistant with access to specialized skills.
      
      When you need specific expertise, load the relevant skill by calling:
      Skill("skill_id")
      
      Then follow the loaded instructions to complete the task.
    tools:
      - python_exec  # Skills often work with code execution
```

### Example Workflow

Here's a complete example showing skill usage:

```yaml
name: financial-model
version: 1.0.0

skills:
  - id: xlsx
    path: ./skills/xlsx

runtime:
  provider: openai
  model_id: gpt-4o

agents:
  analyst:
    prompt: |
      Create financial models following industry best practices.
      Load the xlsx skill when working with spreadsheets.
    tools:
      - python_exec

pattern:
  type: chain
  config:
    steps:
      - agent: analyst
        input: |
          Create a 3-year revenue projection model in Excel.
          Include MRR, growth rates, and proper formatting.

outputs:
  artifacts:
    - path: ./revenue_model.py
      from: "{{ last_response }}"
```

### What Happens at Runtime

1. **System Prompt Enhancement**: The agent receives a list of available skills:
   ```
   Available Skills:
   - xlsx (./skills/xlsx): Comprehensive spreadsheet creation and analysis
   - pdf (./skills/pdf): PDF manipulation toolkit
   ```

2. **Agent Decision**: The agent identifies that spreadsheet expertise is needed

3. **Skill Loading**: Agent calls `Skill("xlsx")`

4. **Content Injection**: The skill loader reads `skills/xlsx/SKILL.md` and returns its content

5. **Guided Execution**: Agent follows the loaded guidelines to create proper code

## Best Practices

### When to Use Skills

✅ **Good use cases:**
- Complex domain knowledge (financial modeling, document processing)
- Detailed formatting requirements (industry standards, style guides)
- Multi-step procedures with specific patterns
- Regulatory or compliance requirements

❌ **Avoid skills for:**
- Simple tasks better handled with direct prompts
- One-off instructions that won't be reused
- Generic knowledge the model already has

### Organizing Skills

**Keep skills focused**: Each skill should cover one domain area (spreadsheets, PDFs, etc.)

**Make skills self-contained**: Include all necessary guidelines in SKILL.md; minimize external dependencies

**Use clear descriptions**: Write concise descriptions that help agents identify when to load the skill

**Follow naming conventions**: Use lowercase IDs with hyphens (e.g., `pdf-processing`, not `PDF_Processing`)

### Writing SKILL.md

**Start with frontmatter**:
```markdown
---
name: xlsx
description: Spreadsheet creation and analysis
license: MIT
---
```

**Structure content clearly**:
- Requirements and standards first
- Common patterns and examples
- Edge cases and gotchas
- Reference code snippets

**Be specific and actionable**:
- Use concrete examples
- Provide code templates
- List common errors to avoid
- Include validation criteria

### Performance Considerations

**Skill caching**: Once loaded, skills remain in context for the agent's session. Avoid reloading the same skill.

**Size matters**: Keep SKILL.md under ~5000 tokens. Large skills increase context usage.

**Selective loading**: Use multiple focused skills rather than one massive skill. Let the agent load only what's needed.

## Advanced Patterns

### Skill Composition

Agents can load multiple skills as needed:

```yaml
skills:
  - id: pdf
    path: ./skills/pdf
  - id: xlsx
    path: ./skills/xlsx

# Agent might load both if task requires PDF data → Excel analysis
```

### Conditional Skill Loading

Skills are loaded only when the agent determines they're relevant:

```yaml
pattern:
  type: chain
  config:
    steps:
      - agent: processor
        input: "Extract data from report.pdf"
        # Agent will load pdf skill
      
      - agent: processor
        input: "Create financial model from extracted data"
        # Agent will load xlsx skill (pdf already loaded)
```

### Skills with Code Execution

Skills often guide code generation that's then executed:

```yaml
agents:
  coder:
    prompt: |
      Generate Python code following the loaded skill's guidelines.
      Return only executable code, no explanations.
    tools:
      - python_exec

pattern:
  type: chain
  config:
    steps:
      - agent: coder
        input: "Create Excel file with quarterly sales data"
        # 1. Agent loads xlsx skill
        # 2. Generates Python code following guidelines
        # 3. Code is executed via python_exec tool
```

## Troubleshooting

### Skill Not Found

**Error**: `Skill 'xyz' not found in workflow spec`

**Solution**: Verify the skill ID in your workflow's `skills:` section matches exactly (case-sensitive)

### SKILL.md Missing

**Error**: `Skill 'xyz' has no SKILL.md or README.md file`

**Solution**: Ensure the skill directory contains `SKILL.md` (or fallback `README.md`)

### Skill Already Loaded

**Warning**: `Skill 'xyz' is already loaded. No need to reload it.`

**Explanation**: This is normal behavior. Skills persist in context once loaded to avoid redundant loading.

### Path Resolution Issues

**Error**: Skill directory not found

**Solution**: Use paths relative to the workflow spec file, not the current working directory:

```yaml
# If spec is at: project/workflows/main.yaml
skills:
  - id: xlsx
    path: ../skills/xlsx  # Correct: relative to spec
    # Not: /absolute/path or ./relative/to/cwd
```

## Example Skills

The Strands CLI includes example skills based on Anthropic's official skills:

- **xlsx**: Spreadsheet creation, formulas, formatting, data analysis
- **pdf**: PDF extraction, creation, merging, form handling
- **docx**: Document creation, tracked changes, formatting
- **pptx**: Presentation creation and editing

These are located in `examples/skills/` and demonstrate best practices for skill structure.

## Next Steps

- Review example skills in `examples/skills/`
- Run the demo: `strands run examples/skills-demo.yaml`
- Create your own domain-specific skills
- See [Tool Development](develop-tools.md) for integrating skills with custom tools
- Read [Context Management](context-management.md) for optimizing token usage
