# Official Anthropic Skills

This directory contains official skills from Anthropic's skills repository.

**Source**: https://github.com/anthropics/skills

## Available Skills

- **pdf**: Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms
- **xlsx**: Comprehensive spreadsheet creation, editing, and analysis with support for formulas, formatting, data analysis, and visualization
- **docx**: Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction
- **pptx**: Presentation creation, editing, and analysis for creating and modifying PowerPoint files

## License

These skills are proprietary and licensed by Anthropic. See the LICENSE.txt file in each skill directory for complete terms.

## Usage in Strands CLI

These skills demonstrate progressive skill loading, where agents dynamically load detailed skill instructions on-demand during workflow execution. This pattern:

1. Reduces initial prompt size by only including skill metadata
2. Loads full skill content only when needed via the `Skill("skill_id")` tool
3. Prevents duplicate loading through state tracking in `AgentCache`

See [examples/skills-demo.yaml](../skills-demo.yaml) for a complete workflow example using these skills.
