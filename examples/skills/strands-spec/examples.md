# Real-World Workflow Examples

Production-ready workflow patterns and templates for common use cases.

## Table of Contents

1. [Data Analysis Pipeline](#data-analysis-pipeline)
2. [API Integration Workflow](#api-integration-workflow)
3. [Code Review & Refactoring](#code-review--refactoring)
4. [Research & Report Generation](#research--report-generation)
5. [Multi-Stage Content Creation](#multi-stage-content-creation)
6. [Customer Support Routing](#customer-support-routing)
7. [Batch Document Processing](#batch-document-processing)
8. [A/B Test Analysis](#ab-test-analysis)

---

## Data Analysis Pipeline

**Pattern:** Workflow (DAG)
**Use case:** Fetch, clean, analyze, and visualize data from multiple sources

```yaml
version: 0
name: "data-analysis-pipeline"

runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"
  budgets:
    max_tokens: 200000
    max_duration_s: 600

inputs:
  required:
    data_sources: string
  optional:
    analysis_type:
      type: string
      default: "statistical"
      enum: ["statistical", "ml", "time-series"]

agents:
  data-fetcher:
    prompt: "Fetch data from: {{ data_sources }}"
    tools: ["http_request"]
    
  data-cleaner:
    prompt: "Clean and normalize data, handle missing values"
    tools: ["python_exec"]
    
  stat-analyzer:
    prompt: "Perform statistical analysis"
    tools: ["python_exec"]
    
  ml-analyzer:
    prompt: "Run machine learning models"
    tools: ["python_exec"]
    
  visualizer:
    prompt: "Create charts and visualizations"
    tools: ["python_exec"]
    
  report-writer:
    prompt: "Generate executive summary report"

pattern:
  type: workflow
  config:
    tasks:
      - id: fetch
        agent: data-fetcher
        input: "Fetch all data sources"
        
      - id: clean
        agent: data-cleaner
        input: "Clean fetched data"
        depends_on: [fetch]
        context: "{{ tasks.fetch.response }}"
        
      - id: analyze-stats
        agent: stat-analyzer
        input: "Run statistical analysis"
        depends_on: [clean]
        condition: "analysis_type == 'statistical' || analysis_type == 'ml'"
        
      - id: analyze-ml
        agent: ml-analyzer
        input: "Run ML models"
        depends_on: [clean]
        condition: "analysis_type == 'ml'"
        
      - id: visualize
        agent: visualizer
        input: "Create visualizations"
        depends_on: [analyze-stats, analyze-ml]
        
      - id: report
        agent: report-writer
        input: "Generate final report"
        depends_on: [visualize]
        context: |
          Analysis: {{ tasks.analyze-stats.response }}
          {% if tasks.analyze-ml.response %}
          ML Results: {{ tasks.analyze-ml.response }}
          {% endif %}
          Charts: {{ tasks.visualize.response }}

outputs:
  artifacts:
    - path: "./reports/analysis-{{ timestamp }}.md"
      from: "{{ tasks.report.response }}"
    - path: "./data/cleaned.csv"
      from: "{{ tasks.clean.response }}"
```

---

## API Integration Workflow

**Pattern:** Chain
**Use case:** Fetch, transform, and sync data between systems

```yaml
version: 0
name: "api-integration"

runtime:
  provider: openai
  model_id: "gpt-4o-mini"
  budgets:
    max_tokens: 50000

env:
  secrets:
    - name: SOURCE_API_KEY
      source: env
    - name: DEST_API_KEY
      source: env

inputs:
  required:
    source_endpoint: string
    dest_endpoint: string
  optional:
    transform_rules: string

agents:
  source-fetcher:
    tools:
      - type: http_request
        config:
          allowlist: ["api.source.com"]
          timeout: 30
    prompt: |
      Fetch data from {{ source_endpoint }}
      Use API key from SOURCE_API_KEY environment variable.
      Return raw JSON response.
      
  transformer:
    tools: ["python_exec"]
    prompt: |
      Transform data according to rules:
      {{ transform_rules }}
      
      Input data: {{ steps[0].response }}
      
      Return transformed JSON ready for destination API.
      
  dest-uploader:
    tools:
      - type: http_request
        config:
          allowlist: ["api.destination.com"]
    prompt: |
      Upload transformed data to {{ dest_endpoint }}
      Use API key from DEST_API_KEY environment variable.
      
      Data: {{ steps[1].response }}
      
      Return upload status and record IDs.
      
  validator:
    prompt: |
      Validate upload success:
      Source count: Extract from {{ steps[0].response }}
      Upload result: {{ steps[2].response }}
      
      Verify all records uploaded successfully.

pattern:
  type: chain
  config:
    steps:
      - agent: source-fetcher
        input: "Fetch source data"
      - agent: transformer
        input: "Transform data"
      - agent: dest-uploader
        input: "Upload to destination"
      - agent: validator
        input: "Validate success"

outputs:
  artifacts:
    - path: "./logs/integration-{{ timestamp }}.json"
      from: "{{ last_response }}"
```

---

## Code Review & Refactoring

**Pattern:** Evaluator-Optimizer
**Use case:** Iteratively improve code quality

```yaml
version: 0
name: "code-refactoring"

runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"

inputs:
  required:
    code_file: string
  optional:
    quality_threshold:
      type: number
      default: 8.5

agents:
  code-generator:
    tools: ["python_exec", "grep"]
    prompt: |
      Refactor code in {{ code_file }}
      Focus on:
      - Readability
      - Performance
      - Type safety
      - Documentation
      
      Return complete refactored code.
      
  code-reviewer:
    tools: ["grep"]
    prompt: |
      Review this code:
      {{ current_output }}
      
      Evaluate on scale 0-10:
      - Readability
      - Performance
      - Type safety
      - Documentation
      - Test coverage
      
      Return JSON:
      {
        "score": <average score>,
        "issues": ["issue 1", "issue 2"],
        "suggestions": ["suggestion 1", "suggestion 2"]
      }
      
  code-improver:
    tools: ["python_exec"]
    prompt: |
      Improve code based on review:
      
      Current code:
      {{ current_output }}
      
      Review feedback:
      {{ evaluation }}
      
      Address all issues and implement suggestions.
      Return improved code.

pattern:
  type: evaluator-optimizer
  config:
    generator: code-generator
    generator_input: "Refactor the code"
    
    evaluator: code-reviewer
    evaluator_input: "Review current version"
    
    optimizer: code-improver
    optimizer_input: "Improve based on feedback"
    
    max_iterations: 5
    quality_threshold: "{{ quality_threshold }}"
    score_path: "score"

outputs:
  artifacts:
    - path: "./refactored/{{ code_file }}"
      from: "{{ last_response }}"
```

---

## Research & Report Generation

**Pattern:** Parallel + Chain
**Use case:** Multi-source research with synthesis

```yaml
version: 0
name: "research-report"

runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"
  budgets:
    max_tokens: 150000

inputs:
  required:
    topic: string
    sources: string
  optional:
    report_format:
      type: string
      default: "markdown"
      enum: ["markdown", "pdf", "html"]

agents:
  academic-researcher:
    tools: ["http_request"]
    prompt: "Research {{ topic }} from academic sources"
    
  industry-researcher:
    tools: ["http_request"]
    prompt: "Research {{ topic }} from industry reports"
    
  news-researcher:
    tools: ["http_request"]
    prompt: "Research {{ topic }} from recent news"
    
  fact-checker:
    prompt: "Verify claims and cross-reference sources"
    
  synthesizer:
    prompt: "Synthesize research into coherent narrative"
    
  formatter:
    tools: ["python_exec"]
    prompt: "Format report as {{ report_format }}"

pattern:
  type: chain
  config:
    steps:
      # Step 1: Parallel research
      - agent: _parallel_research
        pattern:
          type: parallel
          config:
            branches:
              - name: academic
                agent: academic-researcher
                input: "Search academic databases"
                
              - name: industry
                agent: industry-researcher
                input: "Search industry reports"
                
              - name: news
                agent: news-researcher
                input: "Search recent news"
                
      # Step 2: Fact checking
      - agent: fact-checker
        input: |
          Verify all claims from research:
          Academic: {{ branches.academic.response }}
          Industry: {{ branches.industry.response }}
          News: {{ branches.news.response }}
          
      # Step 3: Synthesis
      - agent: synthesizer
        input: "Create comprehensive report"
        
      # Step 4: Formatting
      - agent: formatter
        input: "Format final report"

outputs:
  artifacts:
    - path: "./reports/{{ topic }}-{{ timestamp }}.{{ report_format }}"
      from: "{{ last_response }}"
```

---

## Customer Support Routing

**Pattern:** Routing
**Use case:** Route support tickets to specialized agents

```yaml
version: 0
name: "support-routing"

runtime:
  provider: openai
  model_id: "gpt-4o-mini"

inputs:
  required:
    ticket_content: string
  optional:
    priority: string

agents:
  ticket-classifier:
    prompt: |
      Classify support ticket:
      {{ ticket_content }}
      
      Return JSON:
      {
        "category": "<technical|billing|account|general>",
        "priority": "<low|medium|high|urgent>",
        "sentiment": "<positive|neutral|negative>",
        "confidence": <0-1>
      }
      
  technical-support:
    tools: ["grep", "http_request"]
    prompt: "Provide technical support for: {{ ticket_content }}"
    
  billing-support:
    tools: ["http_request"]
    prompt: "Handle billing inquiry: {{ ticket_content }}"
    
  account-support:
    tools: ["http_request"]
    prompt: "Assist with account issue: {{ ticket_content }}"
    
  general-support:
    prompt: "Provide general support for: {{ ticket_content }}"

pattern:
  type: routing
  config:
    router: ticket-classifier
    router_input: "Classify the ticket"
    
    routes:
      - name: technical
        condition: "contains(category, 'technical')"
        agent: technical-support
        input: "Handle technical issue"
        
      - name: billing
        condition: "contains(category, 'billing')"
        agent: billing-support
        input: "Handle billing inquiry"
        
      - name: account
        condition: "contains(category, 'account')"
        agent: account-support
        input: "Handle account issue"
        
    default: general-support
    default_input: "Handle general inquiry"

outputs:
  artifacts:
    - path: "./tickets/response-{{ timestamp }}.txt"
      from: "{{ last_response }}"
```

---

## Batch Document Processing

**Pattern:** Orchestrator-Workers
**Use case:** Process large batches of documents with specialized workers

```yaml
version: 0
name: "batch-document-processing"

runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"
  max_parallel: 5

inputs:
  required:
    document_directory: string

agents:
  task-planner:
    tools: ["grep"]
    prompt: |
      Scan {{ document_directory }} for documents.
      Create processing tasks for each document type.
      
      Return JSON:
      {
        "tasks": [
          {
            "id": "task-1",
            "description": "Process PDF invoice",
            "worker": "pdf-processor",
            "input": "Extract data from invoice.pdf"
          },
          {
            "id": "task-2",
            "description": "Process Excel report",
            "worker": "spreadsheet-processor",
            "input": "Analyze report.xlsx"
          }
        ]
      }
      
  pdf-processor:
    tools: ["python_exec"]
    prompt: "Extract and structure data from PDF documents"
    
  spreadsheet-processor:
    tools: ["python_exec"]
    prompt: "Process and analyze spreadsheet data"
    
  text-processor:
    tools: ["python_exec"]
    prompt: "Parse and extract information from text files"
    
  image-processor:
    tools: ["python_exec", "http_request"]
    prompt: "Process images and extract text (OCR)"
    
  results-aggregator:
    prompt: |
      Aggregate all processed documents.
      Generate summary report with statistics.

pattern:
  type: orchestrator-workers
  config:
    orchestrator: task-planner
    orchestrator_input: "Create document processing tasks"
    
    workers:
      - id: pdf-processor
        agent: pdf-processor
        description: "PDF document processing"
        
      - id: spreadsheet-processor
        agent: spreadsheet-processor
        description: "Spreadsheet processing"
        
      - id: text-processor
        agent: text-processor
        description: "Text file processing"
        
      - id: image-processor
        agent: image-processor
        description: "Image processing with OCR"
        
    aggregator: results-aggregator
    aggregator_input: "Aggregate all results"
    
    max_tasks: 100

outputs:
  artifacts:
    - path: "./processed/summary-{{ timestamp }}.json"
      from: "{{ last_response }}"
```

---

## A/B Test Analysis

**Pattern:** Graph
**Use case:** Analyze A/B test with conditional statistical tests

```yaml
version: 0
name: "ab-test-analysis"

runtime:
  provider: bedrock
  model_id: "anthropic.claude-3-sonnet-20240229-v1:0"
  region: "us-east-1"

inputs:
  required:
    test_data_path: string
  optional:
    significance_level:
      type: number
      default: 0.05

agents:
  data-loader:
    tools: ["python_exec"]
    prompt: "Load A/B test data from {{ test_data_path }}"
    
  normality-checker:
    tools: ["python_exec"]
    prompt: |
      Test data normality using Shapiro-Wilk test.
      
      Return JSON:
      {
        "is_normal": <boolean>,
        "p_value": <number>,
        "recommendation": "use_parametric or use_nonparametric"
      }
      
  parametric-test:
    tools: ["python_exec"]
    prompt: "Run t-test for normally distributed data"
    
  nonparametric-test:
    tools: ["python_exec"]
    prompt: "Run Mann-Whitney U test for non-normal data"
    
  effect-size-calculator:
    tools: ["python_exec"]
    prompt: "Calculate effect size (Cohen's d or rank-biserial correlation)"
    
  power-analysis:
    tools: ["python_exec"]
    prompt: "Perform statistical power analysis"
    
  report-generator:
    prompt: |
      Generate comprehensive A/B test report with:
      - Test results
      - Effect size
      - Power analysis
      - Recommendations

pattern:
  type: graph
  config:
    nodes:
      - id: load
        agent: data-loader
        input: "Load test data"
        
      - id: check-normality
        agent: normality-checker
        input: "Test data normality"
        
      - id: parametric
        agent: parametric-test
        input: "Run parametric test"
        
      - id: nonparametric
        agent: nonparametric-test
        input: "Run nonparametric test"
        
      - id: effect-size
        agent: effect-size-calculator
        input: "Calculate effect size"
        
      - id: power
        agent: power-analysis
        input: "Analyze statistical power"
        
      - id: report
        agent: report-generator
        input: "Generate final report"
        
    edges:
      - from: load
        to: check-normality
        
      - from: check-normality
        to: parametric
        condition: "is_normal == `true`"
        
      - from: check-normality
        to: nonparametric
        condition: "is_normal == `false`"
        
      - from: parametric
        to: effect-size
        
      - from: nonparametric
        to: effect-size
        
      - from: effect-size
        to: power
        
      - from: power
        to: report
        
    start_node: load
    end_nodes: [report]
    max_iterations: 1

outputs:
  artifacts:
    - path: "./reports/ab-test-{{ timestamp }}.md"
      from: "{{ nodes.report.response }}"
```

---

## Best Practices from Examples

1. **Start Simple**: Begin with chain pattern, migrate to complex patterns when needed
2. **Modular Agents**: Keep agents focused on single responsibilities
3. **Progressive Complexity**: Add features (tools, conditions, parallelism) incrementally
4. **Budget Awareness**: Set realistic token and time budgets
5. **Error Handling**: Use retries and validation steps
6. **Security**: Never hardcode secrets, use environment variables
7. **Observability**: Export traces and artifacts for debugging
8. **Testing**: Validate specs before production deployment
