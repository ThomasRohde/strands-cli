Mimicking Claude Code Skills with Progressive Loading in Strands CLI
Overview of Claude Code Skills and Progressive Loading

Claude Code’s “Agent Skills” system lets an AI dynamically load task-specific instructions from skill files on demand rather than front-loading all content at once. In Claude Code, skills are essentially folders (with a SKILL.md and supporting files) describing specialized capabilities (e.g. a PDF processing toolkit). At runtime, Claude’s system prompt only includes a brief listing of available skills (name + description), along with instructions to invoke a skill tool if relevant. The full skill content (detailed instructions/scripts) is only injected when the model decides to use that skill – a technique often called progressive disclosure
github.com
github.com
. This means:

Initially, Claude sees a list of skill names and what they do, but not the full details.

If the user’s request matches a skill’s purpose, the model will invoke the skill (Claude uses a special Skill("skill_name") call).

The environment intercepts that call and then loads the skill’s detailed instructions into Claude’s context, allowing it to proceed with the task
github.com
.

In short, Claude’s skills function like modular prompt expansions: “premade prompt parts with progressive disclosure” as one commenter put it
reddit.com
. This yields efficiency (only load what’s needed) and flexibility (the agent autonomously chooses the skill).

Existing Skill Support in Strands CLI

The good news is that Strands CLI was already designed with a skills mechanism in mind. The workflow schema allows a top-level skills array where each skill has an id, a filesystem path to its folder, and optional metadata
GitHub
GitHub
. The schema description makes the intention clear: “Skills are injected into agent system prompts as metadata (id/path). Executable skill support is planned for future versions.”
GitHub
. In other words, Strands knows about skill bundles, but as of now it only injects their metadata (identifiers, etc.) into the prompt, without actually running skill code.

Indeed, the current Strands CLI code already injects a list of skills into the system prompt for each agent. In strands_adapter.py, the build_system_prompt() function gathers all spec.skills and appends a section listing each skill’s ID, path, and description under an “Available Skills” heading
GitHub
. For example, if your workflow spec lists a skill with id: pdf and a description, the agent’s system prompt will include something like:

# Available Skills

- **pdf** (path: `path/to/pdf-skill`): Comprehensive PDF manipulation toolkit...
- **xlsx** (path: `path/to/xlsx-skill`): Comprehensive spreadsheet creation and editing...


(This is analogous to Claude Code’s <available_skills> XML block, which lists skill names and descriptions
github.com
.)

However, currently the Strands agent is only given the skill metadata, not the skill’s full instructions or code. There is also a preload_metadata flag in the schema to optionally preload skill details at startup
GitHub
, but by default it’s false – implying an on-demand loading approach. This aligns with our goal: mimic Claude’s progressive loading, where we do not stuff the entire skill content into the initial prompt, but load it when needed.

Designing Progressive Skill Loading in Strands CLI

To implement Claude-like skills in Strands CLI, we need a mechanism for the agent to dynamically request and receive skill content during execution, without manual intervention by the spec author. The high-level design has several pieces:

Skill Metadata in System Prompt (Already in Place): Continue injecting a concise list of available skills into the agent’s system prompt as is done now
GitHub
. This gives the model awareness of skill names and a one-line description of each skill’s capability, just like Claude’s available_skills list. It ensures the model can consider relevant skills for a task. (If not already done, we should also auto-populate each skill’s description by reading a summary from the skill’s folder – e.g. the first lines of a README or a SKILL.md file – so the spec author doesn’t have to duplicate it in the YAML.)

Instruction to Use Skills (System Prompt Enhancement): We need to explicitly instruct the agent how to invoke a skill. Claude Code includes a special <skills_instructions> section with guidelines
github.com
. We should mimic this by adding a short directive in the system prompt explaining when and how to use skills. For example:

“When the user’s request might be solved more effectively by an available skill, you should invoke that skill. To use a skill, call the Skill tool with the skill’s name (e.g. Skill("pdf")). The skill’s detailed instructions will then be loaded for you. Only use skills from the Available Skills list, and do not invoke a skill that’s already been loaded.”

This mirrors Claude’s instructions (tailored to our environment) and guides the model to trigger skill loading via a special call
github.com
github.com
. The spec author doesn’t need to write these instructions – Strands can inject them automatically alongside the skill list in the system prompt.

Special Tool or Trigger for Skill Invocation: We must decide how the agent’s “skill call” is represented and intercepted. Claude uses a built-in Skill("name") function call (Anthropic’s backend recognizes this as a tool invocation)
github.com
. In Strands, we can achieve something similar in two ways:

Option A: Define a Skill Loader Tool in Strands. Since Strands SDK supports tools (Python functions, HTTP calls, etc.), we could implement a Python tool function (e.g. strands_tools.skill_loader.load_skill) that takes a skill ID and returns the skill’s content. We’d then register this tool for the agent. The system prompt instructions would tell the model to call this tool (e.g. Skill("pdf")) when needed. Under the hood, when the model outputs the tool call, the Strands agent can capture it, execute our skill_loader function (which reads the skill’s SKILL.md or README), and then return the content to the model as a tool result. Strands’ schema already hints at such a pattern: tools are expected to return a result object with content
GitHub
, so the agent likely supports a ReACT-style loop where it outputs a tool request and then consumes the tool’s output. By adding our Skill tool to the agent, we leverage the existing mechanism for tool use. In effect, the skill becomes a specialized tool that returns a block of instructions/code from the skill folder.

Option B: Parse Skill Invocation from Model Output. If integrating a formal tool is complex or if we want model-agnostic behavior, we could implement a simpler loop: whenever the model’s response contains a special marker indicating a skill call, the CLI intercepts it and loads the content. For example, we instruct the model to output a line like <<USE_SKILL:pdf>> (or reuse the Skill("name") syntax) when it wants to load a skill. Our execution loop (invoke_agent_with_retry or similar) can detect this token in the assistant’s partial output instead of finalizing the response. It would then fetch the skill data from disk and append it to the conversation history (e.g. as a new system or assistant message containing the skill’s content), and allow the model to continue. This approach requires manually managing the conversation state – essentially pausing the agent’s reply, inserting new context, and resuming the generation. It’s a bit more involved but doesn’t rely on the underlying Strands SDK’s tool interface.

Recommendation: Utilize Option A (Skill as a Tool) if possible, as it fits cleanly with Strands’ architecture. We can create a SkillTool that reads files (which is straightforward in Python) and add it to the agent’s tool list programmatically whenever spec.skills are present. This way the model’s invocation and the content injection happen through the standard tool-use flow. (Notably, Anthropic models are already familiar with the Skill("name") pattern as a tool
github.com
, and other models can learn it from our prompt instructions.)

Loading and Injecting Skill Content: When a skill is invoked, the system needs to load the skill’s detailed content from the filesystem and make it part of the model’s context. Concretely, this means reading the skill directory (likely the SKILL.md or README.md as the main instructions). We should define what content to inject:

At minimum, include the skill’s instructions (the step-by-step guidance in SKILL.md).

Possibly also include any essential reference info or examples in the skill folder. If the skill has large assets or code files, we might not dump them blindly; instead, provide a path or summary unless the model specifically requests more (to avoid context bloat).

The injection can be formatted clearly (e.g. a heading like “Loaded Skill: PDF” followed by the skill’s content in Markdown) so the model knows this is authoritative information to follow.

With Option A (tool), the tool’s return value (a text string) would be fed into the model as the result of the tool call. The Anthropic Claude format for tool responses encloses them in a special <command-result> or similar block, but the Strands SDK might abstract that. The key is that the model will “see” the skill content as if it just received information, and it will then continue the conversation incorporating those instructions. If using Option B (manual intercept), we programmatically insert a new system/assistant message containing the content and resume generation.

Resume Normal Agent Response: After the skill content is loaded into context, the agent can now apply those instructions to the user’s query. In Claude Code, once the skill’s prompt is expanded, Claude proceeds to produce the final answer using the newly-provided guidance
github.com
. In Strands, our loop should then let the model continue its reasoning/writing. We should also mark that skill as “loaded” (perhaps in a list of active skills) to avoid reloading it again if the model tries (the prompt instruction already says not to invoke an already running skill
github.com
, but it’s good to have a safeguard).

Throughout this process, the spec author doesn’t need to do anything special – they just list the skill in the YAML (with id and path, etc.), and write their agent prompts normally. The agent will automatically leverage the skill if appropriate. From the spec writer’s perspective, the agent just “magically” becomes more capable on certain tasks.

Functional Design Summary

To summarize the functional plan:

Initialization: During workflow loading, for each skill in spec.skills, read its metadata:

Ensure Skill.description is populated (either from spec or by reading the skill’s docs if description is missing and preload_metadata:true).

Prepare a Skill Loader tool (if using the tool approach) and attach it to the agent’s allowed tools. This could be done by injecting a Python tool callable (e.g., skill_loader(skill_id)) into spec.tools.python or by using a native mechanism if Strands SDK provides one.

System Prompt Construction: Extend build_system_prompt() to include a “How to use skills” section (mirroring Claude’s instructions) before the “Available Skills” list. Then list each skill (name, path, short description) as is done now
GitHub
. Also include any runtime context banner as usual. This ensures the model knows what skills exist and how to invoke them properly.

Agent Execution Loop: When executing an agent’s step, allow for multiple turns:

Initial Query: Provide the user’s prompt (and any prior context) to the agent (LLM) with the system prompt containing skill info.

Skill Invocation Check: Inspect the model’s output. If the model’s response indicates a skill invocation (e.g. it outputs Skill("xyz") or calls the skill_loader tool):

Log or print a message like “Agent requests skill XYZ – loading skill content.”

Load the skill’s content from the filesystem (read the Markdown and possibly truncate or format it if very large).

Insert the content into the conversation. For example, if using tools, the content might come back as the tool’s result which the model will incorporate. If manual, you might add something like an assistant message: “(Skill xyz loaded:)* [content]”* or a system message with the content.

Update the system prompt or context: Depending on implementation, you might update the agent’s system prompt to include the skill details (though that may require reconstructing the Agent), or simpler, just treat the loaded content as the latest assistant message that the agent itself “sees” as if it had been provided. The approach should ensure the content is in the model’s context window for the next token generation.

Resume Answering: Now let the model continue. It should now incorporate the skill’s instructions and proceed to solve the user’s request. The final output can then be returned to the user as the agent’s answer.

Post-Execution: Consider caching loaded skills if the same agent might reuse them in a long conversation. Also respect the preload_metadata flag: if a spec explicitly set preload_metadata: true for a skill, you could opt to inject its full content from the start (i.e. in the initial system prompt) – though this negates progressive loading for that skill, it might be useful for always-needed domain knowledge.

By following this design, Strands CLI will mimic Claude Code’s skill system. The agent will autonomously decide when to leverage a skill, trigger its loading, and then gain the skill’s knowledge to complete the task. All of this happens behind the scenes; the workflow author only sees that the agent was “smart” enough to use the extra info. This matches Anthropic’s implementation where “Claude autonomously decides when to use [a skill] based on your request and the Skill’s description”
code.claude.com
. In our case, thanks to the system prompt setup, any LLM (Claude or others) can make that decision with the same information.

Reference Example

To tie it all together, here’s an illustrative flow akin to how Claude Code works (now in a Strands context):

System Prompt excerpt:

You are a Strands agent... (base instructions)…

How to use skills: When a user’s query might be solved by a specialized skill, call Skill("<skill_id>") to load it. Only use skills listed below. Do not call a skill already loaded.

Available Skills:
– pdf (path: skills/pdf): Toolkit for extracting text/tables from PDFs, merging/splitting documents, etc.
– xlsx (path: skills/xlsx): Toolkit for creating and editing spreadsheets, with formula support, data analysis, etc.

User Prompt: “Please extract all tables from the attached PDF and summarize them in CSV format.”

Agent’s First Pass: Seeing the term “PDF” and knowing a pdf skill is available, the agent responds with a tool call (instead of a direct answer), e.g.:

Skill("pdf")


(This is the model’s way of saying: “I should use the PDF skill now.”)

Strands intercepts and loads skill: The CLI recognizes this invocation. It reads skills/pdf/SKILL.md (which contains detailed steps or code for PDF extraction). Suppose that content says: “Step 1: Use the PDF parser tool to extract text from each page… Step 2: Identify tables using XYZ library…” etc. Strands then injects this content for the model.

Agent Receives Skill Content: Now the model’s context is expanded with the PDF skill’s instructions. The agent “sees” exactly how to parse and handle PDFs as if it were part of the conversation.

Agent’s Second Pass: With the skill loaded, the agent now continues the conversation. It might output something like: “Using the PDF toolkit, I have extracted 3 tables. Now I will convert them to CSV…” – and eventually produce the final answer (perhaps even using another internal tool if needed, but the gist is it followed the skill’s guidance).

Final Output: The agent returns the summarized CSV or analysis to the user, as was requested, having successfully used the skill behind the scenes.

This approach ensures progressive loading: the PDF skill instructions were only provided when the agent determined they were needed, conserving token budget and keeping the initial prompt focused. It also keeps the interface simple for prompt authors – they just enable skills and the agent does the rest.

Conclusion

In conclusion, implementing Claude-like code skills in Strands CLI involves dynamic prompt management and tool integration. We inject skill metadata upfront (already supported in the schema and code
GitHub
GitHub
), and enable on-demand injection of full skill content via a skill invocation mechanism. The key is to rewrite the system prompt to advertise available skills and how to use them, and then intercept the model’s skill calls using specialized tooling. By doing so, Strands will mimic Claude Code’s progressive disclosure of skills – extending the agent’s capabilities in a modular way without burdening the user to manage those details. This design is fully in line with the AWS Strands SDK philosophy of tool-based extensibility and should integrate well (Anthropic Claude models, in particular, will readily follow the Skill("name") pattern
github.com
, and other models can be taught to do so through our prompt instructions).

With this complete functional design in place, the code changes should be straightforward: define the skill-loading tool and adjust the prompt construction and agent loop. The existing code structure (prompt builder, tool loader, etc.) is well prepared for this – “see the code – it will be obvious” how these pieces fit together once the above approach is understood. By leveraging the prior art in Claude’s skills system and the hints already present in Strands CLI, we can implement a robust progressive skill loading feature that greatly enhances the agent’s power while keeping prompts simple.

Sources:

Strands Workflow Schema (Skills support and description)
GitHub

Strands CLI system prompt builder (build_system_prompt injecting skills list)
GitHub

Anthropic Claude Code Skills documentation (skill invocation and progressive loading behavior)
github.com
github.com

OpenSkills project (reproducing Claude’s skill format and usage)
github.com
github.com