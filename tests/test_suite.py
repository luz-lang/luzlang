import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter

def test_arithmetic():
    print("Probando aritmética...")
    interpreter = Interpreter()
    cases = [("1 + 2 * 3", 7.0), ("(1 + 2) * 3", 9.0), ("10 / 2 - 1", 4.0)]
    for code, expected in cases:
        tokens = Lexer(code).get_tokens()
        ast = Parser(tokens).parse()
        assert interpreter.visit(ast) == expected
    print("Aritmética: OK")

def test_variables_and_strings():
    print("Probando variables y strings...")
    interpreter = Interpreter()
    # Variables y concatenación
    code = 'a = "hola" b = " mundo" res = a + b'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == "hola mundo"
    
    # Multiplicación de strings
    code = 'risa = "ja" * 3'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('risa') == "jajaja"
    print("Variables y strings: OK")

def test_control_flow():
    print("Probando flujo de control (if, while, for)...")
    interpreter = Interpreter()
    
    # If/Else
    code = 'x = 10 if x > 5 { res = "si" } else { res = "no" }'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == "si"
    
    # While
    code = 'i = 0 while i < 5 { i = i + 1 }'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('i') == 5.0
    
    # For
    code = 'total = 0 for k = 1 to 5 { total = total + k }'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('total') == 15.0
    print("Flujo de control: OK")

def test_logical_and_booleans():
    print("Probando booleanos y lógica...")
    interpreter = Interpreter()
    cases = [
        ("true and false", False),
        ("true or false", True),
        ("not false", True),
        ("10 > 5 and not (2 == 3)", True)
    ]
    for code, expected in cases:
        tokens = Lexer(code).get_tokens()
        ast = Parser(tokens).parse()
        assert interpreter.visit(ast) == expected
    print("Booleanos y lógica: OK")

def test_functions():
    print("Probando funciones...")
    interpreter = Interpreter()
    code = '''
    function factorial(n) {
        if n <= 1 { return 1 }
        return n * factorial(n - 1)
    }
    res = factorial(5)
    '''
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == 120.0
    print("Funciones y recursividad: OK")

def test_lists():
    print("Probando listas...")
    interpreter = Interpreter()
    
    # Literales y acceso
    code = 'l = [10, "hola", true] res = l[0] + 5'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == 15.0
    
    # Modificación
    code = 'l[1] = "mundo" val = l[1]'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('val') == "mundo"
    
    # Built-ins
    code = 'append(l, 40) tam = len(l) ultimo = pop(l)'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('tam') == 4.0
    assert interpreter.global_env.lookup('ultimo') == 40.0
    print("Listas: OK")

def test_dicts():
    print("Probando diccionarios...")
    interpreter = Interpreter()
    
    # Literales y acceso
    code = 'd = {"nombre": "Eloi", "edad": 25} res = d["nombre"]'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == "Eloi"
    
    # Modificación e inserción
    code = 'd["edad"] = 26 d["ciudad"] = "BCN"'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    d = interpreter.global_env.lookup('d')
    assert d["edad"] == 26.0
    assert d["ciudad"] == "BCN"
    
    # Built-ins
    code = 'ks = keys(d) tam = len(d)'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('tam') == 3.0
    # keys() devuelve una lista, el orden puede variar pero el contenido no
    ks = interpreter.global_env.lookup('ks')
    assert "nombre" in ks and "edad" in ks and "ciudad" in ks
    print("Diccionarios: OK")

def run_all():
    print("=== INICIANDO SUITE DE PRUEBAS DE LUZ ===\n")
    try:
        test_arithmetic()
        test_variables_and_strings()
        test_control_flow()
        test_logical_and_booleans()
        test_functions()
        test_lists()
        test_dicts()
        print("\n=== ¡TODAS LAS PRUEBAS PASARON CON ÉXITO! ===")
    except Exception as e:
        print(f"\nERROR EN LAS PRUEBAS: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_all()
