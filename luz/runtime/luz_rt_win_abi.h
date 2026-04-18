/*
 * luz_rt_win_abi.h — Pointer-based ABI wrappers for Luz runtime functions.
 *
 * On Windows x64, structs larger than 8 bytes (like luz_value_t at 16 bytes)
 * are returned via a hidden first pointer parameter.  When LLVM-generated code
 * and MinGW/GCC-compiled code disagree on this convention the result is
 * misaligned arguments and crashes ("out of memory" from a garbage malloc size).
 *
 * These wrapper functions pass every luz_value_t by pointer, eliminating all
 * struct-by-value ABI ambiguity.  The Luz codegen calls them instead of the
 * original functions when targeting Windows.
 *
 * Naming convention: original name + "_pw" (pointer-wrapped).
 *   Value-returning: void func_pw(luz_value_t *out, const luz_value_t *a, ...)
 *   Void-returning:  void func_pw(const luz_value_t *a, ...)
 *   _Bool-returning: _Bool func_pw(const luz_value_t *a)
 *
 * Non-luz_value_t parameters (int, int64_t, char*) are kept as-is.
 */

#ifndef LUZ_RT_WIN_ABI_H
#define LUZ_RT_WIN_ABI_H

#include "luz_runtime.h"
#include "luz_rt_ops.h"
#include <stdint.h>

/* ── I/O ─────────────────────────────────────────────────────────────────── */

void luz_builtin_write_pw(const luz_value_t *v);
void luz_builtin_listen_pw(luz_value_t *out);

/* ── Type conversion ─────────────────────────────────────────────────────── */

void luz_builtin_to_int_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_to_float_pw(luz_value_t *out, const luz_value_t *v);
void luz_builtin_to_str_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_to_bool_pw (luz_value_t *out, const luz_value_t *v);

/* ── Introspection ───────────────────────────────────────────────────────── */

void luz_builtin_typeof_pw(luz_value_t *out, const luz_value_t *v);
void luz_builtin_len_pw   (luz_value_t *out, const luz_value_t *v);

/* ── Math ────────────────────────────────────────────────────────────────── */

void luz_builtin_abs_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_sqrt_pw (luz_value_t *out, const luz_value_t *v);
void luz_builtin_floor_pw(luz_value_t *out, const luz_value_t *v);
void luz_builtin_ceil_pw (luz_value_t *out, const luz_value_t *v);
void luz_builtin_round_pw(luz_value_t *out, const luz_value_t *v);
void luz_builtin_exp_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_ln_pw   (luz_value_t *out, const luz_value_t *v);
void luz_builtin_sin_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_cos_pw  (luz_value_t *out, const luz_value_t *v);
void luz_builtin_tan_pw  (luz_value_t *out, const luz_value_t *v);

void luz_builtin_min_pw  (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_builtin_max_pw  (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_builtin_clamp_pw(luz_value_t *out, const luz_value_t *v,
                           const luz_value_t *lo, const luz_value_t *hi);

/* ── List ────────────────────────────────────────────────────────────────── */

void luz_builtin_append_pw (const luz_value_t *lst, const luz_value_t *v);
void luz_builtin_pop_pw    (luz_value_t *out, const luz_value_t *lst);
void luz_builtin_insert_pw (const luz_value_t *lst, const luz_value_t *idx,
                             const luz_value_t *v);
void luz_builtin_range_pw  (luz_value_t *out, const luz_value_t *start,
                             const luz_value_t *end, const luz_value_t *step);
void luz_builtin_sum_pw    (luz_value_t *out, const luz_value_t *lst);
void luz_builtin_any_pw    (luz_value_t *out, const luz_value_t *lst);
void luz_builtin_all_pw    (luz_value_t *out, const luz_value_t *lst);
void luz_builtin_reverse_pw(luz_value_t *out, const luz_value_t *lst);

/* ── String ──────────────────────────────────────────────────────────────── */

void luz_builtin_split_pw      (luz_value_t *out, const luz_value_t *s,
                                 const luz_value_t *sep);
void luz_builtin_join_pw       (luz_value_t *out, const luz_value_t *sep,
                                 const luz_value_t *lst);
void luz_builtin_trim_pw       (luz_value_t *out, const luz_value_t *s);
void luz_builtin_upper_pw      (luz_value_t *out, const luz_value_t *s);
void luz_builtin_lower_pw      (luz_value_t *out, const luz_value_t *s);
void luz_builtin_find_pw       (luz_value_t *out, const luz_value_t *haystack,
                                 const luz_value_t *needle);
void luz_builtin_replace_pw    (luz_value_t *out, const luz_value_t *s,
                                 const luz_value_t *old, const luz_value_t *new_);
void luz_builtin_starts_with_pw(luz_value_t *out, const luz_value_t *s,
                                 const luz_value_t *prefix);
void luz_builtin_ends_with_pw  (luz_value_t *out, const luz_value_t *s,
                                 const luz_value_t *suffix);

/* ── Dict ────────────────────────────────────────────────────────────────── */

void luz_builtin_keys_pw  (luz_value_t *out, const luz_value_t *d);
void luz_builtin_values_pw(luz_value_t *out, const luz_value_t *d);
void luz_builtin_remove_pw(const luz_value_t *d, const luz_value_t *key);

/* ── Alert / exceptions ──────────────────────────────────────────────────── */

LUZ_NORETURN void luz_builtin_alert_pw(const luz_value_t *msg);
LUZ_NORETURN void luz_raise_pw(const luz_value_t *exc);

/* ── Arithmetic ops ──────────────────────────────────────────────────────── */

void luz_rt_add_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_sub_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_mul_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_div_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_floordiv_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_mod_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_pow_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_neg_pw     (luz_value_t *out, const luz_value_t *a);

/* ── Comparison ops ──────────────────────────────────────────────────────── */

void luz_rt_eq_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_ne_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_lt_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_le_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_gt_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_ge_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);

/* ── Logical ops ─────────────────────────────────────────────────────────── */

void luz_rt_and__pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_or__pw (luz_value_t *out, const luz_value_t *a, const luz_value_t *b);
void luz_rt_not_pw (luz_value_t *out, const luz_value_t *a);

/* ── Membership ──────────────────────────────────────────────────────────── */

void luz_rt_in__pw  (luz_value_t *out, const luz_value_t *item, const luz_value_t *col);
void luz_rt_not_in_pw(luz_value_t *out, const luz_value_t *item, const luz_value_t *col);

/* ── Collection access ───────────────────────────────────────────────────── */

void luz_rt_getindex_pw(luz_value_t *out, const luz_value_t *col,
                         const luz_value_t *idx);
void luz_rt_setindex_pw(const luz_value_t *col, const luz_value_t *idx,
                         const luz_value_t *value);
void luz_rt_getfield_pw(luz_value_t *out, const luz_value_t *obj, const char *name);
void luz_rt_setfield_pw(const luz_value_t *obj, const char *name,
                         const luz_value_t *value);

/* ── Constructors ────────────────────────────────────────────────────────── */

void luz_rt_make_list_pw   (luz_value_t *out, int n);
void luz_rt_make_dict_pw   (luz_value_t *out, int n);
void luz_rt_str_literal_pw (luz_value_t *out, const char *data, int64_t len);

/* ── Truthiness (returns _Bool, not luz_value_t) ─────────────────────────── */

_Bool luz_rt_truthy_pw(const luz_value_t *v);

/* ── Class registry / dispatch (luz_rt_class) ────────────────────────────── */

/* luz_rt_new_obj: returns luz_value_t; class_id is i32 (no struct arg). */
void luz_rt_new_obj_pw(luz_value_t *out, uint32_t class_id);

/* luz_rt_obj_call: obj is luz_value_t (by ptr); args is already a ptr. */
void luz_rt_obj_call_pw(luz_value_t *out, const luz_value_t *obj,
                         const char *name, const luz_value_t *args,
                         int32_t nargs);

/* luz_rt_isinstance: obj is luz_value_t (by ptr); class_id is i32. */
void luz_rt_isinstance_pw(luz_value_t *out, const luz_value_t *obj,
                           uint32_t class_id);

#endif /* LUZ_RT_WIN_ABI_H */
