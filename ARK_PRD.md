# Strands CLI translate Command – Product Requirements

## Objective and Summary

The goal of the strands translate command is to provide a seamless way to **convert McKinsey ARK agent specification files into the native Strands CLI workflow format**. This enables teams to take ARK-defined agents (which run on Kubernetes via custom resource definitions) and run or test them locally using Strands CLI. In essence, the command acts as a **bridge between ARK’s CRD schema and Strands’ YAML workflow schema**, automating what would otherwise be a manual translation process.

**Key Objectives:**

**Interoperability:** Allow users to leverage existing ARK specs (Agents, Teams, Queries, Tools, etc.) by translating them into Strands CLI workflows, preserving functionality and intent.

**Full Spec Support:** Cover the entire ARK CRD feature set – all fields and resource types defined in ARK v1alpha1 should be recognized and handled (Agents, Models, Teams, Tools, Queries, etc.).

**Developer-Friendly Validation:** Include robust validation on both ends. The tool should catch errors in the ARK input (e.g. missing fields, unknown values) and ensure the output YAML conforms to Strands’ JSON schema (version, structure, allowed values). Any issues should result in clear, actionable error messages rather than silent failures.

**User Convenience:** Simplify what could be a complex multi-step conversion into a single CLI command. The output should be **ready to use** – a developer can immediately run strands validate or strands run on the generated file without further editing (assuming any required secrets or external inputs are provided).

By achieving the above, the translate command will accelerate migration of ARK-based agentic workflows to the Strands platform, and allow side-by-side use of ARK and Strands in development. This PRD details the required functionality, interface, and edge-case considerations to implement this feature within the existing Strands CLI codebase.

## Functional Requirements

The strands translate feature must fulfill the following requirements:

**Accept ARK CRD Input:** Read an input file (YAML) containing one or more ARK custom resources. The file may include multiple documents separated by --- (e.g. an Agent plus its Model and Tool definitions). The command should support all relevant ARK kinds:

Agent – single agent definitions (with prompt, tools, etc.).

Team – multi-agent team definitions.

Query – query scenarios targeting agents/teams.

Model – model provider configurations.

Tool – custom tool definitions (including MCP server references).

(If the input contains other ARK resource types like Memory, A2AServer, etc., the translator should handle or gracefully ignore them as appropriate – see **Edge Cases**.)

**CLI Command Interface:** Provide a clear syntax for invoking the command. It should integrate into the Strands CLI as a top-level command (e.g. strands translate ...). The implementation should align with the CLI’s existing structure (likely extending the Click/Argparse definitions). See **CLI Syntax and Examples** below for specifics.

**Mapping ARK → Strands:** Transform ARK spec content into an equivalent Strands workflow YAML:

**Metadata and Naming:** Use ARK resource names to inform Strands names:

If a Query CRD is provided, use its metadata.name as the Strands workflow name field.

If only a Team (and agents) are provided (no query), use the team’s name (or a combination like <team-name>-workflow) for the output name.

Default to a reasonable name (or require --name option) if no obvious name is present.

The output YAML must include version: 0 and a non-empty name (Strands required fields).

**Agents:** For each ARK Agent:

Create a corresponding entry in the Strands agents map. Use the agent’s metadata.name as the key (ID) and carry over its prompt exactly. For example, an ARK agent named “weather-agent” with a prompt becomes:

agents:
  weather-agent:
    prompt: | 
      <agent prompt text>

(If ARK agent had a multi-line prompt, preserve formatting and indentation.)

Include agent-specific overrides: If the ARK Agent’s spec includes a modelRef, map this to the Strands agent’s model_id override. For example, if agent references model gpt-4-model in ARK, and if that model CRD resolves to provider OpenAI with model gpt-4o, then set model_id: gpt-4o (and possibly provider: openai) for that agent in Strands. The translator should **resolve model references** by looking up any provided Model CRD:

If the corresponding Model spec is in the input, extract its provider/type and model value (e.g. ARK type: openai with model.value: gpt-4o → Strands provider: openai, model_id: gpt-4o).

If the Model CRD is not provided, the translator may either error (missing dependency) or use a best guess default (e.g. assume OpenAI provider if model name looks like an OpenAI model). **Open question:** how to handle missing model details (see **Open Questions**).

If the ARK Agent specifies an executionEngine (external execution engine reference), note that Strands CLI does not support external execution engines – all agents run within Strands itself. The translator can **ignore** executionEngine fields or log a warning, since this detail isn’t applicable outside the ARK/K8s context.

Map agent tools: ARK Agents list tools by type and name. In Strands, tools are declared globally under a tools: section grouped by language/runtime (e.g. tools: python: for native Python tools). For each tool that an agent can use:

If the tool is a known **built-in** in Strands (e.g. ARK’s calculator or web-search – note: Strands has a calculator tool but **no built-in web-search**), map it to the appropriate tool registry name. Common mapping might be:

ARK built-in web-search – **No direct Strands equivalent** (will require custom implementation; see **Edge Cases**).

ARK built-in calculator – Strands built-in calculator (include it under tools: python:).

ARK built-in file-<ops> – map to Strands file_read/file_write if possible.

If the tool is a **custom tool** (ARK type: custom referencing a Tool CRD or MCP server), include it by name under tools: python: as well, assuming the user will provide an implementation. For example, if ARK agent uses a custom tool named get-coordinates, output:

tools:
  python:
    - get-coordinates

This registers the tool name in the workflow so that if a corresponding Python tool plugin exists, it can be invoked. If the translator can detect the tool’s nature (e.g. an MCP server call) from the Tool CRD:

It should try to preserve that information. For instance, if ARK Tool spec has type: mcp with mcpServerRef and toolName, the translator might simply register the toolName (since Strands cannot directly interface with the ARK MCP server). It should warn the user that external MCP tools need manual adaptation.

**Important:** The translator must aggregate all unique tool names used by agents into the Strands tools section, to satisfy schema and allow execution. (Strands validation will fail if an agent references tools not declared in tools block.)

Map agent parameters: ARK Agents can define template parameters in their spec (with values from ConfigMaps, Secrets, or Query parameters). Strands CLI does not have a per-agent parameter list; instead, **workflow-level inputs** serve this role. The translator should handle each case:

**Static parameters (value)**: If an ARK agent parameter has a hardcoded value, it effectively personalizes the agent’s prompt. The translator can inline these into the prompt (if feasible) or convert them into global inputs.values in the Strands spec. For simplicity, static parameters could become default input variables. *Example:* ARK agent parameter name: mode, value: "production" could yield a global input mode: "production" and the agent’s prompt can reference {{ mode }}.

**ConfigMap/Secret parameters (valueFrom)**: Since Strands workflows aren’t Kubernetes-native, they cannot fetch ConfigMaps or Secrets at runtime. The translator should **not embed raw secret values** (for security) and instead expose such parameters as inputs that the user must provide. For each parameter with configMapKeyRef or secretKeyRef, do the following:

Create a corresponding entry in the inputs.required section of the output (marking that the user needs to supply it) or at least mention it in documentation. For instance, api_token coming from a K8s Secret would become an input variable api_token with no default.

In the agent’s prompt or any template, replace {{ .api_token }} (Go template syntax) with {{ api_token }} to match Strands/Jinja context. Essentially drop the leading dot and ensure the variable name matches the one put in inputs.

**Query parameter references (queryParameterRef)**: ARK allows an agent’s prompt to reference values provided in a Query CRD. In translation, this is naturally handled by Strands inputs as well. For example, if an ARK agent prompt uses {{.user_name}} via a queryParameterRef, the translator should include user_name as an input to the Strands spec (populated by the query’s value if that query is part of input). If we are also translating the Query, see Query mapping below for how values flow.

**Output Schema:** ARK Agents may define outputSchema (a JSON schema for structured output enforcement). Strands CLI does not currently enforce structured output schemas on agents – the agent can output free-form text or JSON without a schema check. The translator can ignore outputSchema for execution purposes. However, it might be useful to:

Emit a comment in the YAML indicating the expected structure, or

Optionally, if the schema is simple and the Strands workflow intends to use the agent’s output, we could incorporate it in documentation. For now, this field can be dropped or turned into a non-functional comment since it has no equivalent in Strands execution.

**Teams:** For ARK Team CRDs, construct the Strands workflow pattern that captures the team’s coordination strategy:

Read the team’s strategy field and map it to one of Strands’ supported pattern types:

strategy: sequential – Map to a **Chain** pattern in Strands (a simple ordered sequence). Each team member agent will become a step in the chain, invoked in the given order. The first agent receives the initial input, then each subsequent agent could receive the previous agent’s output as input (if that’s implied by the use case). We may assume a simple chaining of outputs (since ARK sequential likely means agent1 → agent2 → etc.).

strategy: round-robin – **Not directly supported** as a distinct pattern in Strands. Round-robin implies agents taking turns possibly for multiple iterations. Strands has no built-in looping pattern (aside from the generic Graph which can model loops). For an initial implementation, we can handle round-robin in a limited way:

If maxTurns is specified in the Team spec (the number of exchange rounds), we could unroll that many rounds explicitly in a Graph pattern (this can get complex).

More likely, we should document that full round-robin multi-turn dialogue is not automatically translated. The translator might produce a single sequence (similar to sequential) or a Graph with a note that round-robin dynamics need custom handling. **This is a limitation** (see **Edge Cases**).

strategy: graph – Map to Strands **Workflow** or **Graph** pattern. ARK’s team graph likely specifies directed edges between agents (tasks) to form a workflow DAG. Strands “workflow” pattern is a DAG-based execution with dependency resolution, which is a natural fit. The translator should:

Take each team member as a node (task) in the workflow.

Use the graph.edges list to define dependencies (deps) between tasks in the Strands spec. For example, if ARK graph edges contain { from: agentA, to: agentB }, then in Strands YAML, make agentB’s step depend on agentA’s step: deps: [agentA].

Ensure the pattern is declared as type: workflow (or graph if we choose the Graph pattern for more complex flows). **Note:** The Strands graph pattern is more advanced (supports loops/conditionals), but for a static DAG, workflow pattern is sufficient and simpler.

strategy: selector – Map to Strands **Orchestrator-Workers** pattern if possible. In ARK, a selector strategy means one “leader” agent dynamically chooses which agent runs next (AI-driven orchestration). Strands’ orchestrator_workers pattern is designed for a similar purpose: an orchestrator agent that can assign tasks to other agents dynamically. The translator should:

Identify the selector agent (ARK likely specifies selector.agent and a selectorPrompt in the Team spec for the deciding agent).

In the Strands spec, designate this agent as the “orchestrator”. The other team members become the pool of workers.

Set pattern.type: orchestrator_workers and configure the config with the orchestrator and workers. (Strands schema likely requires an orchestrator agent and possibly initial task list – we will use the team’s members as the worker list).

Because dynamic decision-making is complex to capture, initially the translator can produce a structure where the orchestrator agent is called first (with the user’s query), and its response is interpreted as a decision. Then the chosen agent is invoked. *However*, full dynamic looping (multiple cycles) might not be supported in a single run without custom logic. The translator’s output may handle one cycle (or simply set up the orchestrator and one worker step), with a note that multi-turn selection would need iteration. This is an advanced scenario – we can target basic support where a selector picks one next step.

**Team Members:** Regardless of strategy, the translator needs to incorporate the team’s members (agents) into the workflow:

Ensure every member.name in the Team spec corresponds to an agent defined in the input. If not, error out (“Team references unknown agent X”). If the agent exists only as a name (no Agent CRD given), we cannot proceed with a complete translation.

For sequential or round-robin, maintain the order given (the ARK spec might not explicitly order members for round-robin beyond listing – assume list order to start).

For graph, order is determined by dependencies, not list position.

For selector/orchestrator, ensure the orchestrator agent is identified. Possibly the team spec’s selector.agent is the orchestrator’s name.

**Team Input Handling:** ARK Teams likely don’t themselves take direct input; input comes via a Query CRD targeting the team. If we are translating an ARK Team *without* a Query, we should still design the Strands pattern to accept an input (so the resulting workflow can be executed). We can achieve this by defining an inputs: section in the Strands spec for the user query or conversation that the team will process. For example, a team might expect a question to start the interaction. The translator can define an input variable like user_input and ensure the first agent’s step uses it (e.g. input: "{{ user_input }}" for the first step in a chain, or pass it into the orchestrator agent’s prompt, etc.).

**Termination:** Teams might not explicitly define an end condition except in round-robin with maxTurns. For chain/sequential and graph patterns, the workflow ends after the last defined step. For orchestrator (selector) pattern, we may end after one orchestrator decision for now. This is acceptable for initial translation; any further continuation is a manual extension (the user can always modify the output if needed for complex loops).

**Queries:** If an ARK Query CRD is provided, the translator will generate a Strands workflow pattern to emulate that query execution:

**Targets:** ARK Query spec.targets can list multiple targets of types agent, team, model, or tool. This is essentially a fan-out where the same input is sent to all specified targets in parallel, and ARK will collect multiple responses. Strands can naturally represent parallel execution via the **Parallel** pattern. Therefore:

If more than one target is present, use pattern.type: parallel with a branch for each target.

If only one target is present, we could use a simpler pattern (chain) instead of parallel-of-one. However, for uniformity, using a chain for a single target is fine. The translator can decide to use a chain when a single agent target is given (since it’s just one sequence), and use parallel when multiple concurrent targets are needed.

**Mapping each target to Strands branches/steps:**

**Agent target:** Create a branch (or the main sequence) where that agent is invoked. This would be a single-step chain: the agent processes the query input. For example, if Query targets agent: weather-agent, and the user question is provided, the Strands workflow might simply call weather-agent with the input prompt. In a chain pattern, that’s one step; in a parallel pattern branch, that’s one step in that branch.

**Team target:** The translator needs to inline the team’s logic into the workflow, because Strands does not have a concept of “call this team” – the team *is* a set of steps/pattern. If the Query targets a team that is also provided in the input, the translator essentially merges the team’s pattern into the overall workflow. Two approaches:

**Treat each team target as a separate branch** in a parallel pattern. For each team target, create a branch whose steps implement the team’s strategy. For example, a Query targeting a team of agents A and B sequentially could produce one branch that runs A then B (so that branch has two steps). Meanwhile another branch might be an independent agent, etc.

If only one target and it’s a Team, we could choose to output a single workflow (chain/graph/orchestrator as needed) rather than parallel. Essentially, translate the team to the main pattern directly (similar to translating a Team CRD without Query), but also incorporate the Query’s input (see below) and possibly session/memory.

**Model target:** ARK Query can target a raw model (meaning the query is sent directly to a model without an agent persona). Strands CLI **requires an agent** to interact with a model (there is no direct “model” target concept in workflows). To handle this:

The translator can automatically generate a simple agent as a proxy for the model. For example, if the target is a model named gpt-4, create a temporary agent in the agents section (e.g. call it model-gpt-4) whose prompt is essentially an identity prompt (“You are the model and will return answers directly.”). This agent would use the appropriate provider and model_id (from the Model CRD or default) in runtime overrides, so it effectively channels calls to that model.

Then the query can be translated as if it targeted that agent. This way, the model output is captured via an agent interface. We should clearly mark this as a generated agent (perhaps in description or as a comment) since it has no real prompt behavior.

**Alternative approach:** If adding a synthetic agent is undesirable or confusing, we may treat model targets as unsupported. However, to fulfill “full spec support”, generating a simple agent stub is reasonable.

**Tool target:** ARK allows queries that directly invoke a tool (e.g. run a tool without an agent). Strands does not support tool execution outside the context of an agent’s step. To simulate this, the translator will need to introduce an agent (or use an existing one) to carry out the tool action:

The translator could create a stub agent like “tool-runner” with a prompt instructing it to immediately use the specified tool. For instance: *“Use the tool X to process the request and return the result.”*

In the workflow, that agent’s single step would call the tool. Strands supports a step property tool_overrides or simply allows the agent to decide to use the tool. In practice, since we cannot inject execution instructions easily, a simpler approach is to have the agent’s prompt mention the input, and trust the agent (which is actually the LLM) to decide to call the tool. This is not guaranteed. Another approach is using Strands’ Python API directly, but that’s outside a pure YAML spec.

Given the complexity, **direct tool targets may be marked as unsupported** in this first iteration. The translator can error or warn if a Query target is a tool, advising the user to create an agent to use that tool.

**Input and conversation:** ARK Query spec has two modes of input:

type: user with a single prompt string (optionally containing template placeholders).

type: messages with an array of role-tagged messages (user/assistant/system) for multi-turn context. In Strands:

A **single-turn user input** fits naturally. The translator should take the Query’s input field (after resolving any parameters into it) and supply it to the first step(s) of the workflow. If the workflow is a chain or orchestrator, the first agent’s input can be this string. If parallel, each branch’s first step uses the same input. The translator should also place this string (or a placeholder) into the Strands inputs.values or a variable to allow easy substitution. For example, define an input variable query and set its default to the query text, then use {{ query }} in agent prompts. This way, the user can override it when running, or see clearly what input is being used.

A **multi-turn messages input** is harder to map directly. Strands CLI doesn’t have a built-in concept of “conversation history” input in the YAML spec – instead, multi-turn would usually be handled by chaining agents or using memory. We have a few options:

Flatten the message history into a single system/user prompt for the first agent. E.g. concatenate the conversation into one prompt text (not ideal, but straightforward).

Represent each user/assistant message as separate steps: e.g. a user message could be fed to an agent, the assistant response captured, then another user message prompts maybe the same or another agent, etc. However, this would require encoding roles and might confuse the translation (especially if the “assistant” in the ARK messages is supposed to be the same agent responding).

**Initial approach:** If type: messages is encountered, the translator can fallback to a simpler translation: take all user-role messages and combine them as one input, or just take the last user message as the input (assuming earlier messages are context that the agent might handle in prompt).

This is an edge case; we will document that complex multi-turn queries are not fully supported in automated translation. The output might include as a comment the entire conversation and recommend manually constructing a multi-step Strands workflow if needed.

**Parameters:** ARK Query supports a list of parameters for template expansion in the input. The translator should apply these parameters to produce the final input string (effectively perform the template substitution) if possible, or carry them into the Strands spec:

If the ARK Query input is "What is the weather in {{.location}}?" with parameter location = "New York", the translator can simply substitute and use "What is the weather in New York?" as the input to the agent. However, to maintain fidelity and allow user override, it might be better to keep it templated in Strands as well:

Define an input variable location with default "New York", and use {{ location }} in the query text in Strands output. This aligns with Strands approach where template variables come from inputs.values or --var overrides.

For parameters that come from ConfigMaps/Secrets in ARK Query (similar to agent parameters), treat them as needing user input. We won’t have those external resources in Strands, so expose them as input variables (no default), to be provided at runtime.

**Session and Memory:** ARK Query allows specifying sessionId (for conversation continuity) and memory (to use a named memory store). Strands CLI has its own session mechanism (for resumability) but not a concept of persistent memory by name. The translator will:

Ignore sessionId values because Strands will automatically handle session IDs internally if --save-session is on. (We could potentially map ARK’s sessionId to a fixed session name, but it’s not necessary – sessions in Strands are usually identified by an auto-generated UUID or provided at resume time.)

Omit or comment out any memory reference. ARK’s memory (like a cluster-memory) cannot be replicated outside Kubernetes. Strands does maintain conversation context within a session (the agent’s previous outputs can be referenced via templates like {{ last_response }} or using the conversation skill if it exists), but there is no drop-in replacement for ARK’s external memory resource. We simply note that memory persistence is not applicable, and proceed without it. (All needed context should be managed in the workflow steps themselves.)

**Query Output (Responses):** ARK Query status contains collected responses for each target, but in the spec input file we get, that status may or may not be present. We do not use the status in translation (we only translate the desired behavior, not the results). In the Strands workflow, if multiple branches (parallel) are used, the user will get multiple outputs (which Strands can collect as artifacts or just console output). If needed, the translator can configure an outputs: section:

If only one response (single agent), maybe write it to a file or console. But Strands doesn’t automatically save output unless asked. We could add a default artifact output mapping the last response to, say, ./response.txt to mimic ARK’s behavior of having a result (as seen in some Strands examples).

If multiple responses (parallel branches), we might not know how to label each easily. Possibly, we skip adding artifacts for multiple responses, or name them generically per branch ID.

This is optional; the primary goal is to execute successfully. The user can always capture outputs via --out directory or by modifying the spec.

**Validation of Input (ARK side):** The translator must validate that the ARK spec file is well-formed and logically consistent **before** attempting translation:

**YAML Parsing:** If the input file is not valid YAML (parse error, improper syntax), the command should fail fast with a clear error: e.g. *"Failed to parse input YAML: <details of parse error (line number, etc.)>"*.

**ARK Schema Validation:** Enforce the presence of required fields in each CRD:

Every resource must have the minimal Kubernetes fields: apiVersion, kind, metadata.name, and a spec section. If any of these are missing or misspelled, error out (*"Invalid ARK spec: kind not specified"* or *"Missing spec for resource X"*).

For each specific kind, check key required fields:

Agent: ensure spec.prompt is present (empty prompt would be invalid for an agent) and that metadata.name is a valid identifier (no spaces, etc.). Ideally also ensure at least one model reference (either via modelRef or default model availability) so the agent isn’t headless – ARK defaults to model default if not specified, so if no modelRef, that’s fine (the translator will assume a default model).

Team: ensure spec.members (non-empty list) and spec.strategy are provided (these are required by ARK schema). If strategy is graph, ensure the graph.edges structure is present with at least one edge. If strategy is selector, ensure a selector agent is specified. If round-robin with a finite loop, ensure maxTurns is given (not strictly required by ARK, but without it, round-robin could be infinite – translator can handle it but may warn).

Query: ensure either spec.input is provided (for type "user") or a non-empty spec.input message array (for type "messages"). Also require at least one target in spec.targets. If no targets, the query does nothing – we should error (*"Query has no targets to execute"*).

Model: ensure spec.type and spec.model.value are present. Without these, a Model CRD is not meaningful. If a required config (like API key) is missing in the Model spec, warn the user that the model might not function outside ARK.

Tool: ensure spec.type and any identifying fields the translator might need. (For example, if type is mcp, we expect an mcpServerRef and toolName in spec; if type is python or other, ensure command/template is present. This might be complex to validate fully, so at least ensure name and type exist.)

Cross-resource validation:

If a Team references agent names, ensure those Agent CRDs are included (or possibly that an Agent of that name is also targeted by a Query which includes the prompt – but safer to require the Agent CRD).

If a Query references a team or agent, ensure those are provided.

If an Agent references a Model by name, ensure the Model spec is provided (or warn that default will be assumed).

If an Agent references Tools by name/type, ensure those tools have either a provided Tool CRD or a known built-in mapping. If not, warning (not a hard error, since user might handle tool implementation).

**ARK Version**: If apiVersion is not ark.mckinsey.com/v1alpha1 (e.g. a newer version or a completely different group/kind is given), the tool should warn or reject unknown versions. This ensures we don’t try to translate unsupported CRDs. (We can accept v1alpha1 and possibly v1beta1 if ARK moves to that, but if significantly different we’d need updates.)

The validation errors should be **user-friendly**: clearly indicate the resource and field causing the issue. For example:

*"Input validation error in Agent 'assistant': missing required field** **prompt**."*

*"Team 'support-team' references unknown agent 'billing-agent' (no such Agent spec provided)."*

*"Unsupported resource kind 'Deployment' in input – only ARK spec CRDs are allowed."*

The translator should **not proceed to generate output if input validation fails**. Instead, exit with an error message (and a non-zero exit code as appropriate). This prevents generating nonsense output.

**Construction of Output (Strands YAML):** The translator will build a complete Strands workflow spec in memory and then serialize to YAML. Requirements for this output:

Must include all **required top-level fields** that Strands expects:

version: 0 (integer).

name: ... (string) – as determined from input or options.

runtime: – If the input includes Model definitions or agent modelRefs, set the appropriate default provider and possibly model_id. If multiple models are used by different agents, one agent might override model_id as discussed, but we still need a base. We can choose a sane default:

If exactly one Model CRD is provided and marked as “default” (ARK often uses a Model named “default” for the primary model), use that for runtime.

Otherwise, if agents specify different providers, this is a multi-provider scenario. Strands allows overrides per agent for provider/model, but the runtime.provider still must be set to something (perhaps arbitrarily one of them, since it’s required). We might set runtime.provider to the first agent’s provider or "openai" as a fallback, and rely on overrides to handle others. (Document this choice as an open question or limitation.)

If no Model info at all is given, default to runtime.provider: openai (common case) and let model_id perhaps remain empty or default. Actually, Strands requires at least provider but model_id can be omitted if each agent specifies one. If no agent gave any model info, we assume something like model_id: gpt-4 or instruct user to set via CLI environment (OpenAI key).

agents: {} – the map of agents filled as above. Must have at least one entry.

pattern: – the workflow pattern configuration. Must include type and config subfields. The translator is responsible for choosing the correct pattern type and building a valid config structure as per Strands schema. Examples: *Chain pattern:*

pattern:
  type: chain
  config:
    steps:
      - agent: agent1
        input: "{{ user_input }}"
      - agent: agent2
        input: "{{ last_response }}"

(ensuring each step has required fields). *Parallel pattern:*

pattern:
  type: parallel
  config:
    branches:
      - id: branch1
        steps:
          - agent: agentA
            input: "{{ query }}"
      - id: branch2
        steps:
          - agent: agentB
            input: "{{ query }}"
            deps: []   # if needed, or omit if single step

etc. *Workflow (DAG) pattern:*

pattern:
  type: workflow
  config:
    tasks:
      - id: step1
        agent: agentX
        input: "{{ user_question }}"
      - id: step2
        agent: agentY
        deps: [step1]
        input: "Follow-up based on {{ tasks.step1.response }}"

(Strands expects tasks as a list with id, agent, input, deps). *Orchestrator pattern:* will have its own structure (likely an orchestrator agent and maybe a list of worker agent IDs). The translator must ensure the YAML conforms to the expected structure for the chosen pattern. (Refer to Strands JSON schema definitions of each pattern for required fields and field names).

If present/needed: inputs: – define input variables. This is not strictly required by schema, but any placeholders we use in prompts or steps should be declared:

Use inputs.values to provide defaults for any known required variables (like in the Query example, default for location or query text).

We might also separate into inputs.required if we want to mark some as required (the Strands schema does allow inputs.required to list variable names that must be provided). For simplicity, we can just provide defaults or leave them all in values and trust the user to override if needed. Marking required vs optional in the spec can be an enhancement (Strands will then error if required inputs are missing at runtime).

outputs: – Optionally include outputs:

If the user did not specify, we can omit, as Strands doesn’t require it. But adding an output artifact mapping is user-friendly. For example, if a single chain, output the last response to a file (like artifacts: - path: ./response.txt from: "{{ last_response }}").

If multiple branches, we might skip artifacts or just output combined if possible. This is secondary.

Other top-level sections Strands supports that ARK doesn’t:

skills, security, telemetry, etc. These can be left out unless we have compelling info to fill them. (E.g., ARK’s tool usage might correspond to Strands skills or environment policies, but likely not needed initially.)

We ensure additionalProperties: false compliance – i.e. do not introduce unknown keys. Only emit keys defined by the schema.

**Schema Validation (Output):** After constructing the output spec object, the translator should validate it against Strands’ JSON Schema (using the existing schema/validator.py module or similar). This will catch any structural mistakes in our translation logic. For example:

Missing a required section like pattern or runtime.provider will trigger a schema error.

Misnaming a field (e.g., using agent_id instead of agent in steps) would be caught.

Using a pattern type but not providing the correct config fields (schema will list which fields are expected).

If validation passes, we are confident the output will be accepted by strands run (aside from any runtime issues with model API keys or missing tool implementations).

If validation fails (which likely indicates a bug in translation), the translator should not output invalid YAML. This might be an internal development assertion – ideally by the time this feature is released, it should consistently produce valid specs. But as a safety, we can output an error like *"Internal error: generated spec failed validation"* and possibly dump the validation errors (with JSON Pointer references as given by the validator).

**User-Friendly Output Errors:** In cases where we *attempt* translation but encounter a situation that leads to invalid output or inability to map:

For example, an ARK team with strategy: round-robin and no easy mapping – rather than output something incorrect, we might stop with a message: *"Translation of round-robin teams is not supported in this version."* Or we output a partial spec with a big warning comment at the top.

Another example: ARK tool references that can’t be resolved – we might still output the spec including the tool name (so user can attempt to run), but also print a warning: *"Warning: Tool 'web-search' is not a built-in Strands tool. The workflow will include it, but you must implement this tool or remove it."*. Warnings can be printed to stderr or as comments in the YAML (the former is cleaner).

All such messages should guide the developer on how to fix or adjust, rather than leaving them confused. For instance, if we drop memory, we could log: *"Note: Ignoring ARK memory settings (not applicable in Strands CLI, context will not persist across runs without sessions)."*.

**CLI Integration & Ecosystem:**

The command should fit into the existing CLI without disrupting other commands. It will be implemented in Python within the strands-cli codebase, likely under a new module or subpackage (e.g. strands_cli.translate).

It should reuse existing utilities where possible:

YAML parsing/loading should use the same library/config as strands run (to ensure consistency in supported YAML features).

Output schema validation will leverage the existing JSON schema file and validation logic used by strands validate.

Error handling and messaging should follow the CLI conventions (probably using the same logger or exception patterns).

Performance is not a primary concern here (files will be relatively small, containing a handful of YAML documents). However, the code should be mindful of not doing anything extremely heavy (like network calls – none should be needed; it’s a purely local translation).

The translator must not require an active ARK cluster or any external connectivity. It should operate solely on the file contents given (self-contained conversion).

Ensure that adding this command does not bloat the CLI in terms of dependencies. (All needed info is basically parsing text and formatting text, which Python can handle with PyYAML and existing libs.)

In summary, the functional requirements ensure that strands translate can intake valid ARK specs and produce an equivalent Strands spec or clear errors, covering the entire spec range and giving developers confidence in the conversion.

## CLI Syntax and Examples

**Command:** strands translate

**Description:** Translate an ARK specification (CRD file) into a Strands workflow YAML.

**Usage:**

strands translate [OPTIONS] ARK_SPEC_FILE

- ARK_SPEC_FILE – path to the input YAML file containing one or more ARK CRD definitions to translate.

**Options:** - -o, --output <FILE>: Write the translated YAML to <FILE>. If not provided, the output will be printed to stdout. The tool should not overwrite an existing file unless --force is specified. - --force: Overwrite the output file if it already exists, without prompting. (This can be useful in scripts or Makefiles to regenerate specs.) - --format <fmt>: (Optional) Choose output format, e.g. yaml (default) or json. By default, the command produces YAML. JSON output might be useful for programmatic consumption or debugging, but YAML is expected for human-edited workflow files. - --name <workflow_name>: (Optional) Override the name field of the generated workflow. If not given, the translator will derive the name as described in Functional Requirements (e.g. from Query or Team name). This allows users to ensure a unique or meaningful name in the output. - --no-validate: (Optional) Skip validation of the output spec against the schema. By default, the translator **will** validate and only produce output if it’s valid. This flag could allow advanced users to get the raw translated spec even if it might not pass schema (not recommended for general use). In normal operation, leaving validation on is safer.

*(Any other global flags like** **--debug** **and** **--verbose** **are inherited from the CLI framework and should function as usual, e.g.** **--debug** **might print internal mapping steps or decisions for troubleshooting.)*

**Examples:**

**Basic translation to a file** – Suppose you have an ARK spec file customer-support.yaml that defines several Agents, a Team, and a sample Query. To translate it:

strands translate customer-support.yaml -o customer-support-workflow.yaml

This will read customer-support.yaml, and output the equivalent Strands workflow to customer-support-workflow.yaml. On success, a message might be printed:

Translation complete. Output written to customer-support-workflow.yaml

You can then run strands validate customer-support-workflow.yaml or open the file to review the contents.

**Translate and print to console** – If you omit the -o option:

strands translate quick-test.yaml

The command will output the translated YAML to standard output. This is useful for quick viewing or piping. For example, you could pipe it directly to the Strands validator:

strands translate quick-test.yaml | strands validate --format text /dev/stdin

(Assuming the CLI supports reading from stdin for validation; if not, user can visually inspect or redirect the output.)

**Force overwrite** – If my-workflow.yaml already exists and you want to overwrite it:

strands translate ark-spec.yaml -o my-workflow.yaml --force

Without --force, the command would refuse to overwrite and instead throw an error or prompt (depending on implementation). With --force, it silently replaces the file.

**Custom naming** – If the ARK spec doesn’t have a clear name or you want to give a different name:

strands translate team-spec.yaml -o team-workflow.yaml --name "support-team-workflow"

This ensures the generated YAML uses name: support-team-workflow at the top, regardless of what the ARK Team or Query was called. (Useful if ARK names contain characters Strands doesn’t allow, for instance.)

**Verbose output for debugging** – Using the global --verbose or --debug flags:

strands translate problematic-spec.yaml --debug

In debug mode, the tool might print details like “Parsing Agent X… mapping fields…”, “Agent X modelRef -> provider=openai, model=gpt-4o-mini”, or warnings about untranslatable parts. This helps a developer understand how the ARK spec is being interpreted. In normal mode, the tool should be relatively quiet aside from errors or a success confirmation.

**Output format:** The YAML produced will follow Strands CLI conventions (2-space indentation, keys in lowercase, etc.). It will include comments for any important notes or TODOs. For example, if a tool isn’t supported, the YAML might contain a comment:

# NOTE: Tool 'web-search' has no direct equivalent in Strands; requires custom implementation.
tools:
  python:
    - web-search
    - data-fetcher

The translator should strive to format the YAML cleanly for readability: proper indentation, quoting strings only when necessary, using | for multi-line prompts exactly as in the ARK input. (This ensures that prompts which are multi-line are preserved in a block scalar format, and not turned into awkward single-line strings with \n.)

**Confirmation & Errors:** On successful translation, the CLI can output a one-liner confirmation (or nothing except the result if piping). On failure, it should exit with a non-zero status and print errors to stderr. Example error messages a user might see: - *"Error: Failed to parse ARK spec file (YAML syntax error at line 20)."* - *"Error: Agent 'analyst-bot' is missing a prompt – cannot translate."* - *"Error: No supported ARK resources found in file. Make sure you're providing a valid ARK CRD YAML."* - *"Warning: Some features could not be translated fully. See notes in output file."* (if we choose to still output partially).

These examples illustrate typical usage scenarios and expected behaviors, ensuring the command is intuitive for developers. The focus is on making the translation as straightforward as running any other Strands command, with sensible defaults and helpful messaging.

## Input/Output Specification Details

This section details how ARK input is interpreted and the exact structure of the Strands CLI output spec.

### Supported ARK Input Format

The translator expects the input to follow the **ARK CRD design** (v1alpha1) for agentic resources. It will process the following resource kinds (case-sensitive in YAML):

**Agent (ark.mckinsey.com/v1alpha1, kind: Agent):** Defines a single autonomous agent (prompt, tools, model, etc.).

**Team (kind: Team):** Defines a team of agents with a collaboration strategy (sequential, round-robin, etc.).

**Query (kind: Query):** Defines an execution request (prompt or conversation) directed at one or more agents/teams.

**Model (kind: Model):** Defines an LLM model configuration (provider, model ID, endpoints, auth).

**Tool (kind: Tool):** Defines a tool (either a built-in capability or an external/MCP tool) available for agents.

*(If present:)* **Memory (kind: Memory)** and **A2AServer**, etc. – these will be recognized but **ignored** or only partially used, as they have no direct standalone effect in a Strands workflow. Memory is handled as part of Query (session context), and A2A servers (for agent-to-agent communication) are not applicable outside ARK’s cluster environment.

The input file can contain **multiple documents**. For example, a single YAML file could include: one Model, two Agent definitions, one Team, and one Query (in any order, separated by ---). The translator will gather all of them first, then perform the mapping. The order of documents is not critical except when resolving references (e.g., an Agent might appear before the Model it references; this is fine, we’ll handle it).

**ARK CRD Fields of Interest:**

Below we list key ARK fields and how the translator uses them:

**metadata.name:** Used as the primary identifier for cross-references. Agent and Team names become IDs in the Strands spec. Model names are used to match modelRefs. Tool names identify tools. (We ensure to use these names verbatim in the YAML output for agents/tools unless they have characters not allowed by Strands schema – e.g., Strands agent IDs must match pattern ^[A-Za-z0-9._:-]+$. ARK names are usually DNS compliant, so should be fine. If any name is invalid in Strands context, we will sanitize (e.g. replace unsupported chars with hyphen) and inform the user.)

**Agent.spec.prompt:** The entire prompt string (which can be multi-line) is carried over as-is into the Strands spec. We preserve newlines and any ARK template syntax, adjusting for Jinja as needed (see Template Syntax below).

**Agent.spec.modelRef:** If present, signals which Model resource to use. The translator will link this to Strands provider/model_id either globally or per agent:

If the referenced Model CRD is included, extract its details:

E.g. spec.type: openai and spec.model.value: gpt-4o means OpenAI GPT-4 (ChatGPT-4 32k context in ARK shorthand). We’d set provider=openai, model_id=gpt-4o in Strands.

If spec.type: azure with a model name, provider might be azure_openai in Strands terminology (if supported) and model_id accordingly.

If spec.type: bedrock, provider=bedrock and model_id as given (often a lengthy ARN or Bedrock ID).

The translator should have a mapping for known ARK provider types to Strands provider strings:

openai -> openai

azure -> openai (Strands might treat Azure OpenAI as just another endpoint of OpenAI; or possibly a separate provider string like azure_openai – need to confirm Strands capabilities for Azure. If Strands doesn’t directly support Azure OpenAI endpoints, we might treat it as openai with a custom host.)

bedrock -> bedrock

For others (e.g. ARK could have ollama or others in future) – map accordingly if known.

If the model CRD contains secret references (for API keys, etc.), those do not appear in the Strands spec. Strands relies on environment variables (e.g. OPENAI_API_KEY) or AWS credentials for Bedrock. We will **not** embed keys. It’s the user’s responsibility to have the environment configured (the translator can remind via comments if appropriate).

If modelRef is present but the actual Model spec isn’t in the input, we attempt a reasonable default:

If modelRef.name is “default”, we assume the default model is something like GPT-4 (OpenAI) unless context says otherwise. Possibly just leave the output agent without an override (so it will use the Strands default model configured in runtime, which if the user sets up, could be something).

If modelRef.name matches a well-known model alias (e.g. “gpt-3.5” or “claude-2”), we can set model_id accordingly, but this is guesswork. Safer might be to require the Model CRD. We’ll warn: *"Model reference 'claude-2' not provided; please adjust** **runtime** **in output."*.

**Agent.spec.tools:** A list of tools the agent can use. ARK distinguishes type: built-in vs type: custom. The translator will translate this into a list of tool names for Strands:

For each entry: take the name. If type is built-in and name corresponds to a known built-in, fine. If unknown built-in or custom, still include the name (assuming a Python tool plugin or MCP proxy by that name might be made available).

We do not explicitly mark built-in vs custom in Strands YAML (Strands doesn’t require that in the spec; it just needs the name registered under the appropriate language runtime). All tools will likely go under tools: python: because Strands implements even “native” tools in Python. (There is also tools: mcp: concept possibly for MCP tools? The Strands example shows only grouping by execution environment like python: or others like shell: if they exist. Since ARK’s concept of built-in vs custom doesn’t directly map, we treat everything as a tool name and let Strands figure it out via its registry.)

**Agent.spec.parameters:** Covered above – these define templating values. We will convert them to global inputs. For each parameter:

If value is provided (literal), we can set a default input.

If valueFrom.configMapKeyRef or ...secretKeyRef, just create an input with no default (and maybe a comment # was from ConfigMap X). Encourage the user to supply it via --var or environment (for secrets, environment is better; but Strands cannot directly pull secrets, so user must provide).

If valueFrom.queryParameterRef, this ties to a Query’s parameter. The translator, when handling Query and Agent together, will ensure the Query’s parameters are translated to inputs, and the agent simply uses the same input name. E.g. ARK agent parameter name: userId, valueFrom.queryParameterRef.name: user_id means the agent expects a query param user_id. We will have inputs.values.user_id (or required) and agent prompt referencing {{ user_id }}.

**Agent.spec.description:** A description field (string). Strands doesn’t have per-agent description in the spec; we can ignore or incorporate it as a YAML comment above the agent’s prompt for documentation. (It might be nice to preserve it as it often explains the agent’s role.)

**Team.spec.members:** List of team members. Each member has name and type. From ARK docs, it appears type might indicate member category – likely “Agent” or “Team” (i.e. a team can nest other teams) or possibly “Model”. We should confirm:

The CRD snippet shows members[] name, type and requires both. We will assume most common case: members are individual agents, so type would be “Agent”. If a team included a model as a member (perhaps to treat a raw model as part of a team, though that’s unusual), type could be “Model”.

For translation: if type is Agent, we expect an Agent spec for that name. If type is Team, that implies nested team – we would need that team spec as well (and then essentially flatten or nest patterns, which gets complex; possibly out of scope to fully nest, but we could attempt to recursively translate the sub-team within this workflow).

If type is Model (the team directly includes a model’s output as a participant), we again would create a stub agent for that model as described in Query’s model handling, and include that stub in the pattern.

We should document that deeply nested teams or unusual member types might not translate perfectly.

**Team.spec.strategy:** The coordination strategy – must be one of the recognized values (“sequential”, “round-robin”, “graph”, “selector”, possibly “parallel” though not mentioned in ARK code – ARK might not have a “parallel” strategy because they treat parallel as separate queries rather than a team mode).

The translator has mapping logic per strategy (as detailed earlier in Functional Requirements). We reiterate mapping:

sequential -> chain

round-robin -> best-effort (no direct mapping; possibly chain or graph with loop, see limitations)

graph -> workflow (or graph pattern)

selector -> orchestrator_workers pattern

If ARK adds new strategies (e.g. “all-active” or something), translator will need updates. For now, handle the known ones and throw error if an unknown strategy appears.

**Team.spec.graph:** Present if strategy is graph – contains edges (list of from→to relations). We use this to set deps in tasks as described. Note: ARK might allow complex graphs (multiple start nodes, etc.), which Strands workflow can handle (multiple tasks with no deps means they start in parallel).

We need to create an ordered list of tasks. Likely we can list tasks in the order given by members, but ensure that dependencies link them appropriately. The schema expects tasks list to cover all tasks; order in the YAML doesn’t strictly matter except for human readability. We might order them such that if A has no deps it comes first, etc. This is a detail – main point is to include all tasks and their deps correctly.

**Team.spec.selector:** Present if strategy is selector – likely contains at least agent (the orchestrator agent name) and possibly a selectorPrompt or other config.

If a special prompt is provided for the selector agent to decide, that might correspond to an agent’s prompt or an input. Possibly ARK uses selectorPrompt to override the agent’s own prompt during selection. In translation, since the orchestrator agent will just use its normal prompt (from its Agent spec), we might not need selectorPrompt. If the ARK agent itself has logic to pick next agent, we trust the prompt in its Agent CRD. If ARK gave an explicit selector prompt, we could incorporate that into the orchestrator agent’s prompt (maybe appending it).

The translator needs to know which agent is orchestrator: it’s the one named in selector.agent. We should verify that agent exists and is part of the team members. We then treat it specially in orchestrator_workers config.

**Team.spec.maxTurns:** (Integer) – likely used for round-robin or maybe selector to limit cycles. If present and strategy is round-robin, it indicates how many rounds of agent cycling to do. Strands cannot easily loop N times without explicitly writing it out or using a graph with a loop. This is tricky:

If maxTurns is small, we could unroll the sequence that many times (e.g. if 3 turns and members [A, B], we’d do A->B->A->B->A->B if that’s how turns are counted – but more likely “turn” means each agent speaking once, so 3 turns each = 6 steps).

We might decide not to handle this explicitly. Instead, output a single sequence of one round (A->B) and comment that “maxTurns was 3, iterative execution not fully represented”.

Alternatively, if we assume “turn” means a pair (one cycle through all members), maxTurns=3 could mean 3 cycles. But ARK likely means each agent speaking = one turn. Needs clarification. Without ARK runtime to confirm, better to avoid trying to replicate loops.

**Query.spec.type:** either "user" or "messages". We covered handling: user → straightforward single prompt; messages → partially supported.

**Query.spec.input:** The content (string or list). We will use this directly or with template variables. Ensure to capture multi-line inputs properly (YAML block if needed).

**Query.spec.parameters:** Template parameters for the input. Either substitute or convert to inputs as discussed.

**Query.spec.targets:** Array of targets with type and name. We iterate each:

If type is “agent”, “team”, “model”, “tool”, handle accordingly by invoking or embedding as described.

Note: ARK might allow multiple types in one query. We must combine them in one Strands workflow (likely parallel branches).

**Query.spec.sessionId:** (string) – can ignore (not used in output).

**Query.spec.memory:** (object with name of Memory resource) – ignore for execution (no output).

**Query.spec.timeout:** (duration, e.g. "5m") – Strands workflow YAML does not have a direct timeout field. Timeout in ARK likely means the query will be aborted after that time. Strands currently might not support per-workflow timeouts except via external means. We will not include this in YAML (or possibly as a comment). Execution timeout can be handled by the user by other means if needed.

**Template Syntax Conversion:**

ARK uses Go template syntax with {{ .variable }} notation. Strands uses Jinja2, which also uses {{ variable }} for insertion. They are very similar in usage. However, ARK templates have certain context objects: - {{ .input.foo }} appears in ARK to reference fields of structured inputs (especially in Query or Tools templates). - {{ .environment }}, {{ .api_token }} etc. refer to parameters by name. - {{ .parameterName }} in ARK is equivalent to just using the parameter name as a variable in Jinja (assuming we provide it). - {{ .input }} might need special handling if ARK passes a whole input object. For example, ARK’s Query with type=messages probably not applicable here. Or ARK’s Tool templates might use .input to refer to the agent’s input. In Strands, an agent’s prompt can’t programmatically access a “parent input” object unless we explicitly supply it as a variable.

**General rule**: We will strip the leading . in most template expressions: - {{ .foo }} becomes {{ foo }} and assume foo is provided via inputs or context. - {{ .input.bar }} – if this appears in an agent prompt (via queryParameterRef usage perhaps), in Strands the query’s input variables are global, so if bar was provided as a query param, it’s now an input variable bar. So {{ .input.bar }} -> {{ bar }}. - If {{ .input.bar }} was meant to refer to something like the agent’s own input content (there’s a possibility ARK’s .input in an agent’s prompt refers to the query’s input text), then {{ .input }} would be the entire user question. Strands doesn’t auto-supply entire user prompt inside agent prompt (the user prompt is just fed as the agent’s input step). So if an ARK prompt literally contains {{ .input }}, that probably means the agent is supposed to repeat the user’s query or have access to it. In Strands, the easiest way is to ensure the user query is stored in a variable and then the agent prompt includes that. E.g., define user_question = query text, then agent prompt uses {{ user_question }}. The translator should detect such usage and adjust accordingly. - We must verify that double braces in ARK are used the same way (they are). ARK doesn’t use any custom delimiters, so just ensure no stray Go template functions (like {{printf ...}}) are present – if they are, Strands (Jinja) won’t understand them. Those would be rare in YAML specs; ARK templates seem simple. - We will not actually evaluate any template; we just carry them over. The user will provide actual values when running the Strands CLI (via --var or default in inputs.values).

**Example Mapping Walkthrough:**

To illustrate, consider a concrete (simplified) example input and output:

**ARK Input:** (Given in ark-spec.yaml)

apiVersion: ark.mckinsey.com/v1alpha1
kind: Model
metadata:
  name: default
spec:
  type: openai
  model:
    value: gpt-4o-mini
  config:
    openai:
      apiKey:
        valueFrom:
          secretKeyRef:
            name: openai-key
            key: token

---
apiVersion: ark.mckinsey.com/v1alpha1
kind: Agent
metadata:
  name: technical-agent
spec:
  prompt: |
    You are a technical support agent.
    Current environment: {{.environment}}
  modelRef:
    name: default
  tools:
    - type: built-in
      name: web-search
    - type: custom
      name: get-logs
  parameters:
    - name: environment
      valueFrom:
        configMapKeyRef:
          name: settings
          key: env

---
apiVersion: ark.mckinsey.com/v1alpha1
kind: Agent
metadata:
  name: billing-agent
spec:
  prompt: "You are a billing support agent."
  modelRef:
    name: default

---
apiVersion: ark.mckinsey.com/v1alpha1
kind: Team
metadata:
  name: support-team
spec:
  strategy: selector
  members:
    - name: technical-agent
      type: Agent
    - name: billing-agent
      type: Agent
  selector:
    agent: technical-agent
    selectorPrompt: "Decide whether to handle this query or pass to billing."

---
apiVersion: ark.mckinsey.com/v1alpha1
kind: Query
metadata:
  name: example-query
spec:
  input: "My internet bill is wrong. Can you help me?"
  targets:
    - type: team
      name: support-team

**Strands Output:** (Generated in support-team-workflow.yaml)

version: 0
name: support-team-workflow
description: Workflow translated from ARK 'support-team' and query 'example-query'
runtime:
  provider: openai
  model_id: gpt-4o-mini
agents:
  technical-agent:
    prompt: |
      You are a technical support agent.
      Current environment: {{ environment }}
    model_id: gpt-4o-mini        # from ARK modelRef 'default' (OpenAI GPT-4 mini)
    # Note: Uses provider 'openai'. Expect OPENAI_API_KEY in env.
  billing-agent:
    prompt: "You are a billing support agent."
    model_id: gpt-4o-mini        # uses same model as default
support-team-orchestrator:
    prompt: "{{ query }}"       # (generated agent)
    # This agent will simply take the user query and decide who answers.
    model_id: gpt-4o-mini
tools:
  python:
    - web-search      # ARK built-in (no direct Strands equivalent; requires custom tool implementation or removal)
    - get-logs        # ARK custom tool (user must implement as a Strands Python tool)
pattern:
  type: orchestrator_workers
  config:
    orchestrator: 
      agent: technical-agent
      input: "{{ query }}"    # feed user query to the selector agent
    workers:
      - billing-agent
      # Note: 'technical-agent' can also answer directly if it decides to.
    # We can't fully encode the decision logic in static YAML. The orchestrator agent will respond,
    # but auto-invoking a chosen worker is not automated here. This pattern implies technical-agent (orchestrator)
    # might delegate tasks to billing-agent dynamically.
inputs:
  values:
    query: "My internet bill is wrong. Can you help me?"
    environment: ""   # was from ConfigMap 'settings.env'; must be provided (e.g. "prod" or "dev")

Several things to note in this output: - We took the single Model and applied its provider/model to runtime and model overrides. - Both agents appear with prompts intact, adjusted template {{.environment}} -> {{ environment }}. - We introduced a support-team-orchestrator agent (Alternatively, we could reuse technical-agent as orchestrator since ARK specified that as selector agent. Actually, it’s probably better to use technical-agent itself as orchestrator to avoid duplication. The above output may be slightly off in having a separate orchestrator agent; a cleaner approach: just use technical-agent in orchestrator role. We would then list billing-agent as worker, and orchestrator agent as technical-agent. We’d remove support-team-orchestrator entirely. This example shows one approach, but to refine: use existing agent as orchestrator rather than making a new one.) - Tools section includes both tools that technical-agent had. web-search note indicates the translator flagged it as not implemented in Strands by default. - Pattern type orchestrator_workers is used to reflect a selector pattern. However, Strands orchestrator pattern likely requires a structure for tasks or something. We showed an interpretation: orchestrator gets the query, and there's a list of workers. In a real orchestrator pattern, the orchestrator agent’s output might be used to decide which worker to run. Strands might not handle that automatically without code – this is a limitation we highlight. - The query input is stored in an input variable query, with the actual user question as default. - environment input is left empty with a comment that user must fill it (came from ConfigMap). - description at top is optional but added for context.

This example demonstrates the translator’s processing of each part. In practice, the actual output YAML formatting would be carefully validated and tested.

The PRD expects the developer to implement logic for all these transformations, ensuring that each ARK concept is appropriately represented in Strands format or flagged if not possible.

### Validation Expectations

We want the translation process to be **reliable** – meaning it either produces a correct output spec or clearly explains why it couldn’t. To that end, validation plays a big role at two stages: **pre-validation of input** and **post-validation of output**.

**Input Validation (Detailed):**

The translator should use a combination of structural checks and known constraints from ARK’s CRD guidelines:

Validate that each document’s apiVersion starts with ark.mckinsey.com/ (to ensure it’s an ARK resource, not some unrelated Kubernetes manifest).

Ensure the kind is one of the supported ones listed above. If not, produce an error like *"Unsupported resource kind 'Service' in input – only ARK resource kinds (Agent, Team, Query, Model, Tool, etc.) are allowed."*.

For required fields within each spec, cross-check as per ARK’s spec:

ARK doesn’t publish an official JSON schema externally, but the design guide and CRD definitions imply required fields: *Team members and strategy are required*, *Agent prompt likely required*, etc. The translator should catch glaring omissions (missing prompt, missing members, etc.).

Also validate types of fields if easily done: *E.g.* if maxTurns is present, ensure it’s an integer; if timeout is present in Query, ensure it’s a string with a duration format (this might be too detailed – could skip).

Cross-resource consistency checks:

Unknown references: The translator can build a set of names for each resource type from the input. Then:

For each Agent’s modelRef (if any): ensure a Model by that name exists (unless the name is “default” which ARK always has – if none given, assume default is a known provider’s default model).

For each Agent’s tool of type custom: ensure a Tool resource by that name exists *if* that name likely corresponds to a Tool CRD (though ARK uses tool CRDs to define MCP tools typically, not necessarily for every custom tool by name – some custom tools might be defined entirely in code or via MCP servers).

If a tool name matches one of ARK’s sample tools or has no CRD, we can’t truly validate existence. Might skip strict validation here but warn if Tool CRDs are provided but not used or vice versa.

For each Team’s member: ensure an Agent or Team by that name exists depending on type. If a member type is "Agent" but no such Agent spec is found, error. If type "Team" but that team spec not found, error (or warn if perhaps the user didn’t include sub-team).

For each Query’s target: ensure target exists (agent or team or model or tool). If target type is model and no Model by that name found, warn (we can still create stub agent if needed). If target type is tool and no Tool spec found, that’s fine (tool could be built-in or external; we can’t fully know, but we know Strands will need an implementation).

Duplicates: If two resources have the same metadata.name and kind, that’s probably an error (e.g., two Agent definitions both named "assistant"). The translator should at least warn or pick one. It’s unlikely in one file, but possible if user concatenated files. We should handle gracefully by either merging info or erroring. Safer to error: *"Duplicate Agent name 'assistant' in input; each agent must be defined only once."*.

If any input validation fails, **no output file should be generated** (to avoid confusion). The CLI should return an error code (likely 2 for usage errors, as per Strands convention, or some code indicating invalid input).

The error messages should be clear. Use the resource name in messages, not just a generic “validation failed”. For example:

Bad: "Validation error in input".

Good: "Validation error: Team 'support-team' has no members defined." or "Agent 'X': unrecognized field 'model' (did you mean 'modelRef'?)."

We might incorporate ARK’s own validation ideas (from CRD annotations) to give specific hints, but replicating full ARK validation is out of scope. We focus on critical aspects that affect translation.

**Output Validation (Detailed):**

After producing the output spec object (before writing to file or stdout), run it through Strands’ JSON schema validator. The Strands schema (draft 2020-12 JSON Schema) will catch most structural errors. The translator can programmatically call the validation (e.g., via schema.validator.validate_spec(data)).

If the schema returns errors, format them for the user. The schema errors typically include JSON Pointers to fields and a message. For instance, an error might look like: $.pattern.config.steps[1].agent: string [not provided] – field required. We should convert that into a friendlier form if possible:

e.g. "Output validation error: In pattern.config.steps[1], required field 'agent' is missing."

The translator developer can leverage the existing strands validate --format json output for hints: it provides errors with pointers and reasons. Perhaps reuse that code or logic to display similar.

In many cases, if the translator logic is correct, we won’t hit schema errors. But one scenario: If ARK spec had something that translator doesn’t know how to map, we might have left a placeholder or omitted something, causing schema invalidity. It’s better to catch that than to write a broken file.

If output validation fails due to an **unsupported ARK feature** mapping (like we attempted something but schema didn’t like it), then it’s essentially our limitation. We should inform the user that the translation couldn’t be completed due to this feature:

For example, if we try to map round-robin by writing a pseudo-structure that doesn’t conform, the schema fails. Instead of exposing raw schema jargon, better to say: *"Cannot translate 'round-robin' team into a valid Strands workflow. Please consider rewriting this scenario manually."* and abort.

In other words, we may decide to pre-empt certain known unsupported constructs by not outputting them at all (thus failing input validation or giving a specific message), rather than generating an invalid YAML.

Once the output spec passes schema validation, we know it has:

All required fields present (version, name, runtime.provider, agents, pattern.*).

Correct data types (e.g., version as integer, not string; max_tokens if any as int, etc. The schema enforces those).

Allowed values for enums (e.g., runtime.provider must be one of the supported providers, pattern.type one of known types, etc.). If we accidentally set a provider to something not in schema, we’d catch it here.

The translator should also consider **Strands capability validation**: The Strands CLI has an additional concept of capability checks (e.g., if a pattern is supported by current version, if a tool is allowed, etc.). These are not part of the JSON schema but rather runtime checks (pydantic model validation or custom logic). For example, certain pattern combinations or tool usage might be flagged as “capability_unsupported”. We likely can’t easily run the full pydantic validation that Strands CLI does without invoking internal APIs. However, we can approximate:

Tools: Strands might have an allowlist of safe tools. If we include a tool that’s not recognized, Strands might warn or error at runtime (“Tool not found” or “Unsupported tool”). We can pre-check tool names against the list of auto-discovered tools if accessible via code. But since the user might add their own tools, we shouldn’t block unknown tools. We just warn for ones we know are problematic (like web-search not existing).

Patterns: If we try to use a pattern that Strands CLI version doesn’t support, that’s an issue. The patterns we plan to use (chain, workflow, parallel, routing, orchestrator_workers, etc.) are all listed as supported in Strands README. So that should be fine. If we attempted something exotic not in that list, the schema would likely catch it anyway (enum).

We might not replicate the entire “capability_supported” logic, but ensure no glaring unsupported combos (like an orchestrator pattern with missing orchestrator agent will fail logically – but schema would catch missing orchestrator field).

If output validation passes, the translator writes the YAML. We may still include some **non-fatal warnings** in the output as comments or on stderr for things that schema cannot capture but a developer should know:

e.g., “Workflow uses orchestrator pattern for selector strategy – this will run the orchestrator agent but *will not automatically call the other agent*. You may need to manually route the output.” This is a nuance that goes beyond schema.

“Tool X included but not found in Strands built-ins. Ensure a plugin is available or remove it.”

Such warnings should be emitted after the file is written (or as comments in the file) so they are not missed. Ideally, any critical limitation is also documented in the file for whoever opens it later.

In summary, the translator will be considered successful if, for a given valid ARK input, it produces a YAML that passes strands validate with no errors and performs the intended behavior when run. Any deviations (due to unsupported features) should be clearly called out. Both stages of validation ensure a robust tool that doesn’t silently produce wrong configurations.

## Edge Cases and Limitations

Despite aiming to support the full ARK spec, there are several edge cases and limitations to note:

**Round-Robin Team Strategy:** As discussed, ARK’s round-robin (where agents take turns multiple times) has no straightforward representation in Strands. The translator **will not fully implement looping dialogues**. It may output a single cycle of the round-robin (each member once) or just error/warn that round-robin is not supported. The user would then need to manually create a loop or use the Strands Graph pattern with conditional looping. We choose to explicitly document this limitation: *“Round-robin team strategy is not automatically converted; only a single pass is included. Multi-turn exchanges require manual workflow extension.”*

**Nested Teams:** If an ARK Team has a member of type Team (nested teams), our translator does not deeply nest patterns (this could become very complex). We do not plan to handle multi-level team references in the first release. If encountered:

Option 1: Flatten by inlining the sub-team’s members into the main team pattern (could be messy and lose the sub-team’s strategy).

Option 2: Error out: *“Nested team 'teamB' referenced in team 'teamA'. Nested teams are not supported by translate – please convert 'teamB' to an independent workflow or integrate its logic manually.”*

We likely go with producing an error or a very basic flattening with warning. Given ARK’s design, nested teams might be rare (teams usually composed of agents, not other teams, but we should be cautious).

**Tool Implementations:** Any tool listed in the Strands tools section that is not actually available will cause a runtime error if used. The translator cannot provide the implementation. Notable cases:

ARK built-in web-search: Strands CLI doesn’t have this. The output will include web-search in tools (since ARK agent might call it), but if the user runs the workflow, when the agent tries to use web-search, the Strands registry will not find it, likely causing an error. We will clearly flag this in the output (comment) and maybe console warning. The user has to either remove that tool or implement a custom web-search tool (maybe wrapping a real web search API) to use that workflow.

ARK get-logs (custom) or any MCP tool: similarly, the translator can’t magically make it work. It surfaces the tool name. If the ARK spec included details (like which MCP server and toolName), we might pass that in a comment, but Strands has no concept of contacting an ARK MCP server. The user would need to replicate that tool’s functionality (perhaps by writing a Python tool that calls the needed service).

**Limitation:** The translator does not convert the internal logic of tools. For example, if ARK Tool spec defined an HTTP request template, we do not convert that into a Strands http_request step. Tools remain as black-box references. A potential improvement (not in initial scope) could be: if an ARK Tool is of type HTTP and simply calls an API, we could map that to Strands built-in http_request tool usage. However, ARK likely handles tools differently (via either MCP or built-ins), so we skip this complexity for now.

**Model Availability:** If ARK uses a provider or model that Strands CLI doesn’t support or the user doesn’t have access to, the output may not run. For instance, ARK might have a model type “huggingface” or something not in Strands schema (which currently allows openai, bedrock, ollama, etc.). The translator might include that in runtime.provider which would fail schema or capability check if not recognized. We should map known ones and if an unknown appears, either default to a generic or warn:

e.g. ARK model type "huggingface" – Strands might not have first-class support (unless via Ollama for local maybe). We could set provider to openai as a placeholder which is not correct. Better to warn: *“Model provider 'huggingface' from ARK is not directly supported in Strands. Using OpenAI as default – please adjust manually (e.g. use Ollama for local models).”*

Or we output provider: openai, and comment that the user should change it if needed.

In any case, the limitation is: some model configs might not translate one-to-one. Azure OpenAI might require user to set runtime.host and environment variables for API version – Strands schema does allow a host field in runtime for custom endpoints. Perhaps if ARK Model config contains a baseUrl for Azure, we should populate runtime.host with that. We should at least include it:

e.g., for Azure, output runtime.provider: openai, runtime.host: <azure base url>. And note user must have the Azure key in OPENAI_API_KEY and maybe a custom header for deployment name. ARK’s model config might include apiVersion and headers – too detailed to fully map. We mention it in a comment if possible.

Summing up: **The translator might not cover all model configuration nuances** (like custom headers, timeouts). It ensures the provider and model_id are set to get the right model, but extra config may be lost.

**Query “messages” not supported:** As noted, multi-message conversations in a single Query aren’t translated into a multi-step flow. The limitation is that this command doesn’t generate a memory of previous messages. If an ARK Query with type messages is given, the translator will either:

Convert it to a single prompt by concatenation (with roles annotated perhaps),

Or use only the last user message as the main prompt, effectively ignoring the prior context (not ideal, but mention if we do this).

Possibly output a warning: *“Multi-turn query with messages has been flattened to a single input for translation. Context from earlier messages may not be fully preserved.”*

The user would then know to refine the workflow to handle multi-turn if needed (maybe by splitting into multiple steps manually).

**Memory & Session**: As explained, ARK’s Memory CRD and Query.session are ignored. This means any persistence of conversation or state across queries is lost in translation. If the ARK scenario relied on a memory store (e.g., a shared memory between agents or queries), the Strands translation won’t reflect that. Strands can keep state *within* one workflow execution (via variables or step references), but not across separate runs unless using its session resume. We assume each Query is standalone. We should caution: *“ARK memory resources (e.g., cluster-memory) are not applicable – the translated workflow won’t have persistent memory across runs.”*

**ExecutionEngine differences:** ARK’s ExecutionEngine CRD (for LangChain or other execution frameworks) is not considered. Our translation runs everything through Strands’ built-in execution engine (the LLM calls via provider APIs). If the ARK Agent was meant to run in a special way (like via a LangChain agent executor), that nuance is lost – we simply run the prompt through the model. This could change behavior (LangChain might do different prompting). It’s out of scope to replicate execution engines. A note can be added if an agent had an executionEngine specified: *“Ignoring custom execution engine for agent X; using default LLM calls.”*

**Large or Complex Specs:** If an ARK spec is very large (say dozens of agents, extremely large prompts), the translator might output a very large YAML. This is fine, but we should ensure formatting is not corrupted (especially with large prompts or JSON schemas inside prompts). We rely on PyYAML or similar to handle large content safely. The main risk is performance (which should still be fine for dozens of agents). No special limitation here beyond typical memory usage.

**Maintaining Comments from ARK:** YAML comments in the ARK input file will likely be dropped during parse and re-dump (unless we implement a comment-preserving parser). Typically, that’s acceptable – but if the ARK spec had important instructions in comments, they’ll be lost. That’s an understood limitation; we don’t attempt to preserve user comments from input. We will, however, **add our own comments** in the output for important notes as described.

**Partial Inputs (only Agents, only Model, etc.):** What if a user runs translate on a single Agent CRD without a Team or Query?

The translator can still produce a valid Strands spec containing that agent and perhaps a trivial pattern. But what should the workflow do? We have an agent but no defined task for it.

Options:

We could default to a **Chain pattern with one step** that simply calls this agent with an input. We’d then definitely require an inputs: for that input (since nothing else provides it). This effectively makes a minimal workflow that just queries the agent once. This might be reasonable as a placeholder (like a test harness for the agent).

Or we output just the agent and no pattern – but that would fail schema (pattern is required).

Or possibly treat that as a library spec (though Strands doesn’t have a concept of “just define an agent without executing it”). Unlikely needed, better to provide a runnable workflow.

We lean towards outputting a simple chain if only an Agent is provided:

pattern:
  type: chain
  config:
    steps:
      - agent: <agent-name>
        input: "{{ user_input }}"
inputs:
  required:
    user_input: "string"

This way, running the workflow will prompt the agent with whatever --var user_input="..." the user provides. It’s essentially a one-shot query to that agent.

Document this: *“Note: Only an Agent was provided, so the translated workflow will just query that agent once using the variable** **user_input**.”*

If multiple Agents provided and no Team/Query ties them, we face a similar situation: we have several agents defined but no overall pattern. Perhaps the user intended to just convert agent definitions for reference, not to run them. Strands requires a pattern to run. We have to either pick one agent to run or create a dummy structure:

We could create a parallel or chain that invokes each agent sequentially (just to have something) – but that assumption could be wrong (those agents might be unrelated).

Alternatively, warn that without a Query or Team context, we can’t produce a meaningful workflow involving all agents. We might choose one (the first?) arbitrarily to demonstrate usage.

This is an edge case; likely users will provide either a Team or Query if they want a runnable flow. If not, maybe they just wanted to see how an agent spec looks in Strands – in that case, we could output all agents and a dummy chain calling the first one. We’ll clarify this in documentation or decide to require at least something linking agents.

For now, plan: if multiple unlinked agents, just create a chain for the first agent and print a comment that other agents were translated but not used in the pattern. We will still include the other agents in agents: section (so they are available if user wants to manually craft something).

**Error Handling:** As a rule, **no silent failures**. Any aspect the translator cannot handle will either:

prevent output (with an error message),

or result in an output with explicit warnings.

We do not want a scenario where the user assumes everything translated perfectly but in fact, something was skipped without notice. Transparency is key given the critical nature of workflow correctness.

**Testing Edge Conditions:** The implementation team should test the translator on various scenarios to ensure these edge cases are handled:

Single agent, no query.

Team without agent specs (should error).

Query referencing missing agent (error).

Tool references with and without Tool CRD present.

Unknown strategy or future ARK version (should at least warn).

Extremely long prompts or unusual characters (ensure YAML dump handles them properly, e.g., quotes vs literal blocks).

Agents with identical names in different namespaces (ARK could scope by namespace – our translator currently doesn’t consider K8s namespace, only name. We assume either names are unique globally in input or if not, user should supply one at a time. We’ll mention that if multiple resources have same name in different namespaces, the translator might conflict them, and it’s best to translate them separately or rename).

**Summary of Limitations to Communicate:**

Not all dynamic multi-turn behaviors (loops, round-robin cycles, dynamic agent selection beyond one step) can be encoded in static Strands YAML. The translator provides a *single-pass approximation*.

Tools and external integrations require manual effort after translation (the command does not create code for tools or connect to external services).

Some ARK features (memory persistence, external controllers) are out of scope in Strands – they will be omitted.

The translator is built against ARK v1alpha1. If ARK’s CRDs evolve (new fields, removed fields), the translator might need updates. Using it on a significantly different version could yield errors or incomplete mappings (and the tool should detect mismatched versions in apiVersion).

Translation is one-time static. If the ARK spec is updated, you need to run the translator again; there is no continuous sync. And once a workflow is translated, it can diverge – it’s not guaranteed that changes in ARK spec will merge nicely into an edited Strands spec. (This is just to set expectation that this is a migration aid, not a bi-directional sync tool.)

By recognizing these edges and limitations, developers and users can better understand the output and adjust accordingly. The PRD includes them so engineering can implement checks/warnings for each, and documentation can be written to manage user expectations.

## Open Questions

Finally, there are a few open questions and decisions to be made during implementation:

**How to handle multiple isolated Agents in one input?** If the input file contains several Agent CRDs without a Team or Query tying them together, what should the output do? Possible approaches:

Translate each agent into its own minimal workflow (but our CLI command currently outputs a single file for the whole input).

Or output one workflow containing all agents defined, but then we need a pattern. Do we arbitrarily choose one agent to actually run in the pattern?

*Proposal:* If multiple agents and no higher-level spec, perhaps require the user to translate one agent at a time or supply a team. Alternatively, we could add an option like --each-agent to generate one workflow per agent. This complicates the interface though. This remains an open design choice.

**Nested Teams and Orchestrator Implementation:** Should we attempt to flatten nested teams or simply error out? Flattening could be done recursively, but might lead to very complex patterns. Given time constraints, likely we will not implement recursion fully. So erroring with an explanation is safer.

For orchestrator (selector) teams – do we use the Strands orchestrator pattern even though Strands may not automatically invoke the next agent? Or would it be better to simply convert a selector team to a **Routing** pattern (where an agent chooses a route from predefined ones)? Strands has a routing pattern where you define conditions and target agents for those conditions. That’s a different approach: if we could interpret the selector agent’s decision as classification, we could map to routing (with conditions that approximate what the AI might decide). But ARK’s selector is AI-driven, not rule-based, so routing pattern doesn’t truly capture it.

We will likely stick to orchestrator_workers pattern (to at least reflect that structure), but it’s an open question how to handle the actual invocation of the chosen agent. We might conclude that full automation isn’t possible and the user has to implement logic or run the orchestrator agent and then manually resume with the chosen agent’s step (which Strands doesn’t natively support mid-run). This might just be a documented limitation.

**Output Workflow Name Convention:** If both a Team and a Query are provided, which name do we use for the workflow? The Query is like a specific instance of using the Team. Perhaps use the Query’s name, since it’s likely describing the scenario (“example-query”). But if the Query is generic (just named “test-query”) and the team is “customer-support-team”, maybe the team name is more descriptive for the workflow’s purpose.

Potential approach: if one Query is present, use Query name. If no Query but one Team, use Team name. If multiple queries (that would be unusual to have in one file), maybe we don’t support multiple queries at once (user should translate them separately).

If neither (only models/agents), let user specify --name or default to something like “translated-workflow”.

This is a minor decision but affects user experience of naming.

**Mapping ARK “parallel” patterns if they exist:** Does ARK have an equivalent of Strands “parallel” or “graph” outside of Teams? They have Teams with graph strategy (which is basically parallel tasks with dependencies) and perhaps they rely on Query with multiple targets for parallelism. Strands has distinct “parallel” and “workflow” patterns. We should double-check if ARK Teams ever do pure parallel (all agents at once without specified dependencies). If ARK had a “all” or if you simply omit edges and strategy, unclear. Probably not – ARK would use multiple query targets for concurrency rather than a team, except teams might have graph where some tasks have no dependencies meaning they start concurrently.

No direct open question here, just ensure translator can output a Parallel pattern when needed (which is mostly for Query with multiple targets scenario).

**Validation of ARK input using ARK’s schema definitions:** Should we attempt to use ARK’s OpenAPI schemas (from the CRD YAML) to validate? The ARK CRD YAML (like we saw for Team) is embedded in their codebase. We could theoretically compile a mini validator for ARK fields, but that’s heavy and probably not worth it (given ARK is evolving and our own checks suffice for main fields). So we likely won’t use a formal schema validation for ARK, just handcrafted checks. We note this as a design decision (no need for external dependencies or schema files for ARK).

Instead, rely on robust error handling if something is missing when we try to access it (e.g. if our code expects spec.strategy and it’s not there, catch that and report).

**Choice of Strands pattern when both Team and Query exist:** We touched on this – if Query exists, do we always use Parallel (because Query could target multiple)? Or do we embed team logic and essentially ignore the fact it was a query (i.e. treat it as a scenario and use the team’s pattern)? Possibly:

If Query has a single target which is a Team, maybe we prefer using the Team’s pattern rather than a parallel with one branch. That seems logical: just output the team’s workflow (like sequential, etc.) and include the Query’s input as starting data.

If Query has multiple targets including a Team and maybe an extra agent, then we must go parallel because the query is truly fan-out.

So translator needs to decide pattern type based on number of targets:

If targets count > 1 -> use parallel.

If exactly 1 target and it’s a Team -> just do that team’s pattern (no parallel needed).

If exactly 1 target and it’s an Agent -> could do chain of one (or even simpler pattern possibly chain anyway).

This logic seems solid, we'll proceed with that unless there's concern.

**Testing with actual ARK examples:** It would be very helpful to test the translator on real ARK examples from documentation (e.g., the ARK Quickstart or samples provided in their repo). We should verify that, for instance, the Agents and Teams in ARK’s sample yield sensible Strands output. This is more a development task than a spec question, but we might reach out to ARK sample YAMLs to validate our assumptions about field usage. (For instance, confirming if type: Agent is indeed what members use, if ARK uses any namespacing in references that we need to strip, etc.)

**Name collisions or reserved words:** Strands might have reserved words for variables (though unlikely beyond JSON schema keywords). If an ARK parameter is named "steps" or "last_response" or something that conflicts with Strands internal templates, is that an issue? For example, Strands uses {{ last_response }} as a special alias for previous step output. If ARK had a parameter named last_response, theoretically it could shadow that. But since we control the context, we can allow it (it would just be a normal variable in Jinja).

We should just be mindful to not inadvertently use a protected name in the YAML keys. Agent names like "default" or "null" etc. could maybe confuse YAML, but as strings they are fine.

Unusual characters in names (like ARK allows period in agent name? Actually ARK might allow dot in name since K8s does, like "agent.v1" – not sure. Strands agent ID pattern allows dot and colon etc. It’s fairly broad, so likely okay).

So not a major issue, but if any weird thing arises, we’ll handle case by case.

**Optional: two-phase translation?** Should the translator perhaps output intermediate info or require certain inputs? For instance, if a Model CRD isn’t given and it’s not obvious which provider to use, one could imagine an interactive mode or option --provider openai to manually specify. But this complicates usage – we prefer automation. So probably not needed. Just an open thought: e.g., ARK model “gpt-4o” clearly openai, “claude” clearly bedrock or anthropic. If ambiguous, we’ll guess openai by default since it’s common.

In conclusion, these open questions will be resolved during design and implementation, but they do not detract from the primary goals of the translate command. The development team should use these as guidance to make implementation decisions and possibly update documentation accordingly. The PRD covers known unknowns so that there are no surprises when coding and testing the feature.

Agent

Query

spec-generator-agent.yaml

ark.mckinsey.com_teams.yaml

Models

CRD Design Guidelines

strands-workflow.schema.json

TOOL_DEVELOPMENT.md

index.ts

README.md

cli.md
