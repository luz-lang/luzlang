#pragma once
// Minimal test framework — no external dependencies, works on MinGW.org GCC 6.
// Provides: TEST_CASE, CHECK, CHECK_FALSE, REQUIRE, REQUIRE_FALSE,
//           CHECK_THROWS, CHECK_THROWS_AS, doctest::Approx

#include <cmath>
#include <functional>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

// ── failure exception ─────────────────────────────────────────────────────────

namespace tr_detail {

struct Failure : std::exception {
    std::string msg;
    explicit Failure(std::string m) : msg(std::move(m)) {}
    const char* what() const noexcept { return msg.c_str(); }
};

// Global failure counter for the current test (reset per test case).
inline int& g_failures() { static int n = 0; return n; }
inline std::string& g_test_name() { static std::string s; return s; }

inline void soft_fail(const char* file, int line, const std::string& expr) {
    std::cerr << "  CHECK FAILED  " << file << ":" << line
              << "  " << expr << "\n";
    ++g_failures();
}

inline void hard_fail(const char* file, int line, const std::string& expr) {
    std::ostringstream ss;
    ss << file << ":" << line << "  " << expr;
    throw Failure(ss.str());
}

// ── test registry ─────────────────────────────────────────────────────────────

struct TestCase {
    std::string            name;
    std::function<void()>  fn;
};

inline std::vector<TestCase>& registry() {
    static std::vector<TestCase> v;
    return v;
}

struct Registrar {
    Registrar(const char* name, std::function<void()> fn) {
        registry().push_back({name, fn});
    }
};

// ── Approx helper (drop-in for doctest::Approx) ───────────────────────────────

struct Approx {
    double value;
    double epsilon;
    explicit Approx(double v, double eps = 1e-9) : value(v), epsilon(eps) {}
    bool operator==(double rhs) const { return std::fabs(rhs - value) <= epsilon; }
    bool operator==(float  rhs) const { return std::fabs((double)rhs - value) <= epsilon; }
    friend bool operator==(double lhs, const Approx& rhs) { return rhs == lhs; }
    friend bool operator==(float  lhs, const Approx& rhs) { return rhs == lhs; }
};

}  // namespace tr_detail

// ── doctest::Approx alias ─────────────────────────────────────────────────────

namespace doctest { using Approx = tr_detail::Approx; }

// ── macros ────────────────────────────────────────────────────────────────────

#define TR_CAT_(a, b) a##b
#define TR_CAT(a, b)  TR_CAT_(a, b)
#define TR_UNIQ(base) TR_CAT(base, __LINE__)

// Non-fatal: record failure but continue.
#define CHECK(expr) \
    do { if (!(expr)) tr_detail::soft_fail(__FILE__, __LINE__, #expr); } while(0)

#define CHECK_FALSE(expr) \
    do { if (!!(expr)) tr_detail::soft_fail(__FILE__, __LINE__, "not (" #expr ")"); } while(0)

// Fatal: throw on failure, aborting the current test.
#define REQUIRE(expr) \
    do { if (!(expr)) tr_detail::hard_fail(__FILE__, __LINE__, #expr); } while(0)

#define REQUIRE_FALSE(expr) \
    do { if (!!(expr)) tr_detail::hard_fail(__FILE__, __LINE__, "not (" #expr ")"); } while(0)

#define CHECK_THROWS(expr) \
    do { \
        bool tr_threw_ = false; \
        try { (expr); } catch (...) { tr_threw_ = true; } \
        if (!tr_threw_) tr_detail::soft_fail(__FILE__, __LINE__, #expr " (expected exception)"); \
    } while(0)

#define REQUIRE_THROWS(expr) \
    do { \
        bool tr_threw_ = false; \
        try { (expr); } catch (...) { tr_threw_ = true; } \
        if (!tr_threw_) tr_detail::hard_fail(__FILE__, __LINE__, #expr " (expected exception)"); \
    } while(0)

// Test case registration.
#define TEST_CASE(name) \
    static void TR_UNIQ(tr_fn_)(); \
    static tr_detail::Registrar TR_UNIQ(tr_reg_)(name, TR_UNIQ(tr_fn_)); \
    static void TR_UNIQ(tr_fn_)()

// ── main runner ───────────────────────────────────────────────────────────────

inline int run_all_tests() {
    int passed = 0, failed = 0;
    for (auto& tc : tr_detail::registry()) {
        tr_detail::g_failures() = 0;
        tr_detail::g_test_name() = tc.name;
        try {
            tc.fn();
        } catch (const tr_detail::Failure& e) {
            std::cerr << "  FAIL (hard)  " << tc.name << "\n    " << e.what() << "\n";
            ++tr_detail::g_failures();
        } catch (const std::exception& e) {
            std::cerr << "  FAIL (exc)   " << tc.name << "\n    " << e.what() << "\n";
            ++tr_detail::g_failures();
        } catch (...) {
            std::cerr << "  FAIL (unk)   " << tc.name << "\n";
            ++tr_detail::g_failures();
        }
        if (tr_detail::g_failures() == 0) {
            ++passed;
        } else {
            ++failed;
            std::cerr << "               ^ in test: " << tc.name << "\n";
        }
    }
    std::cout << "\n===  " << passed << " passed  /  " << failed << " failed  ===\n";
    return failed ? 1 : 0;
}
