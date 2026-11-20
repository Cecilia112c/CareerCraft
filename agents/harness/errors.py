"""Harness error types. Agent failures all derive from AgentError."""


class HarnessError(RuntimeError):
    code = "harness_error"


class AgentError(HarnessError):
    """An invocation failed (bad output, budget exhausted, provider failure...)."""
    code = "agent_error"


class ValidationFailed(AgentError):
    code = "validation_failed"


class BudgetExhausted(AgentError):
    code = "budget_exhausted"


class ProviderError(AgentError):
    code = "provider_error"


class ContextBudgetExceeded(AgentError):
    """Required context slots alone exceed the input budget; the model is not called."""
    code = "context_budget_exceeded"


class ConfigError(HarnessError):
    code = "config_error"
