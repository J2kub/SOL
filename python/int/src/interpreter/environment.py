"""SOL26 variable environment (scope)."""

from __future__ import annotations

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.sol_objects import SOLObject


class Environment:
    """Stores variables for one scope, with optional parent for closures."""

    def __init__(self, parent: Environment | None = None) -> None:
        """Initialize environment with optional parent scope."""
        self.variables: dict[str, SOLObject] = {}
        self.params: set[str] = set()
        self.parent = parent

    def set(self, name: str, value: SOLObject) -> None:
        """
        Set a variable. If it exists in any parent scope, update it there (closure semantics).
        If not found anywhere, create it in current scope (first assignment = definition).
        """
        if name in self.params:
            raise InterpreterError(
                error_code=ErrorCode.SEM_COLLISION,
                message=f"Cannot assign to formal parameter: '{name}'",
            )
        # Walk up the chain — find where the variable lives
        env: Environment | None = self
        while env is not None:
            if name in env.variables:
                if name in env.params:
                    raise InterpreterError(
                        error_code=ErrorCode.SEM_COLLISION,
                        message=f"Cannot assign to formal parameter: '{name}'",
                    )
                env.variables[name] = value
                return
            env = env.parent
        # Not found anywhere → define in current scope
        self.variables[name] = value

    def get(self, name: str) -> SOLObject | None:
        """Get a variable - looks in current scope then parent."""
        if name in self.variables:
            return self.variables[name]
        if self.parent is not None:
            return self.parent.get(name)
        return None
