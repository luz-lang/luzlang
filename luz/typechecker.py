# typechecker.py
#
# Compile-time type analysis pass for Luz.
# Runs after the Parser produces an AST and before the Interpreter executes it.
#
# Goals for v1.8:
#   - Infer the type of every literal and annotated variable.
#   - Verify typed variable declarations match the assigned value.
#   - Record function signatures (param types + return type).
#   - Verify argument types at call sites for annotated functions.
#   - Verify return statements match the declared return type.
#   - Catch arithmetic operations between incompatible types (e.g. string + int).
#
# Goals for v1.9:
#   - Unused variable / import / parameter detection (Go-style: errors, not warnings).
#     Names prefixed with '_' are exempt from unused checks.
#
# Non-goals (future):
#   - Generic / parameterised types  e.g. list[int]
#   - Full inference across branches (if/else, loops)
#
# The checker collects ALL errors rather than stopping at the first one.

from __future__ import annotations
from dataclasses import dataclass, field as dc_field
from typing import Optional

from luz.parser import (
    NumberNode, StringNode, FStringNode, BooleanNode, NullNode,
    ListNode, DictNode, TupleNode,
    VarAssignNode, TypedVarAssignNode, ConstDefNode, StructDefNode, VarAccessNode,
    BinOpNode, UnaryOpNode,
    FuncDefNode, LambdaNode, AnonFuncNode, ReturnNode,
    CallNode, ExprCallNode, MethodCallNode,
    IfNode, WhileNode, ForNode, ForEachNode,
    ClassDefNode, AttributeAccessNode, AttributeAssignNode,
    ImportNode, AttemptRescueNode, AlertNode,
    IndexAccessNode, SliceNode, IndexAssignNode,
    ListCompNode, TernaryNode, NullCoalesceNode,
    DestructureAssignNode, DictDestructureAssignNode,
    SwitchNode, MatchNode,
    BreakNode, ContinueNode, PassNode,
)
from luz.lexer import TokenType


# ── Type constants ────────────────────────────────────────────────────────────

class T:
    """Namespace for Luz type name constants (mirrors typeof() return values)."""
    UNKNOWN  = "unknown"   # type could not be determined — skip checks
    INT      = "int"
    FLOAT    = "float"
    NUMBER   = "number"    # int or float
    STRING   = "string"
    BOOL     = "bool"
    NULL     = "null"
    LIST     = "list"
    DICT     = "dict"
    FUNCTION = "function"

    # Fixed-size integer types
    INT8   = "int8"
    INT16  = "int16"
    INT32  = "int32"
    INT64  = "int64"
    UINT8  = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"

    # Fixed-size float types
    FLOAT32 = "float32"
    FLOAT64 = "float64"

    # Sets for group membership checks
    FIXED_INTS  = {"int8", "int16", "int32", "int64",
                   "uint8", "uint16", "uint32", "uint64"}
    FIXED_FLOATS = {"float32", "float64"}
    NUMERIC = {INT, FLOAT, NUMBER} | FIXED_INTS | FIXED_FLOATS

    @staticmethod
    def compatible(declared: str, actual: str) -> bool:
        """Return True if `actual` satisfies a `declared` type constraint."""
        if declared == T.UNKNOWN or actual == T.UNKNOWN:
            return True
        if declared == actual:
            return True
        # Nullable type: T? accepts null or any value compatible with T
        if declared.endswith('?'):
            if actual == T.NULL:
                return True
            return T.compatible(declared[:-1], actual)
        if declared == T.NUMBER and actual in (T.INT, T.FLOAT):
            return True
        # Any fixed-size int satisfies 'int' or 'number'
        if actual in T.FIXED_INTS and declared in (T.INT, T.NUMBER):
            return True
        # Any fixed-size float satisfies 'float' or 'number'
        if actual in T.FIXED_FLOATS and declared in (T.FLOAT, T.NUMBER):
            return True
        # Fixed-size int satisfies a wider fixed-size int (widening only)
        # e.g. int8 value is compatible with int16/int32/int64 annotation
        _INT_WIDTH = {"int8": 8, "int16": 16, "int32": 32, "int64": 64}
        _UINT_WIDTH = {"uint8": 8, "uint16": 16, "uint32": 32, "uint64": 64}
        if actual in _INT_WIDTH and declared in _INT_WIDTH:
            return _INT_WIDTH[actual] <= _INT_WIDTH[declared]
        if actual in _UINT_WIDTH and declared in _UINT_WIDTH:
            return _UINT_WIDTH[actual] <= _UINT_WIDTH[declared]
        # float32 satisfies float64
        if actual == T.FLOAT32 and declared == T.FLOAT64:
            return True
        
        if '[' in declared:
            base = declared[:declared.index('[')]
            # bare list/dict literal satisfies list[T]/dict[K,V]
            if declared == actual or actual == base:
                return True
            return False
        if '[' in actual:
            base = actual[:actual.index('[')]
            return declared == base
        return False

    @staticmethod
    def of_literal(node) -> str:
        if isinstance(node, NumberNode):
            return T.INT if node.token.type == TokenType.INT else T.FLOAT
        if isinstance(node, (StringNode, FStringNode)):
            return T.STRING
        if isinstance(node, BooleanNode):
            return T.BOOL
        if isinstance(node, NullNode):
            return T.NULL
        if isinstance(node, ListNode):
            return T.LIST
        if isinstance(node, DictNode):
            return T.DICT
        if isinstance(node, (LambdaNode, AnonFuncNode, FuncDefNode)):
            return T.FUNCTION
        return T.UNKNOWN


# ── Error representation ──────────────────────────────────────────────────────

@dataclass
class TypeCheckError:
    message: str
    line: Optional[int] = None
    col:  Optional[int] = None
    fault_kind: str = "TypeCheckFault"

    def __str__(self):
        loc = f"line {self.line}" if self.line else "unknown location"
        if self.col:
            loc += f", col {self.col}"
        return f"{self.fault_kind} at {loc}: {self.message}"


# ── Per-binding metadata (for usage tracking) ────────────────────────────────

@dataclass
class _Binding:
    typ: str
    token: object = None         # source token; None means "don't track usage"
    is_import: bool = False
    is_param: bool = False
    used: bool = False


# ── Type environment ──────────────────────────────────────────────────────────

class TypeEnv:
    def __init__(self, parent: Optional[TypeEnv] = None):
        self._bindings: dict[str, _Binding] = {}
        self._constants: set = set()
        self.parent = parent

    # ── Core type operations ──────────────────────────────────────────────────

    def define(self, name: str, typ: str, *,
               token=None, is_import: bool = False, is_param: bool = False):
        """Define a new binding in this scope.
        Pass `token` to opt-in to unused-variable tracking.
        Names starting with '_' are always exempt from unused checks."""
        track_tok = token if (token is not None and not name.startswith('_')) else None
        self._bindings[name] = _Binding(typ, track_tok, is_import, is_param)

    def define_const(self, name: str, typ: str, *, token=None):
        track_tok = token if (token is not None and not name.startswith('_')) else None
        self._bindings[name] = _Binding(typ, track_tok)
        self._constants.add(name)

    def is_const(self, name: str) -> bool:
        if name in self._constants:
            return True
        if self.parent:
            return self.parent.is_const(name)
        return False

    def is_defined(self, name: str) -> bool:
        """Return True if name is defined anywhere in this scope chain."""
        if name in self._bindings:
            return True
        if self.parent:
            return self.parent.is_defined(name)
        return False

    def update(self, name: str, typ: str):
        if name in self._bindings:
            self._bindings[name].typ = typ
        elif self.parent:
            self.parent.update(name, typ)
        else:
            self._bindings[name] = _Binding(typ)

    def lookup(self, name: str) -> str:
        if name in self._bindings:
            return self._bindings[name].typ
        if self.parent:
            return self.parent.lookup(name)
        return T.UNKNOWN

    # ── Usage tracking ────────────────────────────────────────────────────────

    def mark_used(self, name: str):
        """Walk up scope chain and mark the binding as used where it is defined."""
        if name in self._bindings:
            self._bindings[name].used = True
        elif self.parent:
            self.parent.mark_used(name)

    def own_unused(self) -> list:
        """Return (name, _Binding) for tracked but unused bindings in THIS scope."""
        return [(n, b) for n, b in self._bindings.items()
                if b.token is not None and not b.used]


# ── Function signature ────────────────────────────────────────────────────────

@dataclass
class FuncSignature:
    param_names: list
    param_types: list
    return_type: str
    is_variadic: bool = False
    min_arity:   int  = -1   # -1 means "same as len(param_types)" (no defaults)


# ── Type checker ──────────────────────────────────────────────────────────────

class TypeChecker:
    """
    Walks the AST and collects type errors without executing any code.

    Usage:
        errors = TypeChecker().check(ast)   # list[TypeCheckError]
    """

    def __init__(self):
        self.errors: list[TypeCheckError] = []
        self.env = TypeEnv()
        self._functions: dict[str, FuncSignature] = {}
        self._current_return_type: str = T.UNKNOWN
        self._in_function_depth: int = 0   # > 0 when inside a function/lambda body
        # Maps class_name -> {attr_name -> inferred_type}, built from init bodies.
        self._class_attrs: dict[str, dict[str, str]] = {}
        # Set to the class name while visiting its init method so that
        # visit_AttributeAssignNode can record self.<attr> types.
        self._collecting_attrs_for: str | None = None
        # Definite assignment analysis: tracks names that are definitely
        # initialized at the current point in the current function.
        self._definite: set[str] = set()
        self._definite_stack: list[set[str]] = []
        self._setup_builtins()

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, ast: list) -> list[TypeCheckError]:
        for node in ast:
            self.visit(node)
        # Check unused imports at global scope (locals at global scope are exempt)
        self._report_unused(self.env, check_locals=False, check_imports=True)
        return self.errors

    # ── Visitor dispatch ──────────────────────────────────────────────────────

    def visit(self, node) -> str:
        method = f"visit_{type(node).__name__}"
        return getattr(self, method, self._visit_unknown)(node)

    def _visit_unknown(self, _) -> str:
        return T.UNKNOWN

    def _tok_loc(self, token):
        """Extract (line, col) from a token, returning (None, None) if absent."""
        return getattr(token, "line", None), getattr(token, "col", None)

    def _err(self, message, token=None, line=None, col=None):
        if token is not None:
            line, col = self._tok_loc(token)
        self.errors.append(TypeCheckError(message, line, col))

    def _env_all_names(self, env: TypeEnv) -> set[str]:
        """Collect all names defined anywhere in the given env chain."""
        names: set[str] = set()
        e: Optional[TypeEnv] = env
        while e is not None:
            names |= set(e._bindings.keys())
            e = e.parent
        return names

    def _report_unused(self, env: TypeEnv, *,
                       check_locals: bool = True, check_imports: bool = True):
        """Append errors for every tracked-but-unused binding in `env`."""
        for name, b in env.own_unused():
            line = getattr(b.token, 'line', None)
            col  = getattr(b.token, 'col',  None)
            if b.is_import and check_imports:
                self.errors.append(TypeCheckError(
                    f"Import '{name}' imported but never used",
                    line, col, fault_kind="UnusedImportFault"
                ))
            elif not b.is_import and check_locals:
                kind = "Parameter" if b.is_param else "Variable"
                self.errors.append(TypeCheckError(
                    f"{kind} '{name}' declared but never used",
                    line, col, fault_kind="UnusedVariableFault"
                ))

    # ── Literals ─────────────────────────────────────────────────────────────

    def visit_NumberNode(self, node) -> str:
        return T.INT if node.token.type == TokenType.INT else T.FLOAT

    def visit_StringNode(self, _)  -> str: return T.STRING
    def visit_FStringNode(self, n) -> str:
        for part in n.parts:
            if not isinstance(part, str):
                self.visit(part)
        return T.STRING
    def visit_BooleanNode(self, _) -> str: return T.BOOL
    def visit_NullNode(self, _)    -> str: return T.NULL

    def visit_ListNode(self, node) -> str:
        for el in node.elements:
            self.visit(el)
        return T.LIST

    def visit_DictNode(self, node) -> str:
        for k, v in node.pairs:
            self.visit(k); self.visit(v)
        return T.DICT

    def visit_TupleNode(self, node) -> str:
        for el in node.elements:
            self.visit(el)
        return T.UNKNOWN

    # ── Variables ─────────────────────────────────────────────────────────────

    def visit_VarAccessNode(self, node) -> str:
        name = node.token.value
        self.env.mark_used(name)
        if (self._in_function_depth > 0
                and name not in self._definite
                and name != 'super'):
            line, col = self._tok_loc(node.token)
            self.errors.append(TypeCheckError(
                f"Variable '{name}' may be used before being assigned",
                line, col, fault_kind="UninitializedFault"
            ))
        return self.env.lookup(name)

    def visit_VarAssignNode(self, node) -> str:
        name = node.var_name_token.value
        if self.env.is_const(name):
            self._err(f"Cannot reassign constant '{name}'", token=node.var_name_token)
        typ = self.visit(node.value_node)
        # Track as a new local when we're inside a function and this is its first appearance
        if self._in_function_depth > 0 and not self.env.is_defined(name):
            self.env.define(name, typ, token=node.var_name_token)
        else:
            self.env.update(name, typ)
        self._definite.add(name)
        return typ

    def visit_ConstDefNode(self, node) -> str:
        actual = self.visit(node.value_node)
        declared = node.type_name or actual
        if node.type_name and not T.compatible(node.type_name, actual):
            self._err(
                f"Constant '{node.var_token.value}' declared as '{node.type_name}' "
                f"but assigned a '{actual}' value",
                token=node.var_token
            )
        # Track if inside a function (consts at global level are module-level constants)
        tok = node.var_token if self._in_function_depth > 0 else None
        self.env.define_const(node.var_token.value, declared, token=tok)
        self._definite.add(node.var_token.value)
        return declared

    def visit_TypedVarAssignNode(self, node) -> str:
        declared = node.type_name
        actual   = self.visit(node.value_node)
        if not T.compatible(declared, actual):
            self._err(
                f"Variable '{node.var_token.value}' declared as '{declared}' "
                f"but assigned a '{actual}' value",
                token=node.var_token
            )
        # Typed declarations are always first-time definitions; track if in function
        if self._in_function_depth > 0:
            self.env.define(node.var_token.value, declared, token=node.var_token)
        else:
            self.env.update(node.var_token.value, declared)
        self._definite.add(node.var_token.value)
        return declared

    def visit_DestructureAssignNode(self, node) -> str:
        self.visit(node.value_node)
        for t in node.var_tokens:
            if self._in_function_depth > 0 and not self.env.is_defined(t.value):
                self.env.define(t.value, T.UNKNOWN, token=t)
            else:
                self.env.update(t.value, T.UNKNOWN)
            self._definite.add(t.value)
        return T.UNKNOWN

    def visit_DictDestructureAssignNode(self, node) -> str:
        self.visit(node.value_node)
        for t in node.key_tokens:
            if self._in_function_depth > 0 and not self.env.is_defined(t.value):
                self.env.define(t.value, T.UNKNOWN, token=t)
            else:
                self.env.update(t.value, T.UNKNOWN)
            self._definite.add(t.value)
        return T.UNKNOWN

    # ── Binary / Unary ops ────────────────────────────────────────────────────

    _NUMERIC_OPS = {
        TokenType.MINUS, TokenType.MUL, TokenType.DIV,
        TokenType.IDIV, TokenType.MOD, TokenType.POW,
        TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE,
    }
    _PLUS_COMPATIBLE = {T.INT, T.FLOAT, T.NUMBER, T.STRING, T.LIST}

    def visit_BinOpNode(self, node) -> str:
        left  = self.visit(node.left_node)
        right = self.visit(node.right_node)
        op    = node.op_token.type

        if T.UNKNOWN not in (left, right):
            if op in self._NUMERIC_OPS:
                for typ, side in ((left, "left"), (right, "right")):
                    if typ not in T.NUMERIC and typ != T.UNKNOWN:
                        self._err(
                            f"Operator '{node.op_token.value}' requires a number "
                            f"but {side} operand is '{typ}'",
                            token=node.op_token
                        )
            elif op == TokenType.PLUS:
                if left in self._PLUS_COMPATIBLE and right in self._PLUS_COMPATIBLE:
                    if left != right and not ({left, right} <= T.NUMERIC):
                        self._err(
                            f"Operator '+' cannot combine '{left}' and '{right}'",
                            token=node.op_token
                        )

        return self._binop_result(op, left, right)

    def _binop_result(self, op, left, right) -> str:
        bool_ops = {TokenType.EE, TokenType.NE,
                    TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE,
                    TokenType.AND, TokenType.OR, TokenType.NOT,
                    TokenType.IN, TokenType.NOT_IN}
        if op in bool_ops:
            return T.BOOL
        if op == TokenType.DIV:
            return T.FLOAT
        if op == TokenType.IDIV:
            return T.INT
        if op in (TokenType.MINUS, TokenType.MUL, TokenType.MOD, TokenType.POW,
                  TokenType.PLUS):
            # Both operands numeric: float wins over int
            if left in T.NUMERIC and right in T.NUMERIC:
                if T.FLOAT in (left, right) or left in T.FIXED_FLOATS or right in T.FIXED_FLOATS:
                    return T.FLOAT
                return T.INT
            # Same non-numeric type (string+string, list+list) — only valid for PLUS
            if op == TokenType.PLUS and left == right and left in self._PLUS_COMPATIBLE:
                return left
        return T.UNKNOWN

    def visit_UnaryOpNode(self, node) -> str:
        typ = self.visit(node.node)
        if node.op_token.type == TokenType.NOT:
            return T.BOOL
        if node.op_token.type == TokenType.MINUS:
            if typ not in T.NUMERIC and typ != T.UNKNOWN:
                self._err(
                    f"Unary '-' requires a number, got '{typ}'",
                    token=node.op_token
                )
        return typ

    # ── Functions ─────────────────────────────────────────────────────────────

    def visit_FuncDefNode(self, node) -> str:
        param_names = [p.value for p in node.arg_tokens]
        param_types = list(node.arg_types) if node.arg_types else [T.UNKNOWN] * len(param_names)
        param_types = [t if t else T.UNKNOWN for t in param_types]
        return_type = node.return_type if node.return_type else T.UNKNOWN

        # min_arity = number of required params (those without a default value)
        defaults   = node.defaults if node.defaults else [None] * len(param_names)
        min_arity  = sum(1 for d in defaults if d is None)
        # If variadic, the variadic param itself is optional (can receive 0 args)
        if node.variadic:
            min_arity = max(0, min_arity - 1)

        sig = FuncSignature(
            param_names=param_names,
            param_types=param_types,
            return_type=return_type,
            is_variadic=bool(node.variadic),
            min_arity=min_arity,
        )
        if node.name_token:
            self._functions[node.name_token.value] = sig
            self.env.define(node.name_token.value, T.FUNCTION)

        child_env = TypeEnv(self.env)
        # The variadic param (last in arg_tokens when node.variadic is True)
        # always collects a list — override its type before defining.
        if node.variadic and param_types:
            param_types[-1] = T.LIST
        # Track parameters for unused detection
        for ptoken, ptype in zip(node.arg_tokens, param_types):
            child_env.define(ptoken.value, ptype, token=ptoken, is_param=True)

        # Definite assignment: initialize with outer scope names + params
        self._definite_stack.append(self._definite)
        self._definite = (self._env_all_names(self.env)
                          | {p.value for p in node.arg_tokens})

        saved_env, saved_ret = self.env, self._current_return_type
        self.env, self._current_return_type = child_env, return_type
        self._in_function_depth += 1

        for stmt in node.block:
            self.visit(stmt)

        self._in_function_depth -= 1
        # Report unused params and locals defined directly in this function scope
        self._report_unused(child_env, check_locals=True, check_imports=True)
        self.env, self._current_return_type = saved_env, saved_ret
        self._definite = self._definite_stack.pop()
        return T.FUNCTION

    def visit_LambdaNode(self, node) -> str:
        child_env = TypeEnv(self.env)
        for t in node.param_tokens:
            child_env.define(t.value, T.UNKNOWN, token=t, is_param=True)
        self._definite_stack.append(self._definite)
        self._definite = (self._env_all_names(self.env)
                          | {t.value for t in node.param_tokens})
        saved = self.env; self.env = child_env
        self._in_function_depth += 1
        self.visit(node.expr_node)
        self._in_function_depth -= 1
        self._report_unused(child_env, check_locals=True, check_imports=True)
        self.env = saved
        self._definite = self._definite_stack.pop()
        return T.FUNCTION

    def visit_AnonFuncNode(self, node) -> str:
        child_env = TypeEnv(self.env)
        for t in node.param_tokens:
            child_env.define(t.value, T.UNKNOWN, token=t, is_param=True)
        self._definite_stack.append(self._definite)
        self._definite = (self._env_all_names(self.env)
                          | {t.value for t in node.param_tokens})
        saved = self.env; self.env = child_env
        self._in_function_depth += 1
        for stmt in node.block:
            self.visit(stmt)
        self._in_function_depth -= 1
        self._report_unused(child_env, check_locals=True, check_imports=True)
        self.env = saved
        self._definite = self._definite_stack.pop()
        return T.FUNCTION

    def visit_ReturnNode(self, node) -> str:
        actual = self.visit(node.expression_node) if node.expression_node else T.NULL
        declared = self._current_return_type
        if not T.compatible(declared, actual):
            self._err(
                f"Function declared to return '{declared}' but returns '{actual}'"
            )
        return actual

    # ── Call sites ────────────────────────────────────────────────────────────

    def visit_CallNode(self, node) -> str:
        name = node.func_name_token.value
        arg_types = [self.visit(a) for a in node.arguments]
        for v in node.kwargs.values():
            self.visit(v)

        sig = self._functions.get(name)
        if sig and not sig.is_variadic:
            min_a  = sig.min_arity if sig.min_arity >= 0 else len(sig.param_types)
            max_a  = len(sig.param_types)
            n_args = len(arg_types) + len(node.kwargs)
            if not (min_a <= n_args <= max_a):
                if min_a == max_a:
                    self._err(
                        f"'{name}' expects {max_a} argument(s), got {n_args}",
                        token=node.func_name_token
                    )
                else:
                    self._err(
                        f"'{name}' expects {min_a}–{max_a} argument(s), got {n_args}",
                        token=node.func_name_token
                    )
            else:
                for actual, declared, pname in zip(arg_types, sig.param_types, sig.param_names):
                    if not T.compatible(declared, actual):
                        self._err(
                            f"Argument '{pname}' of '{name}' expects '{declared}', "
                            f"got '{actual}'",
                            token=node.func_name_token
                        )

        return sig.return_type if sig else T.UNKNOWN

    def visit_ExprCallNode(self, node) -> str:
        self.visit(node.callee_node)
        for a in node.arguments:
            self.visit(a)
        return T.UNKNOWN

    def visit_MethodCallNode(self, node) -> str:
        self.visit(node.obj_node)
        for a in node.arguments:
            self.visit(a)
        return T.UNKNOWN

    # ── Control flow ──────────────────────────────────────────────────────────

    def visit_IfNode(self, node) -> str:
        in_fn = self._in_function_depth > 0
        definite_before = self._definite.copy()
        branch_additions: list[set[str]] = []

        for condition, body in node.cases:
            self.visit(condition)
            child = TypeEnv(self.env)
            saved = self.env; self.env = child
            self._definite = definite_before.copy()
            for stmt in body:
                self.visit(stmt)
            branch_additions.append(self._definite - definite_before)
            self._report_unused(child, check_locals=in_fn, check_imports=True)
            self.env = saved

        has_else = bool(node.else_case)
        if node.else_case:
            child = TypeEnv(self.env)
            saved = self.env; self.env = child
            self._definite = definite_before.copy()
            for stmt in node.else_case:
                self.visit(stmt)
            branch_additions.append(self._definite - definite_before)
            self._report_unused(child, check_locals=in_fn, check_imports=True)
            self.env = saved

        # Restore and propagate only variables assigned in ALL branches
        self._definite = definite_before
        if has_else and branch_additions:
            guaranteed = branch_additions[0].copy()
            for s in branch_additions[1:]:
                guaranteed &= s
            self._definite |= guaranteed
        return T.UNKNOWN

    def visit_WhileNode(self, node) -> str:
        self.visit(node.condition_node)
        saved_definite = self._definite.copy()
        for stmt in node.block:
            self.visit(stmt)
        # Loop body does not guarantee assignments (may never execute)
        self._definite = saved_definite
        return T.UNKNOWN

    def visit_ForNode(self, node) -> str:
        self.visit(node.start_value_node)
        self.visit(node.end_value_node)
        if node.step_node:
            self.visit(node.step_node)
        in_fn = self._in_function_depth > 0
        child = TypeEnv(self.env)
        child.define(node.var_name_token.value, T.INT,
                     token=node.var_name_token if in_fn else None)
        saved = self.env; self.env = child
        saved_definite = self._definite.copy()
        self._definite.add(node.var_name_token.value)  # loop var available inside body
        for stmt in node.block:
            self.visit(stmt)
        self._definite = saved_definite  # loop body doesn't guarantee new assignments
        self._report_unused(child, check_locals=in_fn, check_imports=True)
        self.env = saved
        return T.UNKNOWN

    def visit_ForEachNode(self, node) -> str:
        self.visit(node.iterable_node)
        in_fn = self._in_function_depth > 0
        child = TypeEnv(self.env)
        child.define(node.var_name_token.value, T.UNKNOWN,
                     token=node.var_name_token if in_fn else None)
        saved = self.env; self.env = child
        saved_definite = self._definite.copy()
        self._definite.add(node.var_name_token.value)  # loop var available inside body
        for stmt in node.block:
            self.visit(stmt)
        self._definite = saved_definite  # loop body doesn't guarantee new assignments
        self._report_unused(child, check_locals=in_fn, check_imports=True)
        self.env = saved
        return T.UNKNOWN

    def visit_TernaryNode(self, node) -> str:
        self.visit(node.condition_node)
        t = self.visit(node.value_node)
        f = self.visit(node.else_node)
        return t if t == f else T.UNKNOWN

    def visit_NullCoalesceNode(self, node) -> str:
        self.visit(node.left)
        return self.visit(node.right)

    # ── Classes ───────────────────────────────────────────────────────────────

    def visit_StructDefNode(self, node) -> str:
        # Register the struct name as a callable type and visit default expressions
        self.env.define(node.name_token.value, T.UNKNOWN)
        for _, _, default_node in node.fields:
            if default_node:
                self.visit(default_node)
        return T.UNKNOWN

    def visit_ClassDefNode(self, node) -> str:
        class_name = node.name_token.value
        self.env.define(class_name, T.UNKNOWN)
        # Register the class constructor as a callable returning an instance of
        # this class.  is_variadic=True skips arity checking since we don't
        # track the full constructor signature here.
        self._functions[class_name] = FuncSignature(
            param_names=[], param_types=[], return_type=class_name, is_variadic=True
        )
        self._class_attrs[class_name] = {}
        for method in node.methods:
            is_init = (method.name_token and method.name_token.value == 'init')
            if is_init:
                self._collecting_attrs_for = class_name
            self.visit(method)
            if is_init:
                self._collecting_attrs_for = None
        return T.UNKNOWN

    def visit_AttributeAccessNode(self, node) -> str:
        obj_type = self.visit(node.obj_node)
        if obj_type in self._class_attrs:
            return self._class_attrs[obj_type].get(node.attr_token.value, T.UNKNOWN)
        return T.UNKNOWN

    def visit_AttributeAssignNode(self, node) -> str:
        self.visit(node.obj_node)
        val_type = self.visit(node.value_node)
        # While scanning the init method, record the inferred type of each
        # self.<attr> assignment (first assignment wins).
        if (self._collecting_attrs_for is not None
                and isinstance(node.obj_node, VarAccessNode)
                and node.obj_node.token.value == 'self'):
            attr = node.attr_token.value
            attrs = self._class_attrs[self._collecting_attrs_for]
            if attr not in attrs:
                attrs[attr] = val_type
        return T.UNKNOWN

    # ── Error handling ────────────────────────────────────────────────────────

    def visit_AttemptRescueNode(self, node) -> str:
        in_fn = self._in_function_depth > 0
        for stmt in node.try_block:
            self.visit(stmt)
        rescue_env = TypeEnv(self.env)
        if node.error_var_token:
            rescue_env.define(node.error_var_token.value, T.STRING,
                              token=node.error_var_token if in_fn else None)
        saved = self.env; self.env = rescue_env
        for stmt in node.catch_block:
            self.visit(stmt)
        self._report_unused(rescue_env, check_locals=in_fn, check_imports=True)
        self.env = saved
        if node.finally_block:
            for stmt in node.finally_block:
                self.visit(stmt)
        return T.UNKNOWN

    def visit_AlertNode(self, node) -> str:
        self.visit(node.expression_node)
        return T.UNKNOWN

    # ── Collections / indexing ────────────────────────────────────────────────

    def visit_IndexAccessNode(self, node) -> str:
        self.visit(node.base_node)
        self.visit(node.index_node)
        return T.UNKNOWN

    def visit_SliceNode(self, node) -> str:
        self.visit(node.base_node)
        for n in (node.start_node, node.end_node, node.step_node):
            if n: self.visit(n)
        return T.UNKNOWN

    def visit_IndexAssignNode(self, node) -> str:
        self.visit(node.base_node)
        self.visit(node.index_node)
        self.visit(node.value_node)
        return T.UNKNOWN

    def visit_ListCompNode(self, node) -> str:
        clause_var_names: list[str] = []
        for var_tok, iterable in node.clauses:
            self.visit(iterable)
            name = var_tok.value if hasattr(var_tok, 'value') else str(var_tok)
            clause_var_names.append(name)
            self._definite.add(name)
        self.visit(node.expr)
        if node.condition:
            self.visit(node.condition)
        # Clause vars are only valid inside the comprehension
        for name in clause_var_names:
            self._definite.discard(name)
        return T.LIST

    # ── Imports ───────────────────────────────────────────────────────────────

    def visit_ImportNode(self, node) -> str:
        if node.alias:
            self.env.define(node.alias.value, T.UNKNOWN, token=node.alias, is_import=True)
        elif node.names:
            for t in node.names:
                self.env.define(t.value, T.UNKNOWN, token=t, is_import=True)
        # Plain `import "path"` (no alias, no names) dumps into current scope —
        # we can't know what names it brings in, so no tracking.
        return T.UNKNOWN

    # ── Switch / Match ────────────────────────────────────────────────────────

    def visit_SwitchNode(self, node) -> str:
        self.visit(node.subject_node)
        for value_nodes, body in node.cases:
            for v in value_nodes:
                self.visit(v)
            for stmt in body:
                self.visit(stmt)
        if node.else_block:
            for stmt in node.else_block:
                self.visit(stmt)
        return T.UNKNOWN

    def visit_MatchNode(self, node) -> str:
        self.visit(node.subject_node)
        for patterns, result in node.arms:
            if patterns:
                for p in patterns:
                    self.visit(p)
            self.visit(result)
        return T.UNKNOWN

    # ── No-ops ────────────────────────────────────────────────────────────────

    def visit_BreakNode(self, _)    -> str: return T.UNKNOWN
    def visit_ContinueNode(self, _) -> str: return T.UNKNOWN
    def visit_PassNode(self, _)     -> str: return T.UNKNOWN

    # ── Builtin signatures ────────────────────────────────────────────────────

    def _setup_builtins(self):
        builtins = {
            "write":    FuncSignature(["value"], [T.UNKNOWN], T.NULL, is_variadic=True),
            "len":      FuncSignature(["x"],     [T.UNKNOWN], T.INT),
            "to_int":   FuncSignature(["x"],     [T.UNKNOWN], T.INT),
            "to_float": FuncSignature(["x"],     [T.UNKNOWN], T.FLOAT),
            "to_str":   FuncSignature(["x"],     [T.UNKNOWN], T.STRING),
            "to_bool":  FuncSignature(["x"],     [T.UNKNOWN], T.BOOL),
            "typeof":   FuncSignature(["x"],     [T.UNKNOWN], T.STRING),
            "sqrt":     FuncSignature(["x"],     [T.NUMBER],  T.FLOAT),
            "abs":      FuncSignature(["x"],     [T.NUMBER],  T.NUMBER),
            "round":    FuncSignature(["x"],     [T.NUMBER],  T.NUMBER),
            "floor":    FuncSignature(["x"],     [T.NUMBER],  T.INT),
            "ceil":     FuncSignature(["x"],     [T.NUMBER],  T.INT),
            "exp":      FuncSignature(["x"],     [T.NUMBER],  T.FLOAT),
            "ln":       FuncSignature(["x"],     [T.NUMBER],  T.FLOAT),
            "append":   FuncSignature(["lst", "val"], [T.LIST, T.UNKNOWN], T.NULL),
            "pop":      FuncSignature(["lst"],   [T.LIST],    T.UNKNOWN, is_variadic=True),
            "insert":   FuncSignature(["lst", "idx", "val"], [T.LIST, T.INT, T.UNKNOWN], T.NULL),
            "keys":     FuncSignature(["d"],     [T.DICT],    T.LIST),
            "values":   FuncSignature(["d"],     [T.DICT],    T.LIST),
            "split":    FuncSignature(["s"],     [T.STRING],  T.LIST, is_variadic=True),
            "join":     FuncSignature(["sep", "lst"], [T.STRING, T.LIST], T.STRING),
            "range":    FuncSignature(["start", "end"], [T.INT, T.INT], T.LIST, is_variadic=True),
            "min":      FuncSignature(["x"],     [T.UNKNOWN], T.UNKNOWN, is_variadic=True),
            "max":      FuncSignature(["x"],     [T.UNKNOWN], T.UNKNOWN, is_variadic=True),
            "sum":      FuncSignature(["lst"],   [T.LIST],    T.NUMBER),
            "clamp":    FuncSignature(["x", "low", "high"], [T.NUMBER, T.NUMBER, T.NUMBER], T.NUMBER),
            "alert":    FuncSignature(["msg"],   [T.UNKNOWN], T.NULL),
        }
        for name, sig in builtins.items():
            self._functions[name] = sig
            self.env.define(name, T.FUNCTION)
