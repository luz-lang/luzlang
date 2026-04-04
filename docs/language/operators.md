# Operators

## Arithmetic

| Operator | Description | Example | Result |
|---|---|---|---|
| `+` | Addition / string concat | `3 + 2` | `5` |
| `-` | Subtraction / unary negation | `10 - 4` | `6` |
| `*` | Multiplication / string repeat | `"ab" * 3` | `"ababab"` |
| `/` | Division (always float) | `7 / 2` | `3.5` |
| `//` | Integer (floor) division | `7 // 2` | `3` |
| `%` | Modulo | `10 % 3` | `1` |
| `**` | Exponentiation (right-associative) | `2 ** 8` | `256` |

## Compound assignment

| Operator | Equivalent |
|---|---|
| `x += n` | `x = x + n` |
| `x -= n` | `x = x - n` |
| `x *= n` | `x = x * n` |
| `x /= n` | `x = x / n` |

```
total = 0
total += 10
total *= 2
write(total)   # 20
```

## Comparison

| Operator | Description |
|---|---|
| `==` | Equal |
| `!=` | Not equal |
| `<` | Less than |
| `>` | Greater than |
| `<=` | Less than or equal |
| `>=` | Greater than or equal |

## Logical

| Operator | Description |
|---|---|
| `and` | True if both operands are true |
| `or` | True if at least one operand is true |
| `not` | Negates a boolean |

## Membership

`in` tests whether a value is present in a list, string, or dictionary:

```
write(3 in [1, 2, 3])          # true
write("ell" in "hello")        # true
write("age" in {"age": 30})    # true
write(5 not in [1, 2, 3])      # true
```

In a `for` loop, `in` iterates over the collection. As an expression it is a membership test.

## Null-coalescing (??)

Returns the left operand if it is not `null`, otherwise returns the right operand:

```
name: string? = null
display = name ?? "Anonymous"   # "Anonymous"

name = "Alice"
display = name ?? "Anonymous"   # "Alice"
```

Useful for providing safe defaults when a function may return `null`.

## Ternary

```
result = "yes" if condition else "no"
```

## Operator precedence

From highest to lowest:

```
**
* / // %
+ -
== != < > <= >=
not
in  not in
and
or
??  (null-coalescing)
ternary (if … else)
```
