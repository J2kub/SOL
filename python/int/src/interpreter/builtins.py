"""SOL26 built-in method dispatch."""

from __future__ import annotations

import sys
from collections.abc import Callable

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.sol_objects import (
    SOLBlock,
    SOLBool,
    SOLInstance,
    SOLInteger,
    SOLNil,
    SOLObject,
    SOLString,
)

# Typ callbacku pre spustenie bloku — inject z Interpreter._invoke_block
BlockInvoker = Callable[[SOLBlock, list[SOLObject]], SOLObject]

# Globálne singletons
_NIL = SOLNil()
_TRUE = SOLBool(True)
_FALSE = SOLBool(False)


def get_nil() -> SOLNil:
    """Return the singleton Nil object."""
    return _NIL


def get_bool(value: bool) -> SOLBool:
    """Return singleton True or False."""
    return _TRUE if value else _FALSE


# ------------------------------------------------------------------
# Main dispatch entry point
# ------------------------------------------------------------------

def dispatch_builtin(
    receiver: SOLObject,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """
    Try to dispatch a message on a built-in object.
    Returns SOLObject on success, None if the selector is unknown (→ INT_DNU in interpreter).
    """
    # Object-level methods first (inherited by everything)
    result = _dispatch_object(receiver, selector, args, invoke_block)
    if result is not None:
        return result

    # Type-specific dispatch
    if isinstance(receiver, SOLInteger):
        return _dispatch_integer(receiver, selector, args, invoke_block)
    if isinstance(receiver, SOLString):
        return _dispatch_string(receiver, selector, args)
    if isinstance(receiver, SOLBool):
        return _dispatch_bool(receiver, selector, args, invoke_block)
    if isinstance(receiver, SOLNil):
        return _dispatch_nil(receiver, selector)
    if isinstance(receiver, SOLBlock):
        return _dispatch_block(receiver, selector, args, invoke_block)

    # SOLInstance — only Object-level methods apply (already checked above)
    return None


# ------------------------------------------------------------------
# Class messages: new, from:, String read
# ------------------------------------------------------------------

def dispatch_class_message(
    class_name: str,
    selector: str,
    args: list[SOLObject],
) -> SOLObject:
    """Handle class-level messages: new, from:, String read."""
    match selector:
        case "new":
            return _instantiate(class_name)
        case "from":
            if not args:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="from: requires one argument",
                )
            return _copy_from(class_name, args[0])
        case "read" if class_name == "String":
            line = sys.stdin.readline()
            # Strip trailing newline only (spec: reads one line without the newline)
            if line.endswith("\n"):
                line = line[:-1]
            return SOLString(line)
        case _:
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF,
                message=f"Class '{class_name}' does not understand class message '{selector}'",
            )


# ------------------------------------------------------------------
# Object methods (inherited by all)
# ------------------------------------------------------------------

def _dispatch_object(
    receiver: SOLObject,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """Methods defined on Object — available to all SOL26 objects."""
    match selector:
        case "identicalTo":
            return get_bool(receiver is args[0])
        case "equalTo":
            return get_bool(_sol_equal(receiver, args[0]))
        case "asString":
            return SOLString(receiver.sol_as_string())
        case "isNil":
            return get_bool(isinstance(receiver, SOLNil))
        case "notNil":
            return get_bool(not isinstance(receiver, SOLNil))
        case "isNumber":
            return get_bool(isinstance(receiver, SOLInteger))
        case "isString":
            return get_bool(isinstance(receiver, SOLString))
        case "isBlock":
            return get_bool(isinstance(receiver, SOLBlock))
        case "isBoolean":
            return get_bool(isinstance(receiver, SOLBool))
        case "print":
            # Fallback print for any object
            print(receiver.sol_as_string(), end="")
            return receiver
        case "ifNil:":
            _assert_block(args[0], selector, expected_arity=0)
            if isinstance(receiver, SOLNil):
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            return receiver
        case "ifNotNil:":
            _assert_block(args[0], selector, expected_arity=1)
            if not isinstance(receiver, SOLNil):
                return invoke_block(args[0], [receiver])  # type: ignore[arg-type]
            return _NIL
        case "ifNil:ifNotNil:":
            if isinstance(receiver, SOLNil):
                _assert_block(args[0], selector, expected_arity=0)
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            _assert_block(args[1], selector, expected_arity=1)
            return invoke_block(args[1], [receiver])  # type: ignore[arg-type]
        case "ifNotNil:ifNil:":
            if not isinstance(receiver, SOLNil):
                _assert_block(args[0], selector, expected_arity=1)
                return invoke_block(args[0], [receiver])  # type: ignore[arg-type]
            _assert_block(args[1], selector, expected_arity=0)
            return invoke_block(args[1], [])  # type: ignore[arg-type]
    return None


# ------------------------------------------------------------------
# Integer
# ------------------------------------------------------------------

def _dispatch_integer(
    receiver: SOLInteger,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    match selector:
        case "plus":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value + _int(args[0]))
        case "minus":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value - _int(args[0]))
        case "multiplyBy":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value * _int(args[0]))
        case "divBy":
            _assert_integer(args[0], selector)
            if _int(args[0]) == 0:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Division by zero",
                )
            # Integer division compatible with implementation language (Python //)
            return SOLInteger(receiver.value // _int(args[0]))
        case "modBy":
            _assert_integer(args[0], selector)
            if _int(args[0]) == 0:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Modulo by zero",
                )
            return SOLInteger(receiver.value % _int(args[0]))
        case "equalTo":
            if not isinstance(args[0], SOLInteger):
                return _FALSE
            return get_bool(receiver.value == _int(args[0]))
        case "greaterThan":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value > _int(args[0]))
        case "lessThan":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value < _int(args[0]))
        case "greaterOrEqualTo":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value >= _int(args[0]))
        case "lessOrEqualTo":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value <= _int(args[0]))
        case "asString":
            return SOLString(str(receiver.value))
        case "asInteger":
            # Returns self
            return receiver
        case "print":
            print(receiver.sol_as_string(), end="")
            return receiver
        case "timesRepeat:":
            block = args[0]
            if not isinstance(block, SOLBlock):
                raise InterpreterError(
                    error_code=ErrorCode.INT_DNU,
                    message=f"'{selector}' expects Block argument, got '{block.class_name}'",
                )

            arity = len(block.block_def.parameters)  # type: ignore[union-attr]
            result: SOLObject = _NIL

            if receiver.value <= 0:
                return result

            if arity == 0:
                for _ in range(receiver.value):
                    result = invoke_block(block, [])
                return result

            if arity == 1:
                for i in range(1, receiver.value + 1):
                    result = invoke_block(block, [SOLInteger(i)])
                return result

            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=f"'{selector}' expects block with arity 0 or 1, got arity {arity}",
            )
    return None


# ------------------------------------------------------------------
# String
# ------------------------------------------------------------------

def _dispatch_string(
    receiver: SOLString,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    match selector:
        case "print":
            print(receiver.value, end="")
            return receiver
        case "equalTo":
            if not isinstance(args[0], SOLString):
                return _FALSE
            return get_bool(receiver.value == args[0].value)
        case "asString":
            return receiver
        case "asInteger":
            # Returns Integer if easily convertible, nil otherwise (spec)
            try:
                return SOLInteger(int(receiver.value))
            except ValueError:
                return _NIL
        case "concatenateWith":
            # Returns nil if argument is not a String or subclass
            if not isinstance(args[0], SOLString):
                return _NIL
            return SOLString(receiver.value + args[0].value)
        case "length":
            return SOLInteger(len(receiver.value))
        case "startsWith:endsBefore":
            return _string_substring(receiver, args)
    return None


def _string_substring(receiver: SOLString, args: list[SOLObject]) -> SOLObject:
    """
    startsWith:endsBefore: — returns substring.
    Spec: indexes from 1; if args non-positive or non-integer → nil;
    if endsBefore > length → return up to end; if diff <= 0 → empty string.
    """
    if not isinstance(args[0], SOLInteger) or not isinstance(args[1], SOLInteger):
        return _NIL
    start = args[0].value
    end = args[1].value
    if start <= 0 or end <= 0:
        return _NIL
    if end - start <= 0:
        return SOLString("")
    # Convert to 0-based indexing
    py_start = start - 1
    py_end = end - 1  # endsBefore is exclusive in spec (char BEFORE this index)
    return SOLString(receiver.value[py_start:py_end])


# ------------------------------------------------------------------
# Bool (True / False)
# ------------------------------------------------------------------

def _dispatch_bool(
    receiver: SOLBool,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    match selector:
        case "ifTrue:":
            _assert_block(args[0], selector, expected_arity=0)
            if receiver.value:
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            return _NIL
        case "ifFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            if not receiver.value:
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            return _NIL
        case "ifTrue:ifFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            _assert_block(args[1], selector, expected_arity=0)
            if receiver.value:
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            return invoke_block(args[1], [])  # type: ignore[arg-type]
        case "ifFalse:ifTrue:":
            _assert_block(args[0], selector, expected_arity=0)
            _assert_block(args[1], selector, expected_arity=0)
            if not receiver.value:
                return invoke_block(args[0], [])  # type: ignore[arg-type]
            return invoke_block(args[1], [])  # type: ignore[arg-type]
        case "not":
            return get_bool(not receiver.value)
        case "and:":
            # Short-circuit: if false, don't evaluate block
            _assert_block(args[0], selector, expected_arity=0)
            if not receiver.value:
                return _FALSE
            result = invoke_block(args[0], [])  # type: ignore[arg-type]
            if not isinstance(result, SOLBool):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="'and:' block must return a Bool",
                )
            return result
        case "or:":
            # Short-circuit: if true, don't evaluate block
            _assert_block(args[0], selector, expected_arity=0)
            if receiver.value:
                return _TRUE
            result = invoke_block(args[0], [])  # type: ignore[arg-type]
            if not isinstance(result, SOLBool):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="'or:' block must return a Bool",
                )
            return result
        case "equalTo":
            if not isinstance(args[0], SOLBool):
                return _FALSE
            return get_bool(receiver.value == args[0].value)
        case "asString":
            return SOLString("true" if receiver.value else "false")
        case "isBoolean":
            return _TRUE
        case "print":
            print(receiver.sol_as_string(), end="")
            return receiver
    return None


# ------------------------------------------------------------------
# Nil
# ------------------------------------------------------------------

def _dispatch_nil(
    receiver: SOLNil,
    selector: str,
) -> SOLObject | None:
    match selector:
        case "isNil":
            return _TRUE
        case "notNil":
            return _FALSE
        case "asString":
            return SOLString("nil")
        case "equalTo":
            return get_bool(isinstance(args[0], SOLNil))
        case "print":
            print("nil", end="")
            return receiver
    return None


# ------------------------------------------------------------------
# Block
# ------------------------------------------------------------------

def _dispatch_block(
    receiver: SOLBlock,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    expected_arity = len(receiver.block_def.parameters)  # type: ignore[union-attr]
    expected_selector = "value" if expected_arity == 0 else ":".join(["value"] * expected_arity)

    match selector:
        case s if s == expected_selector:
            # Correct value / value: / value:value: call
            return invoke_block(receiver, args)

        case "whileTrue:":
            # [condBlock] whileTrue: [bodyBlock]
            # condBlock must be zero-arity, bodyBlock must be zero-arity
            _assert_block(args[0], selector, expected_arity=0)
            result: SOLObject = _NIL
            while True:
                cond = invoke_block(receiver, [])
                if not isinstance(cond, SOLBool):
                    raise InterpreterError(
                        error_code=ErrorCode.INT_OTHER,
                        message="'whileTrue:' condition block must return Bool",
                    )
                if not cond.value:
                    break
                result = invoke_block(args[0], [])  # type: ignore[arg-type]
            return result

        case "whileFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            result = _NIL
            while True:
                cond = invoke_block(receiver, [])
                if not isinstance(cond, SOLBool):
                    raise InterpreterError(
                        error_code=ErrorCode.INT_OTHER,
                        message="'whileFalse:' condition block must return Bool",
                    )
                if cond.value:
                    break
                result = invoke_block(args[0], [])  # type: ignore[arg-type]
            return result

        case s if s.startswith("value"):
            # value selector with wrong arity
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=(
                    f"Block expects '{expected_selector}' "
                    f"but received '{selector}' (arity mismatch)"
                ),
            )
    return None


# ------------------------------------------------------------------
# Constructors: new, from:
# ------------------------------------------------------------------

def _instantiate(class_name: str) -> SOLObject:
    """Create a new instance of a built-in class with default values."""
    match class_name:
        case "Integer":
            return SOLInteger(0)
        case "String":
            return SOLString("")
        case "True":
            return _TRUE
        case "False":
            return _FALSE
        case "Nil":
            return _NIL
        case "Block":
            # Block new → empty zero-arity block (spec: Block new creates empty value block)
            # We create a minimal SOLBlock with no block_def — handle carefully
            # For now return a placeholder; real usage is rare
            raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,
                message="Block new is not yet supported",
            )
        case _:
            # User-defined class
            from interpreter.sol_objects import SOLInstance
            return SOLInstance(class_name)


def _copy_from(class_name: str, obj: SOLObject) -> SOLObject:
    """
    Create a new instance of class_name initialized from obj (from: constructor).
    Copies internal attributes and does a shallow copy of instance attributes.
    Raises error 53 if internal attribute types are incompatible.
    """
    match class_name:
        case "Integer":
            if not isinstance(obj, SOLInteger):
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message=f"Integer from: expects Integer, got '{obj.class_name}'",
                )
            new_obj: SOLObject = SOLInteger(obj.value)
        case "String":
            if not isinstance(obj, SOLString):
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message=f"String from: expects String, got '{obj.class_name}'",
                )
            new_obj = SOLString(obj.value)
        case "Nil":
            # Nil is singleton — from: always returns the same nil
            return _NIL
        case "True":
            return _TRUE
        case "False":
            return _FALSE
        case _:
            # User-defined subclass — must be compatible with any built-in parent
            new_obj = _instantiate_subclass(class_name, obj)

    # Shallow copy of instance attributes (spec: mělká kopie)
    new_obj.attributes = dict(obj.attributes)
    return new_obj


def _instantiate_subclass(class_name: str, obj: SOLObject) -> SOLObject:
    """
    For user-defined subclasses of built-in types (e.g. Factorial(Integer)).
    Copies the internal value from obj.
    """

    # Check compatibility: if obj has an internal value, the new class must too
    if isinstance(obj, SOLInteger):
        new_instance = SOLInteger(obj.value)
        new_instance.class_name = class_name
        return new_instance
    elif isinstance(obj, SOLString):
        raise InterpreterError(
            error_code=ErrorCode.INT_INVALID_ARG,
            message=(
                f"Cannot create '{class_name}' from '{obj.class_name}': "
                f"incompatible internal attributes (error 53)"
            ),
        )
    elif isinstance(obj, SOLInstance):
        return SOLInstance(class_name)

    raise InterpreterError(
        error_code=ErrorCode.INT_INVALID_ARG,
        message=(
            f"Cannot create '{class_name}' from '{obj.class_name}': "
            f"incompatible internal attributes (error 53)"
        ),
    )


# ------------------------------------------------------------------
# Equality
# ------------------------------------------------------------------

def _sol_equal(a: SOLObject, b: SOLObject) -> bool:
    """
    Standard SOL26 equality.
    For objects with internal attributes (Integer, String, Bool): compare values.
    For others (instances, nil): use identity.
    """
    if isinstance(a, SOLInteger) and isinstance(b, SOLInteger):
        return a.value == b.value
    if isinstance(a, SOLString) and isinstance(b, SOLString):
        return a.value == b.value
    if isinstance(a, SOLBool) and isinstance(b, SOLBool):
        return a.value == b.value
    if isinstance(a, SOLNil) and isinstance(b, SOLNil):
        return True
    return a is b


# ------------------------------------------------------------------
# Assertion helpers
# ------------------------------------------------------------------

def _assert_integer(arg: SOLObject, selector: str) -> None:
    """Raise INT_OTHER 52 if argument is not SOLInteger."""
    if not isinstance(arg, SOLInteger):
        raise InterpreterError(
            error_code=ErrorCode.INT_OTHER,  # ← ZMENA: 52 namiesto 51
            message=f"'{selector}' expects Integer argument, got '{arg.class_name}'",
        )


def _assert_block(obj: SOLObject, selector: str, expected_arity: int) -> None:
    """Raise INT_DNU if obj is not a SOLBlock with the expected arity."""
    if not isinstance(obj, SOLBlock):
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"'{selector}' expects Block argument, got '{obj.class_name}'",
        )
    actual = len(obj.block_def.parameters)  # type: ignore[union-attr]
    if actual != expected_arity:
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=(
                f"'{selector}' expects block with arity {expected_arity}, "
                f"got arity {actual}"
            ),
        )


def _int(obj: SOLObject) -> int:
    """Extract int value from SOLInteger — caller must assert type first."""
    assert isinstance(obj, SOLInteger)
    return obj.value
