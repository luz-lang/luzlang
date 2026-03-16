from .tokens import TokenType

class ReturnException(Exception):
    def __init__(self, value):
        self.value = value

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
        raise Exception(f"Variable '{name}' no definida")

    def assign(self, name, value):
        if name in self.records:
            self.records[name] = value
            return value
        if self.parent:
            return self.parent.assign(name, value)
        # Si no existe en ningún ámbito superior, la creamos en el actual (comportamiento por defecto)
        self.records[name] = value
        return value

class LuzFunction:
    def __init__(self, node, closure):
        self.node = node
        self.closure = closure

    def __call__(self, interpreter, arguments):
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
        self.builtins = {
            'write': self.builtin_write,
            'listen': self.builtin_listen,
            'len': self.builtin_len,
            'append': self.builtin_append,
            'pop': self.builtin_pop
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
        raise Exception(f'No visit_{type(node).__name__} method defined')

    def visit_NumberNode(self, node):
        return node.token.value

    def visit_StringNode(self, node):
        return node.token.value

    def visit_BooleanNode(self, node):
        return True if node.token.type == TokenType.TRUE else False

    def visit_ListNode(self, node):
        return [self.visit(element) for element in node.elements]

    def visit_ListAccessNode(self, node):
        list_obj = self.visit(node.list_node)
        index = self.visit(node.index_node)
        
        if not isinstance(list_obj, list):
            raise Exception("El objeto no es una lista")
        
        try:
            return list_obj[int(index)]
        except IndexError:
            raise Exception(f"Índice {index} fuera de rango")

    def visit_ListAssignNode(self, node):
        list_obj = self.visit(node.list_node)
        index = self.visit(node.index_node)
        value = self.visit(node.value_node)
        
        if not isinstance(list_obj, list):
            raise Exception("El objeto no es una lista")
        
        try:
            list_obj[int(index)] = value
            return value
        except IndexError:
            raise Exception(f"Índice {index} fuera de rango")

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
            return left + right
        elif node.op_token.type == TokenType.MINUS:
            if isinstance(left, str) or isinstance(right, str):
                raise Exception("Operación '-' no soportada para strings")
            return left - right
        elif node.op_token.type == TokenType.MUL:
            if isinstance(left, str) and isinstance(right, float):
                return left * int(right)
            if isinstance(left, float) or isinstance(right, float):
                 return left * right
            raise Exception("Operación '*' solo soportada entre números o string y número")
        elif node.op_token.type == TokenType.DIV:
            if isinstance(left, str) or isinstance(right, str):
                raise Exception("Operación '/' no soportada para strings")
            if right == 0:
                raise Exception("Error: División por cero")
            return left / right
        elif node.op_token.type == TokenType.EE:
            return left == right
        elif node.op_token.type == TokenType.NE:
            return left != right
        elif node.op_token.type == TokenType.LT:
            return left < right
        elif node.op_token.type == TokenType.GT:
            return left > right
        elif node.op_token.type == TokenType.LTE:
            return left <= right
        elif node.op_token.type == TokenType.GTE:
            return left >= right
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

        i = start_value
        # Creamos un ámbito local para el bucle for
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
                raise Exception(f"'{func_name}' no es una función")
            
            if len(arguments) != len(function.node.arg_tokens):
                raise Exception(f"Esperados {len(function.node.arg_tokens)} argumentos, recibidos {len(arguments)}")
            
            return function(self, arguments)
        except Exception as e:
            if "no definida" in str(e):
                raise Exception(f"Función '{func_name}' no definida")
            raise e

    def builtin_write(self, *args):
        print(*args)
        return None

    def builtin_listen(self, prompt=""):
        res = input(prompt)
        try:
            return float(res)
        except ValueError:
            return res

    def builtin_len(self, obj):
        try:
            return float(len(obj))
        except:
            raise Exception("El objeto no tiene longitud")

    def builtin_append(self, list_obj, element):
        if not isinstance(list_obj, list):
            raise Exception("append() requiere una lista como primer argumento")
        list_obj.append(element)
        return None

    def builtin_pop(self, list_obj, index=None):
        if not isinstance(list_obj, list):
            raise Exception("pop() requiere una lista como primer argumento")
        try:
            if index is None:
                return list_obj.pop()
            return list_obj.pop(int(index))
        except IndexError:
            raise Exception("Índice fuera de rango en pop()")
