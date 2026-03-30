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
# Non-goals for v1.8 (future):
#   - Unused variable / import detection (v1.9)
#   - Generic / parameterised types  e.g. list[int]
#   - Full inference across branches (if/else, loops)
#
# The checker collects ALL errors rather than stopping at the first one.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from luz.parser import (
    NumberNode, StringNode, FStringNode, BooleanNode, NullNode,
    ListNode, DictNode, TupleNode,
    VarAssignNode, TypedVarAssignNode, VarAccessNode,
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

    NUMERIC = {INT, FLOAT, NUMBER}

    @staticmethod
    def compatible(declared: str, actual: str) -> bool:
        """Return True if `actual` satisfies a `declared` type constraint."""
        if declared == T.UNKNOWN or actual == T.UNKNOWN:
            return True
        if declared == actual:
            return True
        if declared == T.NUMBER and actual in (T.INT, T.FLOAT):
            return True
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

    def __str__(self):
        loc = f"line {self.line}" if self.line else "unknown location"
        if self.col:
            loc += f", col {self.col}"
        return f"TypeCheckFault at {loc}: {self.message}"


# ── Type environment ──────────────────────────────────────────────────────────

class TypeEnv:
    def __init__(self, parent: Optional[TypeEnv] = None):
        self._types: dict[str, str] = {}
        self.parent = parent

    def define(self, name: str, typ: str):
        self._types[name] = typ

    def update(self, name: str, typ: str):
        if name in self._types:
            self._types[name] = typ
        elif self.parent:
            self.parent.update(name, typ)
        else:
            self._types[name] = typ

    def lookup(self, name: str) -> str:
        if name in self._types:
            return self._types[name]
        if self.parent:
            return self.parent.lookup(name)
        return T.UNKNOWN


# ── Function signature ────────────────────────────────────────────────────────

@dataclass
class FuncSignature:
    param_names: list
    param_types: list
    return_type: str
    is_variadic: bool = False


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
        self._setup_builtins()

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, ast: list) -> list[TypeCheckError]:
        for node in ast:
            self.visit(node)
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
        return self.env.lookup(node.token.value)

    def visit_VarAssignNode(self, node) -> str:
        typ = self.visit(node.value_node)
        self.env.update(node.var_name_token.value, typ)
        return typ

    def visit_TypedVarAssignNode(self, node) -> str:
        declared = node.type_name
        actual   = self.visit(node.value_node)
        if not T.compatible(declared, actual):
            self._err(
                f"Variable '{node.var_token.value}' declared as '{declared}' "
                f"but assigned a '{actual}' value",
                token=node.var_token
            )
        self.env.update(node.var_token.value, declared)
        return declared

    def visit_DestructureAssignNode(self, node) -> str:
        self.visit(node.value_node)
        for t in node.var_tokens:
            self.env.update(t.value, T.UNKNOWN)
        return T.UNKNOWN

    def visit_DictDestructureAssignNode(self, node) -> str:
        self.visit(node.value_node)
        for t in node.key_tokens:
            self.env.update(t.value, T.UNKNOWN)
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
        if op in (TokenType.MINUS, TokenType.MUL, TokenType.MOD, TokenType.POW):
            if T.FLOAT in (left, right): return T.FLOAT
            if left == T.INT and right == T.INT: return T.INT
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

        sig = FuncSignature(
            param_names=param_names,
            param_types=param_types,
            return_type=return_type,
            is_variadic=bool(node.variadic),
        )
        if node.name_token:
            self._functions[node.name_token.value] = sig
            self.env.define(node.name_token.value, T.FUNCTION)

        child_env = TypeEnv(self.env)
        for pname, ptype in zip(param_names, param_types):
            child_env.define(pname, ptype)

        saved_env, saved_ret = self.env, self._current_return_type
        self.env, self._current_return_type = child_env, return_type

        for stmt in node.block:
            self.visit(stmt)

        self.env, self._current_return_type = saved_env, saved_ret
        return T.FUNCTION

    def visit_LambdaNode(self, node) -> str:
        child_env = TypeEnv(self.env)
        for t in node.param_tokens:
            child_env.define(t.value, T.UNKNOWN)
        saved = self.env; self.env = child_env
        self.visit(node.expr_node)
        self.env = saved
        return T.FUNCTION

    def visit_AnonFuncNode(self, node) -> str:
        child_env = TypeEnv(self.env)
        for t in node.param_tokens:
            child_env.define(t.value, T.UNKNOWN)
        saved = self.env; self.env = child_env
        for stmt in node.block:
            self.visit(stmt)
        self.env = saved
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
            if len(arg_types) != len(sig.param_types):
                self._err(
                    f"'{name}' expects {len(sig.param_types)} argument(s), "
                    f"got {len(arg_types)}",
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
        for condition, body in node.cases:
            self.visit(condition)
            child = TypeEnv(self.env)
            saved = self.env; self.env = child
            for stmt in body:
                self.visit(stmt)
            self.env = saved
        if node.else_case:
            child = TypeEnv(self.env)
            saved = self.env; self.env = child
            for stmt in node.else_case:
                self.visit(stmt)
            self.env = saved
        return T.UNKNOWN

    def visit_WhileNode(self, node) -> str:
        self.visit(node.condition_node)
        for stmt in node.block:
            self.visit(stmt)
        return T.UNKNOWN

    def visit_ForNode(self, node) -> str:
        self.visit(node.start_value_node)
        self.visit(node.end_value_node)
        if node.step_node:
            self.visit(node.step_node)
        child = TypeEnv(self.env)
        child.define(node.var_name_token.value, T.INT)
        saved = self.env; self.env = child
        for stmt in node.block:
            self.visit(stmt)
        self.env = saved
        return T.UNKNOWN

    def visit_ForEachNode(self, node) -> str:
        self.visit(node.iterable_node)
        child = TypeEnv(self.env)
        child.define(node.var_name_token.value, T.UNKNOWN)
        saved = self.env; self.env = child
        for stmt in node.block:
            self.visit(stmt)
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

    def visit_ClassDefNode(self, node) -> str:
        self.env.define(node.name_token.value, T.UNKNOWN)
        for method in node.methods:
            self.visit(method)
        return T.UNKNOWN

    def visit_AttributeAccessNode(self, node) -> str:
        self.visit(node.obj_node)
        return T.UNKNOWN

    def visit_AttributeAssignNode(self, node) -> str:
        self.visit(node.obj_node)
        self.visit(node.value_node)
        return T.UNKNOWN

    # ── Error handling ────────────────────────────────────────────────────────

    def visit_AttemptRescueNode(self, node) -> str:
        for stmt in node.try_block:
            self.visit(stmt)
        rescue_env = TypeEnv(self.env)
        if node.error_var_token:
            rescue_env.define(node.error_var_token.value, T.STRING)
        saved = self.env; self.env = rescue_env
        for stmt in node.catch_block:
            self.visit(stmt)
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
        self.visit(node.obj_node)
        self.visit(node.index_node)
        return T.UNKNOWN

    def visit_SliceNode(self, node) -> str:
        self.visit(node.obj_node)
        for n in (node.start, node.end, node.step):
            if n: self.visit(n)
        return T.UNKNOWN

    def visit_IndexAssignNode(self, node) -> str:
        self.visit(node.obj_node)
        self.visit(node.index_node)
        self.visit(node.value_node)
        return T.UNKNOWN

    def visit_ListCompNode(self, node) -> str:
        for _, iterable in node.clauses:
            self.visit(iterable)
        self.visit(node.expr)
        if node.condition:
            self.visit(node.condition)
        return T.LIST

    # ── Imports ───────────────────────────────────────────────────────────────

    def visit_ImportNode(self, node) -> str:
        if node.alias:
            self.env.define(node.alias.value, T.UNKNOWN)
        elif node.names:
            for t in node.names:
                self.env.define(t.value, T.UNKNOWN)
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
