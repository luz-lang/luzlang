#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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