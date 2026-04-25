#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// ── Strings ───────────────────────────────────────────────────────────────────

char* luz_str_concat(const char* a, const char* b) {
    size_t la = strlen(a), lb = strlen(b);
    char* out = (char*)malloc(la + lb + 1);
    memcpy(out, a, la);
    memcpy(out + la, b, lb + 1);
    return out;
}

char* luz_to_str_int(long long v) {
    char buf[32];
    snprintf(buf, sizeof(buf), "%lld", v);
    return strdup(buf);
}

char* luz_to_str_float(double v) {
    char buf[64];
    snprintf(buf, sizeof(buf), "%g", v);
    return strdup(buf);
}

char* luz_to_str_bool(int v) {
    return strdup(v ? "true" : "false");
}

long long luz_str_len(const char* s) {
    return (long long)strlen(s);
}

int luz_str_eq(const char* a, const char* b) {
    return strcmp(a, b) == 0;
}

int luz_str_contains(const char* haystack, const char* needle) {
    return strstr(haystack, needle) != NULL;
}

// ── Dict ──────────────────────────────────────────────────────────────────────
// Values are stored as a tagged union so the dict can hold any scalar type.

typedef struct {
    int       tag;   // 1=int 2=float 3=bool 4=str
    long long i;
    double    f;
    char*     s;
} LuzVal;

typedef struct {
    char*  key;
    LuzVal val;
} LuzEntry;

typedef struct {
    LuzEntry* entries;
    int       size;
    int       cap;
} LuzDict;

static LuzEntry* dict_find(LuzDict* d, const char* key) {
    for (int i = 0; i < d->size; i++)
        if (strcmp(d->entries[i].key, key) == 0)
            return &d->entries[i];
    return NULL;
}

static void dict_grow(LuzDict* d) {
    if (d->size < d->cap) return;
    d->cap = d->cap ? d->cap * 2 : 4;
    d->entries = (LuzEntry*)realloc(d->entries, (size_t)d->cap * sizeof(LuzEntry));
}

static void dict_set(LuzDict* d, const char* key, LuzVal val) {
    LuzEntry* e = dict_find(d, key);
    if (e) { e->val = val; return; }
    dict_grow(d);
    d->entries[d->size].key = strdup(key);
    d->entries[d->size].val = val;
    d->size++;
}

LuzDict* luz_dict_new(void) {
    LuzDict* d = (LuzDict*)calloc(1, sizeof(LuzDict));
    return d;
}

void luz_dict_set_int(LuzDict* d, const char* k, long long v) {
    LuzVal val = {1, v, 0.0, NULL};
    dict_set(d, k, val);
}
void luz_dict_set_float(LuzDict* d, const char* k, double v) {
    LuzVal val = {2, 0, v, NULL};
    dict_set(d, k, val);
}
void luz_dict_set_bool(LuzDict* d, const char* k, int v) {
    LuzVal val = {3, v, 0.0, NULL};
    dict_set(d, k, val);
}
void luz_dict_set_str(LuzDict* d, const char* k, const char* v) {
    LuzVal val = {4, 0, 0.0, strdup(v)};
    dict_set(d, k, val);
}

long long luz_dict_get_int(LuzDict* d, const char* k) {
    LuzEntry* e = dict_find(d, k);
    return e ? e->val.i : 0;
}
double luz_dict_get_float(LuzDict* d, const char* k) {
    LuzEntry* e = dict_find(d, k);
    return e ? e->val.f : 0.0;
}
int luz_dict_get_bool(LuzDict* d, const char* k) {
    LuzEntry* e = dict_find(d, k);
    return e ? (int)e->val.i : 0;
}
char* luz_dict_get_str(LuzDict* d, const char* k) {
    LuzEntry* e = dict_find(d, k);
    return e ? e->val.s : (char*)"";
}

long long luz_dict_len(LuzDict* d) {
    return (long long)d->size;
}

int luz_dict_contains(LuzDict* d, const char* k) {
    return dict_find(d, k) != NULL;
}

void luz_dict_remove(LuzDict* d, const char* k) {
    for (int i = 0; i < d->size; i++) {
        if (strcmp(d->entries[i].key, k) == 0) {
            free(d->entries[i].key);
            if (d->entries[i].val.tag == 4) free(d->entries[i].val.s);
            d->entries[i] = d->entries[--d->size];
            return;
        }
    }
}
