class AgenticTraderException(Exception):
    """Base exception for all agentic trader errors."""
    pass

class GuardrailViolationError(AgenticTraderException):
    """Raised when an order violates safety guardrails."""
    pass

class MT5ConnectionError(AgenticTraderException):
    """Raised when connection to MetaTrader 5 fails."""
    pass

class OrderExecutionError(AgenticTraderException):
    """Raised when an order fails to execute on the broker."""
    pass
