# Strands CLI: Unsupported Features Report

**Spec File:** `.\examples\multi-agent-unsupported.yaml`  
**Fingerprint:** `e7443b497ec46eb4`  
**Issues Found:** 2

---

## Summary

This workflow specification contains features that are not yet supported in the current MVP.
Please review the issues below and apply the suggested remediations.

## Issues

### 1. `/agents`

**Reason:** Found 2 agents, but MVP supports exactly 1  
**Remediation:** Keep only one agent (e.g., 'researcher' if available)

### 2. `/pattern/config/steps`

**Reason:** Chain has 2 steps, but MVP supports only 1  
**Remediation:** Reduce to 1 step in pattern.config.steps

---

## Minimal Runnable Example

Here's a minimal single-agent workflow that is supported in MVP:

```yaml
version: 0
name: minimal-single-agent

runtime:
  provider: ollama
  model_id: gpt-oss
  host: http://localhost:11434

agents:
  main:
    prompt: You are a helpful assistant.

pattern:
  type: chain
  config:
    steps:
      - agent: main
        input: "Process this task."

outputs:
  artifacts:
    - path: ./artifacts/output.md
      from: '{{ last_response }}'
```

---

## Next Steps

1. Review the issues listed above
2. Apply suggested remediations to your spec
3. Run `strands-cli validate <spec>` to verify changes
4. Run `strands-cli plan <spec>` to preview execution
5. Run `strands-cli run <spec>` to execute
