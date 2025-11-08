"""Streaming file operations for JIT tools - Technical Design.

This document outlines the streaming implementation strategy for grep and search
tools to handle very large files (>1GB) without loading them entirely into memory.

Phase 2 Remediation: Tooling enhancements (design only, implementation deferred)

## Current Implementation

Both `grep` and `search` tools currently load entire files into memory:

```python
with open(path, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()  # Loads entire file into memory
```

This works well for typical code files (<10MB) but can cause issues with:
- Large log files (>100MB)
- Data dumps (>1GB)
- Memory-constrained environments

## Proposed Streaming Implementation

### Strategy

1. **Line-by-line processing**: Process one line at a time without buffering
2. **Bounded context windows**: Keep only N lines in memory for context
3. **Early termination**: Stop reading when `max_matches` reached
4. **Memory safety**: Set hard limit on total output size

### Implementation Sketch

```python
def grep_streaming(pattern, path, context_lines=3, max_matches=100, max_output_bytes=1_000_000):
    """Streaming grep implementation."""
    matches = []
    context_buffer = []  # Circular buffer of size context_lines
    total_bytes = 0
    
    with open(path, encoding="utf-8", errors="replace") as f:
        for line_num, line in enumerate(f, start=1):
            # Update context buffer (circular)
            context_buffer.append((line_num, line))
            if len(context_buffer) > context_lines * 2 + 1:
                context_buffer.pop(0)
            
            # Check for match
            if pattern.search(line):
                # Extract context window from buffer
                match_context = extract_context(context_buffer, line_num, context_lines)
                match_size = sum(len(l) for _, l in match_context)
                
                if total_bytes + match_size > max_output_bytes:
                    # Output size limit reached
                    matches.append(("...", "Output truncated - size limit reached"))
                    break
                
                matches.append(match_context)
                total_bytes += match_size
                
                if len(matches) >= max_matches:
                    break
    
    return format_matches(matches)
```

### Benefits

- **Memory efficiency**: O(context_lines) memory instead of O(file_size)
- **Early termination**: Can stop reading after finding enough matches
- **Large file support**: Handle multi-GB files without issue
- **Safety**: Bounded output size prevents OOM

### Trade-offs

- **Complexity**: More complex than simple `readlines()`
- **Context limitations**: Context lines must fit in buffer
- **Testing**: Need tests for edge cases (match at file start/end, etc.)

## Implementation Plan

### Phase 1: Add streaming flag (optional)

Add `streaming: bool = True` parameter to tools (default: True for compatibility).
Keep current implementation as fallback for small files.

```python
def grep(tool, **kwargs):
    path = Path(tool_input["path"])
    file_size = path.stat().st_size
    
    # Use streaming for files >10MB
    if file_size > 10_000_000:
        return grep_streaming(...)
    else:
        return grep_classic(...)
```

### Phase 2: Optimize context buffer

Use `collections.deque` for efficient circular buffer:

```python
from collections import deque

context_buffer = deque(maxlen=context_lines * 2 + 1)
```

### Phase 3: Add memory limits

Track output size and enforce limits:

```python
MAX_OUTPUT_BYTES = 1_000_000  # 1MB max output
MAX_MATCHES = 100  # Existing limit
```

### Phase 4: Performance testing

Benchmark against test files:
- 1MB (baseline)
- 10MB (typical log file)
- 100MB (large log file)
- 1GB (stress test)

Target: <1s for 10MB, <10s for 100MB, <60s for 1GB

## Migration Strategy

1. **Backward compatible**: Existing specs continue to work
2. **Opt-in initially**: Add `streaming: true` flag to spec
3. **Default later**: Make streaming the default in next major version
4. **Deprecation**: Remove non-streaming after 2 versions

## Security Considerations

- **Output size limit**: Prevent DoS via large output
- **Timeout**: Add per-file timeout (default: 30s)
- **Path validation**: Already handled by existing code
- **Encoding errors**: Already handled with `errors="replace"`

## Testing Requirements

1. **Unit tests**:
   - Empty file
   - Single line file
   - Match at start/end of file
   - No matches
   - Max matches exceeded
   - Output size limit exceeded

2. **Performance tests**:
   - 1MB file with 100 matches (baseline)
   - 100MB file with 1000 matches (stress)
   - Memory usage validation (<100MB resident)

3. **Edge cases**:
   - Binary file detection still works
   - Unicode handling (emoji, special chars)
   - Very long lines (>10KB)

## Deferred to Future Phase

This design is documented for future implementation. For Phase 2, we:
1. Document the limitation in tool descriptions
2. Add this design document for future reference
3. Add TODO comments in the code
4. Create GitHub issue for tracking

The current implementation is sufficient for the MVP and most use cases.
Very large file support can be added when there's demonstrated need.
"""
