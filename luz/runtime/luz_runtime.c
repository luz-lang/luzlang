/*
 * luz_runtime.c — Implementation of the Luz runtime library.
 *
 * Compile with:
 *   gcc -O2 -std=c11 -Wall -Wextra -c luz_runtime.c -o luz_runtime.o
 *   ar rcs libluz_runtime.a luz_runtime.o
 */

#include "luz_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <assert.h>
#include <inttypes.h>

/* ── Internal helpers ────────────────────────────────────────────────────── */

/* int64 → NUL-terminated string, returns pointer to static buffer (not thread-safe) */
static const char *_i64str(int64_t v) {
    static char buf[24];
    int neg = v < 0;
    uint64_t u = neg ? (uint64_t)(-(v + 1)) + 1 : (uint64_t)v;
    char *p = buf + sizeof(buf) - 1;
    *p = '\0';
    if (u == 0) { *--p = '0'; } else {
        while (u > 0) { *--p = (char)('0' + (u % 10)); u /= 10; }
    }
    if (neg) *--p = '-';
    return p;
}

static void _oom(void) {
    fprintf(stderr, "luz runtime: out of memory\n");
    abort();
}

static void *_xmalloc(size_t n) {
    void *p = malloc(n);
    if (!p) _oom();
    return p;
}

static void *_xrealloc(void *p, size_t n) {
    void *q = realloc(p, n);
    if (!q) _oom();
    return q;
}

static void *_xcalloc(size_t n, size_t sz) {
    void *p = calloc(n, sz);
    if (!p) _oom();
    return p;
}

/* Normalize a Python-style index into [0, len). Returns -1 if out of range. */
static int64_t _norm_idx(int64_t idx, int64_t len) {
    if (idx < 0) idx += len;
    if (idx < 0 || idx >= len) return -1;
    return idx;
}

/* ── ARC: generic value retain / release ─────────────────────────────────── */

void luz_value_retain(luz_value_t v) {
    switch (v.type) {
        case LUZ_STRING: luz_str_retain(v.str);   break;
        case LUZ_LIST:   luz_list_retain(v.list); break;
        case LUZ_DICT:   luz_dict_retain(v.dict); break;
        case LUZ_OBJECT: luz_obj_retain(v.obj);   break;
        default: break;
    }
}

void luz_value_release(luz_value_t v) {
    switch (v.type) {
        case LUZ_STRING: luz_str_release(v.str);   break;
        case LUZ_LIST:   luz_list_release(v.list); break;
        case LUZ_DICT:   luz_dict_release(v.dict); break;
        case LUZ_OBJECT: luz_obj_release(v.obj);   break;
        default: break;
    }
}

/* ── Value utilities ─────────────────────────────────────────────────────── */

int luz_value_truthy(luz_value_t v) {
    switch (v.type) {
        case LUZ_NULL:   return 0;
        case LUZ_BOOL:   return v.i != 0;
        case LUZ_INT:    return v.i != 0;
        case LUZ_FLOAT:  return v.f != 0.0;
        case LUZ_STRING: return v.str->len > 0;
        case LUZ_LIST:   return v.list->len > 0;
        case LUZ_DICT:   return v.dict->len > 0;
        default:         return 1;
    }
}

int luz_value_eq(luz_value_t a, luz_value_t b) {
    if (a.type != b.type) {
        /* int and float cross-comparison */
        if (a.type == LUZ_INT   && b.type == LUZ_FLOAT) return (double)a.i == b.f;
        if (a.type == LUZ_FLOAT && b.type == LUZ_INT)   return a.f == (double)b.i;
        return 0;
    }
    switch (a.type) {
        case LUZ_NULL:   return 1;
        case LUZ_BOOL:   /* fall-through */
        case LUZ_INT:    return a.i == b.i;
        case LUZ_FLOAT:  return a.f == b.f;
        case LUZ_STRING: return luz_str_eq(a.str, b.str);
        case LUZ_LIST:
            if (a.list->len != b.list->len) return 0;
            for (size_t i = 0; i < a.list->len; i++)
                if (!luz_value_eq(a.list->data[i], b.list->data[i])) return 0;
            return 1;
        case LUZ_OBJECT: return a.obj == b.obj;  /* identity for objects */
        default:         return 0;
    }
}

const char *luz_typeof(luz_value_t v) {
    switch (v.type) {
        case LUZ_NULL:     return "null";
        case LUZ_BOOL:     return "bool";
        case LUZ_INT:      return "int";
        case LUZ_FLOAT:    return "float";
        case LUZ_STRING:   return "string";
        case LUZ_LIST:     return "list";
        case LUZ_DICT:     return "dict";
        case LUZ_OBJECT:   return v.obj->vtable ? v.obj->vtable->class_name : "object";
        case LUZ_FUNCTION: return "function";
        default:           return "unknown";
    }
}

luz_string_t *luz_value_to_string(luz_value_t v) {
    char buf[64];
    switch (v.type) {
        case LUZ_NULL:
            return luz_str_from_cstr("null");
        case LUZ_BOOL:
            return luz_str_from_cstr(v.i ? "true" : "false");
        case LUZ_INT:
            strncpy(buf, _i64str(v.i), sizeof(buf) - 1);
            return luz_str_from_cstr(buf);
        case LUZ_FLOAT: {
            snprintf(buf, sizeof(buf), "%g", v.f);
            /* Ensure at least one decimal digit so it reads as float */
            if (!strchr(buf, '.') && !strchr(buf, 'e'))
                strncat(buf, ".0", sizeof(buf) - strlen(buf) - 1);
            return luz_str_from_cstr(buf);
        }
        case LUZ_STRING:
            luz_str_retain(v.str);
            return v.str;
        case LUZ_LIST: {
            /* "[elem, elem, …]" */
            luz_string_t *acc = luz_str_from_cstr("[");
            for (size_t i = 0; i < v.list->len; i++) {
                luz_string_t *elem = luz_value_to_string(v.list->data[i]);
                luz_string_t *tmp  = luz_str_concat(acc, elem);
                luz_str_release(acc);
                luz_str_release(elem);
                acc = tmp;
                if (i + 1 < v.list->len) {
                    luz_string_t *sep = luz_str_from_cstr(", ");
                    tmp = luz_str_concat(acc, sep);
                    luz_str_release(acc);
                    luz_str_release(sep);
                    acc = tmp;
                }
            }
            luz_string_t *close = luz_str_from_cstr("]");
            luz_string_t *result = luz_str_concat(acc, close);
            luz_str_release(acc);
            luz_str_release(close);
            return result;
        }
        default:
            snprintf(buf, sizeof(buf), "<%s>", luz_typeof(v));
            return luz_str_from_cstr(buf);
    }
}

/* ── String ──────────────────────────────────────────────────────────────── */

luz_string_t *luz_str_new(const char *data, size_t len) {
    luz_string_t *s = _xmalloc(sizeof(luz_string_t));
    s->refcount = 1;
    s->len      = len;
    if (len <= LUZ_SSO_MAX) {
        memcpy(s->sso, data, len);
        s->sso[len] = '\0';
        s->is_sso   = 1;
    } else {
        s->heap = _xmalloc(len + 1);
        memcpy(s->heap, data, len);
        s->heap[len] = '\0';
        s->is_sso    = 0;
    }
    return s;
}

luz_string_t *luz_str_from_cstr(const char *cstr) {
    return luz_str_new(cstr, strlen(cstr));
}

void luz_str_retain(luz_string_t *s) {
    if (s) s->refcount++;
}

void luz_str_release(luz_string_t *s) {
    if (!s) return;
    if (--s->refcount == 0) {
        if (!s->is_sso) free(s->heap);
        free(s);
    }
}

luz_string_t *luz_str_concat(luz_string_t *a, luz_string_t *b) {
    size_t      len   = a->len + b->len;
    const char *adata = luz_str_data(a);
    const char *bdata = luz_str_data(b);
    luz_string_t *s = _xmalloc(sizeof(luz_string_t));
    s->refcount = 1;
    s->len      = len;
    if (len <= LUZ_SSO_MAX) {
        memcpy(s->sso, adata, a->len);
        memcpy(s->sso + a->len, bdata, b->len);
        s->sso[len] = '\0';
        s->is_sso   = 1;
    } else {
        s->heap = _xmalloc(len + 1);
        memcpy(s->heap, adata, a->len);
        memcpy(s->heap + a->len, bdata, b->len);
        s->heap[len] = '\0';
        s->is_sso    = 0;
    }
    return s;
}

luz_string_t *luz_str_slice(luz_string_t *s, int64_t start, int64_t end, int64_t step) {
    int64_t len = (int64_t)s->len;
    if (step == 0) {
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("Slice step cannot be zero")));
    }
    /* Normalize bounds */
    if (start < 0) start = start + len < 0 ? 0 : start + len;
    if (end   < 0) end   = end   + len < 0 ? 0 : end   + len;
    if (start > len) start = len;
    if (end   > len) end   = len;

    const char *data = luz_str_data(s);
    /* Count output chars */
    size_t out_len = 0;
    if (step > 0) {
        for (int64_t i = start; i < end; i += step) out_len++;
    } else {
        for (int64_t i = start; i > end; i += step) out_len++;
    }
    char *buf = _xmalloc(out_len + 1);
    size_t bi = 0;
    if (step > 0)
        for (int64_t i = start; i < end; i += step) buf[bi++] = data[i];
    else
        for (int64_t i = start; i > end; i += step) buf[bi++] = data[i];
    buf[bi] = '\0';
    luz_string_t *result = luz_str_new(buf, out_len);
    free(buf);
    return result;
}

int luz_str_eq(luz_string_t *a, luz_string_t *b) {
    if (a->len != b->len) return 0;
    return memcmp(luz_str_data(a), luz_str_data(b), a->len) == 0;
}

int64_t luz_str_len(luz_string_t *s) { return (int64_t)s->len; }

int luz_str_contains(luz_string_t *haystack, luz_string_t *needle) {
    return luz_str_find(haystack, needle) >= 0;
}

int64_t luz_str_find(luz_string_t *haystack, luz_string_t *needle) {
    if (needle->len == 0) return 0;
    if (needle->len > haystack->len) return -1;
    const char *h = luz_str_data(haystack);
    const char *n = luz_str_data(needle);
    for (size_t i = 0; i <= haystack->len - needle->len; i++) {
        if (memcmp(h + i, n, needle->len) == 0) return (int64_t)i;
    }
    return -1;
}

luz_string_t *luz_str_upper(luz_string_t *s) {
    size_t len = s->len;
    char *buf  = _xmalloc(len + 1);
    const char *d = luz_str_data(s);
    for (size_t i = 0; i < len; i++) buf[i] = (char)toupper((unsigned char)d[i]);
    buf[len] = '\0';
    luz_string_t *result = luz_str_new(buf, len);
    free(buf);
    return result;
}

luz_string_t *luz_str_lower(luz_string_t *s) {
    size_t len = s->len;
    char *buf  = _xmalloc(len + 1);
    const char *d = luz_str_data(s);
    for (size_t i = 0; i < len; i++) buf[i] = (char)tolower((unsigned char)d[i]);
    buf[len] = '\0';
    luz_string_t *result = luz_str_new(buf, len);
    free(buf);
    return result;
}

luz_string_t *luz_str_trim(luz_string_t *s) {
    const char *d     = luz_str_data(s);
    const char *start = d;
    const char *end   = d + s->len;
    while (start < end && isspace((unsigned char)*start)) start++;
    while (end   > start && isspace((unsigned char)*(end - 1))) end--;
    return luz_str_new(start, (size_t)(end - start));
}

luz_list_t *luz_str_split(luz_string_t *s, luz_string_t *sep) {
    luz_list_t *result = luz_list_new();
    const char *data   = luz_str_data(s);
    size_t      len    = s->len;

    if (sep->len == 0) {
        /* Split on whitespace */
        size_t i = 0;
        while (i < len) {
            while (i < len && isspace((unsigned char)data[i])) i++;
            size_t j = i;
            while (j < len && !isspace((unsigned char)data[j])) j++;
            if (j > i)
                luz_list_push(result, LUZ_STR_VAL(luz_str_new(data + i, j - i)));
            i = j;
        }
    } else {
        const char *sep_data = luz_str_data(sep);
        size_t sep_len       = sep->len;
        size_t start         = 0;
        for (size_t i = 0; i + sep_len <= len; i++) {
            if (memcmp(data + i, sep_data, sep_len) == 0) {
                luz_list_push(result, LUZ_STR_VAL(luz_str_new(data + start, i - start)));
                start = i + sep_len;
                i    += sep_len - 1;
            }
        }
        luz_list_push(result, LUZ_STR_VAL(luz_str_new(data + start, len - start)));
    }
    return result;
}

/* ── List ────────────────────────────────────────────────────────────────── */

#define LUZ_LIST_INIT_CAP 8

luz_list_t *luz_list_new(void) {
    return luz_list_with_cap(LUZ_LIST_INIT_CAP);
}

luz_list_t *luz_list_with_cap(size_t cap) {
    if (cap == 0) cap = 1;
    luz_list_t *l = _xmalloc(sizeof(luz_list_t));
    l->refcount = 1;
    l->len      = 0;
    l->cap      = cap;
    l->data     = _xmalloc(cap * sizeof(luz_value_t));
    return l;
}

void luz_list_retain(luz_list_t *l) {
    if (l) l->refcount++;
}

void luz_list_release(luz_list_t *l) {
    if (!l) return;
    if (--l->refcount == 0) {
        for (size_t i = 0; i < l->len; i++) luz_value_release(l->data[i]);
        free(l->data);
        free(l);
    }
}

static void _list_grow(luz_list_t *l) {
    l->cap  = l->cap * 2;
    l->data = _xrealloc(l->data, l->cap * sizeof(luz_value_t));
}

void luz_list_push(luz_list_t *l, luz_value_t v) {
    if (l->len == l->cap) _list_grow(l);
    luz_value_retain(v);
    l->data[l->len++] = v;
}

luz_value_t luz_list_pop(luz_list_t *l) {
    if (l->len == 0) {
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr(
            "IndexError: pop from empty list")));
    }
    luz_value_t v = l->data[--l->len];
    /* Caller owns the value; refcount is already +1 from when it was pushed */
    return v;
}

luz_value_t luz_list_get(luz_list_t *l, int64_t idx) {
    int64_t i = _norm_idx(idx, (int64_t)l->len);
    if (i < 0) {
        char msg[64];
        snprintf(msg, sizeof(msg), "IndexError: list index %s out of range", _i64str(idx));
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr(msg)));
    }
    return l->data[i];
}

void luz_list_set(luz_list_t *l, int64_t idx, luz_value_t v) {
    int64_t i = _norm_idx(idx, (int64_t)l->len);
    if (i < 0) {
        char msg[64];
        snprintf(msg, sizeof(msg), "IndexError: list index %s out of range", _i64str(idx));
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr(msg)));
    }
    luz_value_release(l->data[i]);
    luz_value_retain(v);
    l->data[i] = v;
}

void luz_list_insert(luz_list_t *l, int64_t idx, luz_value_t v) {
    /* Clamp index */
    if (idx < 0) idx = idx + (int64_t)l->len;
    if (idx < 0) idx = 0;
    if (idx > (int64_t)l->len) idx = (int64_t)l->len;
    if (l->len == l->cap) _list_grow(l);
    memmove(l->data + idx + 1, l->data + idx,
            (l->len - (size_t)idx) * sizeof(luz_value_t));
    luz_value_retain(v);
    l->data[idx] = v;
    l->len++;
}

luz_list_t *luz_list_slice(luz_list_t *l, int64_t start, int64_t end, int64_t step) {
    int64_t len = (int64_t)l->len;
    if (step == 0)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("Slice step cannot be zero")));
    if (start < 0) start = start + len < 0 ? 0 : start + len;
    if (end   < 0) end   = end   + len < 0 ? 0 : end   + len;
    if (start > len) start = len;
    if (end   > len) end   = len;

    luz_list_t *result = luz_list_new();
    if (step > 0)
        for (int64_t i = start; i < end; i += step)
            luz_list_push(result, l->data[i]);
    else
        for (int64_t i = start; i > end; i += step)
            luz_list_push(result, l->data[i]);
    return result;
}

luz_list_t *luz_list_concat(luz_list_t *a, luz_list_t *b) {
    luz_list_t *result = luz_list_with_cap(a->len + b->len);
    for (size_t i = 0; i < a->len; i++) luz_list_push(result, a->data[i]);
    for (size_t i = 0; i < b->len; i++) luz_list_push(result, b->data[i]);
    return result;
}

int luz_list_contains(luz_list_t *l, luz_value_t v) {
    for (size_t i = 0; i < l->len; i++)
        if (luz_value_eq(l->data[i], v)) return 1;
    return 0;
}

static int _cmp_values(const void *a, const void *b) {
    const luz_value_t *va = (const luz_value_t *)a;
    const luz_value_t *vb = (const luz_value_t *)b;
    if (va->type == LUZ_INT && vb->type == LUZ_INT) {
        return va->i < vb->i ? -1 : va->i > vb->i ? 1 : 0;
    }
    if ((va->type == LUZ_INT || va->type == LUZ_FLOAT) &&
        (vb->type == LUZ_INT || vb->type == LUZ_FLOAT)) {
        double fa = va->type == LUZ_INT ? (double)va->i : va->f;
        double fb = vb->type == LUZ_INT ? (double)vb->i : vb->f;
        return fa < fb ? -1 : fa > fb ? 1 : 0;
    }
    if (va->type == LUZ_STRING && vb->type == LUZ_STRING) {
        return strcmp(luz_str_data(va->str), luz_str_data(vb->str));
    }
    return 0;
}

void luz_list_sort(luz_list_t *l) {
    qsort(l->data, l->len, sizeof(luz_value_t), _cmp_values);
}

void luz_list_reverse(luz_list_t *l) {
    for (size_t i = 0, j = l->len - 1; i < j; i++, j--) {
        luz_value_t tmp = l->data[i];
        l->data[i]      = l->data[j];
        l->data[j]      = tmp;
    }
}

/* ── Dict ────────────────────────────────────────────────────────────────── */

#define LUZ_DICT_INIT_CAP 16
#define LUZ_DICT_LOAD_MAX 0.75

static uint32_t _hash_value(luz_value_t v) {
    switch (v.type) {
        case LUZ_NULL:   return 0;
        case LUZ_BOOL:   /* fall-through */
        case LUZ_INT: {
            uint64_t x = (uint64_t)v.i;
            x = ((x >> 16) ^ x) * 0x45d9f3bUL;
            x = ((x >> 16) ^ x) * 0x45d9f3bUL;
            x = (x >> 16) ^ x;
            return (uint32_t)x;
        }
        case LUZ_FLOAT: {
            /* Hash float by its bit pattern */
            uint64_t bits;
            memcpy(&bits, &v.f, sizeof(bits));
            return _hash_value(LUZ_INT_VAL((int64_t)bits));
        }
        case LUZ_STRING: {
            const char *d   = luz_str_data(v.str);
            size_t      len = v.str->len;
            uint32_t    h   = 2166136261u;
            for (size_t i = 0; i < len; i++) {
                h ^= (uint8_t)d[i];
                h *= 16777619u;
            }
            return h;
        }
        default:
            return (uint32_t)(uintptr_t)v.obj;
    }
}

static void _dict_grow(luz_dict_t *d);

luz_dict_t *luz_dict_new(void) {
    luz_dict_t *d = _xmalloc(sizeof(luz_dict_t));
    d->refcount = 1;
    d->len      = 0;
    d->cap      = LUZ_DICT_INIT_CAP;
    d->entries  = _xcalloc(d->cap, sizeof(luz_dict_entry_t));
    return d;
}

void luz_dict_retain(luz_dict_t *d) { if (d) d->refcount++; }

void luz_dict_release(luz_dict_t *d) {
    if (!d) return;
    if (--d->refcount == 0) {
        for (size_t i = 0; i < d->cap; i++) {
            if (d->entries[i].occupied) {
                luz_value_release(d->entries[i].key);
                luz_value_release(d->entries[i].value);
            }
        }
        free(d->entries);
        free(d);
    }
}

void luz_dict_set(luz_dict_t *d, luz_value_t key, luz_value_t value) {
    if ((double)d->len / d->cap >= LUZ_DICT_LOAD_MAX) _dict_grow(d);
    uint32_t hash = _hash_value(key);
    size_t   idx  = hash & (d->cap - 1);
    for (;;) {
        luz_dict_entry_t *e = &d->entries[idx];
        if (!e->occupied && !e->tombstone) {
            /* Empty slot */
            luz_value_retain(key);
            luz_value_retain(value);
            e->key      = key;
            e->value    = value;
            e->hash     = hash;
            e->occupied = 1;
            d->len++;
            return;
        }
        if (e->occupied && e->hash == hash && luz_value_eq(e->key, key)) {
            /* Update existing */
            luz_value_release(e->value);
            luz_value_retain(value);
            e->value = value;
            return;
        }
        idx = (idx + 1) & (d->cap - 1);
    }
}

luz_value_t luz_dict_get(luz_dict_t *d, luz_value_t key) {
    uint32_t hash = _hash_value(key);
    size_t   idx  = hash & (d->cap - 1);
    for (;;) {
        luz_dict_entry_t *e = &d->entries[idx];
        if (!e->occupied && !e->tombstone) return LUZ_NULL_VAL;
        if (e->occupied && e->hash == hash && luz_value_eq(e->key, key))
            return e->value;
        idx = (idx + 1) & (d->cap - 1);
    }
}

int luz_dict_has(luz_dict_t *d, luz_value_t key) {
    uint32_t hash = _hash_value(key);
    size_t   idx  = hash & (d->cap - 1);
    for (;;) {
        luz_dict_entry_t *e = &d->entries[idx];
        if (!e->occupied && !e->tombstone) return 0;
        if (e->occupied && e->hash == hash && luz_value_eq(e->key, key)) return 1;
        idx = (idx + 1) & (d->cap - 1);
    }
}

void luz_dict_delete(luz_dict_t *d, luz_value_t key) {
    uint32_t hash = _hash_value(key);
    size_t   idx  = hash & (d->cap - 1);
    for (;;) {
        luz_dict_entry_t *e = &d->entries[idx];
        if (!e->occupied && !e->tombstone) return; /* not found */
        if (e->occupied && e->hash == hash && luz_value_eq(e->key, key)) {
            luz_value_release(e->key);
            luz_value_release(e->value);
            e->occupied  = 0;
            e->tombstone = 1;
            d->len--;
            return;
        }
        idx = (idx + 1) & (d->cap - 1);
    }
}

static void _dict_grow(luz_dict_t *d) {
    size_t            old_cap = d->cap;
    luz_dict_entry_t *old     = d->entries;
    d->cap    = old_cap * 2;
    d->entries = _xcalloc(d->cap, sizeof(luz_dict_entry_t));
    d->len    = 0;
    for (size_t i = 0; i < old_cap; i++) {
        if (old[i].occupied)
            luz_dict_set(d, old[i].key, old[i].value);
    }
    /* Release old entries' ARC counts (dict_set added new ones) */
    for (size_t i = 0; i < old_cap; i++) {
        if (old[i].occupied) {
            luz_value_release(old[i].key);
            luz_value_release(old[i].value);
        }
    }
    free(old);
}

luz_list_t *luz_dict_keys(luz_dict_t *d) {
    luz_list_t *result = luz_list_with_cap(d->len);
    for (size_t i = 0; i < d->cap; i++)
        if (d->entries[i].occupied)
            luz_list_push(result, d->entries[i].key);
    return result;
}

luz_list_t *luz_dict_values(luz_dict_t *d) {
    luz_list_t *result = luz_list_with_cap(d->len);
    for (size_t i = 0; i < d->cap; i++)
        if (d->entries[i].occupied)
            luz_list_push(result, d->entries[i].value);
    return result;
}

/* ── Object / class instance ─────────────────────────────────────────────── */

luz_object_t *luz_obj_new(const luz_vtable_t *vtable) {
    luz_object_t *o = _xmalloc(sizeof(luz_object_t));
    o->refcount = 1;
    o->vtable   = vtable;
    size_t n    = vtable ? vtable->attr_count : 0;
    o->attrs    = n > 0 ? _xcalloc(n, sizeof(luz_value_t)) : NULL;
    return o;
}

void luz_obj_retain(luz_object_t *o) { if (o) o->refcount++; }

void luz_obj_release(luz_object_t *o) {
    if (!o) return;
    if (--o->refcount == 0) {
        if (o->vtable) {
            for (size_t i = 0; i < o->vtable->attr_count; i++)
                luz_value_release(o->attrs[i]);
        }
        free(o->attrs);
        free(o);
    }
}

static int64_t _obj_attr_idx(luz_object_t *o, const char *name) {
    if (!o->vtable) return -1;
    for (size_t i = 0; i < o->vtable->attr_count; i++)
        if (strcmp(o->vtable->attr_names[i], name) == 0) return (int64_t)i;
    return -1;
}

luz_value_t luz_obj_get_attr(luz_object_t *o, const char *name) {
    int64_t i = _obj_attr_idx(o, name);
    if (i < 0) {
        char msg[128];
        snprintf(msg, sizeof(msg), "AttributeNotFoundFault: '%s' has no attribute '%s'",
                 o->vtable ? o->vtable->class_name : "object", name);
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr(msg)));
    }
    return o->attrs[i];
}

void luz_obj_set_attr(luz_object_t *o, const char *name, luz_value_t v) {
    int64_t i = _obj_attr_idx(o, name);
    if (i < 0) {
        /* Dynamic attribute: not in vtable — store in a side dict (future).
           For now, fatal error to encourage correct class design. */
        char msg[128];
        snprintf(msg, sizeof(msg), "AttributeNotFoundFault: '%s' has no attribute '%s'",
                 o->vtable ? o->vtable->class_name : "object", name);
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr(msg)));
    }
    luz_value_release(o->attrs[i]);
    luz_value_retain(v);
    o->attrs[i] = v;
}

/* ── Exception handling ──────────────────────────────────────────────────── */

luz_exc_frame_t *luz_exc_stack = NULL;

void luz_exc_push(luz_exc_frame_t *frame) {
    frame->prev   = luz_exc_stack;
    frame->active = 1;
    memset(&frame->exception, 0, sizeof(luz_value_t));
    luz_exc_stack = frame;
}

void luz_exc_pop(void) {
    if (luz_exc_stack) luz_exc_stack = luz_exc_stack->prev;
}

void luz_raise(luz_value_t exc) {
    if (luz_exc_stack && luz_exc_stack->active) {
        luz_exc_stack->exception = exc;
        luz_exc_stack->active    = 0;
        longjmp(luz_exc_stack->env, 1);
    }
    /* Uncaught exception — print and abort */
    luz_string_t *msg = luz_value_to_string(exc);
    fprintf(stderr, "Unhandled exception: %s\n", luz_str_data(msg));
    luz_str_release(msg);
    abort();
}

/* ── Builtins ────────────────────────────────────────────────────────────── */

void luz_builtin_write(luz_value_t v) {
    luz_string_t *s = luz_value_to_string(v);
    printf("%s\n", luz_str_data(s));
    luz_str_release(s);
}

luz_value_t luz_builtin_listen(void) {
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) return LUZ_STR_VAL(luz_str_from_cstr(""));
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') buf[--len] = '\0';
    return LUZ_STR_VAL(luz_str_new(buf, len));
}

luz_value_t luz_builtin_typeof(luz_value_t v) {
    return LUZ_STR_VAL(luz_str_from_cstr(luz_typeof(v)));
}

luz_value_t luz_builtin_len(luz_value_t v) {
    switch (v.type) {
        case LUZ_STRING: return LUZ_INT_VAL((int64_t)v.str->len);
        case LUZ_LIST:   return LUZ_INT_VAL((int64_t)v.list->len);
        case LUZ_DICT:   return LUZ_INT_VAL((int64_t)v.dict->len);
        default:
            luz_raise(LUZ_STR_VAL(luz_str_from_cstr(
                "TypeError: len() requires string, list, or dict")));
    }
}

luz_value_t luz_builtin_to_int(luz_value_t v) {
    switch (v.type) {
        case LUZ_INT:    return v;
        case LUZ_FLOAT:  return LUZ_INT_VAL((int64_t)v.f);
        case LUZ_BOOL:   return LUZ_INT_VAL(v.i);
        case LUZ_STRING: return LUZ_INT_VAL(strtoll(luz_str_data(v.str), NULL, 10));
        default:
            luz_raise(LUZ_STR_VAL(luz_str_from_cstr("CastFault: cannot convert to int")));
    }
}

luz_value_t luz_builtin_to_float(luz_value_t v) {
    switch (v.type) {
        case LUZ_FLOAT:  return v;
        case LUZ_INT:    return LUZ_FLOAT_VAL((double)v.i);
        case LUZ_BOOL:   return LUZ_FLOAT_VAL((double)v.i);
        case LUZ_STRING: return LUZ_FLOAT_VAL(strtod(luz_str_data(v.str), NULL));
        default:
            luz_raise(LUZ_STR_VAL(luz_str_from_cstr("CastFault: cannot convert to float")));
    }
}

luz_value_t luz_builtin_to_str(luz_value_t v) {
    return LUZ_STR_VAL(luz_value_to_string(v));
}

luz_value_t luz_builtin_to_bool(luz_value_t v) {
    return LUZ_BOOL_VAL(luz_value_truthy(v));
}

/* Math builtins — delegate to libm */
#define _MATH1(name, fn) \
    luz_value_t luz_builtin_##name(luz_value_t v) { \
        double x = v.type == LUZ_INT ? (double)v.i : v.f; \
        return LUZ_FLOAT_VAL(fn(x)); \
    }

_MATH1(sqrt,  sqrt)
_MATH1(exp,   exp)
_MATH1(ln,    log)
_MATH1(sin,   sin)
_MATH1(cos,   cos)
_MATH1(tan,   tan)
_MATH1(floor, floor)
_MATH1(ceil,  ceil)

luz_value_t luz_builtin_round(luz_value_t v) {
    double x = v.type == LUZ_INT ? (double)v.i : v.f;
    return LUZ_FLOAT_VAL(round(x));
}

luz_value_t luz_builtin_abs(luz_value_t v) {
    if (v.type == LUZ_INT)   return LUZ_INT_VAL(v.i < 0 ? -v.i : v.i);
    if (v.type == LUZ_FLOAT) return LUZ_FLOAT_VAL(fabs(v.f));
    luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: abs() requires a number")));
}

luz_value_t luz_builtin_min(luz_value_t a, luz_value_t b) {
    return _cmp_values(&a, &b) <= 0 ? a : b;
}

luz_value_t luz_builtin_max(luz_value_t a, luz_value_t b) {
    return _cmp_values(&a, &b) >= 0 ? a : b;
}

luz_value_t luz_builtin_clamp(luz_value_t v, luz_value_t lo, luz_value_t hi) {
    if (_cmp_values(&v, &lo) < 0) return lo;
    if (_cmp_values(&v, &hi) > 0) return hi;
    return v;
}

/* List builtins */
void luz_builtin_append(luz_value_t lst, luz_value_t v) {
    if (lst.type != LUZ_LIST)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: append() requires a list")));
    luz_list_push(lst.list, v);
}

luz_value_t luz_builtin_pop(luz_value_t lst) {
    if (lst.type != LUZ_LIST)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: pop() requires a list")));
    return luz_list_pop(lst.list);
}

void luz_builtin_insert(luz_value_t lst, luz_value_t idx, luz_value_t v) {
    if (lst.type != LUZ_LIST || idx.type != LUZ_INT)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: insert() requires list and int index")));
    luz_list_insert(lst.list, idx.i, v);
}

luz_value_t luz_builtin_range(luz_value_t start, luz_value_t end, luz_value_t step) {
    int64_t s  = start.i;
    int64_t e  = end.i;
    int64_t st = step.type == LUZ_INT ? step.i : 1;
    if (st == 0) luz_raise(LUZ_STR_VAL(luz_str_from_cstr("ValueError: range step cannot be zero")));
    luz_list_t *l = luz_list_new();
    if (st > 0) for (int64_t i = s; i < e; i += st) luz_list_push(l, LUZ_INT_VAL(i));
    else        for (int64_t i = s; i > e; i += st) luz_list_push(l, LUZ_INT_VAL(i));
    return LUZ_LIST_VAL(l);
}

luz_value_t luz_builtin_sum(luz_value_t lst) {
    if (lst.type != LUZ_LIST)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: sum() requires a list")));
    double total = 0.0;
    int    has_float = 0;
    for (size_t i = 0; i < lst.list->len; i++) {
        luz_value_t v = lst.list->data[i];
        if (v.type == LUZ_FLOAT) { total += v.f; has_float = 1; }
        else if (v.type == LUZ_INT) total += (double)v.i;
    }
    return has_float ? LUZ_FLOAT_VAL(total) : LUZ_INT_VAL((int64_t)total);
}

luz_value_t luz_builtin_any(luz_value_t lst) {
    if (lst.type != LUZ_LIST) return LUZ_BOOL_VAL(0);
    for (size_t i = 0; i < lst.list->len; i++)
        if (luz_value_truthy(lst.list->data[i])) return LUZ_BOOL_VAL(1);
    return LUZ_BOOL_VAL(0);
}

luz_value_t luz_builtin_all(luz_value_t lst) {
    if (lst.type != LUZ_LIST) return LUZ_BOOL_VAL(1);
    for (size_t i = 0; i < lst.list->len; i++)
        if (!luz_value_truthy(lst.list->data[i])) return LUZ_BOOL_VAL(0);
    return LUZ_BOOL_VAL(1);
}

luz_value_t luz_builtin_reverse(luz_value_t lst) {
    if (lst.type != LUZ_LIST)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: reverse() requires a list")));
    luz_list_reverse(lst.list);
    return LUZ_NULL_VAL;
}

/* String builtins */
luz_value_t luz_builtin_split(luz_value_t s, luz_value_t sep) {
    if (s.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: split() requires a string")));
    luz_string_t *sep_str = sep.type == LUZ_STRING ? sep.str : luz_str_from_cstr("");
    luz_list_t *result = luz_str_split(s.str, sep_str);
    if (sep.type != LUZ_STRING) luz_str_release(sep_str);
    return LUZ_LIST_VAL(result);
}

luz_value_t luz_builtin_join(luz_value_t sep, luz_value_t lst) {
    if (sep.type != LUZ_STRING || lst.type != LUZ_LIST)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: join() requires string and list")));
    luz_string_t *acc = luz_str_from_cstr("");
    for (size_t i = 0; i < lst.list->len; i++) {
        if (i > 0) {
            luz_string_t *tmp = luz_str_concat(acc, sep.str);
            luz_str_release(acc);
            acc = tmp;
        }
        luz_string_t *elem = luz_value_to_string(lst.list->data[i]);
        luz_string_t *tmp  = luz_str_concat(acc, elem);
        luz_str_release(acc);
        luz_str_release(elem);
        acc = tmp;
    }
    return LUZ_STR_VAL(acc);
}

luz_value_t luz_builtin_trim(luz_value_t s) {
    if (s.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: trim() requires a string")));
    return LUZ_STR_VAL(luz_str_trim(s.str));
}

luz_value_t luz_builtin_upper(luz_value_t s) {
    if (s.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: upper() requires a string")));
    return LUZ_STR_VAL(luz_str_upper(s.str));
}

luz_value_t luz_builtin_lower(luz_value_t s) {
    if (s.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: lower() requires a string")));
    return LUZ_STR_VAL(luz_str_lower(s.str));
}

luz_value_t luz_builtin_find(luz_value_t haystack, luz_value_t needle) {
    if (haystack.type != LUZ_STRING || needle.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: find() requires two strings")));
    return LUZ_INT_VAL(luz_str_find(haystack.str, needle.str));
}

luz_value_t luz_builtin_replace(luz_value_t s, luz_value_t old, luz_value_t new_) {
    if (s.type != LUZ_STRING || old.type != LUZ_STRING || new_.type != LUZ_STRING)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: replace() requires three strings")));
    /* Split on old, join with new_ */
    luz_list_t   *parts  = luz_str_split(s.str, old.str);
    luz_value_t   result = luz_builtin_join(new_, LUZ_LIST_VAL(parts));
    luz_list_release(parts);
    return result;
}

luz_value_t luz_builtin_starts_with(luz_value_t s, luz_value_t prefix) {
    if (s.type != LUZ_STRING || prefix.type != LUZ_STRING) return LUZ_BOOL_VAL(0);
    if (prefix.str->len > s.str->len) return LUZ_BOOL_VAL(0);
    return LUZ_BOOL_VAL(memcmp(luz_str_data(s.str), luz_str_data(prefix.str), prefix.str->len) == 0);
}

luz_value_t luz_builtin_ends_with(luz_value_t s, luz_value_t suffix) {
    if (s.type != LUZ_STRING || suffix.type != LUZ_STRING) return LUZ_BOOL_VAL(0);
    if (suffix.str->len > s.str->len) return LUZ_BOOL_VAL(0);
    size_t offset = s.str->len - suffix.str->len;
    return LUZ_BOOL_VAL(memcmp(luz_str_data(s.str) + offset, luz_str_data(suffix.str), suffix.str->len) == 0);
}

/* Dict builtins */
luz_value_t luz_builtin_keys(luz_value_t d) {
    if (d.type != LUZ_DICT)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: keys() requires a dict")));
    return LUZ_LIST_VAL(luz_dict_keys(d.dict));
}

luz_value_t luz_builtin_values(luz_value_t d) {
    if (d.type != LUZ_DICT)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: values() requires a dict")));
    return LUZ_LIST_VAL(luz_dict_values(d.dict));
}

void luz_builtin_remove(luz_value_t d, luz_value_t key) {
    if (d.type != LUZ_DICT)
        luz_raise(LUZ_STR_VAL(luz_str_from_cstr("TypeError: remove() requires a dict")));
    luz_dict_delete(d.dict, key);
}

void luz_builtin_alert(luz_value_t msg) {
    luz_raise(msg);
}
