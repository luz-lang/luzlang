from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter

def main():
    interpreter = Interpreter()
    print("Intérprete de Luz v1.0 - Escribe 'salir' para finalizar")
    
    while True:
        try:
            text = input("Luz > ")
            if text.strip().lower() == "salir":
                break
            if not text.strip():
                continue
                
            lexer = Lexer(text)
            tokens = lexer.get_tokens()
            
            parser = Parser(tokens)
            ast = parser.parse()
            
            result = interpreter.visit(ast)
            print(result)
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
