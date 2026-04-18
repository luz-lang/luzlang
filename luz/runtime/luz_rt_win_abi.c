/*
 * luz_rt_win_abi.c — Pointer-based ABI wrappers for Luz runtime functions.
 *
 * Each wrapper dereferences its pointer arguments, calls the real function,
 * and writes the result through the output pointer.  All luz_value_t values
 * travel as pointers so the Windows x64 struct-return ABI is never involved.
 *
 * See luz_rt_win_abi.h for the full rationale.
 */

#include "luz_runtime.h"
#include "luz_rt_ops.h"
#include "luz_rt_win_abi.h"

/* ── I/O ─────────────────────────────────────────────────────────────────── */

void luz_builtin_write_pw(const luz_value_t *v)  { luz_builtin_write(*v); }
void luz_builtin_listen_pw(luz_value_t *out)      { *out = luz_builtin_listen(); }

/* ── Type conversion ─────────────────────────────────────────────────────── */

void luz_builtin_to_int_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_to_int(*v); }
void luz_builtin_to_float_pw(luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_to_float(*v); }
void luz_builtin_to_str_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_to_str(*v); }
void luz_builtin_to_bool_pw (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_to_bool(*v); }

/* ── Introspection ───────────────────────────────────────────────────────── */

void luz_builtin_typeof_pw(luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_typeof(*v); }
void luz_builtin_len_pw   (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_len(*v); }

/* ── Math ────────────────────────────────────────────────────────────────── */

void luz_builtin_abs_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_abs(*v); }
void luz_builtin_sqrt_pw (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_sqrt(*v); }
void luz_builtin_floor_pw(luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_floor(*v); }
void luz_builtin_ceil_pw (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_ceil(*v); }
void luz_builtin_round_pw(luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_round(*v); }
void luz_builtin_exp_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_exp(*v); }
void luz_builtin_ln_pw   (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_ln(*v); }
void luz_builtin_sin_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_sin(*v); }
void luz_builtin_cos_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_cos(*v); }
void luz_builtin_tan_pw  (luz_value_t *out, const luz_value_t *v) { *out = luz_builtin_tan(*v); }

void luz_builtin_min_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) {
    *out = luz_builtin_min(*a, *b);
}
void luz_builtin_max_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) {
    *out = luz_builtin_max(*a, *b);
}
void luz_builtin_clamp_pw(luz_value_t *out, const luz_value_t *v,
                           const luz_value_t *lo, const luz_value_t *hi) {
    *out = luz_builtin_clamp(*v, *lo, *hi);
}

/* ── List ────────────────────────────────────────────────────────────────── */

void luz_builtin_append_pw(const luz_value_t *lst, const luz_value_t *v) {
    luz_builtin_append(*lst, *v);
}
void luz_builtin_pop_pw(luz_value_t *out, const luz_value_t *lst) {
    *out = luz_builtin_pop(*lst);
}
void luz_builtin_insert_pw(const luz_value_t *lst, const luz_value_t *idx,
                            const luz_value_t *v) {
    luz_builtin_insert(*lst, *idx, *v);
}
void luz_builtin_range_pw(luz_value_t *out, const luz_value_t *start,
                           const luz_value_t *end, const luz_value_t *step) {
    *out = luz_builtin_range(*start, *end, *step);
}
void luz_builtin_sum_pw    (luz_value_t *out, const luz_value_t *lst) { *out = luz_builtin_sum(*lst); }
void luz_builtin_any_pw    (luz_value_t *out, const luz_value_t *lst) { *out = luz_builtin_any(*lst); }
void luz_builtin_all_pw    (luz_value_t *out, const luz_value_t *lst) { *out = luz_builtin_all(*lst); }
void luz_builtin_reverse_pw(luz_value_t *out, const luz_value_t *lst) { *out = luz_builtin_reverse(*lst); }

/* ── String ──────────────────────────────────────────────────────────────── */

void luz_builtin_split_pw(luz_value_t *out, const luz_value_t *s,
                           const luz_value_t *sep) {
    *out = luz_builtin_split(*s, *sep);
}
void luz_builtin_join_pw(luz_value_t *out, const luz_value_t *sep,
                          const luz_value_t *lst) {
    *out = luz_builtin_join(*sep, *lst);
}
void luz_builtin_trim_pw       (luz_value_t *out, const luz_value_t *s) { *out = luz_builtin_trim(*s); }
void luz_builtin_upper_pw      (luz_value_t *out, const luz_value_t *s) { *out = luz_builtin_upper(*s); }
void luz_builtin_lower_pw      (luz_value_t *out, const luz_value_t *s) { *out = luz_builtin_lower(*s); }

void luz_builtin_find_pw(luz_value_t *out, const luz_value_t *haystack,
                          const luz_value_t *needle) {
    *out = luz_builtin_find(*haystack, *needle);
}
void luz_builtin_replace_pw(luz_value_t *out, const luz_value_t *s,
                             const luz_value_t *old, const luz_value_t *new_) {
    *out = luz_builtin_replace(*s, *old, *new_);
}
void luz_builtin_starts_with_pw(luz_value_t *out, const luz_value_t *s,
                                 const luz_value_t *prefix) {
    *out = luz_builtin_starts_with(*s, *prefix);
}
void luz_builtin_ends_with_pw(luz_value_t *out, const luz_value_t *s,
                               const luz_value_t *suffix) {
    *out = luz_builtin_ends_with(*s, *suffix);
}

/* ── Dict ────────────────────────────────────────────────────────────────── */

void luz_builtin_keys_pw  (luz_value_t *out, const luz_value_t *d) { *out = luz_builtin_keys(*d); }
void luz_builtin_values_pw(luz_value_t *out, const luz_value_t *d) { *out = luz_builtin_values(*d); }
void luz_builtin_remove_pw(const luz_value_t *d, const luz_value_t *key) {
    luz_builtin_remove(*d, *key);
}

/* ── Alert / exceptions ──────────────────────────────────────────────────── */

LUZ_NORETURN void luz_builtin_alert_pw(const luz_value_t *msg) { luz_builtin_alert(*msg); }
LUZ_NORETURN void luz_raise_pw(const luz_value_t *exc)         { luz_raise(*exc); }

/* ── Arithmetic ops ──────────────────────────────────────────────────────── */

void luz_rt_add_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_add(*a, *b); }
void luz_rt_sub_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_sub(*a, *b); }
void luz_rt_mul_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_mul(*a, *b); }
void luz_rt_div_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_div(*a, *b); }
void luz_rt_floordiv_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_floordiv(*a, *b); }
void luz_rt_mod_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_mod(*a, *b); }
void luz_rt_pow_pw     (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_pow(*a, *b); }
void luz_rt_neg_pw     (luz_value_t *out, const luz_value_t *a)                       { *out = luz_rt_neg(*a); }

/* ── Comparison ops ──────────────────────────────────────────────────────── */

void luz_rt_eq_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_eq(*a, *b); }
void luz_rt_ne_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_ne(*a, *b); }
void luz_rt_lt_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_lt(*a, *b); }
void luz_rt_le_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_le(*a, *b); }
void luz_rt_gt_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_gt(*a, *b); }
void luz_rt_ge_pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_ge(*a, *b); }

/* ── Logical ops ─────────────────────────────────────────────────────────── */

void luz_rt_and__pw(luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_and_(*a, *b); }
void luz_rt_or__pw (luz_value_t *out, const luz_value_t *a, const luz_value_t *b) { *out = luz_rt_or_(*a, *b); }
void luz_rt_not_pw (luz_value_t *out, const luz_value_t *a)                        { *out = luz_rt_not(*a); }

/* ── Membership ──────────────────────────────────────────────────────────── */

void luz_rt_in__pw  (luz_value_t *out, const luz_value_t *item, const luz_value_t *col) { *out = luz_rt_in_(*item, *col); }
void luz_rt_not_in_pw(luz_value_t *out, const luz_value_t *item, const luz_value_t *col) { *out = luz_rt_not_in(*item, *col); }

/* ── Collection access ───────────────────────────────────────────────────── */

void luz_rt_getindex_pw(luz_value_t *out, const luz_value_t *col,
                         const luz_value_t *idx) {
    *out = luz_rt_getindex(*col, *idx);
}
void luz_rt_setindex_pw(const luz_value_t *col, const luz_value_t *idx,
                         const luz_value_t *value) {
    luz_rt_setindex(*col, *idx, *value);
}
void luz_rt_getfield_pw(luz_value_t *out, const luz_value_t *obj, const char *name) {
    *out = luz_rt_getfield(*obj, name);
}
void luz_rt_setfield_pw(const luz_value_t *obj, const char *name,
                         const luz_value_t *value) {
    luz_rt_setfield(*obj, name, *value);
}

/* ── Constructors ────────────────────────────────────────────────────────── */

void luz_rt_make_list_pw  (luz_value_t *out, int n)                    { *out = luz_rt_make_list(n); }
void luz_rt_make_dict_pw  (luz_value_t *out, int n)                    { *out = luz_rt_make_dict(n); }
void luz_rt_str_literal_pw(luz_value_t *out, const char *data, int64_t len) {
    *out = luz_rt_str_literal(data, len);
}

/* ── Truthiness ──────────────────────────────────────────────────────────── */

_Bool luz_rt_truthy_pw(const luz_value_t *v) { return luz_rt_truthy(*v); }

/* ── Class registry / dispatch ───────────────────────────────────────────── */

#include "luz_rt_class.h"

void luz_rt_new_obj_pw(luz_value_t *out, uint32_t class_id) {
    *out = luz_rt_new_obj(class_id);
}

void luz_rt_obj_call_pw(luz_value_t *out, const luz_value_t *obj,
                         const char *name, const luz_value_t *args,
                         int32_t nargs) {
    *out = luz_rt_obj_call(*obj, name, (luz_value_t *)args, nargs);
}

void luz_rt_isinstance_pw(luz_value_t *out, const luz_value_t *obj,
                           uint32_t class_id) {
    *out = luz_rt_isinstance(*obj, class_id);
}
