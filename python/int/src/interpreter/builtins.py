"""
SOL26 built-in method dispatch.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Jakub Glončák <xgloncj00@stud.fit.vut.cz>
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import cast

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

# BlockInvoker type — injected from Interpreter._invoke_block
BlockInvoker = Callable[[SOLBlock, list[SOLObject]], SOLObject]

# Singletons for Nil, True, False
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

    Returns SOLObject on success, None if the selector is unknown.
    """
    result = _dispatch_object(receiver, selector, args, invoke_block)
    if result is not None:
        return result

    if isinstance(receiver, SOLInteger):
        return _dispatch_integer(receiver, selector, args, invoke_block)
    if isinstance(receiver, SOLString):
        return _dispatch_string(receiver, selector, args)
    if isinstance(receiver, SOLBool):
        return _dispatch_bool(receiver, selector, args, invoke_block)
    if isinstance(receiver, SOLNil):
        return _dispatch_nil(receiver, selector, args)
    if isinstance(receiver, SOLBlock):
        return _dispatch_block(receiver, selector, args, invoke_block)

    return None


# ------------------------------------------------------------------
# Class messages: new, from:, String read, Transcript show:
# ------------------------------------------------------------------


def dispatch_class_message(
    class_name: str,
    selector: str,
    args: list[SOLObject],
) -> SOLObject:
    """Handle class-level messages: new, from:, String read, Transcript show:."""
    match selector:
        case "new":
            return _instantiate(class_name)
        case "from:":
            if not args:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="from: requires one argument",
                )
            return _copy_from(class_name, args[0])
        case "read" if class_name == "String":
            line = sys.stdin.readline()
            if line.endswith("\n"):
                line = line[:-1]
            return SOLString(line)
        case "show:" if class_name == "Transcript":
            if not args:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Transcript show: requires one argument",
                )
            arg = args[0]
            if not isinstance(arg, SOLString):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message=f"Transcript show: expects String, got '{arg.class_name}'",
                )
            # Per spec: Transcript show: prints WITHOUT a trailing newline
            print(arg.value, end="")
            return _NIL
        case _:
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=(f"Class '{class_name}' does not understand class message '{selector}'"),
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
    result = _dispatch_object_basic(receiver, selector, args)
    if result is not None:
        return result
    return _dispatch_object_nil_checks(receiver, selector, args, invoke_block)


def _dispatch_object_basic(
    receiver: SOLObject,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Identity, equality, type checks and printing for all objects."""
    match selector:
        case "identicalTo:":
            return get_bool(receiver is args[0])
        case "equalTo:" | "=":
            return get_bool(_sol_equal(receiver, args[0]))
        case "asString" | "printString":
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
            # print: write string representation WITHOUT newline
            print(receiver.sol_as_string(), end="")
            return receiver
        case "printNl":
            # printNl: write string representation WITH trailing newline
            print(receiver.sol_as_string())
            return receiver
    return None


def _dispatch_object_nil_checks(
    receiver: SOLObject,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """ifNil:/ifNotNil: variants for all objects.

    ifNil:     — block arity 0 only (receiver is nil when fired)
    ifNotNil:  — block arity 0 OR 1:
                   arity 1 → called with the receiver as argument
                   arity 0 → called with no arguments
    ifNil:ifNotNil: / ifNotNil:ifNil: — same rules per branch
    """
    match selector:
        case "ifNil:":
            _assert_block(args[0], selector, expected_arity=0)
            block_arg = cast(SOLBlock, args[0])
            if isinstance(receiver, SOLNil):
                return invoke_block(block_arg, [])
            return receiver

        case "ifNotNil:":
            block_arg = _assert_block_arity_0_or_1(args[0], selector)
            if not isinstance(receiver, SOLNil):
                assert block_arg.block_def is not None
                actual_arity = len(block_arg.block_def.parameters)
                invoke_args = [receiver] if actual_arity == 1 else []
                return invoke_block(block_arg, invoke_args)
            return _NIL

        case "ifNil:ifNotNil:":
            if isinstance(receiver, SOLNil):
                _assert_block(args[0], selector, expected_arity=0)
                return invoke_block(cast(SOLBlock, args[0]), [])
            block_arg = _assert_block_arity_0_or_1(args[1], selector)
            assert block_arg.block_def is not None
            actual_arity = len(block_arg.block_def.parameters)
            invoke_args = [receiver] if actual_arity == 1 else []
            return invoke_block(block_arg, invoke_args)

        case "ifNotNil:ifNil:":
            if not isinstance(receiver, SOLNil):
                block_arg = _assert_block_arity_0_or_1(args[0], selector)
                assert block_arg.block_def is not None
                actual_arity = len(block_arg.block_def.parameters)
                invoke_args = [receiver] if actual_arity == 1 else []
                return invoke_block(block_arg, invoke_args)
            _assert_block(args[1], selector, expected_arity=0)
            return invoke_block(cast(SOLBlock, args[1]), [])

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
    """Dispatch messages understood by Integer."""
    result = _dispatch_integer_arithmetic(receiver, selector, args)
    if result is not None:
        return result
    return _dispatch_integer_other(receiver, selector, args, invoke_block)


def _dispatch_integer_arithmetic(
    receiver: SOLInteger,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Arithmetic and comparison messages for Integer."""
    result = _dispatch_integer_math(receiver, selector, args)
    if result is not None:
        return result
    return _dispatch_integer_cmp(receiver, selector, args)


def _dispatch_integer_math(
    receiver: SOLInteger,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Arithmetic operations (+, -, *, //, \\\\) for Integer."""
    match selector:
        case "plus:" | "+":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value + _int(args[0]))
        case "minus:" | "-":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value - _int(args[0]))
        case "multiplyBy:" | "*":
            _assert_integer(args[0], selector)
            return SOLInteger(receiver.value * _int(args[0]))
        case "divBy:" | "//":
            _assert_integer(args[0], selector)
            if _int(args[0]) == 0:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Division by zero",
                )
            return SOLInteger(receiver.value // _int(args[0]))
        case "modBy:" | "\\\\":
            _assert_integer(args[0], selector)
            if _int(args[0]) == 0:
                raise InterpreterError(
                    error_code=ErrorCode.INT_INVALID_ARG,
                    message="Modulo by zero",
                )
            return SOLInteger(receiver.value % _int(args[0]))
    return None


def _dispatch_integer_cmp(
    receiver: SOLInteger,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Comparison operations (>, <, >=, <=, equalTo:, ~=) for Integer."""
    match selector:
        case "greaterThan:" | ">":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value > _int(args[0]))
        case "lessThan:" | "<":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value < _int(args[0]))
        case "greaterOrEqualTo:" | ">=":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value >= _int(args[0]))
        case "lessOrEqualTo:" | "<=":
            _assert_integer(args[0], selector)
            return get_bool(receiver.value <= _int(args[0]))
        case "equalTo:":
            if not isinstance(args[0], SOLInteger):
                return _FALSE
            return get_bool(receiver.value == _int(args[0]))
        case "~=":
            if not isinstance(args[0], SOLInteger):
                return _TRUE
            return get_bool(receiver.value != _int(args[0]))
    return None


def _dispatch_integer_other(
    receiver: SOLInteger,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """Non-arithmetic messages for Integer (conversion, repetition)."""
    match selector:
        case "asString" | "printString":
            return SOLString(str(receiver.value))
        case "asInteger":
            return receiver
        case "print":
            print(receiver.sol_as_string(), end="")
            return receiver
        case "printNl":
            print(receiver.sol_as_string())
            return receiver
        case "timesRepeat:":
            return _integer_times_repeat(receiver, args, invoke_block)
    return None


def _integer_times_repeat(
    receiver: SOLInteger,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject:
    """Implement Integer>>timesRepeat: for arity 0 and 1 blocks."""
    block = args[0]
    if not isinstance(block, SOLBlock):
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"'timesRepeat:' expects Block argument, got '{block.class_name}'",
        )
    assert block.block_def is not None
    arity = len(block.block_def.parameters)
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
        message=f"'timesRepeat:' expects block with arity 0 or 1, got arity {arity}",
    )


# ------------------------------------------------------------------
# String
# ------------------------------------------------------------------


def _dispatch_string(
    receiver: SOLString,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Dispatch messages understood by String."""
    match selector:
        case "print":
            print(receiver.value, end="")
            return receiver
        case "printNl":
            print(receiver.value)
            return receiver
        case "equalTo:" | "=":
            if not isinstance(args[0], SOLString):
                return _FALSE
            return get_bool(receiver.value == args[0].value)
        case "asString" | "printString":
            return receiver
        case "asInteger":
            try:
                return SOLInteger(int(receiver.value))
            except ValueError:
                return _NIL
        case "concatenateWith:" | ",":
            if not isinstance(args[0], SOLString):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message=(
                        f"'{selector}' expects String argument, "
                        f"got '{args[0].class_name}'"
                    ),
                )
            return SOLString(receiver.value + args[0].value)
        case "length" | "size":
            return SOLInteger(len(receiver.value))
        case "startsWith:endsBefore:":
            return _string_substring(receiver, args)
    return None


def _string_substring(receiver: SOLString, args: list[SOLObject]) -> SOLObject:
    """Implement String>>startsWith:endsBefore: (1-based, end-exclusive)."""
    if not isinstance(args[0], SOLInteger) or not isinstance(args[1], SOLInteger):
        return _NIL
    start = args[0].value
    end = args[1].value
    if start <= 0 or end <= 0:
        return _NIL
    if end - start <= 0:
        return SOLString("")
    return SOLString(receiver.value[start - 1 : end - 1])


# ------------------------------------------------------------------
# Bool (True / False)
# ------------------------------------------------------------------


def _dispatch_bool(
    receiver: SOLBool,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """Dispatch messages understood by True/False."""
    result = _dispatch_bool_conditionals(receiver, selector, args, invoke_block)
    if result is not None:
        return result
    return _dispatch_bool_other(receiver, selector, args, invoke_block)


def _dispatch_bool_conditionals(
    receiver: SOLBool,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """ifTrue:/ifFalse: and combined variants for Bool."""
    match selector:
        case "ifTrue:":
            _assert_block(args[0], selector, expected_arity=0)
            if receiver.value:
                return invoke_block(cast(SOLBlock, args[0]), [])
            return _NIL
        case "ifFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            if not receiver.value:
                return invoke_block(cast(SOLBlock, args[0]), [])
            return _NIL
        case "ifTrue:ifFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            _assert_block(args[1], selector, expected_arity=0)
            if receiver.value:
                return invoke_block(cast(SOLBlock, args[0]), [])
            return invoke_block(cast(SOLBlock, args[1]), [])
        case "ifFalse:ifTrue:":
            _assert_block(args[0], selector, expected_arity=0)
            _assert_block(args[1], selector, expected_arity=0)
            if not receiver.value:
                return invoke_block(cast(SOLBlock, args[0]), [])
            return invoke_block(cast(SOLBlock, args[1]), [])
    return None


def _dispatch_bool_other(
    receiver: SOLBool,
    selector: str,
    args: list[SOLObject],
    invoke_block: BlockInvoker,
) -> SOLObject | None:
    """not, and:, or:, equality and printing for Bool."""
    match selector:
        case "not":
            return get_bool(not receiver.value)
        case "and:" | "&":
            _assert_block(args[0], selector, expected_arity=0)
            if not receiver.value:
                return _FALSE
            result = invoke_block(cast(SOLBlock, args[0]), [])
            if not isinstance(result, SOLBool):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="'and:' block must return a Bool",
                )
            return result
        case "or:" | "|":
            _assert_block(args[0], selector, expected_arity=0)
            if receiver.value:
                return _TRUE
            result = invoke_block(cast(SOLBlock, args[0]), [])
            if not isinstance(result, SOLBool):
                raise InterpreterError(
                    error_code=ErrorCode.INT_OTHER,
                    message="'or:' block must return a Bool",
                )
            return result
        case "equalTo:" | "=":
            if not isinstance(args[0], SOLBool):
                return _FALSE
            return get_bool(receiver.value == args[0].value)
        case "asString" | "printString":
            return SOLString("true" if receiver.value else "false")
        case "isBoolean":
            return _TRUE
        case "print":
            print(receiver.sol_as_string(), end="")
            return receiver
        case "printNl":
            print(receiver.sol_as_string())
            return receiver
    return None


# ------------------------------------------------------------------
# Nil
# ------------------------------------------------------------------


def _dispatch_nil(
    receiver: SOLNil,
    selector: str,
    args: list[SOLObject],
) -> SOLObject | None:
    """Dispatch messages understood by Nil."""
    match selector:
        case "isNil":
            return _TRUE
        case "notNil":
            return _FALSE
        case "asString" | "printString":
            return SOLString("nil")
        case "equalTo:" | "=":
            return get_bool(isinstance(args[0], SOLNil))
        case "print":
            print("nil", end="")
            return receiver
        case "printNl":
            print("nil")
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
    """Dispatch messages understood by Block."""
    assert receiver.block_def is not None
    expected_arity = len(receiver.block_def.parameters)
    n = expected_arity
    expected_selector = "value" if n == 0 else ":".join(["value"] * n) + ":"

    match selector:
        case s if s == expected_selector:
            return invoke_block(receiver, args)

        case "whileTrue:":
            _assert_block(args[0], selector, expected_arity=0)
            return _while_loop(receiver, cast(SOLBlock, args[0]), invoke_block, while_true=True)

        case "whileFalse:":
            _assert_block(args[0], selector, expected_arity=0)
            return _while_loop(receiver, cast(SOLBlock, args[0]), invoke_block, while_true=False)

        case s if s.startswith("value"):
            raise InterpreterError(
                error_code=ErrorCode.INT_DNU,
                message=(
                    f"Block expects '{expected_selector}' "
                    f"but received '{selector}' (arity mismatch)"
                ),
            )
    return None


def _while_loop(
    cond_block: SOLBlock,
    body_block: SOLBlock,
    invoke_block: BlockInvoker,
    *,
    while_true: bool,
) -> SOLObject:
    """Shared implementation for whileTrue: and whileFalse:."""
    selector = "whileTrue:" if while_true else "whileFalse:"
    result: SOLObject = _NIL
    while True:
        cond = invoke_block(cond_block, [])
        if not isinstance(cond, SOLBool):
            raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,
                message=f"'{selector}' condition block must return Bool",
            )
        if cond.value != while_true:
            break
        result = invoke_block(body_block, [])
    return result


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
            raise InterpreterError(
                error_code=ErrorCode.INT_OTHER,
                message="Block new is not yet supported",
            )
        case _:
            return SOLInstance(class_name)


def _copy_from(class_name: str, obj: SOLObject) -> SOLObject:
    """Implement ClassName from: obj — shallow-copy with optional type coercion."""
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
            return _NIL
        case "True":
            return _TRUE
        case "False":
            return _FALSE
        case _:
            new_obj = _instantiate_subclass(class_name, obj)

    # Shallow-copy instance attributes from source object
    new_obj.attributes = dict(obj.attributes)
    return new_obj


def _instantiate_subclass(class_name: str, obj: SOLObject) -> SOLObject:
    """Create a subclass instance from an existing object (from: on user-defined class)."""
    if isinstance(obj, SOLInteger):
        new_instance = SOLInteger(obj.value)
        new_instance.class_name = class_name
        # attributes copied by caller (_copy_from)
        return new_instance
    if isinstance(obj, SOLString):
        raise InterpreterError(
            error_code=ErrorCode.INT_INVALID_ARG,
            message=(
                f"Cannot create '{class_name}' from '{obj.class_name}': "
                f"incompatible internal attributes (error 53)"
            ),
        )
    if isinstance(obj, SOLInstance):
        new_instance2 = SOLInstance(class_name)
        # attributes copied by caller (_copy_from)
        return new_instance2

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
    """Value equality for built-in types; identity fallback for instances."""
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
    """Raise INT_OTHER if arg is not an Integer."""
    if not isinstance(arg, SOLInteger):
        raise InterpreterError(
            error_code=ErrorCode.INT_OTHER,
            message=f"'{selector}' expects Integer argument, got '{arg.class_name}'",
        )


def _assert_block(obj: SOLObject, selector: str, expected_arity: int) -> None:
    """Raise INT_DNU if obj is not a Block or has the wrong arity."""
    if not isinstance(obj, SOLBlock):
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"'{selector}' expects Block argument, got '{obj.class_name}'",
        )
    assert obj.block_def is not None
    actual = len(obj.block_def.parameters)
    if actual != expected_arity:
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=(
                f"'{selector}' expects block with arity {expected_arity}, got arity {actual}"
            ),
        )


def _assert_block_arity_0_or_1(obj: SOLObject, selector: str) -> SOLBlock:
    """Raise INT_DNU if obj is not a Block or has arity other than 0 or 1."""
    if not isinstance(obj, SOLBlock):
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"'{selector}' expects Block argument, got '{obj.class_name}'",
        )
    assert obj.block_def is not None
    actual = len(obj.block_def.parameters)
    if actual not in (0, 1):
        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=(
                f"'{selector}' expects block with arity 0 or 1, got arity {actual}"
            ),
        )
    return obj


def _int(obj: SOLObject) -> int:
    """Unwrap a guaranteed-Integer SOLObject to a Python int."""
    assert isinstance(obj, SOLInteger)
    return obj.value
