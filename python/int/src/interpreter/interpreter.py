"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

import logging
from pathlib import Path
from typing import TextIO

from lxml import etree
from lxml.etree import ParseError, _Element
from pydantic import ValidationError

from interpreter.builtins import dispatch_builtin, dispatch_class_message, get_bool, get_nil
from interpreter.class_table import ClassTable
from interpreter.environment import Environment
from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, Expr, Literal, Method, Program
from interpreter.sol_objects import (
    SOLBlock,
    SOLClassRef,
    SOLInstance,
    SOLInteger,
    SOLObject,
    SOLString,
)
from interpreter.static_checks import run_static_checks

logger = logging.getLogger(__name__)

# Singletons re-exported from builtins for use inside interpreter
_NIL = get_nil()


class SuperWrapper(SOLObject):
    """
    Internal marker for super dispatch.
    As message receiver: method lookup starts from parent of current_class.
    As argument / assigned value: behaves identically to self (real_obj).
    """

    def __init__(self, real_obj: SOLObject, current_class: str) -> None:
        """Initialize SuperWrapper."""
        super().__init__("__super__")
        self.real_obj = real_obj
        self.current_class = current_class

    def sol_as_string(self) -> str:
        """Delegate to wrapped object."""
        return self.real_obj.sol_as_string()


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        """Initialize the interpreter."""
        self.current_program: Program | None = None
        self.class_table: ClassTable = ClassTable()

    def load_program(self, source_file_path: Path) -> None:
        """
        Reads the source SOL-XML file and stores it as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.
        """
        logger.info("Opening source file: %s", source_file_path)
        try:
            xml_tree = etree.parse(source_file_path)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            root = xml_tree.getroot()
            self.current_program = Program.from_xml_tree(root)
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

    def load_program_string(self, source: str) -> None:
        """
        Parses the SOL-XML program from a string (e.g. read from stdin) and stores it
        as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.
        """
        logger.info("Loading program from string input")
        try:
            raw_root: _Element = etree.fromstring(source.encode())
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            self.current_program = Program.from_xml_tree(raw_root)  # type: ignore[arg-type]
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e

    def execute(self, input_io: TextIO) -> None:
        """Executes the currently loaded program."""
        logger.info("Executing program")
        if self.current_program is None:
            raise InterpreterError(
                error_code=ErrorCode.GENERAL_OTHER, message="No program loaded"
            )

        for class_def in self.current_program.classes:
            self.class_table.register(class_def)

        run_static_checks(self.current_program, self.class_table)

        main_instance = SOLInstance("Main")
        env = Environment()
        self._send_message(main_instance, "run", [], env)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_method_with_class(
        self, start_class: str, selector: str
    ) -> tuple[Method, str] | None:
        """
        Walk the inheritance chain from start_class upward.
        Returns (method, defining_class) or None if not found.
        Storing defining_class is critical for correct super dispatch inside the method.
        """
        current: str | None = start_class
        while current is not None:
            if current in self.class_table.user_classes:
                for method in self.class_table.user_classes[current].methods:
                    if method.selector == selector:
                        return method, current
            current = self.class_table.get_parent(current)
        return None

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    def _send_message(
        self,
        receiver: SOLObject,
        selector: str,
        args: list[SOLObject],
        env: Environment,
    ) -> SOLObject:
        """Send a message to a receiver object and return the result."""

        # Per spec: super used as argument/value behaves as self
        resolved_args: list[SOLObject] = [
            a.real_obj if isinstance(a, SuperWrapper) else a for a in args
        ]

        # ── 1. Class message (new, from:, String read)
        # ─────────────────────────────────────────────
        if isinstance(receiver, SOLClassRef):
            return dispatch_class_message(
                receiver.ref_class_name, selector, resolved_args
            )

        # ── 2. Resolve SuperWrapper ─────────────────────────────────────────────────────
        super_start_class: str | None = None
        actual_receiver: SOLObject

        if isinstance(receiver, SuperWrapper):
            actual_receiver = receiver.real_obj
            parent = self.class_table.get_parent(receiver.current_class)
            if parent is None:
                raise InterpreterError(
                    error_code=ErrorCode.INT_DNU,
                    message=f"No parent class for '{receiver.current_class}'",
                )
            super_start_class = parent
        else:
            actual_receiver = receiver

        # ── 3. Block value / whileTrue: / whileFalse: ───────────────────────────────────────────
        # Blocks are only dispatched without super (super on a Block makes no sense)
        if isinstance(actual_receiver, SOLBlock) and super_start_class is None:
            block_result = dispatch_builtin(
                actual_receiver, selector, resolved_args, self._invoke_block
            )
            if block_result is not None:
                return block_result
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=f"Block does not understand '{selector}'",
            )

        # ── 4. User-defined method lookup ──────────────────────────────────────────────────
        start_class = (
            super_start_class if super_start_class else actual_receiver.class_name
        )
        method_result = self._find_method_with_class(start_class, selector)

        if method_result is not None:
            method, defining_class = method_result
            method_env = Environment()  # Fresh scope — never inherit caller's variables
            method_env.set("self", actual_receiver)
            # IMPORTANT: store DEFINING class, not receiver class.
            # This ensures super inside the method correctly skips to the right parent.
            method_env.set("__current_class__", SOLString(defining_class))
            for param, arg in zip(method.block.parameters, resolved_args, strict=True):
                method_env.set(param.name, arg)
            return self._execute_block(method.block, method_env)

        # ── 5. Built-in method (Integer, String, Bool, Nil, Object) ─────────────────────────
        builtin_result = dispatch_builtin(
            actual_receiver, selector, resolved_args, self._invoke_block
        )
        if builtin_result is not None:
            return builtin_result

        # ── 6. Instance attribute getter (no args, no colon) ────────────────────────────
        if not resolved_args and ":" not in selector:
            if selector in actual_receiver.attributes:
                return actual_receiver.attributes[selector]
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=f"'{actual_receiver.class_name}' does not understand '{selector}'",
            )

        # ── 7. Instance attribute setter (one arg, exactly one colon) ─────────────────────
        if (
            len(resolved_args) == 1
            and selector.endswith(":")
            and selector.count(":") == 1
        ):
            return self._set_attribute(
                actual_receiver,
                selector,
                resolved_args[0],
                use_super=super_start_class is not None,
            )

        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"'{actual_receiver.class_name}' does not understand '{selector}'",
        )

    def _invoke_block(self, sol_block: SOLBlock, args: list[SOLObject]) -> SOLObject:
        """
        Invoke a SOLBlock with given args inside its captured (lexical) environment.
        self_ref and __current_class__ are inherited from the captured env chain —
        this ensures correct static scoping even when a block is passed to another object.
        """
        block_def = sol_block.block_def
        assert block_def is not None, "SOLBlock must have a block_def"
        block_env = Environment(parent=sol_block.captured_env)

        # Restore captured self (static scoping of self per spec section 1.2.7)
        if sol_block.self_ref is not None:
            block_env.set("self", sol_block.self_ref)
        # __current_class__ flows through parent chain from captured_env — no reset needed

        for param, arg in zip(block_def.parameters, args, strict=True):
            block_env.set(param.name, arg)

        return self._execute_block(block_def, block_env)

    def _execute_block(self, block: Block, env: Environment) -> SOLObject:
        """Execute a sequence of assignments and return the last evaluated value."""
        # Use the singleton nil — important for identicalTo: correctness
        result: SOLObject = _NIL
        for assign in block.assigns:
            raw = self._evaluate_expr(assign.expr, env)
            # super on right side of assignment behaves as self
            value = raw.real_obj if isinstance(raw, SuperWrapper) else raw
            # _ is the "don't care" variable — evaluate for side effects, skip storing
            if assign.target.name != "_":
                env.set(assign.target.name, value)
            result = value
        return result

    # ------------------------------------------------------------------
    # Expression evaluation
    # ------------------------------------------------------------------

    def _evaluate_expr(self, expr: Expr, env: Environment) -> SOLObject:
        """Evaluate an expression node and return the resulting SOL26 object."""
        if expr.literal is not None:
            return self._evaluate_literal(expr.literal)

        if expr.var is not None:
            return self._evaluate_var(expr.var.name, env)

        if expr.block is not None:
            # Capture current self for static scoping (spec section 1.2.7)
            self_ref = env.get("self")
            return SOLBlock(expr.block, env, self_ref=self_ref)

        if expr.send is not None:
            recv = self._evaluate_expr(expr.send.receiver, env)
            send_args = [
                self._evaluate_expr(arg.expr, env) for arg in expr.send.args
            ]
            return self._send_message(recv, expr.send.selector, send_args, env)

        raise InterpreterError(
            error_code=ErrorCode.GENERAL_OTHER,
            message="Empty expression node encountered",
        )

    def _evaluate_var(self, name: str, env: Environment) -> SOLObject:
        """Resolve a variable name or keyword (nil, true, false, self, super)."""
        match name:
            case "nil":
                # Return the singleton nil — identicalTo: nil == nil must be true
                return _NIL
            case "true":
                # Return the singleton true
                return get_bool(True)
            case "false":
                # Return the singleton false
                return get_bool(False)
            case "self":
                self_obj = env.get("self")
                if self_obj is None:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_OTHER,
                        message="'self' used outside of method context",
                    )
                return self_obj
            case "super":
                self_obj = env.get("self")
                current_class_obj = env.get("__current_class__")
                if self_obj is None or current_class_obj is None:
                    raise InterpreterError(
                        error_code=ErrorCode.INT_OTHER,
                        message="'super' used outside of method context",
                    )
                if not isinstance(current_class_obj, SOLString):
                    raise InterpreterError(
                        error_code=ErrorCode.GENERAL_OTHER,
                        message="Internal: __current_class__ is not SOLString",
                    )
                return SuperWrapper(self_obj, current_class_obj.value)
            case _:
                val = env.get(name)
                if val is None:
                    # Undefined variable at runtime is a runtime error (52), not static (32)
                    raise InterpreterError(
                        error_code=ErrorCode.INT_OTHER,
                        message=f"Undefined variable: '{name}'",
                    )
                return val

    def _evaluate_literal(self, literal: Literal) -> SOLObject:
        """Convert a literal XML node to a SOL26 runtime object."""
        match literal.class_id:
            case "Integer":
                return SOLInteger(int(literal.value))
            case "String":
                return SOLString(literal.value)
            case "True":
                # Use singleton — identicalTo: true == true must be true
                return get_bool(True)
            case "False":
                # Use singleton — identicalTo: false == false must be true
                return get_bool(False)
            case "Nil":
                # Use singleton — identicalTo: nil == nil must be true
                return _NIL
            case "class":
                # Class literal used as receiver for new / from: / read
                return SOLClassRef(literal.value)
            case _:
                raise InterpreterError(
                    error_code=ErrorCode.GENERAL_OTHER,
                    message=f"Unknown literal type: '{literal.class_id}'",
                )

    # ------------------------------------------------------------------
    # Instance attribute management
    # ------------------------------------------------------------------

    def _set_attribute(
        self,
        receiver: SOLObject,
        selector: str,
        value: SOLObject,
        use_super: bool = False,
    ) -> SOLObject:
        """
        Create or update an instance attribute.
        Raises error 54 if the attribute name would collide with a method.

        use_super=True  → check only parent class methods (spec: super skips own class)
        use_super=False → check own class + inherited methods
        """
        attr_name = selector.rstrip(":")

        builtin_method_names = {
            "identicalTo",
            "equalTo",
            "=",
            "~=",
            "asString",
            "printString",
            "isNil",
            "notNil",
            "isNumber",
            "isString",
            "isBlock",
            "isBoolean",
            "print",
            "printNl",
            "ifNil",
            "ifNotNil",
            "ifNil:ifNotNil",
            "ifNotNil:ifNil",
            "plus",
            "minus",
            "multiplyBy",
            "divBy",
            "modBy",
            "greaterThan",
            "lessThan",
            "greaterOrEqualTo",
            "lessOrEqualTo",
            "asInteger",
            "timesRepeat",
            "concatenateWith",
            "length",
            "size",
            "startsWith:endsBefore",
            "ifTrue",
            "ifFalse",
            "ifTrue:ifFalse",
            "ifFalse:ifTrue",
            "not",
            "and",
            "or",
            "whileTrue",
            "whileFalse",
            "value",
            "value:value",
            "value:value:value",
        }

        if attr_name in builtin_method_names:
            raise InterpreterError(
                error_code=ErrorCode.INT_INST_ATTR,
                message=(
                    f"Cannot create attribute '{attr_name}': "
                    "collides with a built-in method"
                ),
            )

        if use_super:
            parent = self.class_table.get_parent(receiver.class_name)
            collides = (
                parent is not None
                and self.class_table.find_method(parent, attr_name) is not None
            )
        else:
            collides = any(
                self.class_table.find_method(ancestor, attr_name) is not None
                for ancestor in self.class_table.get_ancestors(receiver.class_name)
            )

        if collides:
            raise InterpreterError(
                error_code=ErrorCode.INT_INST_ATTR,
                message=(
                    f"Cannot create attribute '{attr_name}': "
                    f"collides with a method in '{receiver.class_name}'"
                ),
            )

        receiver.attributes[attr_name] = value
        return receiver  # spec: setter returns self
