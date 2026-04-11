"""SOL26 class table - stores all class definitions.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

from __future__ import annotations

from typing import ClassVar

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import ClassDef, Method


class ClassTable:
    """Stores all class definitions (built-in and user-defined)."""

    # Správna hierarchia podľa spec — žiadna trieda Boolean neexistuje!
    BUILTIN_PARENTS: ClassVar[dict[str, str | None]] = {
        "Object": None,
        "Nil": "Object",
        "True": "Object",
        "False": "Object",
        "Integer": "Object",
        "String": "Object",
        "Block": "Object",
        "Transcript": "Object",
    }

    def __init__(self) -> None:
        """Initialize class table with built-in classes."""
        self.user_classes: dict[str, ClassDef] = {}

    def register(self, class_def: ClassDef) -> None:
        """
        Register a user-defined class.
        Raises error 35 on duplicate or collision with built-in class name.
        """
        if class_def.name in self.BUILTIN_PARENTS:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ERROR,
                message=f"Cannot redefine built-in class '{class_def.name}'",
            )
        if class_def.name in self.user_classes:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ERROR,
                message=f"Duplicate class definition: '{class_def.name}'",
            )
        self.user_classes[class_def.name] = class_def

    def exists(self, class_name: str) -> bool:
        """Return True if the class is known (built-in or user-defined)."""
        return class_name in self.BUILTIN_PARENTS or class_name in self.user_classes

    def get_parent(self, class_name: str) -> str | None:
        """
        Return parent class name, or None for Object.
        Raises error 52 for unknown class names.
        """
        if class_name in self.BUILTIN_PARENTS:
            return self.BUILTIN_PARENTS[class_name]
        if class_name in self.user_classes:
            return self.user_classes[class_name].parent
        raise InterpreterError(
            error_code=ErrorCode.INT_OTHER,
            message=f"Unknown class: '{class_name}'",
        )

    def find_method(self, class_name: str, selector: str) -> Method | None:
        """
        Find a user-defined method by selector, walking up the inheritance chain.
        Built-in methods are handled in builtins.py.
        """
        current: str | None = class_name
        while current is not None:
            if current in self.user_classes:
                for method in self.user_classes[current].methods:
                    if method.selector == selector:
                        return method
            current = self.get_parent(current)
        return None

    def find_method_from_parent(self, class_name: str, selector: str) -> Method | None:
        """
        Like find_method, but starts from the PARENT of class_name.
        Used for super dispatch.
        """
        parent = self.get_parent(class_name)
        if parent is None:
            return None
        return self.find_method(parent, selector)

    def is_subclass_of(self, class_name: str, potential_parent: str) -> bool:
        """
        Return True if class_name is equal to or inherits from potential_parent.
        Useful for type checks (e.g. from: compatibility).
        """
        current: str | None = class_name
        while current is not None:
            if current == potential_parent:
                return True
            current = self.get_parent(current)
        return False

    def get_ancestors(self, class_name: str) -> list[str]:
        """
        Return ordered list of ancestors: [class_name, parent, ..., Object].
        Useful for MRO debugging.
        """
        chain: list[str] = []
        current: str | None = class_name
        while current is not None:
            chain.append(current)
            current = self.get_parent(current)
        return chain
