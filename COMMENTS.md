# Comment good practice

## Purpose  
These guidelines define how our AI agents (and human developers) should produce comments and docstrings in Python code within our enterprise architecture and banking-domain projects. The goal is readable, maintainable, purpose-driven code with consistent, high-quality commentary.

---

## 1. Scope & Key Principles  
- Comments and docstrings must **explain intent, assumptions, and business logic** — not just restate code. According to best practices, comments should focus on *why* and *non-obvious intent rather than *what* the code is doing. :contentReference[oaicite:0]{index=0}  
- Avoid comments that become outdated, misleading, or irrelevant. As the PEP 8 style guide warns: *“Comments that contradict the code are worse than no comments.”* :contentReference[oaicite:2]{index=2}  
- Comments should support both maintainers and future reviewers: they should provide context, assumptions, and domain rationale (e.g., “Due to MiFID II requirement…”), not project-phase or timeline details.

---

## 2. Docstrings (Modules, Classes, Public Functions)  
### 2.1 Mandatory  
- Every module must start with a module-level triple-quoted docstring summarising its purpose, key functionality, and high-level domain context.  
- Every class must include a docstring describing its responsibility, key methods, usage example (if helpful), and any domain-specific relationships.  
- Every public function or method must include a docstring describing:
  - What the function does (business/domain logic)  
  - Parameters: names, types, meanings  
  - Return value: type and meaning  
  - Side-effects, exceptions raised, external dependencies  
  - Domain/model context (e.g., this function maps to the CapModel “CustomerOnboarding” capability)  

### 2.2 Style  
- Use the chosen team style (e.g., **Google docstring style**, or **NumPy style**). Define which one and stick with it.  
- Example (Google style):
  ```python
  def process_payment(amount: Decimal, currency: str) -> Receipt:
      """Process a payment using internal ledger and external clearing.

      Args:
          amount (Decimal): Payment amount in the smallest sub-unit (e.g., cents).
          currency (str): ISO currency code, uppercase.

      Returns:
          Receipt: A receipt object summarising the cleared transaction.

      Raises:
          UnsupportedCurrencyError: If the currency is not supported by the clearing house.
      """
      ...
````

* The first line is a short summary. After a blank line, add more detail (when needed).
* Keep docstring lines usually under ~72–79 characters (per PEP 8 guidance). ([realpython.com][1])

---

## 3. Inline & Block Comments

### 3.1 When to comment

* Use inline or above-line comments to explain:

  * Non-obvious business logic or algorithm choices
  * Assumptions (especially domain/regulatory)
  * Workarounds or temporary fixes (with context)
  * External dependencies or constraints (e.g., “Regulatory rule X dictates rounding here”)
* Avoid comments that simply restate what the code does (this is considered W.E.T. – “Write Everything Twice”). ([Kinsta®][2])
* Do not comment trivial code such as `value += 1` with “increment by one” unless there is a business reason to highlight it.

### 3.2 Placement & style

* Place comments at the same indentation level as the code they refer to. Block comments should be preceded by a blank line. ([Kinsta®][2])
* Use sentence case for comments: `# Calculate the risk factor cap here` rather than `# CALCULATE RISK FACTOR CAP HERE`.
* Use tags for actionable comments: `# TODO: …`, `# FIXME: …`, `# HACK: …` with sufficient context (what, why, when). ([Kinsta®][2])

---

## 4. Prohibited Comment Content

To maintain clarity, relevance and maintainability, **do not** include comments that:

* Refer to project-phases, timelines, rollout statuses or other events outside the code’s scope.

  * Example **not allowed**: `# Limited to the MVP release, will be refactored later`.
  * Example **not allowed**: `# Temporary solution until end-of-quarter go-live`.
* Mention developer names unless absolutely necessary for audit/tracking (and then use structured metadata, not casual comments).
* Contain irrelevant history or log-style commentary (e.g., “Changed by John on 2024-09-09”). Use version control for that.
* Be snarky, derogatory, or unprofessional. Comments are part of our codebase and may be audited or reviewed externally. ([realpython.com][1])

---

## 5. Maintenance & Review

* **Whenever** you change logic, update the associated docstrings and comments *in the same commit*. Outdated comments are misleading and worse than none. ([Python Enhancement Proposals (PEPs)][3])
* During code review (or automated linting) check:

  * Does every module/class/public function have a docstring?
  * Are all parameters/returns/exceptions documented?
  * Do inline comments explain *why* rather than *what*?
  * Are there `TODO`/`FIXME` tags and do they include context (who, what, when)?
  * Are any comments referring to external timelines, MVPs, release phases (which are disallowed)?
* Use static analysis / linting tools to enforce comment rules where possible (for example ensuring docstring presence, comment length, placement consistency).

---

## 6. Domain-Specific Additions for Banking/Enterprise Architecture

* Any comment referencing PII, encryption, messaging flows, or regulatory rules must be explicit about the rule/requirement (e.g., `# GDPR: email consent required before storing user_email`).
* If a code fragment corresponds to a business capability (e.g., part of “CustomerOnboarding” domain) or architecture view (e.g., “Payments Clearing – Ledger Interface”), the docstring or comment should reference that.
* Use standard terms from the capability/domain model rather than generic or ad-hoc language to align with our architecture taxonomy.

---

## 7. Example Commenting Patterns

```python
# Validate customer profile completeness before credit check (MiFID II requirement)
if not customer_profile.is_complete():
    raise IncompleteProfileError("Cannot proceed until profile is complete.")

def allocate_resources(capacity: int) -> List[Resource]:
    """Allocate resources for the given capacity in the Core Ledger Engine.

    Args:
        capacity (int): Required capacity units (business layer units).

    Returns:
        List[Resource]: Allocated resource instances ready for assignment.

    Raises:
        ResourceOverflowError: If capacity exceeds available limit.
    """
    # We deliberately use integer division here because rounding up would breach our capacity quota rule
    units = capacity // UNIT_SIZE  
    return [Resource() for _ in range(units)]
```
