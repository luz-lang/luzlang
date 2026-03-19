from .tokens import TokenType
from .exceptions import *
from .lexer import Lexer
from .parser import Parser
import os

class Environment:
    def __init__(self, parent=None):
        self.records = {}
        self.parent = parent

    def define(self, name, value):
        self.records[name] = value
        return value

    def lookup(self, name):
        if name in self.records:
            return self.records[name]
        if self.parent:
            return self.parent.lookup(name)
        raise UndefinedSymbolFault(f"Symbol '{name}' is not defined in the current scope")

    def assign(self, name, value):
        if name in self.records:
            self.records[name] = value
            return value
        if self.parent:
            return self.parent.assign(name, value)
        self.records[name] = value
        return value

class LuzFunction:
    def __init__(self, node, closure):
        self.node = node
        self.closure = closure

    def __call__(self, interpreter, arguments):
        if len(arguments) != len(self.node.arg_tokens):
            raise ArityFault(f"Function '{self.node.name_token.value}' expects {len(self.node.arg_tokens)} arguments, but received {len(arguments)}")
            
        env = Environment(self.closure)
        for i in range(len(self.node.arg_tokens)):
            env.define(self.node.arg_tokens[i].value, arguments[i])
        
        try:
            interpreter.execute_block(self.node.block, env)
        except ReturnException as e:
            return e.value
        return None

class Interpreter:
    def __init__(self):
        self.global_env = Environment()
        self.current_env = self.global_env
        self.imported_files = set()
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
            'to_bool': self.builtin_to_bool
        }

    def execute_block(self, block, env):
        previous_env = self.current_env
        self.current_env = env
        try:
            result = None
            for statement in block:
                result = self.visit(statement)
            return result
        finally:
            self.current_env = previous_env

    def visit(self, node):
        if isinstance(node, list):
            result = None
            for statement in node:
                result = self.visit(statement)
            return result

        method_name = f'visit_{type(node).__name__}'
        method = getattr(self, method_name, self.no_visit_method)
        return method(node)

    def no_visit_method(self, node):
        raise InternalFault(f"No visit_{type(node).__name__} method defined in the interpreter")

    def visit_NumberNode(self, node):
        return node.token.value

    def visit_StringNode(self, node):
        return node.token.value

    def visit_BooleanNode(self, node):
        return True if node.token.type == TokenType.TRUE else False

    def visit_ListNode(self, node):
        return [self.visit(element) for element in node.elements]

    def visit_DictNode(self, node):
        res = {}
        for key_node, value_node in node.pairs:
            key = self.visit(key_node)
            value = self.visit(value_node)
            res[key] = value
        return res

    def visit_IndexAccessNode(self, node):
        base = self.visit(node.base_node)
        index = self.visit(node.index_node)
        
        if isinstance(base, list):
            if not isinstance(index, int):
                raise TypeViolationFault(f"List index must be an integer, not {type(index).__name__}")
            try:
                return base[index]
            except IndexError:
                raise IndexFault(f"Index {index} is out of range for list of size {len(base)}")
        elif isinstance(base, dict):
            try:
                return base[index]
            except KeyError:
                raise MemoryAccessFault(f"Key '{index}' not found in dictionary")
            except TypeError:
                raise TypeViolationFault(f"Unhashable type: '{type(index).__name__}' cannot be used as a dictionary key")
        else:
            raise InvalidUsageFault(f"Type '{type(base).__name__}' does not support indexing")

    def visit_IndexAssignNode(self, node):
        base = self.visit(node.base_node)
        index = self.visit(node.index_node)
        value = self.visit(node.value_node)
        
        if isinstance(base, list):
            if not isinstance(index, int):
                raise TypeViolationFault(f"List index must be an integer, not {type(index).__name__}")
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

    def visit_AttemptRescueNode(self, node):
        try:
            return self.visit(node.try_block)
        except LuzError as e:
            if isinstance(e, ReturnException):
                raise e
            
            previous_env = self.current_env
            rescue_env = Environment(previous_env)
            self.current_env = rescue_env
            try:
                self.current_env.define(node.error_var_token.value, str(e))
                return self.visit(node.catch_block)
            finally:
                self.current_env = previous_env
        except Exception as e:
            previous_env = self.current_env
            rescue_env = Environment(previous_env)
            self.current_env = rescue_env
            try:
                self.current_env.define(node.error_var_token.value, f"InternalFault: {str(e)}")
                return self.visit(node.catch_block)
            finally:
                self.current_env = previous_env

    def visit_AlertNode(self, node):
        msg = self.visit(node.expression_node)
        raise UserFault(str(msg))

    def visit_ImportNode(self, node):
        file_path = node.file_path_token.value
        abs_path = os.path.abspath(file_path)
        
        if abs_path in self.imported_files:
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
        except FileNotFoundError:
            raise ModuleNotFoundFault(f"Module file '{file_path}' not found")
        except Exception as e:
            raise ImportFault(f"Failed to read module '{file_path}': {str(e)}")
            
        self.imported_files.add(abs_path)
        
        try:
            lexer = Lexer(code)
            tokens = lexer.get_tokens()
            parser = Parser(tokens)
            ast = parser.parse()
            
            temp_env = self.current_env
            self.current_env = self.global_env
            try:
                self.visit(ast)
            finally:
                self.current_env = temp_env
                
        except LuzError as e:
            raise ImportFault(f"Error in module '{file_path}': {str(e)}")
        except Exception as e:
            raise ImportFault(f"Unexpected error in module '{file_path}': {str(e)}")
            
        return None

    def visit_UnaryOpNode(self, node):
        res = self.visit(node.node)
        if node.op_token.type == TokenType.NOT:
            return not res
        return res

    def visit_VarAssignNode(self, node):
        var_name = node.var_name_token.value
        value = self.visit(node.value_node)
        self.current_env.assign(var_name, value)
        return value

    def visit_VarAccessNode(self, node):
        var_name = node.token.value
        return self.current_env.lookup(var_name)

    def visit_BinOpNode(self, node):
        left = self.visit(node.left_node)
        right = self.visit(node.right_node)

        if node.op_token.type == TokenType.PLUS:
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
            if isinstance(left, str) and isinstance(right, (int, float)):
                return left * int(right)
            try:
                return left * right
            except TypeError:
                raise IllegalOperationFault(f"Multiplication is not supported for {type(left).__name__} and {type(right).__name__}")
        elif node.op_token.type == TokenType.DIV:
            if right == 0:
                raise ZeroDivisionFault("Division by zero is not allowed")
            try:
                # In Luz, / is always float division (following Python 3)
                return float(left) / float(right)
            except TypeError:
                raise IllegalOperationFault(f"Unsupported operand types for '/': {type(left).__name__} and {type(right).__name__}")
        elif node.op_token.type == TokenType.EE:
            return left == right
        elif node.op_token.type == TokenType.NE:
            return left != right
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
        elif node.op_token.type == TokenType.AND:
            return left and right
        elif node.op_token.type == TokenType.OR:
            return left or right

    def visit_IfNode(self, node):
        for condition, block in node.cases:
            if self.visit(condition):
                return self.visit(block)
        if node.else_case:
            return self.visit(node.else_case)
        return None

    def visit_WhileNode(self, node):
        while self.visit(node.condition_node):
            self.visit(node.block)
        return None

    def visit_ForNode(self, node):
        var_name = node.var_name_token.value
        start_value = self.visit(node.start_value_node)
        end_value = self.visit(node.end_value_node)

        if not isinstance(start_value, (int, float)) or not isinstance(end_value, (int, float)):
            raise TypeViolationFault("For loop range boundaries must be numeric")

        i = start_value
        previous_env = self.current_env
        self.current_env = Environment(previous_env)
        try:
            while i <= end_value:
                self.current_env.define(var_name, i)
                self.visit(node.block)
                i += 1
        finally:
            self.current_env = previous_env
        return None

    def visit_FuncDefNode(self, node):
        func_name = node.name_token.value
        function = LuzFunction(node, self.current_env)
        self.current_env.define(func_name, function)
        return None

    def visit_ReturnNode(self, node):
        value = None
        if node.expression_node:
            value = self.visit(node.expression_node)
        raise ReturnException(value)

    def visit_CallNode(self, node):
        func_name = node.func_name_token.value
        arguments = [self.visit(arg) for arg in node.arguments]

        if func_name in self.builtins:
            return self.builtins[func_name](*arguments)
        
        try:
            function = self.current_env.lookup(func_name)
            if not isinstance(function, LuzFunction):
                raise InvalidUsageFault(f"'{func_name}' is not a callable function")
            return function(self, arguments)
        except UndefinedSymbolFault:
            raise FunctionNotFoundFault(f"Function '{func_name}' was not found")
        except LuzError as e:
            raise e
        except Exception as e:
            raise InternalFault(str(e))

    def builtin_write(self, *args):
        formatted_args = []
        for arg in args:
            if isinstance(arg, bool):
                formatted_args.append("true" if arg else "false")
            else:
                formatted_args.append(arg)
        print(*formatted_args)
        return None

    def builtin_listen(self, prompt=""):
        res = input(prompt)
        try:
            if '.' in res:
                return float(res)
            return int(res)
        except ValueError:
            return res

    def builtin_len(self, obj):
        try:
            return int(len(obj))
        except:
            raise TypeViolationFault(f"Object of type '{type(obj).__name__}' has no length")

    def builtin_append(self, list_obj, element):
        if not isinstance(list_obj, list):
            raise ArgumentFault("append() requires a list as its first argument")
        list_obj.append(element)
        return None

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
        return list(dict_obj.keys())

    def builtin_values(self, dict_obj):
        if not isinstance(dict_obj, dict):
            raise ArgumentFault("values() requires a dictionary")
        return list(dict_obj.values())

    def builtin_remove(self, dict_obj, key):
        if not isinstance(dict_obj, dict):
            raise ArgumentFault("remove() requires a dictionary")
        try:
            return dict_obj.pop(key)
        except KeyError:
            raise MemoryAccessFault(f"Key '{key}' not found in dictionary")
        except TypeError:
            raise TypeViolationFault(f"Invalid key type: '{type(key).__name__}'")

    def builtin_to_num(self, value):
        try:
            if isinstance(value, str) and '.' not in value:
                return int(value)
            return float(value)
        except (ValueError, TypeError):
            raise CastFault(f"Cannot cast value '{value}' to Number")

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

    def builtin_to_str(self, value):
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def builtin_to_bool(self, value):
        return bool(value)
