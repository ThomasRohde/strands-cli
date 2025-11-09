---
title: Quickstart with Ollama
description: Get started with Strands CLI using Ollama for local AI model execution
keywords: ollama, quickstart, tutorial, local llm, llama, mistral, installation, getting started
---

# Quickstart with Ollama

This tutorial will guide you through setting up and running your first Strands workflow using Ollama, a local AI model runtime that lets you run large language models on your own hardware without API costs.

## What You'll Learn

- How to install and configure Ollama
- How to create and validate a simple workflow
- How to run workflows and understand the output
- Basic debugging techniques

## Prerequisites

Before starting, ensure you have:

- **Python 3.12 or higher** installed
- **Basic command-line experience**
- **At least 8GB of RAM** (for running local models)
- **5-10GB of free disk space** (for model downloads)

## Step 1: Install Ollama

### macOS and Linux

```bash
# Download and install Ollama
curl -fsSL https://ollama.com/install.sh | sh
```

### Windows

Download and run the installer from [ollama.com/download/windows](https://ollama.com/download/windows)

### Verify Installation

```bash
# Check Ollama version
ollama --version

# Start Ollama service (if not auto-started)
ollama serve
```

The Ollama service should now be running on `http://localhost:11434`.

## Step 2: Pull a Model

Ollama supports many models. We'll use `llama3.2` which provides a good balance of performance and resource usage:

```bash
# Pull the model (this may take a few minutes)
ollama pull llama3.2

# Verify the model is available
ollama list
```

!!! tip "Other Models"
    You can use other models like `llama3.2:70b`, `mistral`, `qwen2.5`, or `gemma2`. See [ollama.com/library](https://ollama.com/library) for the full list.

## Step 3: Install Strands CLI

Install Strands CLI using pip or uv:

=== "Using uv (recommended)"

    ```bash
    # Install uv if not already installed
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install Strands CLI
    uv pip install strands-cli

    # Verify installation
    uv run strands --version
    ```

=== "Using pip"

    ```bash
    # Install Strands CLI
    pip install strands-cli

    # Verify installation
    strands --version
    ```

## Step 4: Create Your First Workflow

Create a new file called `my-first-workflow.yaml`:

```yaml
version: 0
name: my-first-workflow
description: My first Strands workflow using Ollama

runtime:
  provider: ollama
  model_id: llama3.2
  host: http://localhost:11434

inputs:
  values:
    topic: "quantum computing"

agents:
  explainer:
    prompt: |
      You are a knowledgeable science educator who explains complex topics
      in simple, accessible language. Use analogies and examples that anyone
      can understand. Format your response in clear Markdown.

pattern:
  type: single_agent
  config:
    agent: explainer
    input: "Explain {{ topic }} in simple terms that a beginner can understand."

outputs:
  artifacts:
    - path: ./explanation.md
      from: "{{ last_response }}"
```

### Understanding the Workflow

Let's break down the key sections:

- **`runtime`**: Configures which AI provider and model to use
  - `provider: ollama` tells Strands to use Ollama
  - `model_id: llama3.2` specifies which model to run
  - `host` points to the Ollama service

- **`inputs`**: Defines variables you can use in your workflow
  - We define a `topic` variable that can be referenced later

- **`agents`**: Defines AI agents with specific prompts and behaviors
  - The `explainer` agent has instructions to explain things simply

- **`pattern`**: Defines how the workflow executes
  - `single_agent` is the simplest pattern - one agent, one response
  - The `input` uses `{{ topic }}` to inject our variable

- **`outputs`**: Specifies where to save results
  - Creates a file `explanation.md` with the agent's response

## Step 5: Validate Your Workflow

Before running, validate that your workflow is correctly formatted:

```bash
uv run strands validate my-first-workflow.yaml
```

You should see:

```
✓ Workflow is valid
```

If you see errors, check:

- YAML syntax (indentation, colons, quotes)
- Required fields are present
- Values match the expected types

## Step 6: Run Your Workflow

Execute the workflow:

```bash
uv run strands run my-first-workflow.yaml
```

You should see output like:

```
🚀 Starting workflow: my-first-workflow
📊 Runtime: ollama (llama3.2)
🤖 Agent: explainer
✅ Workflow completed successfully
📝 Artifact written: ./explanation.md
```

## Step 7: Check the Output

Open the generated `explanation.md` file to see the AI-generated explanation of quantum computing.

```bash
cat explanation.md
```

## Step 8: Customize with Variables

You can override variables from the command line without editing the YAML:

```bash
# Ask about a different topic
uv run strands run my-first-workflow.yaml --var topic="black holes"

# Multiple variables
uv run strands run my-first-workflow.yaml \
  --var topic="photosynthesis" \
  --var output_file="photosynthesis.md"
```

## Troubleshooting

### Ollama Connection Failed

**Problem**: `Error: Could not connect to Ollama at http://localhost:11434`

**Solution**:
```bash
# Ensure Ollama is running
ollama serve

# In another terminal, verify it's accessible
curl http://localhost:11434/api/tags
```

### Model Not Found

**Problem**: `Error: Model 'llama3.2' not found`

**Solution**:
```bash
# Pull the model
ollama pull llama3.2

# Verify it's available
ollama list
```

### Out of Memory Errors

**Problem**: System freezes or Ollama crashes

**Solution**:
- Use a smaller model: `ollama pull llama3.2:1b`
- Update the workflow to use `model_id: llama3.2:1b`
- Close other memory-intensive applications

### Slow Response Times

**Problem**: Workflow takes a very long time to complete

**Solution**:
- Use GPU acceleration if available
- Try a smaller model variant
- Reduce the complexity of your prompt
- Use fewer tokens in the response

## Next Steps

Now that you have a working Ollama setup, you can:

1. **Explore patterns**: Try the [multi-step workflow tutorial](first-multi-step.md)
2. **Add tools**: Learn about [built-in tools](../howto/tools.md)
3. **Enable telemetry**: Set up [observability](../howto/telemetry.md)
4. **Browse examples**: Check the `examples/` folder for more complex workflows:
   - `examples/single-agent-workflow-ollama.yaml` - Basic single agent
   - `examples/evaluator-optimizer-writing-ollama.yaml` - Iterative refinement
   - `examples/single-agent-chain-ollama.yaml` - Simple chain pattern

## Key Concepts Recap

| Concept | Description |
|---------|-------------|
| **Runtime** | Configures which AI provider and model to use |
| **Agent** | An AI entity with a specific prompt and behavior |
| **Pattern** | The execution flow (single_agent, chain, workflow, etc.) |
| **Variables** | Values you can reference with `{{ variable_name }}` |
| **Artifacts** | Output files generated by the workflow |
| **Validation** | Checking workflow syntax before execution |

## Common Commands Reference

```bash
# Validate workflow
strands validate workflow.yaml

# Run workflow
strands run workflow.yaml

# Run with variable overrides
strands run workflow.yaml --var key=value

# Debug mode (shows detailed execution)
strands run workflow.yaml --debug --verbose

# Check Strands CLI version
strands --version

# Get help
strands --help
strands run --help
```

## See Also

**Next Steps:**

- [First Multi-Step Workflow](first-multi-step.md) - Build a chain pattern workflow
- [Quickstart with Bedrock](quickstart-bedrock.md) - Use AWS Bedrock instead
- [Quickstart with OpenAI](quickstart-openai.md) - Use OpenAI models

**How-To Guides:**

- [Run Workflows](../howto/run-workflows.md) - Advanced execution options
- [Validate Workflows](../howto/validate-workflows.md) - Schema validation techniques
- [Working with Tools](../howto/tools.md) - Add tools to your agents

**Reference:**

- [CLI Reference](../reference/cli.md) - All available commands
- [Schema Reference](../reference/schema.md) - Complete YAML spec
- [Examples Catalog](../reference/examples.md) - Browse example workflows

**External:**

- [Ollama Model Library](https://ollama.com/library) - Browse available models
- [Ollama Documentation](https://github.com/ollama/ollama) - Official Ollama docs
