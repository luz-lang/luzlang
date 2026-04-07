/*
 * luz_rt_ops.h — Dynamic dispatch helpers for LLVM-generated Luz code.
 *
 * These functions implement type-polymorphic arithmetic, comparison,
 * logical, and collection operations that the codegen emits as plain
 * `call` instructions.  All arguments and return values use the
 * luz_value_t tagged-union type from luz_runtime.h.
 *
 * They are separate from luz_runtime.h so that the core runtime can be
 * built independently of the compiler backend.
 */

#ifndef LUZ_RT_OPS_H
#define LUZ_RT_OPS_H

#include "luz_runtime.h"

/* ── Arithmetic ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_add(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_sub(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_mul(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_div(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_floordiv(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_mod(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_pow(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_neg(luz_value_t a);

/* ── Comparison ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_eq(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_ne(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_lt(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_le(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_gt(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_ge(luz_value_t a, luz_value_t b);

/* ── Logical ─────────────────────────────────────────────────────────────── */

luz_value_t luz_rt_and_(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_or_(luz_value_t a, luz_value_t b);
luz_value_t luz_rt_not(luz_value_t a);

/* ── Membership ──────────────────────────────────────────────────────────── */

luz_value_t luz_rt_in_(luz_value_t item, luz_value_t collection);
luz_value_t luz_rt_not_in(luz_value_t item, luz_value_t collection);

/* ── Collection access ───────────────────────────────────────────────────── */

luz_value_t luz_rt_getindex(luz_value_t collection, luz_value_t index);
void        luz_rt_setindex(luz_value_t collection, luz_value_t index,
                             luz_value_t value);
luz_value_t luz_rt_getfield(luz_value_t obj, const char *name);
void        luz_rt_setfield(luz_value_t obj, const char *name,
                             luz_value_t value);

/* ── Constructors ────────────────────────────────────────────────────────── */

luz_value_t luz_rt_make_list(int n);   /* empty list (n is a capacity hint) */
luz_value_t luz_rt_make_dict(int n);   /* empty dict (n is a capacity hint) */

/* ── String literal ──────────────────────────────────────────────────────── */

luz_value_t luz_rt_str_literal(const char *data, int64_t len);

/* ── Slice ───────────────────────────────────────────────────────────────── */

luz_value_t luz_rt_slice(luz_value_t base, luz_value_t start,
                          luz_value_t end,  luz_value_t step);

/* ── Truthiness (returns _Bool / i1) ─────────────────────────────────────── */

_Bool luz_rt_truthy(luz_value_t v);

#endif /* LUZ_RT_OPS_H */
