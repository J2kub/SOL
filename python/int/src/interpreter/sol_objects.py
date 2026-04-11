"""SOL26 runtime objects.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from interpreter.input_model import Block as BlockDef

if TYPE_CHECKING:
    from interpreter.environment import Environment


class SOLObject(ABC):
    """Base class for all SOL26 runtime objects."""

    def __init__(self, class_name: str) -> None:
        """Initialize the object with a class name."""
        self.class_name = class_name
        self.attributes: dict[str, SOLObject] = {}

    @abstractmethod
    def sol_as_string(self) -> str:
        """Return the SOL26 string representation of this object."""


class SOLNil(SOLObject):
    """Represents the nil singleton."""

    def __init__(self) -> None:
        """Initialize Nil."""
        super().__init__("Nil")

    def sol_as_string(self) -> str:
        """Return 'nil'."""
        return "nil"


class SOLBool(SOLObject):
    """Represents the true/false singletons."""

    def __init__(self, value: bool) -> None:
        """Initialize Bool with a value."""
        super().__init__("True" if value else "False")
        self.value = value

    def sol_as_string(self) -> str:
        """Return 'true' or 'false'."""
        return "true" if self.value else "false"


class SOLInteger(SOLObject):
    """Represents an integer value."""

    def __init__(self, value: int) -> None:
        """Initialize Integer with a value."""
        super().__init__("Integer")
        self.value = value

    def sol_as_string(self) -> str:
        """Return the integer as a string."""
        return str(self.value)


class SOLString(SOLObject):
    """Represents a string value."""

    def __init__(self, value: str) -> None:
        """Initialize String with a value."""
        super().__init__("String")
        self.value = value

    def sol_as_string(self) -> str:
        """Return the string value."""
        return self.value


class SOLBlock(SOLObject):
    """Represents a block (closure) capturing its lexical environment."""

    def __init__(
        self,
        block_def: BlockDef,
        env: Environment,
        self_ref: SOLObject | None = None,
    ) -> None:
        """Initialize Block with its definition and captured environment."""
        super().__init__("Block")
        self.block_def = block_def
        self.captured_env: Environment = env
        self.self_ref = self_ref

    def sol_as_string(self) -> str:
        """Return a string representation of this block."""
        return "a Block"


class SOLInstance(SOLObject):
    """Represents an instance of a user-defined class."""

    def __init__(self, class_name: str) -> None:
        """Initialize an instance of a user-defined class."""
        super().__init__(class_name)

    def sol_as_string(self) -> str:
        """Return a string representation of this instance."""
        return f"a {self.class_name}"


class SOLClassRef(SOLObject):
    """Represents a class used as a message receiver (for new, from:)."""

    def __init__(self, class_name: str) -> None:
        """Initialize a class reference for the given class name."""
        super().__init__("class")
        self.ref_class_name = class_name

    def sol_as_string(self) -> str:
        """Return the referenced class name."""
        return self.ref_class_name
