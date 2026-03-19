import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luz.lexer import Lexer
from luz.parser import Parser
from luz.interpreter import Interpreter

def test_arithmetic():
    print("Testing arithmetic (Int and Float)...")
    interpreter = Interpreter()
    # Int result
    tokens = Lexer("5 + 5").get_tokens()
    ast = Parser(tokens).parse()
    res = interpreter.visit(ast)
    assert res == 10
    assert isinstance(res, int)
    
    # Float result
    tokens = Lexer("5 + 5.0").get_tokens()
    ast = Parser(tokens).parse()
    res = interpreter.visit(ast)
    assert res == 10.0
    assert isinstance(res, float)
    
    # Division always float
    tokens = Lexer("10 / 2").get_tokens()
    ast = Parser(tokens).parse()
    res = interpreter.visit(ast)
    assert res == 5.0
    print("Arithmetic: OK")

def test_variables_and_strings():
    print("Testing variables and strings...")
    interpreter = Interpreter()
    code = 'a = "hello" b = " world" res = a + b'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == "hello world"
    print("Variables and strings: OK")

def test_control_flow():
    print("Testing control flow...")
    interpreter = Interpreter()
    code = 'i = 0 while i < 5 { i = i + 1 }'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('i') == 5
    print("Control flow: OK")

def test_functions():
    print("Testing functions and arity...")
    interpreter = Interpreter()
    code = 'function add(a, b) { return a + b } res = add(10, 20)'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('res') == 30
    
    # Arity check
    try:
        interpreter.visit(Parser(Lexer('add(1)').get_tokens()).parse())
        assert False, "Should have raised ArityFault"
    except Exception as e:
        assert type(e).__name__ == "ArityFault"
    print("Functions: OK")

def test_lists_and_indexing():
    print("Testing list indexing constraints...")
    interpreter = Interpreter()
    code = 'l = [10, 20, 30] val = l[1]'
    interpreter.visit(Parser(Lexer(code).get_tokens()).parse())
    assert interpreter.global_env.lookup('val') == 20
    
    # Float index check
    try:
        interpreter.visit(Parser(Lexer('l[1.5]').get_tokens()).parse())
        assert False, "Should have raised TypeViolationFault"
    except Exception as e:
        assert type(e).__name__ == "TypeViolationFault"
    print("Lists and indexing: OK")

def test_casting():
    print("Testing casting functions...")
    interpreter = Interpreter()
    assert interpreter.visit(Parser(Lexer('to_int("10")').get_tokens()).parse()) == 10
    assert interpreter.visit(Parser(Lexer('to_float("10")').get_tokens()).parse()) == 10.0
    assert interpreter.visit(Parser(Lexer('to_str(true)').get_tokens()).parse()) == "true"
    print("Casting: OK")

def run_all():
    print("=== STARTING LUZ TEST SUITE (Int/Float Edition) ===\n")
    try:
        test_arithmetic()
        test_variables_and_strings()
        test_control_flow()
        test_functions()
        test_lists_and_indexing()
        test_casting()
        print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_all()
