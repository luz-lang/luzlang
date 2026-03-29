# interpreter.py
#
# The Interpreter is the final stage of the Luz pipeline.  It walks the Abstract
# Syntax Tree (AST) produced by the Parser and evaluates each node, ultimately
# producing side effects (I/O, variable mutations) and return values.
#
# Pipeline position:
#   list[ASTNode] → [Interpreter.visit()] → runtime values / side effects
#
# Design: Tree-Walking Interpreter
# ─────────────────────────────────
# Rather than compiling to bytecode, Luz uses a simple tree-walking approach:
# each AST node is visited directly, its children are recursively visited, and
# the Python call stack mirrors the Luz call stack.  This is easy to understand
# and debug, though it is slower than bytecode interpretation for large programs.
#
# Visitor Pattern
# ───────────────
# visit() inspects the class name of the incoming node and dynamically resolves
# a method called visit_<ClassName> (e.g. visit_BinOpNode).  This avoids a
# large if/elif chain and makes it trivial to add new node types: just add a
# corresponding visit_ method.
#
# Scoping
# ───────
# Variables live in Environment objects that form a chain.  Each block (loop
# body, function body) gets its own Environment whose parent is the enclosing
# scope.  Variable lookup walks up the chain; assignment also walks up unless a
# function-scope boundary is encountered (preventing closures from accidentally
# mutating caller variables).
#
# Control Flow via Exceptions
# ───────────────────────────
# `return`, `break`, and `continue` are implemented by raising special exception
# classes (ReturnException, BreakException, ContinueException) defined in
# exceptions.py.  The loop/function visitors catch exactly these exceptions to
# implement the semantics.  They are never caught by the Luz `attempt/rescue`
# construct — that only catches real errors.

from .tokens import TokenType
from .exceptions import *
from .lexer import Lexer
from .parser import Parser
import os
import sys
import difflib


# ── Environment (variable store) ─────────────────────────────────────────────

# Environment implements a lexically scoped variable store.
# Each environment has an optional parent; lookups that fail locally are
# forwarded to the parent recursively, walking the scope chain upward.
#
# The is_function_scope flag marks the boundary created when a function is
# called.  This boundary stops assignment from "leaking" through the closure:
# inside a function, assigning to a name that doesn't exist locally creates a
# new local variable rather than modifying the caller's variable.
class Environment:
    def __init__(self, parent=None, is_function_scope=False):
        self.records = {}
        self.types = {}             # Maps variable name → current value
        self.parent = parent          # Enclosing scope (None for global)
        self.is_function_scope = is_function_scope

    # define() unconditionally sets a name in the current scope.
    # Used when entering a for-loop (to bind the loop variable) and when
    # binding function parameters.
    def define(self, name, value):
        self.records[name] = value
        return value
    
    def define_typed(self, name, value, type_name):
        self.records[name] = value
        self.types[name] = type_name
        return value

    # lookup() searches the scope chain upward until it finds the name or
    # reaches the top-level global scope with no parent.
    

    def lookup(self, name):
        if name in self.records:
            return self.records[name]
        if self.parent:
            return self.parent.lookup(name)
        # Collect all names visible from this scope
        all_names = self._all_names()
        suggestion = difflib.get_close_matches(name, all_names, n=1, cutoff=0.6)
        hint = f" — did you mean '{suggestion[0]}'?" if suggestion else ""
        raise UndefinedSymbolFault(f"Symbol '{name}' is not defined{hint}")

    def _all_names(self):
        names = list(self.records.keys())
        if self.parent:
            names += self.parent._all_names()
        return names

    # assign() updates an existing variable, or creates it at the appropriate
    # scope level if it doesn't exist yet.
    #
    # Scope walk rules:
    #   1. If the name exists in the current scope, update it here.
    #   2. If we have a parent AND this is NOT a function boundary, delegate
    #      upward — this lets an if/while/for block read+write outer variables.
    #   3. At a function boundary (or the global scope), create the variable
    #      here so it stays local to the function.
    def assign(self, name, value):
        if name in self.records:
            if name in self.types:
                from .interpreter import Interpreter
                type_name = self.types[name]
                if not Interpreter._check_type(value, type_name):
                    raise TypeViolationFault(f"Variable '{name}' expects type '{type_name}', "
                                             f"got '{Interpreter._luz_type_name(value)}'")
            self.records[name] = value
            return value
        # Walk up only if we haven't hit a function boundary AND the name
        # already exists somewhere in the outer scope chain.  This prevents
        # a variable defined inside an if/while/for block from silently
        # escaping to the function or global scope.
        if self.parent and not self.is_function_scope:
            try:
                self.parent.lookup(name)
                return self.parent.assign(name, value)
            except UndefinedSymbolFault:
                pass
        # Name not found in any reachable outer scope: create it here.
        self.records[name] = value
        return value


# ── Function representation ───────────────────────────────────────────────────

# LuzFunction wraps a FuncDefNode (the parsed function definition) together with
# the environment that was active when the function was defined (the closure).
# When the function is called, a fresh child environment of the closure is
# created so that:
#   • Each call gets its own isolated set of local variables.
#   • The function can still read variables from the scope where it was defined
#     (classic lexical closure behaviour).
class LuzFunction:
    def __init__(self, node, closure):
        self.node = node          # FuncDefNode — holds parameter names and body
        self.closure = closure    # The Environment captured at definition time

    # __call__ is invoked by the interpreter's visit_CallNode.
    # It validates the argument count, binds parameters to a new environment,
    # runs the body, and catches ReturnException to extract the return value.
    # If the body completes without a `return`, None is returned implicitly.
    def __call__(self, interpreter, arguments, extra_bindings=None, kwargs=None):
        kwargs = kwargs or {}
        param_names = [t.value for t in self.node.arg_tokens]
        total = len(self.node.arg_tokens)
        variadic = self.node.variadic
        fixed = total - 1 if variadic else total

        # Validate named args refer to real parameters
        for name in kwargs:
            if name not in param_names[:fixed]:
                raise ArgumentFault(f"Function '{self.node.name_token.value}' has no parameter '{name}'")

        # Check no positional arg also given as named arg
        for i, arg_token in enumerate(self.node.arg_tokens[:min(len(arguments), fixed)]):
            if arg_token.value in kwargs:
                raise ArgumentFault(f"Argument '{arg_token.value}' given both positionally and by name")

        required = sum(1 for i, d in enumerate(self.node.defaults[:fixed])
                       if d is None and self.node.arg_tokens[i].value not in kwargs)

        if variadic:
            if len(arguments) < required:
                raise ArityFault(f"Function '{self.node.name_token.value}' expects at least {required} argument(s), but received {len(arguments)}")
        else:
            total_provided = len(arguments) + len(kwargs)
            if total_provided < required or len(arguments) > fixed:
                if required == fixed:
                    raise ArityFault(f"Function '{self.node.name_token.value}' expects {fixed} argument(s), but received {total_provided}")
                else:
                    raise ArityFault(f"Function '{self.node.name_token.value}' expects {required}–{fixed} argument(s), but received {total_provided}")

        env = Environment(self.closure, is_function_scope=True)
        for i in range(fixed):
            name = self.node.arg_tokens[i].value
            if i < len(arguments):
                value = arguments[i]
            elif name in kwargs:
                value = kwargs[name]
            else:
                value = interpreter.visit(self.node.defaults[i])
            type_ann = self.node.arg_types[i]
            if type_ann is not None and not Interpreter._check_type(value, type_ann):
                raise TypeViolationFault(f"Argument '{name}' expects type '{type_ann}', "
                                         f"got '{Interpreter._luz_type_name(value)}'")
            env.define(name, value)
        if variadic:
            env.define(self.node.arg_tokens[fixed].value, list(arguments[fixed:]))

        # extra_bindings lets callers inject additional names (e.g. `super`)
        # into the method's local scope without touching the parameter list.
        if extra_bindings:
            for name, value in extra_bindings.items():
                env.define(name, value)

        try:
            interpreter.execute_block(self.node.block, env)
        except ReturnException as e:
            ret = e.value
            if self.node.return_type is not None and not Interpreter._check_type(ret, self.node.return_type):
                raise TypeViolationFault(f"Function '{self.node.name_token.value}' must return '{self.node.return_type}', "
                                         f"got '{Interpreter._luz_type_name(ret)}'")
            return ret
        if self.node.return_type is not None and self.node.return_type != 'null':
            raise TypeViolationFault(f"Function '{self.node.name_token.value}' must return '{self.node.return_type}', got 'null'")
        return None


# ── Lambda / anonymous function ───────────────────────────────────────────────

# LuzLambda is the runtime value produced by a `fn` expression.
# It covers both forms:
#   Short:  fn(x) => expr      (is_expr=True  — expression is implicitly returned)
#   Long:   fn(x) { body }     (is_expr=False — body may contain any statements)
class LuzLambda:
    def __init__(self, param_tokens, body, closure, is_expr=False):
        self.param_tokens = param_tokens
        self.body = body        # ASTNode for short form, list of nodes for long form
        self.closure = closure
        self.is_expr = is_expr

    def __call__(self, interpreter, arguments, extra_bindings=None, kwargs=None):
        if kwargs:
            raise ArgumentFault("Lambdas do not support named arguments")
        if len(arguments) != len(self.param_tokens):
            raise ArityFault(f"Lambda expects {len(self.param_tokens)} arguments, got {len(arguments)}")
        env = Environment(self.closure, is_function_scope=True)
        for i, token in enumerate(self.param_tokens):
            env.define(token.value, arguments[i])
        if extra_bindings:
            for name, value in extra_bindings.items():
                env.define(name, value)
        if self.is_expr:
            # Short form — evaluate the single expression and return its value.
            previous_env = interpreter.current_env
            interpreter.current_env = env
            try:
                return interpreter.visit(self.body)
            finally:
                interpreter.current_env = previous_env
        else:
            # Long form — run the block and catch any `return` signal.
            try:
                interpreter.execute_block(self.body, env)
            except ReturnException as e:
                return e.value
            return None

    def __repr__(self):
        return "<lambda>"


# ── Class and instance representation ────────────────────────────────────────

# LuzClass holds the class name, its methods, and an optional parent class.
# It is stored in the environment under the class name, just like a function.
class LuzClass:
    def __init__(self, name, methods, parent=None):
        self.name = name
        self.methods = methods  # dict: method_name -> LuzFunction
        self.parent = parent    # LuzClass or None

    def find_method(self, name):
        # Walk up the class hierarchy to find a method by name.
        # visited guards against circular inheritance (A extends B extends A)
        # which would otherwise loop forever.
        visited = set()
        cls = self
        while cls is not None:
            if id(cls) in visited:
                raise InheritanceFault(f"Circular inheritance detected involving class '{cls.name}'")
            visited.add(id(cls))
            if name in cls.methods:
                return cls.methods[name]
            cls = cls.parent
        return None

    def __repr__(self):
        return f"<class {self.name}>"


# BoundMethod wraps a LuzFunction together with the instance it was retrieved
# from.  When called, it automatically prepends the instance as `self` so the
# caller does not need to pass it manually.
class BoundMethod:
    def __init__(self, instance, function):
        self.instance = instance
        self.function = function

    def __repr__(self):
        return f"<bound method '{self.function.node.name}' of {self.instance}>"


# LuzInstance is the runtime object created when a class is called as a
# constructor.  It stores instance attributes in a plain dict and looks up
# methods on its class hierarchy when an attribute is not found locally.
class LuzInstance:
    def __init__(self, luz_class):
        self.luz_class = luz_class
        self.attributes = {}

    def get(self, name):
        if name in self.attributes:
            return self.attributes[name]
        method = self.luz_class.find_method(name)
        if method is not None:
            return BoundMethod(self, method)
        raise AttributeNotFoundFault(f"'{self.luz_class.name}' has no attribute '{name}'")

    def set(self, name, value):
        self.attributes[name] = value

    def __repr__(self):
        return f"<{self.luz_class.name} instance>"


# LuzModule is the runtime object created by `import "x" as alias`.
# It wraps a snapshot of all names defined in the module's global environment,
# exposing them as attributes accessible via dot notation (alias.name).
class LuzModule:
    def __init__(self, name, namespace):
        self.name = name          # module file path (for repr)
        self.namespace = namespace  # dict of name -> value

    def get(self, name):
        if name in self.namespace:
            return self.namespace[name]
        raise AttributeNotFoundFault(f"Module '{self.name}' has no attribute '{name}'")

    def set(self, name, value):
        self.namespace[name] = value

    def __repr__(self):
        return f"<module '{self.name}'>"


# LuzSuperProxy gives methods access to the parent class's versions of methods.
# When a method is called on an instance, `super` is injected into the local
# scope as a LuzSuperProxy(instance, parent_class).  Calling super.method(args)
# invokes the parent's method with the same instance, bypassing the child's override.
class LuzSuperProxy:
    def __init__(self, instance, parent_class):
        self.instance = instance
        self.parent_class = parent_class

    def find_method(self, name):
        method = self.parent_class.find_method(name)
        if method is None:
            raise AttributeNotFoundFault(f"Parent class has no method '{name}'")
        return method


# ── Interpreter ───────────────────────────────────────────────────────────────

class Interpreter:
    def __init__(self):
        # The global environment is the root of the scope chain.
        # All top-level variables and functions live here.
        self.global_env = Environment()
        self.current_env = self.global_env

        # Tracks absolute paths of already-imported files to prevent circular
        # imports and redundant re-execution of modules.
        self.imported_files = set()

        # Stack of directories of files currently being executed, used to
        # resolve imports relative to the importing file's location.
        self._file_stack = []

        # current_line is updated by visit() as nodes are processed.
        # When an error is raised without a line number, this value is attached
        # to give the user a useful "error at line N" message.
        self.current_line = None
        self.current_col = None

        # builtins maps function names that are always in scope to Python
        # methods on this object.  Checking builtins before looking up in the
        # environment means built-in names shadow any user-defined function with
        # the same name (consistent, predictable behaviour).
        self.builtins = {
            'write': self.builtin_write,
            'listen': self.builtin_listen,
            'len': self.builtin_len,
            'append': self.builtin_append,
            'pop': self.builtin_pop,
            'reverse': self.builtin_reverse,
            'any': self.builtin_any,
            'all': self.builtin_all,
            'keys': self.builtin_keys,
            'values': self.builtin_values,
            'remove': self.builtin_remove,
            'to_num': self.builtin_to_num,
            'to_int': self.builtin_to_int,
            'to_float': self.builtin_to_float,
            'to_str': self.builtin_to_str,
            'to_bool': self.builtin_to_bool,
            'trim': self.builtin_trim,
            'uppercase': self.builtin_uppercase,
            'lowercase': self.builtin_lowercase,
            'swap': self.builtin_swap,
            'begins': self.builtin_begins,
            'ends': self.builtin_ends,
            'contains': self.builtin_contains,
            'split': self.builtin_split,
            'join': self.builtin_join,
            'find': self.builtin_find,
            'count': self.builtin_count,
            'typeof': self.builtin_typeof,
            'instanceof': self.builtin_instanceof,
            'abs': self.builtin_abs,
            'sqrt': self.builtin_sqrt,
            'floor': self.builtin_floor,
            'ceil': self.builtin_ceil,
            'round': self.builtin_round,
            'clamp': self.builtin_clamp,
            'max': self.builtin_max,
            'min': self.builtin_min,
            'sign': self.builtin_sign,
            'odd': self.builtin_odd,
            'even': self.builtin_even,
            'index': self.builtin_index,
            'insert': self.builtin_insert,
            # Trigonometric Functions - all angles in radians
            'sin': self.builtin_sin,
            'cos': self.builtin_cos,
            'tan': self.builtin_tan,
            'asin': self.builtin_asin,
            'acos': self.builtin_acos,
            'atan': self.builtin_atan,
            'atan2': self.builtin_atan2,
            # Exponential and logarithmic
            'exp': self.builtin_exp,
            'ln': self.builtin_ln,
            'log2': self.builtin_log2,
            'log10': self.builtin_log10,
            'pow': self.builtin_pow,
            '_rand_float': self.builtin_rand_float,
            '_rand_int': self.builtin_rand_int,
            '_rand_seed': self.builtin_rand_seed,
            'read_file':   self.builtin_read_file,
            'write_file':  self.builtin_write_file,
            'append_file': self.builtin_append_file,
            'file_exists': self.builtin_file_exists,
            'delete_file': self.builtin_delete_file,
            'exec':        self.builtin_exec,
            'exec_code':   self.builtin_exec_code,
            'env_get':     self.builtin_env_get,
            'env_set':     self.builtin_env_set,
            'get_cwd':     self.builtin_get_cwd,
            'set_cwd':     self.builtin_set_cwd,
            'get_os':      self.builtin_get_os,
            'get_hostname': self.builtin_get_hostname,
            'get_username': self.builtin_get_username,
            'get_pid':     self.builtin_get_pid,
            'sys_exit':    self.builtin_sys_exit,
            'list_dir':    self.builtin_list_dir,
            'make_dir':    self.builtin_make_dir,
            'sleep':       self.builtin_sleep,
            # Clock primitives (used by luz-clock stdlib)
            '_clock_now':        self.builtin_clock_now,
            '_clock_stamp':      self.builtin_clock_stamp,
            '_clock_fmt':        self.builtin_clock_fmt,
            '_clock_from_stamp': self.builtin_clock_from_stamp,
            '_clock_parse':      self.builtin_clock_parse,
            '_clock_fmt_stamp':  self.builtin_clock_fmt_stamp,
        }

    # execute_block() runs a list of statements inside a given environment.
    # It temporarily replaces current_env with the provided env, then restores
    # the previous env in a finally block so that control-flow exceptions
    # (ReturnException, BreakException) don't leave the interpreter in the wrong
    # scope if they bubble past this frame.
    def execute_block(self, block, env):
        previous_env = self.current_env
        self.current_env = env
        try:
            result = None
            for statement in block:
                result = self.visit(statement)
            return result
        finally:
            self.current_env = previous_env  # Always restore, even on exception

    # visit() is the central dispatch method of the interpreter.
    #
    # It accepts either a single ASTNode or a list of nodes (treating a list as
    # an implicit block, which is the format statements() returns).
    #
    # For each node it:
    #   1. Updates current_line for error reporting.
    #   2. Looks up a visit_<ClassName> method via getattr.
    #   3. Calls that method and returns its result.
    #   4. If a LuzError is raised and has no line number yet, stamps it with
    #      current_line before re-raising so the user sees "error at line N".
    #      Control-flow signals (Return/Break/Continue) are excluded from this
    #      treatment because they are not errors and should not carry line info.
    def visit(self, node):
        if isinstance(node, list):
            # Convenience: visit a whole block without creating an explicit node.
            result = None
            for statement in node:
                result = self.visit(statement)
            return result

        line = getattr(node, 'line', None)
        col = getattr(node, 'col', None)
        if line is not None:
            self.current_line = line
        if col is not None:
            self.current_col = col

        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, self.no_visit_method)
        try:
            return method(node)
        except LuzError as e:
            # Don't stamp line numbers onto control-flow signals — they are
            # not errors and their "line" would be misleading.
            if not isinstance(e, (ReturnException, BreakException, ContinueException)) and e.line is None:
                e.line = self.current_line
                e.col = self.current_col
            raise
        except RecursionError:
            raise RuntimeFault("Maximum recursion depth exceeded")

    # no_visit_method() is the fallback when visit() cannot find a handler for
    # a node type.  This indicates a bug in the interpreter (a node class was
    # added to the parser but a corresponding visit_ method was never written).
    def no_visit_method(self, node):
        raise InternalFault(f"No visit_{type(node).__name__} method defined in the interpreter")

    # ── Literal value visitors ────────────────────────────────────────────────
    # These simply unwrap the Python value that the lexer already parsed.

    def visit_NumberNode(self, node):
        # The lexer already converted the source text to int or float.
        return node.token.value

    def visit_StringNode(self, node):
        # The lexer already processed escape sequences; the value is a clean string.
        return node.token.value

    def visit_BooleanNode(self, node):
        # TokenType.TRUE/FALSE → Python True/False
        return True if node.token.type == TokenType.TRUE else False

    def visit_NullNode(self, node):
        return None

    def visit_SwitchNode(self, node):
        subject = self.visit(node.subject_node)
        for value_nodes, block in node.cases:
            for vn in value_nodes:
                if self.visit(vn) == subject:
                    return self.visit(block)
        if node.else_block is not None:
            return self.visit(node.else_block)
        return None

    def visit_MatchNode(self, node):
        subject = self.visit(node.subject_node)
        for patterns, result_node in node.arms:
            if patterns is None:  # wildcard _
                return self.visit(result_node)
            for pn in patterns:
                if self.visit(pn) == subject:
                    return self.visit(result_node)
        return None

    def visit_TernaryNode(self, node):
        if self.visit(node.condition_node):
            return self.visit(node.value_node)
        return self.visit(node.else_node)

    def visit_NullCoalesceNode(self, node):
        left = self.visit(node.left)
        if left is not None:
            return left
        return self.visit(node.right)

    def visit_TupleNode(self, node):
        return [self.visit(e) for e in node.elements]

    def visit_DestructureAssignNode(self, node):
        value = self.visit(node.value_node)
        if not isinstance(value, list):
            raise TypeViolationFault("Cannot unpack a non-list value in destructuring assignment")
        if len(value) != len(node.var_tokens):
            raise TypeViolationFault(
                f"Cannot unpack {len(value)} value(s) into {len(node.var_tokens)} variable(s)"
            )
        for token, val in zip(node.var_tokens, value):
            self.current_env.assign(token.value, val)
        return None

    def visit_DictDestructureAssignNode(self, node):
        value = self.visit(node.value_node)
        if not isinstance(value, dict):
            raise TypeViolationFault("Dict destructuring requires a dict on the right side")
        for token in node.key_tokens:
            key = token.value
            if key not in value:
                raise InvalidUsageFault(f"Key '{key}' not found in dict during destructuring")
            self.current_env.assign(key, value[key])
        return None

    # visit_FStringNode() evaluates each expression part and concatenates
    # everything into a single string.  Null, booleans, and instances use
    # their Luz display representations rather than Python's defaults.
    def visit_FStringNode(self, node):
        result = ''
        for part in node.parts:
            if isinstance(part, str):
                result += part
            else:
                val = self.visit(part)
                result += self._luz_str(val)
        return result

    # _luz_str() converts any Luz value to its display string, using Luz
    # conventions (null, true/false) rather than Python's (None, True/False).
    def _luz_str(self, value):
        return self.luz_display(value)

    def visit_ListNode(self, node):
        # Evaluate every element expression and collect the results into a Python list.
        return [self.visit(element) for element in node.elements]

    def visit_ListCompNode(self, node):
        result = []
        prev_env = self.current_env
        self.current_env = Environment(parent=prev_env)
        try:
            self._eval_comp_clauses(node.clauses, 0, node.condition, node.expr, result)
        finally:
            self.current_env = prev_env
        return result

    # Recursively evaluates nested 'for' clauses of a list comprehension.
    # At each level, iterates the current clause's iterable, binds the loop
    # variable, then recurses into the next clause. When all clauses are
    # exhausted, evaluates the filter (if any) and appends the output expression.
    def _eval_comp_clauses(self, clauses, depth, condition, expr, result):
        var_token, iterable_node = clauses[depth]
        iterable = self.visit(iterable_node)
        if not isinstance(iterable, (list, str)):
            raise TypeClashFault(f"List comprehension requires a list or string, got '{self._luz_type_name(iterable)}'")
        for item in iterable:
            self.current_env.define(var_token.value, item)
            if depth + 1 < len(clauses):
                self._eval_comp_clauses(clauses, depth + 1, condition, expr, result)
            elif condition is None or self.visit(condition):
                result.append(self.visit(expr))

    def visit_DictNode(self, node):
        # Evaluate each key and value expression in order and populate a Python dict.
        # Dictionary keys may be any hashable Luz value (string, int, float, bool).
        res = {}
        for key_node, value_node in node.pairs:
            key = self.visit(key_node)
            value = self.visit(value_node)
            res[key] = value
        return res

    # ── Index access & assignment ─────────────────────────────────────────────

    # visit_IndexAccessNode() handles `base[index]` for lists, strings, and dicts.
    # Each container type has slightly different rules (lists/strings require int
    # indices; dicts accept any hashable type).
    def visit_IndexAccessNode(self, node):
        base = self.visit(node.base_node)
        index = self.visit(node.index_node)

        if isinstance(base, list):
            if not isinstance(index, int):
                raise TypeViolationFault(f"List index must be an integer, not '{self._luz_type_name(index)}'")
            if index < 0:
                index = len(base) + index
            try:
                return base[index]
            except IndexError:
                raise IndexFault(f"Index {index} is out of range for list of size {len(base)}")
        elif isinstance(base, str):
            if not isinstance(index, int):
                raise TypeViolationFault(f"String index must be an integer, not '{self._luz_type_name(index)}'")
            if index < 0:
                index = len(base) + index
            try:
                return base[index]
            except IndexError:
                raise IndexFault(f"Index {index} is out of range for string of length {len(base)}")
        elif isinstance(base, dict):
            try:
                return base[index]
            except KeyError:
                raise MemoryAccessFault(f"Key '{index}' not found in dictionary")
            except TypeError:
                # Python raises TypeError when you try to use an unhashable value
                # (e.g. a list) as a dict key.
                raise TypeViolationFault(f"Unhashable type: '{self._luz_type_name(index)}' cannot be used as a dictionary key")
        else:
            raise InvalidUsageFault(f"Type '{self._luz_type_name(base)}' does not support indexing")

    def visit_SliceNode(self, node):
        base = self.visit(node.base_node)
        start = self.visit(node.start_node) if node.start_node is not None else None
        end = self.visit(node.end_node)     if node.end_node is not None else None
        step = self.visit(node.step_node)   if node.step_node is not None else None

        if not isinstance(base, (list, str)):
            raise InvalidUsageFault(f"Slicing is not supported for type '{self._luz_type_name(base)}'")
        
        for name, val in [("start", start), ("end", end), ("step", step)]:
            if val is not None and not isinstance(val, int):
                raise TypeViolationFault(f"Slice {name} must be an integer, not {self._luz_type_name(val)}")

        if step == 0:
            raise ZeroDivisionFault("Slice step cannot be zero")
        
        return base[start:end:step]

    # visit_IndexAssignNode() handles `base[index] = value`.
    # Because lists and dicts in Luz are passed by reference (they are plain
    # Python objects), mutating `base` here automatically updates the variable
    # that holds the list/dict — no additional environment update is needed.
    def visit_IndexAssignNode(self, node):
        base = self.visit(node.base_node)
        index = self.visit(node.index_node)
        value = self.visit(node.value_node)

        if isinstance(base, list):
            if not isinstance(index, int):
                raise TypeViolationFault(f"List index must be an integer, not '{self._luz_type_name(index)}'")
            if index < 0:
                index = len(base) + index
            try:
                base[index] = value
                return value
            except IndexError:
                raise IndexFault(f"Index {index} is out of range")
        elif isinstance(base, dict):
            try:
                base[index] = value
                return value
            except TypeError:
                raise TypeViolationFault(f"Unhashable key type: '{self._luz_type_name(index)}'")
        else:
            raise InvalidUsageFault(f"Type '{self._luz_type_name(base)}' does not support index assignment")

    # ── Error handling ────────────────────────────────────────────────────────

    # visit_AttemptRescueNode() implements structured error handling.
    # The try block is run; if a LuzError is raised (and it is NOT a control-flow
    # signal), the error message is bound to the rescue variable and the catch
    # block runs in a fresh child environment.
    #
    # Control-flow signals (return/break/continue) are deliberately re-raised
    # without being caught so they continue unwinding to the correct handler.
    #
    # Non-LuzError Python exceptions (true internal bugs) are also caught and
    # surfaced as a string prefixed with "InternalFault:" so the Luz programmer
    # at least sees something useful rather than a raw Python traceback.
    def visit_AttemptRescueNode(self, node):
        result = None
        pending_raise = None

        try:
            result = self.visit(node.try_block)
        except LuzError as e:
            if isinstance(e, (ReturnException, BreakException, ContinueException)):
                pending_raise = e
            else:
                rescue_env = Environment(self.current_env)
                if node.error_var_token is not None:
                    rescue_env.define(node.error_var_token.value, str(e))
                try:
                    result = self.execute_block(node.catch_block, rescue_env)
                except Exception as re:
                    pending_raise = re
        except Exception as e:
            rescue_env = Environment(self.current_env)
            if node.error_var_token is not None:
                rescue_env.define(node.error_var_token.value, f"InternalFault: {str(e)}")
            try:
                result = self.execute_block(node.catch_block, rescue_env)
            except Exception as re:
                pending_raise = re

        if node.finally_block:
            if pending_raise is not None:
                # An error is already pending — run finally but don't let it
                # overwrite the original error if it also raises.
                try:
                    self.execute_block(node.finally_block, Environment(self.current_env))
                except Exception:
                    pass
            else:
                self.execute_block(node.finally_block, Environment(self.current_env))

        if pending_raise is not None:
            raise pending_raise

        return result

    # visit_AlertNode() implements the `alert` statement, which intentionally
    # raises a UserFault.  This is Luz's mechanism for user-level errors —
    # analogous to `raise` in Python or `throw` in JavaScript.
    def visit_AlertNode(self, node):
        msg = self.visit(node.expression_node)
        raise UserFault(str(msg))

    # ── Module import ─────────────────────────────────────────────────────────

    # visit_ImportNode() loads and executes another Luz source file.
    # Imported modules run their top-level statements in the global environment
    # so that functions and variables they define are available everywhere.
    #
    # The imported_files set (keyed by absolute path) prevents:
    #   • The same file from being imported twice (idempotent imports).
    #   • Infinite import cycles (A imports B which imports A).
    #
    # The absolute path is added to imported_files BEFORE the module is executed
    # so that if the module itself triggers a re-import of the same file, the
    # set check catches it immediately.
    def visit_ImportNode(self, node):
        file_path = node.file_path_token.value

        # Resolution order:
        #   1. Path as written (relative or absolute)
        #   2. luz_modules/<name>/<name>.luz  (local project)
        #   3. luz_modules/<name>/main.luz    (local project)
        #   4. LUZ_HOME/lib/<name>/<name>.luz (global stdlib)
        #   5. LUZ_HOME/lib/<name>/main.luz   (global stdlib)
        if not os.path.exists(file_path):
            name = os.path.splitext(os.path.basename(file_path))[0]
            candidates = [
                os.path.join("luz_modules", name, f"{name}.luz"),
                os.path.join("luz_modules", name, "main.luz"),
            ]
            # Relative to the importing file's directory (handles sub-imports
            # inside installed stdlib modules like math.luz → constants.luz)
            if self._file_stack:
                importer_dir = os.path.dirname(self._file_stack[-1])
                candidates += [
                    os.path.join(importer_dir, os.path.basename(file_path)),
                    os.path.join(importer_dir, f"{name}.luz"),
                ]
            luz_home = os.environ.get("LUZ_HOME")
            if luz_home:
                candidates += [
                    os.path.join(luz_home, "lib", name, f"{name}.luz"),
                    os.path.join(luz_home, "lib", name, "main.luz"),
                    os.path.join(luz_home, "lib", f"luz-{name}", f"{name}.luz"),
                    os.path.join(luz_home, "lib", f"luz-{name}", "main.luz"),
                    os.path.join(luz_home, "lib", f"luz_{name}", f"{name}.luz"),
                    os.path.join(luz_home, "lib", f"luz_{name}", "main.luz"),
                ]
            # Installed binary fallback: look in lib/ next to the executable
            exe_dir = os.path.dirname(sys.executable)
            candidates += [
                os.path.join(exe_dir, "lib", name, f"{name}.luz"),
                os.path.join(exe_dir, "lib", name, "main.luz"),
                os.path.join(exe_dir, "lib", f"luz-{name}", f"{name}.luz"),
                os.path.join(exe_dir, "lib", f"luz-{name}", "main.luz"),
            ]
            # Development fallback: look in libs/ relative to cwd
            candidates += [
                os.path.join("libs", f"luz-{name}", f"{name}.luz"),
                os.path.join("libs", name, f"{name}.luz"),
                os.path.join("libs", name, "main.luz"),
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    file_path = candidate
                    break

        abs_path = os.path.abspath(file_path)

        if abs_path in self.imported_files:
            return None  # Already imported — skip silently

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except FileNotFoundError:
            raise ModuleNotFoundFault(f"Module file '{file_path}' not found")
        except Exception as e:
            raise ImportFault(f"Failed to read module '{file_path}': {str(e)}")

        try:
            lexer = Lexer(code)
            tokens = lexer.get_tokens()
            ast = Parser(tokens).parse()
        except LuzError as e:
            raise ImportFault(f"Error in module '{file_path}': {str(e)}")

        # ── from "x" import a, b  or  import "x" as alias ────────────────────
        # Both forms execute the module in an isolated environment so its
        # definitions don't spill into the global scope automatically.
        if node.names is not None or node.alias is not None:
            module_env = Environment(self.global_env)
            temp_env = self.current_env
            self.current_env = module_env
            self._file_stack.append(abs_path)
            try:
                self.visit(ast)
            except LuzError as e:
                raise ImportFault(f"Error in module '{file_path}': {str(e)}")
            except Exception as e:
                raise ImportFault(f"Unexpected error in module '{file_path}': {str(e)}")
            finally:
                self._file_stack.pop()
                self.current_env = temp_env

            if node.names is not None:
                # from "x" import a, b  — collect all names first so that a
                # missing name doesn't leave partial definitions in scope.
                collected = {}
                for name_token in node.names:
                    n = name_token.value
                    try:
                        collected[n] = module_env.lookup(n)
                    except UndefinedSymbolFault:
                        raise ImportFault(f"Module '{file_path}' has no name '{n}'")
                for n, v in collected.items():
                    self.global_env.define(n, v)
            else:
                # import "x" as alias  — wrap everything in a LuzModule
                mod_name = os.path.basename(file_path)
                module_obj = LuzModule(mod_name, dict(module_env.records))
                self.global_env.define(node.alias.value, module_obj)
            return None

        # ── Plain import "x"  — current behaviour: run in global env ─────────
        if abs_path in self.imported_files:
            return None  # Already imported — skip silently

        # Register before executing to guard against circular imports.
        self.imported_files.add(abs_path)

        try:
            temp_env = self.current_env
            self.current_env = self.global_env
            self._file_stack.append(abs_path)
            try:
                self.visit(ast)
            finally:
                self._file_stack.pop()
                self.current_env = temp_env

        except LuzError as e:
            self.imported_files.discard(abs_path)
            raise ImportFault(f"Error in module '{file_path}': {str(e)}")
        except Exception as e:
            self.imported_files.discard(abs_path)
            raise ImportFault(f"Unexpected error in module '{file_path}': {str(e)}")

        return None

    # ── Operators ─────────────────────────────────────────────────────────────

    # visit_UnaryOpNode() handles negation (-x) and logical not (not x).
    def visit_UnaryOpNode(self, node):
        res = self.visit(node.node)
        if node.op_token.type == TokenType.NOT:
            return not res
        if node.op_token.type == TokenType.MINUS:
            if not isinstance(res, (int, float)):
                raise TypeClashFault(f"Unary '-' cannot be applied to type '{self._luz_type_name(res)}'")
            return -res
        return res

    # visit_VarAssignNode() evaluates the right-hand side and stores it.
    # Environment.assign() handles the scope chain walk.
    def visit_VarAssignNode(self, node):
        var_name = node.var_name_token.value
        value = self.visit(node.value_node)
        self.current_env.assign(var_name, value)
        return value
    
    def visit_TypedVarAssignNode(self, node):
        var_name = node.var_token.value
        value = self.visit(node.value_node)
        if not self._check_type(value, node.type_name):
            raise TypeViolationFault(f"Variable '{var_name}' expects type '{node.type_name}', "
                                     f"got '{self._luz_type_name(value)}'")
        self.current_env.define_typed(var_name, value, node.type_name)
        return value

    # visit_VarAccessNode() retrieves the value of a variable by walking the
    # scope chain via Environment.lookup().
    def visit_VarAccessNode(self, node):
        var_name = node.token.value
        return self.current_env.lookup(var_name)

    # visit_BinOpNode() dispatches to the appropriate Python operation based on
    # the operator token.  Most operations delegate to Python's native operators;
    # additional checks are added where Luz semantics differ (e.g. `/` always
    # produces a float, string * int is allowed for repetition).
    def visit_BinOpNode(self, node):
        left = self.visit(node.left_node)
        right = self.visit(node.right_node)

        if node.op_token.type == TokenType.PLUS:
            # `+` on strings performs concatenation (Python native behaviour).
            try:
                return left + right
            except TypeError:
                raise TypeClashFault(f"Cannot perform addition between '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.MINUS:
            try:
                return left - right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '-': '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.MUL:
            # Allow string repetition: "ab" * 3 == "ababab" and 3 * "ab" == "ababab"
            if isinstance(left, str) and isinstance(right, (int, float)):
                return left * int(right)
            if isinstance(right, str) and isinstance(left, (int, float)):
                return right * int(left)
            try:
                return left * right
            except TypeError:
                raise IllegalOperationFault(f"Multiplication is not supported for '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.DIV:
            # `/` always returns a float in Luz, matching the intuitive
            # expectation that 5 / 2 == 2.5, not 2.
            if right == 0:
                raise ZeroDivisionFault("Division by zero is not allowed")
            try:
                return float(left) / float(right)
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '/': '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.IDIV:
            # `//` truncates towards negative infinity (Python floor division).
            if right == 0:
                raise ZeroDivisionFault("Integer division by zero is not allowed")
            try:
                return int(left) // int(right)
            except (TypeError, ValueError):
                raise IllegalOperationFault(f"Unsupported operand types for '//': '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.MOD:
            if right == 0:
                raise ZeroDivisionFault("Modulo by zero is not allowed")
            try:
                return left % right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '%': '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")

        elif node.op_token.type == TokenType.POW:
            try:
                return left ** right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '**': '{self._luz_type_name(left)}' and '{self._luz_type_name(right)}'")
            except ZeroDivisionError:
                raise ZeroDivisionFault("Zero cannot be raised to a negative power")

        elif node.op_token.type == TokenType.IN:
            if not isinstance(right, (list, str)):
                raise TypeClashFault(f"'in' requires a list or string on the right, got '{self._luz_type_name(right)}'")
            if isinstance(right, str) and not isinstance(left, str):
                raise TypeClashFault(f"'in <string>' requires a string on the left, got '{self._luz_type_name(left)}'")
            if isinstance(right, dict):
                return left in right.keys()
            return left in right

        elif node.op_token.type == TokenType.NOT_IN:
            if not isinstance(right, (list, str)):
                raise TypeClashFault(f"'not in' requires a list or string on the right, got '{self._luz_type_name(right)}'")
            if isinstance(right, dict):
                return left not in right.keys()
            return left not in right

        # Equality operators work across any types (mixed-type comparison just
        # returns False/True without raising an error).
        elif node.op_token.type == TokenType.EE:
            return left == right
        elif node.op_token.type == TokenType.NE:
            return left != right

        # Ordered comparisons require compatible types; Python raises TypeError
        # for incompatible types (e.g. int < str), which we wrap.
        elif node.op_token.type == TokenType.LT:
            try: return left < right
            except TypeError: raise TypeClashFault("Incompatible types for comparison '<'")
        elif node.op_token.type == TokenType.GT:
            try: return left > right
            except TypeError: raise TypeClashFault("Incompatible types for comparison '>'")
        elif node.op_token.type == TokenType.LTE:
            try: return left <= right
            except TypeError: raise TypeClashFault("Incompatible types for comparison '<='")
        elif node.op_token.type == TokenType.GTE:
            try: return left >= right
            except TypeError: raise TypeClashFault("Incompatible types for comparison '>='")

        # Logical operators use Python short-circuit semantics.
        # `and` returns the first falsy value or the last value if all are truthy.
        # `or`  returns the first truthy value or the last value if all are falsy.
        elif node.op_token.type == TokenType.AND:
            return left and right
        elif node.op_token.type == TokenType.OR:
            return left or right

    # ── Control-flow visitors ─────────────────────────────────────────────────

    # visit_IfNode() evaluates the condition of each case in order and executes
    # the first block whose condition is truthy.  Only one branch ever runs.
    def visit_IfNode(self, node):
        for condition, block in node.cases:
            if self.visit(condition):
                return self.execute_block(block, Environment(self.current_env))
        if node.else_case:
            return self.execute_block(node.else_case, Environment(self.current_env))
        return None

    # visit_WhileNode() re-evaluates the condition before every iteration.
    # BreakException exits the loop; ContinueException skips to the next check.
    def visit_WhileNode(self, node):
        while self.visit(node.condition_node):
            try:
                self.execute_block(node.block, Environment(self.current_env))
            except BreakException:
                break
            except ContinueException:
                continue
        return None

    # visit_ForNode() implements the numeric range loop: for i = start to end
    # The loop variable is defined fresh each iteration in the loop's own scope
    # so that changes inside the body don't corrupt the counter (and to prevent
    # the variable from polluting the surrounding scope after the loop).
    def visit_ForNode(self, node):
        var_name = node.var_name_token.value
        start_value = self.visit(node.start_value_node)
        end_value = self.visit(node.end_value_node)
        step = self.visit(node.step_node) if node.step_node is not None else 1

        if not isinstance(start_value, (int, float)) or not isinstance(end_value, (int, float)):
            raise TypeViolationFault("For loop range boundaries must be numeric")
        if not isinstance(step, (int, float)):
            raise TypeViolationFault("For loop step must be numeric")
        if step == 0:
            raise InvalidUsageFault("For loop step cannot be zero")
        if step > 0 and start_value > end_value:
            raise InvalidUsageFault(
                f"For loop start ({start_value}) is greater than end ({end_value}) but step is positive ({step}) — use 'step -1' to go backwards"
            )
        if step < 0 and start_value < end_value:
            raise InvalidUsageFault(
                f"For loop start ({start_value}) is less than end ({end_value}) but step is negative ({step}) — remove 'step' or use a positive step"
            )

        i = start_value
        previous_env = self.current_env
        self.current_env = Environment(previous_env)
        try:
            while (i <= end_value if step > 0 else i >= end_value):
                self.current_env.define(var_name, i)
                try:
                    self.visit(node.block)
                except BreakException:
                    break
                except ContinueException:
                    pass
                i += step
        finally:
            self.current_env = previous_env
        return None

    # visit_ForEachNode() iterates over a list, string, or dict.
    # Lists and strings yield their elements/characters one by one.
    # Dicts yield their keys (consistent with most languages and Python).
    def visit_ForEachNode(self, node):
        var_name = node.var_name_token.value
        iterable = self.visit(node.iterable_node)

        if not isinstance(iterable, (list, str, dict)):
            raise TypeViolationFault(f"Cannot iterate over type '{self._luz_type_name(iterable)}' — expected list, string, or dict")

        previous_env = self.current_env
        self.current_env = Environment(previous_env)
        try:
            for item in iterable:
                self.current_env.define(var_name, item)
                try:
                    self.visit(node.block)
                except BreakException:
                    break
                except ContinueException:
                    continue
        finally:
            self.current_env = previous_env
        return None

    # visit_BreakNode() and visit_ContinueNode() raise the corresponding signal
    # exceptions, which unwind the call stack to the nearest loop visitor.
    def visit_BreakNode(self, node):
        raise BreakException()

    def visit_ContinueNode(self, node):
        raise ContinueException()

    # visit_PassNode() is a no-op, used as a placeholder in empty blocks.
    def visit_PassNode(self, node):
        return None

    # ── Function definition & calls ───────────────────────────────────────────

    # visit_LambdaNode() creates a LuzLambda for fn(x) => expr
    def visit_LambdaNode(self, node):
        return LuzLambda(node.param_tokens, node.expr_node, self.current_env, is_expr=True)

    # visit_AnonFuncNode() creates a LuzLambda for fn(x) { body }
    def visit_AnonFuncNode(self, node):
        return LuzLambda(node.param_tokens, node.block, self.current_env, is_expr=False)

    # visit_FuncDefNode() creates a LuzFunction that captures the current
    # environment as its closure, then stores it in the environment under the
    # function's name.  The function body is NOT executed here.
    def visit_FuncDefNode(self, node):
        func_name = node.name_token.value
        function = LuzFunction(node, self.current_env)
        self.current_env.define(func_name, function)
        return None

    # visit_ReturnNode() evaluates the return expression (if any) and raises
    # ReturnException to unwind the stack up to LuzFunction.__call__.
    def visit_ReturnNode(self, node):
        value = None
        if node.expression_node:
            value = self.visit(node.expression_node)
        raise ReturnException(value)

    # visit_CallNode() looks up the callee by name, evaluates arguments in
    # left-to-right order, and invokes the function.
    # Built-in functions are checked first (they shadow user-defined functions).
    def visit_CallNode(self, node):
        func_name = node.func_name_token.value
        arguments = [self.visit(arg) for arg in node.arguments]
        kwargs = {name: self.visit(expr) for name, expr in node.kwargs.items()}

        if func_name in self.builtins:
            if kwargs:
                raise ArgumentFault(f"Built-in function '{func_name}' does not support named arguments")
            return self.builtins[func_name](*arguments)

        try:
            function = self.current_env.lookup(func_name)

            if isinstance(function, LuzClass):
                instance = LuzInstance(function)
                init_method = function.find_method('init')
                if init_method is not None:
                    extra = {}
                    if function.parent:
                        extra['super'] = LuzSuperProxy(instance, function.parent)
                    init_method(self, [instance] + arguments, extra_bindings=extra, kwargs=kwargs)
                return instance

            if isinstance(function, BoundMethod):
                extra = {}
                if function.instance.luz_class.parent:
                    extra['super'] = LuzSuperProxy(function.instance, function.instance.luz_class.parent)
                return function.function(self, [function.instance] + arguments, extra_bindings=extra, kwargs=kwargs)

            if not isinstance(function, (LuzFunction, LuzLambda)):
                raise InvalidUsageFault(f"'{func_name}' is not a callable function")
            return function(self, arguments, kwargs=kwargs)
        except UndefinedSymbolFault:
            raise FunctionNotFoundFault(f"Function '{func_name}' was not found")
        except LuzError as e:
            raise e
        except Exception as e:
            raise InternalFault(str(e))

    # visit_ExprCallNode() calls the result of an arbitrary expression.
    # Covers funcs[0](x), make()(y), (fn(x) => x)(5), etc.
    def visit_ExprCallNode(self, node):
        callee = self.visit(node.callee_node)
        arguments = [self.visit(arg) for arg in node.arguments]
        kwargs = {name: self.visit(expr) for name, expr in node.kwargs.items()}

        try:
            if isinstance(callee, LuzClass):
                instance = LuzInstance(callee)
                init_method = callee.find_method('init')
                if init_method is not None:
                    extra = {}
                    if callee.parent:
                        extra['super'] = LuzSuperProxy(instance, callee.parent)
                    init_method(self, [instance] + arguments, extra_bindings=extra, kwargs=kwargs)
                return instance

            if isinstance(callee, BoundMethod):
                extra = {}
                if callee.instance.luz_class.parent:
                    extra['super'] = LuzSuperProxy(callee.instance, callee.instance.luz_class.parent)
                return callee.function(self, [callee.instance] + arguments, extra_bindings=extra, kwargs=kwargs)

            if isinstance(callee, (LuzFunction, LuzLambda)):
                return callee(self, arguments, kwargs=kwargs)

            raise InvalidUsageFault(f"Expression is not callable (got '{self._luz_type_name(callee)}')")
        except LuzError as e:
            raise e
        except Exception as e:
            raise InternalFault(str(e))

    # ── Built-in functions ────────────────────────────────────────────────────
    # Built-ins are implemented as Python methods so they have full access to
    # the host environment.  They receive already-evaluated Luz values as
    # arguments (Python ints, floats, strs, lists, dicts, bools).

    # luz_repr() formats any Luz value using Luz syntax (used inside collections).
    # Strings get double quotes, booleans are lowercase, null is "null".
    @staticmethod
    def luz_repr(val):
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, str):
            return f'"{val}"'
        if isinstance(val, list):
            items = ", ".join(Interpreter.luz_repr(v) for v in val)
            return f"[{items}]"
        if isinstance(val, dict):
            pairs = ", ".join(
                f"{Interpreter.luz_repr(k)}: {Interpreter.luz_repr(v)}"
                for k, v in val.items()
            )
            return "{" + pairs + "}"
        return str(val)

    # luz_display() formats a top-level value for write() — strings print
    # without quotes, everything else delegates to luz_repr().
    @staticmethod
    def luz_display(val):
        if isinstance(val, str):
            return val
        return Interpreter.luz_repr(val)
    
    @staticmethod
    def _check_type(value, type_name):
        if type_name == 'int':
            return isinstance(value, int) and not isinstance(value, bool)
        if type_name == 'float':
            return isinstance(value, float)
        if type_name == 'number':
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if type_name == 'string':
            return isinstance(value, str)
        if type_name == 'bool':
            return isinstance(value, bool)
        if type_name == 'list':
            return isinstance(value, list)
        if type_name == 'dict':
            return isinstance(value, dict)
        if type_name == 'null':
            return value is None
        # Class name - walk the hierarchy to support inheritance
        if isinstance(value, LuzInstance):
            cls = value.luz_class
            while cls is not None:
                if cls.name == type_name:
                    return True
                cls = cls.parent
        return False
    
    @staticmethod
    def _luz_type_name(value):
        if value is None: return 'null'
        if isinstance(value, bool): return 'bool'
        if isinstance(value, float): return 'float'
        if isinstance(value, int): return 'int'
        if isinstance(value, str): return 'string'
        if isinstance(value, dict): return 'dict'
        if isinstance(value, list): return 'list'
        if isinstance(value, LuzInstance): return value.luz_class.name
        return type(value).__name__
    

    # write() is the standard output function.  Booleans are displayed as
    # lowercase "true"/"false" (matching Luz syntax) rather than Python's
    # "True"/"False".
    def builtin_write(self, *args):
        print(*[self.luz_display(arg) for arg in args])
        return None

    # listen() reads a line from stdin.  It tries to parse the input as a
    # number so that numeric I/O doesn't require an explicit cast.  If parsing
    # fails (non-numeric input), the raw string is returned.
    def builtin_listen(self, prompt=""):
        res = input(prompt)
        try:
            # A dot in the string suggests a float; otherwise try integer.
            if '.' in res:
                return float(res)
            return int(res)
        except ValueError:
            return res  # Return as string when the input is not a number

    def builtin_len(self, obj):
        try:
            return int(len(obj))
        except TypeError:
            raise TypeViolationFault(f"Object of type '{self._luz_type_name(obj)}' has no length")

    def builtin_append(self, list_obj, element):
        if not isinstance(list_obj, list):
            raise ArgumentFault("append() requires a list as its first argument")
        list_obj.append(element)  # Mutates in place; caller's variable is updated automatically
        return None

    # pop() removes and returns an element by index, or the last element if no
    # index is given.  This matches Python's list.pop() behaviour.
    def builtin_pop(self, list_obj, index=None):
        if not isinstance(list_obj, list):
            raise ArgumentFault("pop() requires a list as its first argument")
        try:
            if index is None:
                return list_obj.pop()
            if not isinstance(index, int):
                raise TypeViolationFault("Index for pop() must be an integer")
            return list_obj.pop(index)
        except IndexError:
            raise IndexFault("Index out of range in pop() operation")

    def builtin_reverse(self, value):
        """Return a reversed copy of a list or string"""
        if isinstance(value, list):
            return list(reversed(value))
        elif isinstance(value, str):
            return value[::-1]
        else:
            raise TypeClashFault(
                f"reverse() expects a list or string, got '{self._luz_type_name(value)}'"
            )

    def builtin_any(self, lst):
        """Return True if at least one element is truthy"""
        if not isinstance(lst, list):
            raise TypeClashFault("any() requires a list")
        return any(lst)

    def builtin_all(self, lst):
        """Return True if every element is truthy (True for empty list)"""
        if not isinstance(lst, list):
            raise TypeClashFault("all() requires a list")
        return all(lst)

    def builtin_keys(self, dict_obj):
        if not isinstance(dict_obj, dict):
            raise ArgumentFault("keys() requires a dictionary")
        # Wrap in list() so the return value is a Luz list, not a Python dict_keys view.
        return list(dict_obj.keys())

    def builtin_values(self, dict_obj):
        if not isinstance(dict_obj, dict):
            raise ArgumentFault("values() requires a dictionary")
        return list(dict_obj.values())

    # remove() deletes a key from a dictionary and returns its former value
    # (analogous to Python's dict.pop()).
    def builtin_remove(self, dict_obj, key):
        if not isinstance(dict_obj, dict):
            raise ArgumentFault("remove() requires a dictionary")
        try:
            return dict_obj.pop(key)
        except KeyError:
            raise MemoryAccessFault(f"Key '{key}' not found in dictionary")
        except TypeError:
            raise TypeViolationFault(f"Invalid key type: '{self._luz_type_name(key)}'")

    # ── Type-casting built-ins ────────────────────────────────────────────────

    # to_num() converts a value to the most appropriate numeric type:
    # if the string contains a dot it becomes a float, otherwise an int.
    def builtin_to_num(self, value):
        try:
            if isinstance(value, str) and '.' not in value:
                return int(value)
            return float(value)
        except (ValueError, TypeError):
            raise CastFault(f"Cannot cast value '{value}' to Number")

    # to_int() casts via float first so that "3.7" → 3 works correctly (without
    # float(), int("3.7") would raise ValueError).
    def builtin_to_int(self, value):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            raise CastFault(f"Cannot cast value '{value}' to Int")

    def builtin_to_float(self, value):
        try:
            return float(value)
        except (ValueError, TypeError):
            raise CastFault(f"Cannot cast value '{value}' to Float")

    # to_str() uses Luz boolean representation ("true"/"false") rather than
    # Python's capitalised "True"/"False".
    def builtin_to_str(self, value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def builtin_to_bool(self, value):
        # Delegates to Python's truthiness rules (0/empty-string/empty-list → False).
        return bool(value)

    # ── String utility helpers ────────────────────────────────────────────────

    # _require_str() is a DRY helper that validates the type of an argument
    # before string operations, producing a consistent error message format.
    def _require_str(self, value, fname):
        if not isinstance(value, str):
            raise ArgumentFault(f"{fname}() requires a string, got '{self._luz_type_name(value)}'")

    def builtin_trim(self, s):
        # Removes leading and trailing whitespace.
        self._require_str(s, 'trim')
        return s.strip()

    def builtin_uppercase(self, s):
        self._require_str(s, 'uppercase')
        return s.upper()

    def builtin_lowercase(self, s):
        self._require_str(s, 'lowercase')
        return s.lower()

    # swap() replaces all occurrences of `old` with `new` inside `s`.
    # Named "swap" rather than "replace" to feel more natural in the language.
    def builtin_swap(self, s, old, new):
        self._require_str(s, 'swap')
        self._require_str(old, 'swap')
        self._require_str(new, 'swap')
        return s.replace(old, new)

    def builtin_begins(self, s, prefix):
        self._require_str(s, 'begins')
        self._require_str(prefix, 'begins')
        return s.startswith(prefix)

    def builtin_ends(self, s, suffix):
        self._require_str(s, 'ends')
        self._require_str(suffix, 'ends')
        return s.endswith(suffix)

    def builtin_contains(self, s, sub):
        self._require_str(s, 'contains')
        self._require_str(sub, 'contains')
        return sub in s

    # split() splits a string on a separator.  If no separator is given, Python
    # splits on any whitespace and discards empty strings, which is the
    # conventional default for a tokenising split.
    def builtin_split(self, s, sep=None):
        self._require_str(s, 'split')
        if sep is not None:
            self._require_str(sep, 'split')
            if sep == '':
                raise ArgumentFault("split() separator cannot be an empty string")
        return s.split(sep)

    # join() concatenates a list of strings with a separator.
    # Non-string elements in the list are coerced with str() for convenience,
    # matching Python's own join behaviour when iterating mixed lists.
    def builtin_join(self, sep, lst):
        self._require_str(sep, 'join')
        if not isinstance(lst, list):
            raise ArgumentFault("join() requires a list as second argument")
        try:
            return sep.join(str(item) if not isinstance(item, str) else item for item in lst)
        except TypeError:
            raise TypeViolationFault("join() list elements must be strings")

    # find() returns the index of the first occurrence of `sub` in `s`, or -1
    # if not found (mirroring Python's str.find()).
    def builtin_find(self, s, sub):
        self._require_str(s, 'find')
        self._require_str(sub, 'find')
        return s.find(sub)

    # count() returns the number of non-overlapping occurrences of `sub` in `s`.
    def builtin_count(self, s, sub):
        self._require_str(s, 'count')
        self._require_str(sub, 'count')
        return s.count(sub)

    # ── OOP visitors ──────────────────────────────────────────────────────────

    # visit_ClassDefNode() builds a LuzClass from the parsed method definitions
    # and stores it in the current environment under the class name.
    # If an `extends` clause is present, the parent class is resolved from the
    # environment and stored on the new class so method lookup can walk up.
    def visit_ClassDefNode(self, node):
        parent = None
        if node.parent_token is not None:
            parent_val = self.current_env.lookup(node.parent_token.value)
            if not isinstance(parent_val, LuzClass):
                raise InvalidUsageFault(f"'{node.parent_token.value}' is not a class")
            parent = parent_val

        methods = {}
        for method_node in node.methods:
            methods[method_node.name_token.value] = LuzFunction(method_node, self.current_env)
        luz_class = LuzClass(node.name_token.value, methods, parent)
        self.current_env.assign(node.name_token.value, luz_class)
        return luz_class

    # visit_AttributeAccessNode() reads obj.attr from a LuzInstance.
    def visit_AttributeAccessNode(self, node):
        obj = self.visit(node.obj_node)
        if not isinstance(obj, (LuzInstance, LuzModule)):
            raise InvalidUsageFault(f"Cannot access attribute on value '{obj}'")
        return obj.get(node.attr_token.value)

    # visit_AttributeAssignNode() writes obj.attr = value on a LuzInstance.
    def visit_AttributeAssignNode(self, node):
        obj = self.visit(node.obj_node)
        if not isinstance(obj, (LuzInstance, LuzModule)):
            raise InvalidUsageFault(f"Cannot set attribute on value '{obj}'")
        value = self.visit(node.value_node)
        obj.set(node.attr_token.value, value)
        return value

    # visit_MethodCallNode() calls obj.method(args), passing the instance as
    # the first argument so that the method body can access it via `self`.
    # If the instance's class has a parent, `super` is injected into the method's
    # local scope as a LuzSuperProxy so the method can call parent implementations.
    def visit_MethodCallNode(self, node):
        obj = self.visit(node.obj_node)
        args = [self.visit(arg) for arg in node.arguments]
        kwargs = {name: self.visit(expr) for name, expr in node.kwargs.items()}
        def _require_args(method, given, expected):
            if given != expected:
                raise ArityFault(f"{method}() requires {expected} argument{'s' if expected != 1 else ''}, got {given}")

        if isinstance(obj, str):
            method_name = node.method_token.value
            if method_name == 'swap':
                _require_args('swap', len(args), 2)
                return obj.replace(args[0], args[1])
            str_methods = {
                'uppercase': lambda: obj.upper(),
                'lowercase': lambda: obj.lower(),
                'trim': lambda: obj.strip(),
                'split': lambda: obj.split(args[0]) if args else obj.split(),
            }
            if method_name in str_methods:
                return str_methods[method_name]()
            raise InvalidUsageFault(f"String has no method '{method_name}'")
        # super.method(args) — call the parent class's version with the same instance
        if isinstance(obj, LuzSuperProxy):
            method = obj.find_method(node.method_token.value)
            if not isinstance(method, LuzFunction):
                raise InvalidUsageFault(f"'{node.method_token.value}' is not a callable method")
            # Pass the original instance (not the proxy) as `self` in the parent method.
            # Also inject `super` pointing one level higher, enabling super chains.
            extra = {}
            grandparent = obj.parent_class.parent
            if grandparent:
                extra['super'] = LuzSuperProxy(obj.instance, grandparent)
            return method(self, [obj.instance] + args, extra_bindings=extra, kwargs=kwargs)

        # Module function call: m.func(args) — no implicit `self`, no super
        if isinstance(obj, LuzModule):
            fn = obj.get(node.method_token.value)
            if not callable(fn) and not isinstance(fn, (LuzFunction, LuzLambda)):
                raise InvalidUsageFault(f"Module attribute '{node.method_token.value}' is not callable")
            if isinstance(fn, LuzFunction):
                return fn(self, args, kwargs=kwargs)
            if isinstance(fn, LuzLambda):
                return fn(self, args)
            raise InvalidUsageFault(f"Module attribute '{node.method_token.value}' is not callable")

        # List method dot syntax: [1,2,3].append(4), list.pop(), etc.
        if isinstance(obj, list):
            method_name = node.method_token.value
            if method_name == 'append':
                _require_args('append', len(args), 1)
                return self.builtin_append(obj, args[0])
            if method_name == 'contains':
                _require_args('contains', len(args), 1)
                return args[0] in obj
            if method_name == 'join':
                _require_args('join', len(args), 1)
                return self.builtin_join(args[0], obj)
            list_methods = {
                'pop':      lambda: self.builtin_pop(obj, args[0] if args else None),
                'len':      lambda: self.builtin_len(obj),
            }
            if method_name in list_methods:
                return list_methods[method_name]()
            raise InvalidUsageFault(f"List has no method '{method_name}'")

        # Dict method dot syntax: d.keys(), d.values(), d.len(), etc.
        if isinstance(obj, dict):
            method_name = node.method_token.value
            if method_name == 'contains':
                _require_args('contains', len(args), 1)
                return args[0] in obj
            if method_name == 'remove':
                _require_args('remove', len(args), 1)
                return self.builtin_remove(obj, args[0])
            dict_methods = {
                'keys':     lambda: self.builtin_keys(obj),
                'values':   lambda: self.builtin_values(obj),
                'len':      lambda: self.builtin_len(obj),
            }
            if method_name in dict_methods:
                return dict_methods[method_name]()
            raise InvalidUsageFault(f"Dict has no method '{method_name}'")

        if not isinstance(obj, LuzInstance):
            raise InvalidUsageFault(f"Cannot call method on non-instance value '{obj}'")

        raw = obj.get(node.method_token.value)
        method = raw.function if isinstance(raw, BoundMethod) else raw
        if not isinstance(method, LuzFunction):
            raise InvalidUsageFault(f"'{node.method_token.value}' is not a callable method")

        # Inject `super` if the class has a parent so methods can call super.method()
        extra = {}
        if obj.luz_class.parent:
            extra['super'] = LuzSuperProxy(obj, obj.luz_class.parent)

        return method(self, [obj] + args, extra_bindings=extra, kwargs=kwargs)

    # ── Type inspection built-ins ─────────────────────────────────────────────

    # typeof() returns the type of a value as a string.
    # For class instances it returns the class name, for primitives it returns
    # the Luz type name ("int", "float", "string", "bool", "list", "dict").
    def builtin_typeof(self, value):
        if value is None:
            return "null"
        if isinstance(value, LuzInstance):
            return value.luz_class.name
        if isinstance(value, LuzClass):
            return "class"
        if isinstance(value, (LuzFunction, LuzLambda)):
            return "function"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "list"
        if isinstance(value, dict):
            return "dict"
        if isinstance(value, LuzModule):
            return "module"
        return "unknown"

    # instanceof() returns true if value is an instance of the given class or
    # any of its subclasses, walking up the hierarchy.
    # This enables polymorphic checks: instanceof(dog, Animal) == true
    def builtin_instanceof(self, value, luz_class):
        if not isinstance(luz_class, LuzClass):
            raise ArgumentFault("instanceof() second argument must be a class")
        if not isinstance(value, LuzInstance):
            return False
        cls = value.luz_class
        while cls is not None:
            if cls is luz_class:
                return True
            cls = cls.parent
        return False

    # ── Math built-ins ────────────────────────────────────────────────────────
    import math as _math

    def _require_num(self, value, fname):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ArgumentFault(f"{fname}() requires a number, got '{self._luz_type_name(value)}'")

    def builtin_abs(self, x):
        self._require_num(x, 'abs')
        return abs(x)

    def builtin_sqrt(self, x):
        self._require_num(x, 'sqrt')
        if x < 0:
            raise NumericFault("sqrt() cannot be applied to a negative number")
        import math
        return math.sqrt(x)

    def builtin_floor(self, x):
        self._require_num(x, 'floor')
        import math
        return int(math.floor(x))

    def builtin_ceil(self, x):
        self._require_num(x, 'ceil')
        import math
        return int(math.ceil(x))

    # round(x) rounds to nearest integer; round(x, digits) keeps decimal places.
    def builtin_round(self, x, digits=0):
        self._require_num(x, 'round')
        if not isinstance(digits, int):
            raise ArgumentFault(f"round() second argument must be an int, got '{self._luz_type_name(digits)}'")
        return round(x, digits)

    # clamp(x, low, high) forces x into the [low, high] range.
    # Descriptive and not a Python builtin — handy for game logic, UI, etc.
    def builtin_clamp(self, x, low, high):
        self._require_num(x, 'clamp')
        self._require_num(low, 'clamp')
        self._require_num(high, 'clamp')
        return max(low, min(x, high))

    def builtin_sin(self, x):
        self._require_num(x, 'sin')
        import math
        return math.sin(x)
    
    def builtin_cos(self, x):
        self._require_num(x, 'cos')
        import math
        return math.cos(x)
    
    def builtin_tan(self, x):
        self._require_num(x, 'tan')
        import math
        return math.tan(x)
    
    def builtin_asin(self, x):
        self._require_num(x, 'asin')
        if x < -1 or x > 1:
            raise NumericFault(f"asin() domain error: argument must be in [-1, 1], got {x}")
        import math
        return math.asin(x)
    
    def builtin_acos(self, x):
        self._require_num(x, 'acos')
        if x < -1 or x > 1:
            raise NumericFault(f"acos() domain error: argument must be in [-1, 1], got {x}")
        import math
        return math.acos(x)

    def builtin_atan(self, x):
        self._require_num(x, 'atan')
        import math
        return math.atan(x)
    
    def builtin_atan2(self, y, x):
        self._require_num(y, 'atan2')
        self._require_num(x, 'atan2')
        import math
        return math.atan2(y, x)
    
    def builtin_exp(self, x):
        self._require_num(x, 'exp')
        import math
        return math.exp(x)
    
    def builtin_ln(self, x):
        self._require_num(x, 'ln')
        if x <= 0:
            raise NumericFault(f"ln() domain error: argument must be positive, got {x}")
        import math
        return math.log(x)
    
    def builtin_log2(self, x):
        self._require_num(x, 'log2')
        if x <= 0:
            raise NumericFault(f"log2() domain error: argument must be positive, got {x}")
        import math
        return math.log2(x)

    def builtin_log10(self, x):
        self._require_num(x, 'log10')
        if x <= 0:
            raise NumericFault(f"log10() domain error: argument must be positive, got {x}")
        import math
        return math.log10(x)
    
    def builtin_pow(self, base, exp):
        self._require_num(base, 'pow')
        self._require_num(exp, 'pow')
        return base ** exp

    # max(a, b) or max(list) — returns the largest value.
    def builtin_max(self, *args):
        if len(args) == 1 and isinstance(args[0], list):
            lst = args[0]
            if not lst:
                raise ArgumentFault("max() cannot be applied to an empty list")
            return max(lst)
        if len(args) < 2:
            raise ArityFault("max() requires at least two arguments or one list")
        return max(args)

    # min(a, b) or min(list) — returns the smallest value.
    def builtin_min(self, *args):
        if len(args) == 1 and isinstance(args[0], list):
            lst = args[0]
            if not lst:
                raise ArgumentFault("min() cannot be applied to an empty list")
            return min(lst)
        if len(args) < 2:
            raise ArityFault("min() requires at least two arguments or one list")
        return min(args)

    # sign(x) returns -1, 0, or 1 depending on the sign of x.
    def builtin_sign(self, x):
        self._require_num(x, 'sign')
        if x > 0: return 1
        if x < 0: return -1
        return 0

    # odd(x) and even(x) — boolean parity checks, more readable than x % 2 == 1.
    def builtin_odd(self, x):
        self._require_num(x, 'odd')
        return int(x) % 2 != 0

    def builtin_even(self, x):
        self._require_num(x, 'even')
        return int(x) % 2 == 0

    def builtin_index(self, list_obj, value):
        """Return the index of value in list, or -1 if not found."""
        if not isinstance(list_obj, list):
            raise ArgumentFault("index() requires a list as its first argument")
        try:
            return list_obj.index(value)
        except ValueError:
            return -1

    def builtin_insert(self, list_obj, index, value):
        """Insert value at index in list. Returns null."""
        if not isinstance(list_obj, list):
            raise ArgumentFault("insert() requires a list as its first argument")
        if not isinstance(index, int):
            raise TypeViolationFault("Index for insert() must be an integer")
        list_obj.insert(index, value)
        return None

    # ── Random primitives (used by luz-random stdlib) ──────────────────────────

    def builtin_rand_float(self):
        import random
        return random.random()

    def builtin_rand_int(self, a, b):
        import random
        self._require_num(a, '_rand_int')
        self._require_num(b, '_rand_int')
        return random.randint(int(a), int(b))

    def builtin_rand_seed(self, seed):
        import random
        random.seed(seed)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def builtin_read_file(self, path):
        if not isinstance(path, str):
            raise TypeViolationFault("read_file: path must be a string")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise RuntimeFault(f"read_file: file not found: '{path}'")
        except OSError as e:
            raise RuntimeFault(f"read_file: {e}")

    def builtin_write_file(self, path, content):
        if not isinstance(path, str):
            raise TypeViolationFault("write_file: path must be a string")
        if not isinstance(content, str):
            raise TypeViolationFault("write_file: content must be a string")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except OSError as e:
            raise RuntimeFault(f"write_file: {e}")
        return None

    def builtin_append_file(self, path, content):
        if not isinstance(path, str):
            raise TypeViolationFault("append_file: path must be a string")
        if not isinstance(content, str):
            raise TypeViolationFault("append_file: content must be a string")
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content)
        except OSError as e:
            raise RuntimeFault(f"append_file: {e}")
        return None

    def builtin_file_exists(self, path):
        if not isinstance(path, str):
            raise TypeViolationFault("file_exists: path must be a string")
        import os
        return os.path.exists(path)

    def builtin_delete_file(self, path):
        if not isinstance(path, str):
            raise TypeViolationFault("delete_file: path must be a string")
        import os
        try:
            os.remove(path)
        except FileNotFoundError:
            raise RuntimeFault(f"delete_file: file not found: '{path}'")
        except OSError as e:
            raise RuntimeFault(f"delete_file: {e}")
        return None

    # ── System / OS ───────────────────────────────────────────────────────────

    def builtin_exec(self, command):
        if not isinstance(command, str):
            raise TypeViolationFault("exec: command must be a string")
        import subprocess
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr

    def builtin_exec_code(self, command):
        if not isinstance(command, str):
            raise TypeViolationFault("exec_code: command must be a string")
        import subprocess
        result = subprocess.run(command, shell=True)
        return result.returncode

    def builtin_env_get(self, name):
        if not isinstance(name, str):
            raise TypeViolationFault("env_get: name must be a string")
        return os.environ.get(name, None)

    def builtin_env_set(self, name, value):
        if not isinstance(name, str):
            raise TypeViolationFault("env_set: name must be a string")
        os.environ[name] = str(value)
        return None

    def builtin_get_cwd(self):
        return os.getcwd()

    def builtin_set_cwd(self, path):
        if not isinstance(path, str):
            raise TypeViolationFault("set_cwd: path must be a string")
        try:
            os.chdir(path)
        except OSError as e:
            raise RuntimeFault(f"set_cwd: {e}")
        return None

    def builtin_get_os(self):
        import platform
        s = platform.system().lower()
        if s == 'windows': return 'windows'
        if s == 'darwin':  return 'macos'
        return 'linux'

    def builtin_get_hostname(self):
        import socket
        return socket.gethostname()

    def builtin_get_username(self):
        return os.environ.get('USERNAME') or os.environ.get('USER') or 'unknown'

    def builtin_get_pid(self):
        return os.getpid()

    def builtin_sys_exit(self, code=0):
        import sys
        sys.exit(int(code))

    def builtin_list_dir(self, path='.'):
        if not isinstance(path, str):
            raise TypeViolationFault("list_dir: path must be a string")
        try:
            return os.listdir(path)
        except OSError as e:
            raise RuntimeFault(f"list_dir: {e}")

    def builtin_make_dir(self, path):
        if not isinstance(path, str):
            raise TypeViolationFault("make_dir: path must be a string")
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise RuntimeFault(f"make_dir: {e}")
        return None

    def builtin_sleep(self, seconds):
        import time
        time.sleep(float(seconds))
        return None

    def builtin_clock_now(self):
        import datetime
        t = datetime.datetime.now()
        return {
            "year":    t.year,
            "month":   t.month,
            "day":     t.day,
            "hour":    t.hour,
            "min":     t.minute,
            "sec":     t.second,
            "ms":      t.microsecond // 1000,
            "weekday": t.weekday(),   # 0=Monday … 6=Sunday
            "yearday": t.timetuple().tm_yday,
        }

    def builtin_clock_stamp(self):
        import time
        return time.time()

    def builtin_clock_fmt(self, fmt_str):
        import datetime
        return datetime.datetime.now().strftime(str(fmt_str))

    def builtin_clock_from_stamp(self, ts):
        import datetime
        t = datetime.datetime.fromtimestamp(float(ts))
        return {
            "year":    t.year,
            "month":   t.month,
            "day":     t.day,
            "hour":    t.hour,
            "min":     t.minute,
            "sec":     t.second,
            "ms":      t.microsecond // 1000,
            "weekday": t.weekday(),
            "yearday": t.timetuple().tm_yday,
        }

    def builtin_clock_parse(self, date_str, fmt_str):
        import datetime, time
        t = datetime.datetime.strptime(str(date_str), str(fmt_str))
        return time.mktime(t.timetuple())
    
    def builtin_clock_fmt_stamp(self, ts, fmt_str):
        import datetime 
        return datetime.datetime.fromtimestamp(float(ts)).strftime(str(fmt_str))
