"""SOL26 runtime objects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from interpreter.input_model import Block as BlockDef

if TYPE_CHECKING:
    from interpreter.environment import Environment



class SOLObject(ABC):
    """Základná trieda pre všetky SOL26 objekty."""

    def __init__(self, class_name: str) -> None:
        """Initialize the object with a class name."""
        self.class_name = class_name
        self.attributes: dict[str, SOLObject] = {}

    @abstractmethod
    def sol_as_string(self) -> str:
        """Returns string representation of this object."""


class SOLNil(SOLObject):
    """Reprezentuje nil - singleton."""

    def __init__(self) -> None:
        """Initialize Nil."""
        super().__init__("Nil")

    def sol_as_string(self) -> str:
        """Returns 'nil'."""
        return "nil"


class SOLBool(SOLObject):
    """Reprezentuje true/false - singletons."""

    def __init__(self, value: bool) -> None:
        """Initialize Bool with a value."""
        super().__init__("True" if value else "False")
        self.value = value

    def sol_as_string(self) -> str:
        """Returns 'true' or 'false'."""
        return "true" if self.value else "false"


class SOLInteger(SOLObject):
    """Reprezentuje celé číslo."""

    def __init__(self, value: int) -> None:
        """Initialize Integer with a value."""
        super().__init__("Integer")
        self.value = value

    def sol_as_string(self) -> str:
        """Returns number as string."""
        return str(self.value)


class SOLString(SOLObject):
    """Reprezentuje retazec (string)."""

    def __init__(self, value: str) -> None:
        """Initialize String with a value."""
        super().__init__("String")
        self.value = value

    def sol_as_string(self) -> str:
        """Returns the string value."""
        return self.value

class SOLBlock(SOLObject):
    """Reprezentuje blok kódu (closure)."""

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
        """Returns string representation of block."""
        return "a Block"


class SOLInstance(SOLObject):
    """Reprezentuje inštanciu užívateľsky definovanej triedy."""

    def __init__(self, class_name: str) -> None:
        """Initialize instance of a user-defined class."""
        super().__init__(class_name)

    def sol_as_string(self) -> str:
        """Returns string representation of instance."""
        return f"a {self.class_name}"

class SOLClassRef(SOLObject):
    """Reprezentuje triedu ako príjemcu správy (pre new, from:)."""

    def __init__(self, class_name: str) -> None:
        super().__init__("class")
        self.ref_class_name = class_name

    def sol_as_string(self) -> str:
        """Return the referenced class name."""
        return self.ref_class_name
