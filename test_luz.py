from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter

def test_luz():
    interpreter = Interpreter()
    
    cases = [
        ("5 + 5", 10.0),
        ("2 + 3 * 4", 14.0),
        ("(2 + 3) * 4", 20.0),
        ("x = 10", 10.0),
        ("x + 5", 15.0),
        ("y = x * 2", 20.0),
        ("y / 4", 5.0)
    ]
    
    for code, expected in cases:
        lexer = Lexer(code)
        tokens = lexer.get_tokens()
        parser = Parser(tokens)
        ast = parser.parse()
        result = interpreter.visit(ast)
        
        print(f"Código: {code:15} | Resultado: {result:5} | Esperado: {expected}")
        assert result == expected

if __name__ == "__main__":
    test_luz()
    print("\n¡Todas las pruebas pasaron con éxito!")
