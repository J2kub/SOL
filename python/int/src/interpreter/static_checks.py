"""SOL26 static semantic checks."""

from __future__ import annotations

from interpreter.class_table import ClassTable
from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, ClassDef, Expr, Program


def run_static_checks(program: Program, class_table: ClassTable) -> None:
    """Run all static semantic checks before execution."""
    _check_no_duplicate_classes(program)
    _check_no_duplicate_methods(program)
    _check_main_exists(program)
    _check_parent_classes_exist(program, class_table)
    _check_method_arities(program)
    _check_duplicate_params(program)
    _check_assign_to_params(program)
    _check_class_literals_exist(program, class_table)


# ------------------------------------------------------------------
# Individual checks
# ------------------------------------------------------------------


def _check_no_duplicate_classes(program: Program) -> None:
    """
    Check that no class is defined twice (error 35).

    Note: collision with built-in names is handled by ClassTable.register().
    """
    seen: set[str] = set()
    for class_def in program.classes:
        if class_def.name in seen:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ERROR,
                message=f"Duplicate class definition: '{class_def.name}'",
            )
        seen.add(class_def.name)


def _check_no_duplicate_methods(program: Program) -> None:
    """Check that no class defines the same method selector twice (error 35)."""
    for class_def in program.classes:
        seen: set[str] = set()
        for method in class_def.methods:
            if method.selector in seen:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR,
                    message=(
                        f"Duplicate method '{method.selector}' "
                        f"in class '{class_def.name}'"
                    ),
                )
            seen.add(method.selector)


def _check_main_exists(program: Program) -> None:
    """
    Check that class Main with a zero-arity method run exists (error 31).
    """
    for class_def in program.classes:
        if class_def.name == "Main":
            for method in class_def.methods:
                if method.selector == "run":
                    if method.block.arity != 0:
                        raise InterpreterError(
                            error_code=ErrorCode.SEM_MAIN,
                            message="Method 'run' in class 'Main' must have arity 0",
                        )
                    return
            raise InterpreterError(
                error_code=ErrorCode.SEM_MAIN,
                message="Class 'Main' is missing method 'run'",
            )

    raise InterpreterError(
        error_code=ErrorCode.SEM_MAIN,
        message="Missing class 'Main'",
    )


def _check_parent_classes_exist(
    program: Program,
    class_table: ClassTable,
) -> None:
    """
    Check that all declared parent classes exist (error 32).

    We must consider both built-in classes and all user-defined classes
    in the program.
    """
    known = _collect_known_classes(program, class_table)

    for class_def in program.classes:
        if class_def.parent not in known:
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF,
                message=(
                    f"Class '{class_def.name}' inherits from unknown class "
                    f"'{class_def.parent}'"
                ),
            )


def _check_method_arities(program: Program) -> None:
    """
    Check that the block arity matches the selector arity for every method (error 33).

    Selector arity = number of colons in the selector.
    Also verifies that the number of declared parameters matches the block arity.
    """
    for class_def in program.classes:
        _check_class_method_arities(class_def)


def _check_class_method_arities(class_def: ClassDef) -> None:
    """Check method arities for a single class."""
    for method in class_def.methods:
        selector_arity = method.selector.count(":")

        if method.block.arity != selector_arity:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ARITY,
                message=(
                    f"Method '{method.selector}' in class '{class_def.name}': "
                    f"selector arity {selector_arity} "
                    f"!= block arity {method.block.arity}"
                ),
            )

        if len(method.block.parameters) != method.block.arity:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ARITY,
                message=(
                    f"Method '{method.selector}' in class '{class_def.name}': "
                    f"block arity {method.block.arity} "
                    f"!= parameter count {len(method.block.parameters)}"
                ),
            )


def _check_duplicate_params(program: Program) -> None:
    """
    Check for duplicate parameter names within any block (error 35).

    Recursively checks all nested blocks inside method bodies.
    """
    for class_def in program.classes:
        for method in class_def.methods:
            _check_block_duplicate_params(
                method.block,
                context=f"{class_def.name}.{method.selector}",
            )


def _check_block_duplicate_params(block: Block, context: str) -> None:
    """
    Check for duplicate parameter names in this block,
    then recursively check all nested blocks in expressions.
    """
    seen: set[str] = set()

    for param in block.parameters:
        if param.name in seen:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ERROR,
                message=(
                    f"Duplicate parameter name '{param.name}' "
                    f"in block of '{context}'"
                ),
            )
        seen.add(param.name)

    for assign in block.assigns:
        _check_expr_for_duplicate_params(assign.expr, context)


def _check_expr_for_duplicate_params(expr: Expr, context: str) -> None:
    """Recursively find nested block literals and check duplicate parameters."""
    if expr.block is not None:
        _check_block_duplicate_params(expr.block, context)

    if expr.send is not None:
        _check_expr_for_duplicate_params(expr.send.receiver, context)
        for arg in expr.send.args:
            _check_expr_for_duplicate_params(arg.expr, context)


def _check_assign_to_params(program: Program) -> None:
    """
    Check that no assignment targets a formal block parameter (error 34).

    Recursively checks nested blocks as well.
    """
    for class_def in program.classes:
        for method in class_def.methods:
            _check_block_assign_to_params(
                method.block,
                context=f"{class_def.name}.{method.selector}",
            )


def _check_block_assign_to_params(block: Block, context: str) -> None:
    """Check assignment targets in this block and nested blocks."""
    param_names = {param.name for param in block.parameters}

    for assign in block.assigns:
        if assign.var.name in param_names:
            raise InterpreterError(
                error_code=ErrorCode.SEM_ASSIGN,
                message=(
                    f"Assignment to formal parameter '{assign.var.name}' "
                    f"in block of '{context}'"
                ),
            )

        _check_expr_for_assign_to_params(assign.expr, context)


def _check_expr_for_assign_to_params(expr: Expr, context: str) -> None:
    """Recurse into nested block literals to check assignments to params."""
    if expr.block is not None:
        _check_block_assign_to_params(expr.block, context)

    if expr.send is not None:
        _check_expr_for_assign_to_params(expr.send.receiver, context)
        for arg in expr.send.args:
            _check_expr_for_assign_to_params(arg.expr, context)


def _check_class_literals_exist(
    program: Program,
    class_table: ClassTable,
) -> None:
    """Check that all class literals reference known classes (error 32)."""
    known = _collect_known_classes(program, class_table)

    for class_def in program.classes:
        for method in class_def.methods:
            _check_block_class_literals(
                method.block,
                known,
                context=f"{class_def.name}.{method.selector}",
            )


def _check_block_class_literals(
    block: Block,
    known: set[str],
    context: str,
) -> None:
    """Check all expressions in a block for unknown class literals."""
    for assign in block.assigns:
        _check_expr_class_literals(assign.expr, known, context)


def _check_expr_class_literals(
    expr: Expr,
    known: set[str],
    context: str,
) -> None:
    """Recursively check an expression tree for unknown class literals."""
    if expr.literal is not None:
        if expr.literal.class_name == "class" and expr.literal.value not in known:
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF,
                message=(
                    f"Unknown class literal '{expr.literal.value}' "
                    f"in '{context}'"
                ),
            )

    if expr.block is not None:
        _check_block_class_literals(expr.block, known, context)

    if expr.send is not None:
        _check_expr_class_literals(expr.send.receiver, known, context)
        for arg in expr.send.args:
            _check_expr_class_literals(arg.expr, known, context)


def _collect_known_classes(
    program: Program,
    class_table: ClassTable,
) -> set[str]:
    """
    Collect names of all known classes.

    Includes built-ins and user-defined classes.
    """
    known: set[str] = set()

    builtin_parents = getattr(ClassTable, "BUILTIN_PARENTS", None)
    if builtin_parents is not None:
        known.update(builtin_parents.keys())

    for class_def in program.classes:
        known.add(class_def.name)

    return known
