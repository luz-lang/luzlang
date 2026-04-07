/*
 * luz_rt_ops.c — Dynamic dispatch helpers for LLVM-generated Luz code.
 *
 * Each function inspects the type tags of its operands and performs the
 * appropriate numeric or collection operation, mirroring the semantics
 * of the tree-walking interpreter.
 */

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "luz_runtime.h"
#include "luz_rt_ops.h"

/* ── Internal helpers ────────────────────────────────────────────────────── */

/* Abort with a runtime type error. */
static LUZ_NORETURN void _type_err(const char *op,
                                    luz_value_t a, luz_value_t b) {
    fprintf(stderr, "TypeError: unsupported operand type(s) for %s: '%s' and '%s'\n",
            op, luz_typeof(a), luz_typeof(b));
    abort();
}

static LUZ_NORETURN void _type_err1(const char *op, luz_value_t a) {
    fprintf(stderr, "TypeError: unsupported operand type for %s: '%s'\n",
            op, luz_typeof(a));
    abort();
}

static LUZ_NORETURN void _zero_div(void) {
    fprintf(stderr, "ZeroDivisionError: division by zero\n");
    abort();
}

/* Promote int to float when mixing numeric types. */
static inline int _is_numeric(luz_value_t v) {
    return v.type == LUZ_INT || v.type == LUZ_FLOAT;
}

static inline double _to_f64(luz_value_t v) {
    return v.type == LUZ_FLOAT ? v.f : (double)v.i;
}

/* ── Arithmetic ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_add(luz_value_t a, luz_value_t b) {
    if (a.type == LUZ_INT && b.type == LUZ_INT)
        return LUZ_INT_VAL(a.i + b.i);
    if (_is_numeric(a) && _is_numeric(b))
        return LUZ_FLOAT_VAL(_to_f64(a) + _to_f64(b));
    if (a.type == LUZ_STRING && b.type == LUZ_STRING) {
        luz_string_t *s = luz_str_concat(a.str, b.str);
        return LUZ_STR_VAL(s);
    }
    if (a.type == LUZ_LIST && b.type == LUZ_LIST) {
        luz_list_t *l = luz_list_concat(a.list, b.list);
        return LUZ_LIST_VAL(l);
    }
    _type_err("+", a, b);
}

luz_value_t luz_rt_sub(luz_value_t a, luz_value_t b) {
    if (a.type == LUZ_INT && b.type == LUZ_INT)
        return LUZ_INT_VAL(a.i - b.i);
    if (_is_numeric(a) && _is_numeric(b))
        return LUZ_FLOAT_VAL(_to_f64(a) - _to_f64(b));
    _type_err("-", a, b);
}

luz_value_t luz_rt_mul(luz_value_t a, luz_value_t b) {
    if (a.type == LUZ_INT && b.type == LUZ_INT)
        return LUZ_INT_VAL(a.i * b.i);
    if (_is_numeric(a) && _is_numeric(b))
        return LUZ_FLOAT_VAL(_to_f64(a) * _to_f64(b));
    _type_err("*", a, b);
}

luz_value_t luz_rt_div(luz_value_t a, luz_value_t b) {
    if (!_is_numeric(a) || !_is_numeric(b)) _type_err("/", a, b);
    double db = _to_f64(b);
    if (db == 0.0) _zero_div();
    return LUZ_FLOAT_VAL(_to_f64(a) / db);
}

luz_value_t luz_rt_floordiv(luz_value_t a, luz_value_t b) {
    if (a.type == LUZ_INT && b.type == LUZ_INT) {
        if (b.i == 0) _zero_div();
        int64_t q = a.i / b.i;
        /* Floor towards negative infinity */
        if ((a.i ^ b.i) < 0 && q * b.i != a.i) q--;
        return LUZ_INT_VAL(q);
    }
    if (_is_numeric(a) && _is_numeric(b)) {
        double db = _to_f64(b);
        if (db == 0.0) _zero_div();
        return LUZ_FLOAT_VAL(floor(_to_f64(a) / db));
    }
    _type_err("//", a, b);
}

luz_value_t luz_rt_mod(luz_value_t a, luz_value_t b) {
    if (a.type == LUZ_INT && b.type == LUZ_INT) {
        if (b.i == 0) _zero_div();
        int64_t r = a.i % b.i;
        if (r != 0 && (r ^ b.i) < 0) r += b.i;
        return LUZ_INT_VAL(r);
    }
    if (_is_numeric(a) && _is_numeric(b)) {
        double db = _to_f64(b);
        if (db == 0.0) _zero_div();
        return LUZ_FLOAT_VAL(fmod(_to_f64(a), db));
    }
    _type_err("%", a, b);
}

luz_value_t luz_rt_pow(luz_value_t a, luz_value_t b) {
    if (!_is_numeric(a) || !_is_numeric(b)) _type_err("**", a, b);
    if (a.type == LUZ_INT && b.type == LUZ_INT && b.i >= 0) {
        int64_t base = a.i, exp = b.i, result = 1;
        while (exp > 0) {
            if (exp & 1) result *= base;
            base *= base;
            exp >>= 1;
        }
        return LUZ_INT_VAL(result);
    }
    return LUZ_FLOAT_VAL(pow(_to_f64(a), _to_f64(b)));
}

luz_value_t luz_rt_neg(luz_value_t a) {
    if (a.type == LUZ_INT)   return LUZ_INT_VAL(-a.i);
    if (a.type == LUZ_FLOAT) return LUZ_FLOAT_VAL(-a.f);
    _type_err1("-", a);
}

/* ── Comparison ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_eq(luz_value_t a, luz_value_t b) {
    return LUZ_BOOL_VAL(luz_value_eq(a, b));
}

luz_value_t luz_rt_ne(luz_value_t a, luz_value_t b) {
    return LUZ_BOOL_VAL(!luz_value_eq(a, b));
}

static int _cmp(luz_value_t a, luz_value_t b) {
    /* Returns <0, 0, >0 for numeric/string comparisons. */
    if (a.type == LUZ_INT && b.type == LUZ_INT)
        return (a.i > b.i) - (a.i < b.i);
    if (_is_numeric(a) && _is_numeric(b)) {
        double da = _to_f64(a), db = _to_f64(b);
        return (da > db) - (da < db);
    }
    if (a.type == LUZ_STRING && b.type == LUZ_STRING)
        return strcmp(luz_str_data(a.str), luz_str_data(b.str));
    _type_err("<", a, b);
}

luz_value_t luz_rt_lt(luz_value_t a, luz_value_t b) { return LUZ_BOOL_VAL(_cmp(a, b) <  0); }
luz_value_t luz_rt_le(luz_value_t a, luz_value_t b) { return LUZ_BOOL_VAL(_cmp(a, b) <= 0); }
luz_value_t luz_rt_gt(luz_value_t a, luz_value_t b) { return LUZ_BOOL_VAL(_cmp(a, b) >  0); }
luz_value_t luz_rt_ge(luz_value_t a, luz_value_t b) { return LUZ_BOOL_VAL(_cmp(a, b) >= 0); }

/* ── Logical ─────────────────────────────────────────────────────────────── */

luz_value_t luz_rt_and_(luz_value_t a, luz_value_t b) {
    return luz_value_truthy(a) ? b : a;
}

luz_value_t luz_rt_or_(luz_value_t a, luz_value_t b) {
    return luz_value_truthy(a) ? a : b;
}

luz_value_t luz_rt_not(luz_value_t a) {
    return LUZ_BOOL_VAL(!luz_value_truthy(a));
}

/* ── Membership ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_in_(luz_value_t item, luz_value_t col) {
    if (col.type == LUZ_LIST)
        return LUZ_BOOL_VAL(luz_list_contains(col.list, item));
    if (col.type == LUZ_DICT)
        return LUZ_BOOL_VAL(luz_dict_has(col.dict, item));
    if (col.type == LUZ_STRING && item.type == LUZ_STRING)
        return LUZ_BOOL_VAL(luz_str_contains(col.str, item.str));
    _type_err("in", item, col);
}

luz_value_t luz_rt_not_in(luz_value_t item, luz_value_t col) {
    luz_value_t r = luz_rt_in_(item, col);
    r.i = !r.i;
    return r;
}

/* ── Truthiness ──────────────────────────────────────────────────────────── */

_Bool luz_rt_truthy(luz_value_t v) {
    return (_Bool)luz_value_truthy(v);
}

/* ── Collection access ───────────────────────────────────────────────────── */

luz_value_t luz_rt_getindex(luz_value_t col, luz_value_t idx) {
    if (col.type == LUZ_LIST) {
        if (idx.type != LUZ_INT) {
            fprintf(stderr, "TypeError: list index must be int\n");
            abort();
        }
        return luz_list_get(col.list, idx.i);
    }
    if (col.type == LUZ_DICT)
        return luz_dict_get(col.dict, idx);
    if (col.type == LUZ_STRING) {
        if (idx.type != LUZ_INT) {
            fprintf(stderr, "TypeError: string index must be int\n");
            abort();
        }
        /* Return single-character string */
        const char *data = luz_str_data(col.str);
        int64_t     len  = (int64_t)col.str->len;
        int64_t     i    = idx.i < 0 ? idx.i + len : idx.i;
        if (i < 0 || i >= len) {
            fprintf(stderr, "IndexError: string index out of range\n");
            abort();
        }
        luz_string_t *s = luz_str_new(data + i, 1);
        return LUZ_STR_VAL(s);
    }
    fprintf(stderr, "TypeError: '%s' is not subscriptable\n", luz_typeof(col));
    abort();
}

void luz_rt_setindex(luz_value_t col, luz_value_t idx, luz_value_t value) {
    if (col.type == LUZ_LIST) {
        if (idx.type != LUZ_INT) {
            fprintf(stderr, "TypeError: list index must be int\n");
            abort();
        }
        luz_list_set(col.list, idx.i, value);
        return;
    }
    if (col.type == LUZ_DICT) {
        luz_dict_set(col.dict, idx, value);
        return;
    }
    fprintf(stderr, "TypeError: '%s' does not support item assignment\n",
            luz_typeof(col));
    abort();
}

luz_value_t luz_rt_getfield(luz_value_t obj, const char *name) {
    if (obj.type != LUZ_OBJECT) {
        fprintf(stderr, "AttributeError: '%s' has no attribute '%s'\n",
                luz_typeof(obj), name);
        abort();
    }
    return luz_obj_get_attr(obj.obj, name);
}

void luz_rt_setfield(luz_value_t obj, const char *name, luz_value_t value) {
    if (obj.type != LUZ_OBJECT) {
        fprintf(stderr, "AttributeError: '%s' has no attribute '%s'\n",
                luz_typeof(obj), name);
        abort();
    }
    luz_obj_set_attr(obj.obj, name, value);
}

/* ── Constructors ────────────────────────────────────────────────────────── */

luz_value_t luz_rt_make_list(int n) {
    luz_list_t *l = n > 0 ? luz_list_with_cap((size_t)n) : luz_list_new();
    return LUZ_LIST_VAL(l);
}

luz_value_t luz_rt_make_dict(int n) {
    (void)n;
    luz_dict_t *d = luz_dict_new();
    return LUZ_DICT_VAL(d);
}

/* ── String literal ──────────────────────────────────────────────────────── */

luz_value_t luz_rt_str_literal(const char *data, int64_t len) {
    luz_string_t *s = luz_str_new(data, (size_t)len);
    return LUZ_STR_VAL(s);
}

/* ── Slice ───────────────────────────────────────────────────────────────── */

luz_value_t luz_rt_slice(luz_value_t base, luz_value_t start,
                          luz_value_t end,  luz_value_t step) {
    int64_t s = (start.type == LUZ_INT) ? start.i : 0;
    int64_t e = (end.type   == LUZ_INT) ? end.i   : INT64_MAX;
    int64_t k = (step.type  == LUZ_INT) ? step.i  : 1;

    if (k == 0) {
        fprintf(stderr, "ZeroDivisionError: slice step cannot be zero\n");
        abort();
    }

    if (base.type == LUZ_LIST) {
        luz_list_t *l = luz_list_slice(base.list, s, e, k);
        return LUZ_LIST_VAL(l);
    }
    if (base.type == LUZ_STRING) {
        luz_string_t *sl = luz_str_slice(base.str, s, e, k);
        return LUZ_STR_VAL(sl);
    }
    fprintf(stderr, "TypeError: '%s' is not sliceable\n", luz_typeof(base));
    abort();
}
