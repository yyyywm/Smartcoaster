/*
 * 极简宿主侧单元测试框架（无外部依赖）
 *
 * 用法：
 *   TEST_CASE("name") { ... CHECK(cond, "what") ... }
 *   int main(void) { ...; return test_report(); }
 *
 * 编译：gcc -std=c11 -I. test_x.c src.c -o test_x -lm
 */
#ifndef TEST_UTIL_H
#define TEST_UTIL_H

#include <stdio.h>
#include <math.h>
#include <string.h>

static int t_pass = 0;
static int t_fail = 0;
static const char *t_case_name = "";

#define TEST_CASE(name) do { t_case_name = (name); printf("\n[ RUN  ] %s\n", (name)); } while (0)

#define CHECK(cond, msg)                                                     \
    do {                                                                     \
        if (cond) {                                                          \
            t_pass++;                                                        \
        } else {                                                             \
            t_fail++;                                                        \
            printf("  [FAIL] %s:%d: %s  (cond: %s)\n",                       \
                   __FILE__, __LINE__, (msg), #cond);                        \
        }                                                                    \
    } while (0)

#define CHECK_INT(a, b, msg)                                                 \
    do {                                                                     \
        long _a = (long)(a), _b = (long)(b);                                \
        if (_a == _b) { t_pass++; }                                          \
        else { t_fail++; printf("  [FAIL] %s:%d: %s  (got %ld, want %ld)\n",  \
                   __FILE__, __LINE__, (msg), _a, _b); }                      \
    } while (0)

#define CHECK_FLOAT(a, b, tol, msg)                                          \
    do {                                                                     \
        double _a = (double)(a), _b = (double)(b), _t = (double)(tol);      \
        if (fabs(_a - _b) <= _t) { t_pass++; }                              \
        else { t_fail++; printf("  [FAIL] %s:%d: %s  (got %.4f, want %.4f, tol %g)\n", \
                   __FILE__, __LINE__, (msg), _a, _b, _t); }                  \
    } while (0)

#define CHECK_TRUE(cond, msg)  CHECK(cond, msg)
#define CHECK_FALSE(cond, msg) CHECK(!(cond), msg)

#define CHECK_STR(a, b, msg)                                                 \
    do {                                                                     \
        const char *_a = (a), *_b = (b);                                    \
        if (_a && _b && strcmp(_a, _b) == 0) { t_pass++; }                   \
        else { t_fail++; printf("  [FAIL] %s:%d: %s\n        got:      %s\n        want:     %s\n", \
                   __FILE__, __LINE__, (msg), _a ? _a : "(null)", _b ? _b : "(null)"); } \
    } while (0)

static inline int test_report(void)
{
    printf("\n========================================\n");
    printf("  %d passed, %d failed (in %s)\n",
           t_pass, t_fail, t_case_name);
    printf("========================================\n");
    return t_fail == 0 ? 0 : 1;
}

#endif /* TEST_UTIL_H */
