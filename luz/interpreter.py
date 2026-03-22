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
        self.records = {}             # Maps variable name → current value
        self.parent = parent          # Enclosing scope (None for global)
        self.is_function_scope = is_function_scope

    # define() unconditionally sets a name in the current scope.
    # Used when entering a for-loop (to bind the loop variable) and when
    # binding function parameters.
    def define(self, name, value):
        self.records[name] = value
        return value

    # lookup() searches the scope chain upward until it finds the name or
    # reaches the top-level global scope with no parent.
    def lookup(self, name):
        if name in self.records:
            return self.records[name]
        if self.parent:
            return self.parent.lookup(name)
        raise UndefinedSymbolFault(f"Symbol '{name}' is not defined in the current scope")

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
            self.records[name] = value
            return value
        # Walk up only if we haven't hit a function boundary.
        # Stopping at function boundaries prevents accidental closure mutation:
        #   x = 1
        #   function f() { x = 2 }   # should NOT change the outer x
        if self.parent and not self.is_function_scope:
            return self.parent.assign(name, value)
        # Function scope or global: create the variable here rather than raising.
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
    def __call__(self, interpreter, arguments, extra_bindings=None):
        total = len(self.node.arg_tokens)
        variadic = self.node.variadic
        # Number of fixed (non-variadic) params
        fixed = total - 1 if variadic else total
        required = sum(1 for d in self.node.defaults[:fixed] if d is None)

        if variadic:
            if len(arguments) < required:
                raise ArityFault(f"Function '{self.node.name_token.value}' expects at least {required} argument(s), but received {len(arguments)}")
        else:
            if len(arguments) < required or len(arguments) > total:
                if required == total:
                    raise ArityFault(f"Function '{self.node.name_token.value}' expects {total} argument(s), but received {len(arguments)}")
                else:
                    raise ArityFault(f"Function '{self.node.name_token.value}' expects {required}–{total} argument(s), but received {len(arguments)}")

        # Create a new child of the closure so parameters are local to this call.
        # is_function_scope=True prevents assignments inside the body from
        # walking up into the caller's environment.
        env = Environment(self.closure, is_function_scope=True)
        for i in range(fixed):
            if i < len(arguments):
                env.define(self.node.arg_tokens[i].value, arguments[i])
            else:
                prev = interpreter.current_env
                interpreter.current_env = self.closure
                default_val = interpreter.visit(self.node.defaults[i])
                interpreter.current_env = prev
                env.define(self.node.arg_tokens[i].value, default_val)
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
            return e.value
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

    def __call__(self, interpreter, arguments, extra_bindings=None):
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
        cls = self
        while cls is not None:
            if name in cls.methods:
                return cls.methods[name]
            cls = cls.parent
        return None

    def __repr__(self):
        return f"<class {self.name}>"


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
            return method
        raise AttributeNotFoundFault(f"'{self.luz_class.name}' has no attribute '{name}'")

    def set(self, name, value):
        self.attributes[name] = value

    def __repr__(self):
        return f"<{self.luz_class.name} instance>"


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

        # current_line is updated by visit() as nodes are processed.
        # When an error is raised without a line number, this value is attached
        # to give the user a useful "error at line N" message.
        self.current_line = None

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
            '_rand_float': self.builtin_rand_float,
            '_rand_int': self.builtin_rand_int,
            '_rand_seed': self.builtin_rand_seed,
            'read_file':   self.builtin_read_file,
            'write_file':  self.builtin_write_file,
            'append_file': self.builtin_append_file,
            'file_exists': self.builtin_file_exists,
            'delete_file': self.builtin_delete_file,
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
        if line is not None:
            self.current_line = line

        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, self.no_visit_method)
        try:
            return method(node)
        except LuzError as e:
            # Don't stamp line numbers onto control-flow signals — they are
            # not errors and their "line" would be misleading.
            if not isinstance(e, (ReturnException, BreakException, ContinueException)) and e.line is None:
                e.line = self.current_line
            raise

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
        if value is None:
            return 'null'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return str(value)

    def visit_ListNode(self, node):
        # Evaluate every element expression and collect the results into a Python list.
        return [self.visit(element) for element in node.elements]

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
                raise TypeViolationFault(f"List index must be an integer, not {type(index).__name__}")
            if index < 0:
                index = len(base) + index
            try:
                return base[index]
            except IndexError:
                raise IndexFault(f"Index {index} is out of range for list of size {len(base)}")
        elif isinstance(base, str):
            if not isinstance(index, int):
                raise TypeViolationFault(f"String index must be an integer, not {type(index).__name__}")
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
                raise TypeViolationFault(f"Unhashable type: '{type(index).__name__}' cannot be used as a dictionary key")
        else:
            raise InvalidUsageFault(f"Type '{type(base).__name__}' does not support indexing")

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
                raise TypeViolationFault(f"List index must be an integer, not {type(index).__name__}")
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
                raise TypeViolationFault(f"Unhashable key type: '{type(index).__name__}'")
        else:
            raise InvalidUsageFault(f"Type '{type(base).__name__}' does not support index assignment")

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
        try:
            return self.visit(node.try_block)
        except LuzError as e:
            if isinstance(e, (ReturnException, BreakException, ContinueException)):
                # These are control-flow signals, not errors — let them propagate.
                raise e

            # Run the rescue block in a new child scope so the error variable
            # does not leak into the surrounding environment after the block ends.
            previous_env = self.current_env
            rescue_env = Environment(previous_env)
            self.current_env = rescue_env
            try:
                self.current_env.define(node.error_var_token.value, str(e))
                return self.visit(node.catch_block)
            finally:
                self.current_env = previous_env
        except Exception as e:
            # Catch unexpected Python exceptions (interpreter bugs) so Luz code
            # can at least observe that something went wrong.
            previous_env = self.current_env
            rescue_env = Environment(previous_env)
            self.current_env = rescue_env
            try:
                self.current_env.define(node.error_var_token.value, f"InternalFault: {str(e)}")
                return self.visit(node.catch_block)
            finally:
                self.current_env = previous_env

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

        # Register before executing to guard against circular imports.
        self.imported_files.add(abs_path)

        try:
            lexer = Lexer(code)
            tokens = lexer.get_tokens()
            parser = Parser(tokens)
            ast = parser.parse()

            # Switch to the global env for module execution so definitions land
            # at the top level regardless of where `import` appeared in the code.
            temp_env = self.current_env
            self.current_env = self.global_env
            try:
                self.visit(ast)
            finally:
                self.current_env = temp_env  # Restore the caller's env

        except LuzError as e:
            raise ImportFault(f"Error in module '{file_path}': {str(e)}")
        except Exception as e:
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
                raise TypeClashFault(f"Unary '-' cannot be applied to type '{type(res).__name__}'")
            return -res
        return res

    # visit_VarAssignNode() evaluates the right-hand side and stores it.
    # Environment.assign() handles the scope chain walk.
    def visit_VarAssignNode(self, node):
        var_name = node.var_name_token.value
        value = self.visit(node.value_node)
        self.current_env.assign(var_name, value)
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
                raise TypeClashFault(f"Cannot perform addition between {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.MINUS:
            try:
                return left - right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '-': {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.MUL:
            # Allow string repetition: "ab" * 3 == "ababab"
            # The right operand is truncated to int because Luz floats are
            # valid numbers but Python str * float is not allowed.
            if isinstance(left, str) and isinstance(right, (int, float)):
                return left * int(right)
            try:
                return left * right
            except TypeError:
                raise IllegalOperationFault(f"Multiplication is not supported for {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.DIV:
            # `/` always returns a float in Luz, matching the intuitive
            # expectation that 5 / 2 == 2.5, not 2.
            if right == 0:
                raise ZeroDivisionFault("Division by zero is not allowed")
            try:
                return float(left) / float(right)
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '/': {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.IDIV:
            # `//` truncates towards negative infinity (Python floor division).
            if right == 0:
                raise ZeroDivisionFault("Integer division by zero is not allowed")
            try:
                return int(left) // int(right)
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '//': {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.MOD:
            if right == 0:
                raise ZeroDivisionFault("Modulo by zero is not allowed")
            try:
                return left % right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '%': {type(left).__name__} and {type(right).__name__}")

        elif node.op_token.type == TokenType.POW:
            try:
                return left ** right
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '**': {type(left).__name__} and {type(right).__name__}")

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
                return self.visit(block)
        if node.else_case:
            return self.visit(node.else_case)
        return None

    # visit_WhileNode() re-evaluates the condition before every iteration.
    # BreakException exits the loop; ContinueException skips to the next check.
    def visit_WhileNode(self, node):
        while self.visit(node.condition_node):
            try:
                self.visit(node.block)
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

        if not isinstance(start_value, (int, float)) or not isinstance(end_value, (int, float)):
            raise TypeViolationFault("For loop range boundaries must be numeric")

        i = start_value
        # Create a dedicated child environment for the loop so the counter
        # variable (and any variables defined inside the body) don't leak out.
        previous_env = self.current_env
        self.current_env = Environment(previous_env)
        try:
            while i <= end_value:
                # Re-define the loop variable each iteration so it always
                # reflects the current counter value.
                self.current_env.define(var_name, i)
                try:
                    self.visit(node.block)
                except BreakException:
                    break
                except ContinueException:
                    pass  # ContinueException just skips to the i += 1 below
                i += 1
        finally:
            self.current_env = previous_env  # Restore scope even if an error escapes
        return None

    # visit_ForEachNode() iterates over a list, string, or dict.
    # Lists and strings yield their elements/characters one by one.
    # Dicts yield their keys (consistent with most languages and Python).
    def visit_ForEachNode(self, node):
        var_name = node.var_name_token.value
        iterable = self.visit(node.iterable_node)

        if not isinstance(iterable, (list, str, dict)):
            raise TypeViolationFault(f"Cannot iterate over type '{type(iterable).__name__}' — expected list, string, or dict")

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
        # Arguments are fully evaluated before the call so their values are
        # independent of the callee's scope.
        arguments = [self.visit(arg) for arg in node.arguments]

        if func_name in self.builtins:
            return self.builtins[func_name](*arguments)

        try:
            function = self.current_env.lookup(func_name)

            # Class constructor call: Dog("Rex") creates a new LuzInstance and
            # calls `init` if one is defined anywhere in the class hierarchy.
            if isinstance(function, LuzClass):
                instance = LuzInstance(function)
                init_method = function.find_method('init')
                if init_method is not None:
                    extra = {}
                    if function.parent:
                        extra['super'] = LuzSuperProxy(instance, function.parent)
                    init_method(self, [instance] + arguments, extra_bindings=extra)
                return instance

            if not isinstance(function, (LuzFunction, LuzLambda)):
                # The name exists but holds a non-callable value (e.g. a number).
                raise InvalidUsageFault(f"'{func_name}' is not a callable function")
            return function(self, arguments)
        except UndefinedSymbolFault:
            # Re-raise as FunctionNotFoundFault for a more descriptive message.
            raise FunctionNotFoundFault(f"Function '{func_name}' was not found")
        except LuzError as e:
            raise e  # Preserve the original LuzError type (don't wrap it)
        except Exception as e:
            raise InternalFault(str(e))

    # ── Built-in functions ────────────────────────────────────────────────────
    # Built-ins are implemented as Python methods so they have full access to
    # the host environment.  They receive already-evaluated Luz values as
    # arguments (Python ints, floats, strs, lists, dicts, bools).

    # write() is the standard output function.  Booleans are displayed as
    # lowercase "true"/"false" (matching Luz syntax) rather than Python's
    # "True"/"False".
    def builtin_write(self, *args):
        formatted_args = []
        for arg in args:
            if arg is None:
                formatted_args.append("null")
            elif isinstance(arg, bool):
                formatted_args.append("true" if arg else "false")
            else:
                formatted_args.append(arg)
        print(*formatted_args)
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
        except:
            raise TypeViolationFault(f"Object of type '{type(obj).__name__}' has no length")

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
            raise TypeViolationFault(f"Invalid key type: '{type(key).__name__}'")

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
            raise ArgumentFault(f"{fname}() requires a string, got '{type(value).__name__}'")

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
        if not isinstance(obj, LuzInstance):
            raise InvalidUsageFault(f"Cannot access attribute on non-instance value '{obj}'")
        return obj.get(node.attr_token.value)

    # visit_AttributeAssignNode() writes obj.attr = value on a LuzInstance.
    def visit_AttributeAssignNode(self, node):
        obj = self.visit(node.obj_node)
        if not isinstance(obj, LuzInstance):
            raise InvalidUsageFault(f"Cannot set attribute on non-instance value '{obj}'")
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
            return method(self, [obj.instance] + args, extra_bindings=extra)

        if not isinstance(obj, LuzInstance):
            raise InvalidUsageFault(f"Cannot call method on non-instance value '{obj}'")

        method = obj.get(node.method_token.value)
        if not isinstance(method, LuzFunction):
            raise InvalidUsageFault(f"'{node.method_token.value}' is not a callable method")

        # Inject `super` if the class has a parent so methods can call super.method()
        extra = {}
        if obj.luz_class.parent:
            extra['super'] = LuzSuperProxy(obj, obj.luz_class.parent)

        return method(self, [obj] + args, extra_bindings=extra)

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
            raise ArgumentFault(f"{fname}() requires a number, got '{type(value).__name__}'")

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
        return round(x, int(digits))

    # clamp(x, low, high) forces x into the [low, high] range.
    # Descriptive and not a Python builtin — handy for game logic, UI, etc.
    def builtin_clamp(self, x, low, high):
        self._require_num(x, 'clamp')
        self._require_num(low, 'clamp')
        self._require_num(high, 'clamp')
        return max(low, min(x, high))

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
