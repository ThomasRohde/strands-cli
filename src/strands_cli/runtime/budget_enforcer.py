"""Token budget enforcement hook for workflow execution.

Provides real-time budget tracking with configurable warning thresholds and
hard limits. Integrates with context compaction to extend workflow runway
before aborting on budget exhaustion.

Key Features:
- Configurable warning threshold (default 80%)
- Structured logging for observability
- Raises BudgetExceededError at 100% with EX_BUDGET_EXCEEDED
- Compatible with all workflow patterns (chain, workflow, parallel, etc.)

Example:
    from strands_cli.runtime.budget_enforcer import BudgetEnforcerHook

    hook = BudgetEnforcerHook(max_tokens=100000, warn_threshold=0.75)
    # Hook automatically tracks usage via agent.accumulated_usage
"""

from typing import Any

import structlog
from strands.hooks import AfterInvocationEvent

from strands_cli.exit_codes import EX_BUDGET_EXCEEDED

logger = structlog.get_logger(__name__)


class BudgetExceededError(Exception):
    """Raised when token budget is exhausted.

    This exception is caught by executors and translated to EX_BUDGET_EXCEEDED
    exit code. Includes diagnostic information about token usage.

    Attributes:
        message: Human-readable error description
        cumulative_tokens: Total tokens used
        max_tokens: Configured budget limit
        exit_code: Exit code to use (EX_BUDGET_EXCEEDED)
    """

    def __init__(self, message: str, cumulative_tokens: int, max_tokens: int) -> None:
        """Initialize budget exceeded error.

        Args:
            message: Error description
            cumulative_tokens: Total tokens consumed
            max_tokens: Budget limit
        """
        super().__init__(message)
        self.cumulative_tokens = cumulative_tokens
        self.max_tokens = max_tokens
        self.exit_code = EX_BUDGET_EXCEEDED


class BudgetEnforcerHook:
    """Hook to enforce token budgets during workflow execution.

    Tracks cumulative token usage across all steps/tasks and enforces
    configured limits with warnings and hard abort. Designed to run
    AFTER ProactiveCompactionHook to allow compaction to reduce tokens
    before checking hard limit.

    Attributes:
        max_tokens: Maximum allowed token budget
        warn_threshold: Percentage (0.0-1.0) at which to log warning
        warned: Whether warning has been logged (prevents spam)
        cumulative_tokens: Running total of tokens used
    """

    def __init__(
        self,
        max_tokens: int,
        warn_threshold: float = 0.8,
        telemetry_exporter: Any | None = None,
    ) -> None:
        """Initialize budget enforcer.

        Args:
            max_tokens: Maximum token budget (from budgets.max_tokens)
            warn_threshold: Warning threshold percentage (default 0.8 = 80%)
            telemetry_exporter: Optional OTEL exporter (Phase 10, reserved)
        """
        self.max_tokens = max_tokens
        self.warn_threshold = warn_threshold
        self.warn_tokens = int(max_tokens * warn_threshold)
        self.warned = False
        self.cumulative_tokens = 0
        self.telemetry_exporter = telemetry_exporter

        logger.info(
            "budget_enforcer_initialized",
            max_tokens=max_tokens,
            warn_threshold=warn_threshold,
            warn_tokens=self.warn_tokens,
        )

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        """Register hook callbacks with the agent's hook registry.

        Args:
            registry: Hook registry from the agent
            **kwargs: Additional keyword arguments (not used)
        """
        registry.add_callback(AfterInvocationEvent, self._check_budget)

    def _check_budget(self, event: Any) -> None:
        """Check budget after each agent invocation.

        Called by Strands SDK after each agent invocation. Extracts token
        usage from event.agent.accumulated_usage and enforces limits.

        Args:
            event: AfterInvocationEvent with agent and result

        Raises:
            BudgetExceededError: If cumulative usage >= max_tokens
        """
        # Extract token usage from agent
        agent = event.agent
        usage = getattr(agent, "accumulated_usage", None) or {}
        total = usage.get("totalTokens", 0)

        # Update cumulative tracker
        self.cumulative_tokens = total

        # Calculate usage percentage
        usage_pct = (total / self.max_tokens) * 100 if self.max_tokens > 0 else 0

        # Warning at configured threshold (default 80%)
        if total >= self.warn_tokens and not self.warned:
            logger.warning(
                "token_budget_warning",
                cumulative_tokens=total,
                max_tokens=self.max_tokens,
                usage_pct=f"{usage_pct:.1f}",
                threshold_pct=f"{self.warn_threshold * 100:.0f}",
                remaining_tokens=self.max_tokens - total,
            )
            self.warned = True

            # Export to telemetry if available (Phase 10)
            if self.telemetry_exporter:
                self._export_budget_warning(total, usage_pct)

        # Hard limit at 100%
        if total >= self.max_tokens:
            logger.error(
                "token_budget_exceeded",
                cumulative_tokens=total,
                max_tokens=self.max_tokens,
                usage_pct=f"{usage_pct:.1f}",
                overage=total - self.max_tokens,
            )

            # Export to telemetry if available (Phase 10)
            if self.telemetry_exporter:
                self._export_budget_exceeded(total, usage_pct)

            raise BudgetExceededError(
                f"Token budget exhausted: {total}/{self.max_tokens} tokens used (100%). "
                "Workflow aborted to prevent cost overrun.",
                cumulative_tokens=total,
                max_tokens=self.max_tokens,
            )

    def _export_budget_warning(self, tokens: int, usage_pct: float) -> None:
        """Export budget warning to telemetry (Phase 10).

        Args:
            tokens: Cumulative token count
            usage_pct: Usage percentage
        """
        # Reserved for Phase 10 OTEL integration
        pass

    def _export_budget_exceeded(self, tokens: int, usage_pct: float) -> None:
        """Export budget exceeded event to telemetry (Phase 10).

        Args:
            tokens: Cumulative token count
            usage_pct: Usage percentage
        """
        # Reserved for Phase 10 OTEL integration
        pass
