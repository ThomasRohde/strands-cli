# Explanation

This section provides conceptual understanding of Strands CLI's architecture, design decisions, and implementation philosophy. These documents explain the "why" behind the system rather than the "how" (see [How-To](../howto/)) or the "what" (see [Reference](../reference/)).

## Architecture & Design

**[Architecture Overview](architecture.md)** - Understand the system components, data flow, and execution model that powers Strands CLI.

- System overview and component diagrams
- Data flow through the three-phase execution model
- Module boundaries and dependency relationships
- Performance characteristics and configuration

**[Design Decisions](design-decisions.md)** - Learn the rationale behind key architectural choices and technology selections.

- Why YAML/JSON workflow specifications
- Why JSON Schema Draft 2020-12 for validation
- Provider abstraction design
- Security-first design philosophy
- Single event loop strategy
- Exit code discipline

## Patterns & Orchestration

**[Pattern Philosophy](patterns.md)** - Understand why workflow patterns exist, when to use each, and how to choose the right pattern.

- The multi-agent orchestration problem
- Pattern catalog (all 7 patterns explained)
- Pattern selection decision tree
- Comparison matrix with trade-offs
- Pattern composability and anti-patterns

## Performance & Security

**[Performance Optimizations](performance.md)** - Deep dive into the performance optimizations that make Strands CLI efficient.

- Agent caching (10×+ speedup)
- Model client pooling (20×+ reduction)
- Single event loop architecture
- Concurrency control with semaphores
- Benchmark results and best practices

**[Security Model](security-model.md)** - Comprehensive overview of the defense-in-depth security architecture.

- Threat model and attack scenarios
- Template sandboxing (RCE prevention)
- SSRF prevention (URL validation)
- Path traversal protection
- Tool allowlisting
- Audit logging and SIEM integration

---

## Reading Order

For new users, we recommend reading in this order:

1. **[Architecture Overview](architecture.md)** - Get the big picture
2. **[Pattern Philosophy](patterns.md)** - Understand workflow orchestration
3. **[Design Decisions](design-decisions.md)** - Learn the "why" behind key choices
4. **[Performance Optimizations](performance.md)** - Understand efficiency gains
5. **[Security Model](security-model.md)** - Learn about security controls

For developers contributing to Strands CLI, all documents are essential reading.

---

## Related Sections

- **[Tutorials](../tutorials/)** - Step-by-step learning paths for new users
- **[How-To Guides](../howto/)** - Task-oriented guides for common operations
- **[Reference](../reference/)** - Technical specifications (CLI, Schema, API)
