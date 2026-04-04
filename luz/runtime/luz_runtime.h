/*
 * luz_runtime.h — Core runtime library for compiled Luz programs.
 *
 * Provides the heap-allocated, reference-counted data structures that
 * replace Python objects in the interpreter: strings, lists, dicts,
 * and class instances. Also defines the tagged value type (luz_value_t)
 * used throughout compiled output, and the setjmp/longjmp exception frame
 * for attempt/rescue blocks.
 *
 * Memory model: ARC (Automatic Reference Counting).
 *   - Every heap object starts with refcount = 1.
 *   - luz_*_retain(p)  increments refcount.
 *   - luz_*_release(p) decrements refcount; frees when it reaches 0.
 *   - luz_value_retain / luz_value_release dispatch on the value type.
 */

#ifndef LUZ_RUNTIME_H
#define LUZ_RUNTIME_H

#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>

/* ── Forward declarations ─────────────────────────────────────────────────── */

typedef struct luz_string   luz_string_t;
typedef struct luz_list     luz_list_t;
typedef struct luz_dict     luz_dict_t;
typedef struct luz_object   luz_object_t;
typedef struct luz_value    luz_value_t;

/* ── Value type tag ───────────────────────────────────────────────────────── */

typedef enum {
    LUZ_NULL     = 0,
    LUZ_BOOL     = 1,
    LUZ_INT      = 2,
    LUZ_FLOAT    = 3,
    LUZ_STRING   = 4,
    LUZ_LIST     = 5,
    LUZ_DICT     = 6,
    LUZ_OBJECT   = 7,
    LUZ_FUNCTION = 8,
} luz_type_t;

/* ── Tagged value ─────────────────────────────────────────────────────────── */

struct luz_value {
    luz_type_t type;
    union {
        int64_t       i;    /* LUZ_INT, LUZ_BOOL (0/1) */
        double        f;    /* LUZ_FLOAT */
        luz_string_t *str;  /* LUZ_STRING */
        luz_list_t   *list; /* LUZ_LIST */
        luz_dict_t   *dict; /* LUZ_DICT */
        luz_object_t *obj;  /* LUZ_OBJECT */
        void         *fn;   /* LUZ_FUNCTION — function pointer */
    };
};

/* Convenience constructors */
#define LUZ_NULL_VAL      ((luz_value_t){ .type = LUZ_NULL })
#define LUZ_BOOL_VAL(b)   ((luz_value_t){ .type = LUZ_BOOL,  .i = (b) ? 1 : 0 })
#define LUZ_INT_VAL(n)    ((luz_value_t){ .type = LUZ_INT,   .i = (int64_t)(n) })
#define LUZ_FLOAT_VAL(x)  ((luz_value_t){ .type = LUZ_FLOAT, .f = (double)(x) })
#define LUZ_STR_VAL(s)    ((luz_value_t){ .type = LUZ_STRING, .str = (s) })
#define LUZ_LIST_VAL(l)   ((luz_value_t){ .type = LUZ_LIST,   .list = (l) })
#define LUZ_DICT_VAL(d)   ((luz_value_t){ .type = LUZ_DICT,   .dict = (d) })
#define LUZ_OBJ_VAL(o)    ((luz_value_t){ .type = LUZ_OBJECT, .obj = (o) })

/* ARC helpers for generic values */
void luz_value_retain(luz_value_t v);
void luz_value_release(luz_value_t v);

/* Equality and truthiness */
int  luz_value_eq(luz_value_t a, luz_value_t b);
int  luz_value_truthy(luz_value_t v);

/* String representation (caller must luz_str_release the result) */
luz_string_t *luz_value_to_string(luz_value_t v);

/* typeof() — returns a static C string ("int", "string", …) */
const char *luz_typeof(luz_value_t v);

/* ── String ───────────────────────────────────────────────────────────────── */

/* Small String Optimisation: strings up to LUZ_SSO_MAX bytes are stored
   inline (no heap allocation for the char data). */
#define LUZ_SSO_MAX 23

struct luz_string {
    size_t refcount;
    size_t len;
    union {
        char  *heap;               /* used when len > LUZ_SSO_MAX */
        char   sso[LUZ_SSO_MAX + 1]; /* used when len <= LUZ_SSO_MAX */
    };
    int is_sso; /* 1 if SSO is active */
};

/* Lifecycle */
luz_string_t *luz_str_new(const char *data, size_t len);
luz_string_t *luz_str_from_cstr(const char *cstr);   /* NUL-terminated */
void          luz_str_retain(luz_string_t *s);
void          luz_str_release(luz_string_t *s);

/* Operations */
luz_string_t *luz_str_concat(luz_string_t *a, luz_string_t *b);
luz_string_t *luz_str_slice(luz_string_t *s, int64_t start, int64_t end, int64_t step);
int           luz_str_eq(luz_string_t *a, luz_string_t *b);
int           luz_str_contains(luz_string_t *haystack, luz_string_t *needle);
int64_t       luz_str_find(luz_string_t *haystack, luz_string_t *needle);
luz_string_t *luz_str_upper(luz_string_t *s);
luz_string_t *luz_str_lower(luz_string_t *s);
luz_string_t *luz_str_trim(luz_string_t *s);
luz_list_t   *luz_str_split(luz_string_t *s, luz_string_t *sep);
int64_t       luz_str_len(luz_string_t *s);  /* codepoint count (== byte count for ASCII) */

/* Raw data pointer (no ownership transfer) */
static inline const char *luz_str_data(const luz_string_t *s) {
    return s->is_sso ? s->sso : s->heap;
}

/* ── List ─────────────────────────────────────────────────────────────────── */

struct luz_list {
    size_t       refcount;
    size_t       len;
    size_t       cap;
    luz_value_t *data;
};

/* Lifecycle */
luz_list_t *luz_list_new(void);
luz_list_t *luz_list_with_cap(size_t cap);
void        luz_list_retain(luz_list_t *l);
void        luz_list_release(luz_list_t *l);

/* Operations */
void        luz_list_push(luz_list_t *l, luz_value_t v);
luz_value_t luz_list_pop(luz_list_t *l);
luz_value_t luz_list_get(luz_list_t *l, int64_t idx);   /* supports negative */
void        luz_list_set(luz_list_t *l, int64_t idx, luz_value_t v);
void        luz_list_insert(luz_list_t *l, int64_t idx, luz_value_t v);
luz_list_t *luz_list_slice(luz_list_t *l, int64_t start, int64_t end, int64_t step);
luz_list_t *luz_list_concat(luz_list_t *a, luz_list_t *b);
int         luz_list_contains(luz_list_t *l, luz_value_t v);
void        luz_list_sort(luz_list_t *l);
void        luz_list_reverse(luz_list_t *l);

/* ── Dict ─────────────────────────────────────────────────────────────────── */

/* Open-addressing hash table with Robin Hood probing. */
typedef struct {
    luz_value_t key;
    luz_value_t value;
    uint32_t    hash;
    int8_t      occupied;   /* 1 = live slot */
    int8_t      tombstone;  /* 1 = deleted slot */
} luz_dict_entry_t;

struct luz_dict {
    size_t           refcount;
    size_t           len;      /* number of live entries */
    size_t           cap;      /* allocated slots (always power-of-two) */
    luz_dict_entry_t *entries;
};

/* Lifecycle */
luz_dict_t *luz_dict_new(void);
void        luz_dict_retain(luz_dict_t *d);
void        luz_dict_release(luz_dict_t *d);

/* Operations */
void        luz_dict_set(luz_dict_t *d, luz_value_t key, luz_value_t value);
luz_value_t luz_dict_get(luz_dict_t *d, luz_value_t key);  /* returns LUZ_NULL if missing */
int         luz_dict_has(luz_dict_t *d, luz_value_t key);
void        luz_dict_delete(luz_dict_t *d, luz_value_t key);
luz_list_t *luz_dict_keys(luz_dict_t *d);
luz_list_t *luz_dict_values(luz_dict_t *d);

/* ── Object / class instance ──────────────────────────────────────────────── */

typedef struct luz_vtable {
    const char *class_name;
    size_t      attr_count;
    const char **attr_names;  /* NULL-terminated array of attribute name strings */
    /* Method function pointers would be added per-class by the compiler. */
} luz_vtable_t;

struct luz_object {
    size_t            refcount;
    const luz_vtable_t *vtable;
    luz_value_t       *attrs;  /* indexed by position in vtable->attr_names */
};

/* Lifecycle */
luz_object_t *luz_obj_new(const luz_vtable_t *vtable);
void          luz_obj_retain(luz_object_t *o);
void          luz_obj_release(luz_object_t *o);

/* Attribute access (fatal error if name not found) */
luz_value_t   luz_obj_get_attr(luz_object_t *o, const char *name);
void          luz_obj_set_attr(luz_object_t *o, const char *name, luz_value_t v);

/* ── Exception handling ───────────────────────────────────────────────────── */

/* Each attempt/rescue block pushes a frame onto the exception stack.
   Compiled `attempt` blocks call setjmp; `alert` calls longjmp. */
typedef struct luz_exc_frame {
    jmp_buf              env;
    struct luz_exc_frame *prev;
    luz_value_t          exception; /* the value passed to alert() */
    int                  active;    /* 1 while in the try region */
} luz_exc_frame_t;

extern luz_exc_frame_t *luz_exc_stack;  /* thread-local in the future */

/* Push / pop exception frames */
void luz_exc_push(luz_exc_frame_t *frame);
void luz_exc_pop(void);

/* Raise an exception (calls longjmp if a frame is active, otherwise aborts) */
void luz_raise(luz_value_t exc) __attribute__((noreturn));

/* ── Builtin functions ────────────────────────────────────────────────────── */

/* I/O */
void        luz_builtin_write(luz_value_t v);
luz_value_t luz_builtin_listen(void);           /* read line from stdin */

/* Type conversion */
luz_value_t luz_builtin_to_int(luz_value_t v);
luz_value_t luz_builtin_to_float(luz_value_t v);
luz_value_t luz_builtin_to_str(luz_value_t v);
luz_value_t luz_builtin_to_bool(luz_value_t v);

/* Introspection */
luz_value_t luz_builtin_typeof(luz_value_t v);
luz_value_t luz_builtin_len(luz_value_t v);

/* Math */
luz_value_t luz_builtin_abs(luz_value_t v);
luz_value_t luz_builtin_sqrt(luz_value_t v);
luz_value_t luz_builtin_floor(luz_value_t v);
luz_value_t luz_builtin_ceil(luz_value_t v);
luz_value_t luz_builtin_round(luz_value_t v);
luz_value_t luz_builtin_exp(luz_value_t v);
luz_value_t luz_builtin_ln(luz_value_t v);
luz_value_t luz_builtin_sin(luz_value_t v);
luz_value_t luz_builtin_cos(luz_value_t v);
luz_value_t luz_builtin_tan(luz_value_t v);
luz_value_t luz_builtin_min(luz_value_t a, luz_value_t b);
luz_value_t luz_builtin_max(luz_value_t a, luz_value_t b);
luz_value_t luz_builtin_clamp(luz_value_t v, luz_value_t lo, luz_value_t hi);

/* List */
void        luz_builtin_append(luz_value_t lst, luz_value_t v);
luz_value_t luz_builtin_pop(luz_value_t lst);
void        luz_builtin_insert(luz_value_t lst, luz_value_t idx, luz_value_t v);
luz_value_t luz_builtin_range(luz_value_t start, luz_value_t end, luz_value_t step);
luz_value_t luz_builtin_sum(luz_value_t lst);
luz_value_t luz_builtin_any(luz_value_t lst);
luz_value_t luz_builtin_all(luz_value_t lst);
luz_value_t luz_builtin_reverse(luz_value_t lst);

/* String */
luz_value_t luz_builtin_split(luz_value_t s, luz_value_t sep);
luz_value_t luz_builtin_join(luz_value_t sep, luz_value_t lst);
luz_value_t luz_builtin_trim(luz_value_t s);
luz_value_t luz_builtin_upper(luz_value_t s);
luz_value_t luz_builtin_lower(luz_value_t s);
luz_value_t luz_builtin_find(luz_value_t haystack, luz_value_t needle);
luz_value_t luz_builtin_replace(luz_value_t s, luz_value_t old, luz_value_t new_);
luz_value_t luz_builtin_starts_with(luz_value_t s, luz_value_t prefix);
luz_value_t luz_builtin_ends_with(luz_value_t s, luz_value_t suffix);

/* Dict */
luz_value_t luz_builtin_keys(luz_value_t d);
luz_value_t luz_builtin_values(luz_value_t d);
void        luz_builtin_remove(luz_value_t d, luz_value_t key);

/* Alert (user-level exception) */
void        luz_builtin_alert(luz_value_t msg) __attribute__((noreturn));

#endif /* LUZ_RUNTIME_H */
