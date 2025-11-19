# Streamlit Integration Guide

This directory contains the necessary files to enable Streamlit support in your `strands-cli` repository.

## Files Included

- `workflow_session.py`: The new class that handles session-based execution.
- `__init__.py`: The updated API entry point exposing `WorkflowSession`.
- `streamlit_demo.py`: A sample Streamlit application.
- `test_workflow_session.py`: Unit tests for the new functionality.

## Integration Steps

### 1. Add `WorkflowSession` Class

Copy `workflow_session.py` to your source directory:

```bash
cp workflow_session.py src/strands_cli/api/workflow_session.py
```

### 2. Update `strands_cli.api`

**WARNING**: Since you have a custom clone, **DO NOT** simply overwrite your `__init__.py` if you have made other changes to it.

You need to ensure two things are added to `src/strands_cli/api/__init__.py`:

1.  **Import and Export `WorkflowSession`**:
    ```python
    from strands_cli.api.workflow_session import WorkflowSession
    
    __all__ = [
        # ... existing exports ...
        "WorkflowSession",
    ]
    ```

2.  **Add `create_session` method to `Workflow` class**:
    ```python
    def create_session(
        self,
        session_id: str | None = None,
        **variables: Any,
    ) -> WorkflowSession:
        """Create new workflow session for pause/resume execution."""
        return WorkflowSession(
            spec=self.spec,
            variables=variables,
            session_id=session_id,
        )
    ```

If you have **NO** custom changes in `src/strands_cli/api/__init__.py`, you can safely overwrite it:

```bash
cp __init__.py src/strands_cli/api/__init__.py
```

### 3. Add Unit Tests

Copy the test file to your tests directory:

```bash
cp test_workflow_session.py tests/api/test_workflow_session.py
```

Run the tests to verify:

```bash
python -m pytest tests/api/test_workflow_session.py
```

### 4. Run the Demo

1.  Install Streamlit:
    ```bash
    pip install streamlit
    ```

2.  Copy the demo app:
    ```bash
    cp streamlit_demo.py examples/streamlit_demo.py
    ```

3.  Run the app:
    ```bash
    streamlit run examples/streamlit_demo.py
    ```

## Notes

- The `streamlit_demo.py` is configured to use `ProviderType.OPENAI` and `gpt-5-nano`. You may need to adjust this in the `get_workflow()` function if your environment requires different settings.
