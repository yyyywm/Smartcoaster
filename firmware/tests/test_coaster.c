/*
 * coaster 核心状态机宿主单元测试
 *
 * 直接编译 components/coaster/coaster.c（纯逻辑，无 IDF/硬件依赖），
 * 用合成 HX711 raw 采样驱动状态机，覆盖：
 *   - 参数校验 / 创建
 *   - NO_CUP 基线自学习（快下学 + 温漂跟漂）
 *   - 放杯 → 稳定 → cup_placed
 *   - 拿杯 → NO_CUP → cup_removed
 *   - 差值法喝水结算（拿杯前后重量差）
 *   - 在位喝水（吸管）、在位加水（refill）与双模式标定
 *   - 阈值内不记账、getter、set_baseline / set_scale / estimate 开关
 *
 * 编译运行：make test   （或见 tests/README.md）
 */
#include "coaster.h"
#include "test_util.h"

#include <string.h>
#include <math.h>

/* 与 main/coaster_main.c 保持一致 */
#define SCALE_COUNTS_PER_G   384.7f
#define CUP_PRESENT_G        25.0f
#define STABLE_TOL_G         4.0f
#define STABLE_WINDOW        10
#define DRINK_THRESH_G       5.0f
#define REFILL_THRESH_G      15.0f
#define BASE_RAW             800000

#define MAX_EVT 48

typedef struct {
    coaster_handle_t h;
    coaster_event_t  ev[MAX_EVT];
    int              n;
} sim_t;

/* ---------------- 事件采集 ---------------- */

static void sim_event_cb(const coaster_event_t *e, void *ctx)
{
    sim_t *s = (sim_t *)ctx;
    if (s->n < MAX_EVT) {
        s->ev[s->n++] = *e;
    }
}

static int sim_count_of(const sim_t *s, coaster_event_type_t t)
{
    int c = 0;
    for (int i = 0; i < s->n; i++) {
        if (s->ev[i].type == t) {
            c++;
        }
    }
    return c;
}

static coaster_event_t *sim_last_of(sim_t *s, coaster_event_type_t t)
{
    for (int i = s->n - 1; i >= 0; i--) {
        if (s->ev[i].type == t) {
            return &s->ev[i];
        }
    }
    return NULL;
}

/* ---------------- 仿真输入 ---------------- */

/* 以当前内部基线为 0 点，换算出代表 weight_g 的 raw 采样（按默认 scale） */
static int32_t raw_for_weight(coaster_handle_t h, float weight_g)
{
    return (int32_t)lroundf((double)coaster_baseline_raw(h)
                           + (double)weight_g * SCALE_COUNTS_PER_G);
}

static void feed(sim_t *s, float weight_g)
{
    coaster_feed(s->h, raw_for_weight(s->h, weight_g));
}

static void feed_raw(sim_t *s, int32_t raw)
{
    coaster_feed(s->h, raw);
}

static void feed_n(sim_t *s, float weight_g, int n)
{
    for (int i = 0; i < n; i++) {
        feed(s, weight_g);
    }
}

/* 持续喂食直到状态达到 want（或超时），返回迭代次数 */
static int feed_until(sim_t *s, float weight_g, coaster_state_t want, int max_iter)
{
    for (int i = 0; i < max_iter; i++) {
        feed(s, weight_g);
        if (coaster_state(s->h) == want) {
            return i + 1;
        }
    }
    return max_iter;
}

/* ---------------- 构造 ---------------- */

static void default_cfg(coaster_cfg_t *c)
{
    memset(c, 0, sizeof(*c));
    c->scale_counts_per_g = SCALE_COUNTS_PER_G;
    c->baseline_raw       = BASE_RAW;
    c->cup_present_g      = CUP_PRESENT_G;
    c->stable_tol_g       = STABLE_TOL_G;
    c->stable_window      = STABLE_WINDOW;
    c->drink_thresh_g     = DRINK_THRESH_G;
    c->refill_thresh_g    = REFILL_THRESH_G;
    c->estimate_on_refill = true;
}

static void sim_new(sim_t *s, const coaster_cfg_t *cfg)
{
    memset(s, 0, sizeof(*s));
    s->h = coaster_create(cfg, sim_event_cb, s);
}

static void sim_idle(sim_t *s, int n)
{
    for (int i = 0; i < n; i++) {
        feed(s, 0.0f);
    }
}

/* ================= 用例 ================= */

static void test_create(void)
{
    TEST_CASE("create 参数校验与初始状态");
    coaster_cfg_t c;
    default_cfg(&c);

    CHECK_FALSE(coaster_create(NULL, NULL, NULL) != NULL, "cfg=NULL 应失败");

    c.stable_window = 2;
    CHECK_FALSE(coaster_create(&c, NULL, NULL) != NULL, "window<3 应失败");

    c.stable_window = STABLE_WINDOW;
    c.scale_counts_per_g = 0.0f;
    CHECK_FALSE(coaster_create(&c, NULL, NULL) != NULL, "scale<=0 应失败");

    c.scale_counts_per_g = -1.0f;
    CHECK_FALSE(coaster_create(&c, NULL, NULL) != NULL, "scale<0 应失败");

    c.scale_counts_per_g = SCALE_COUNTS_PER_G;
    sim_t s;
    sim_new(&s, &c);
    CHECK_TRUE(s.h != NULL, "合法 cfg 应创建成功");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "初始状态应为 NO_CUP");
    CHECK_FLOAT(coaster_weight_g(s.h), 0.0f, 0.2f, "初始重量应为 0");
    CHECK_TRUE(strcmp(coaster_state_name(s.h), "no_cup") == 0, "状态名应为 no_cup");
    coaster_destroy(s.h);
}

static void test_no_cup_idle(void)
{
    TEST_CASE("NO_CUP 空载重量为 0 且不报事件");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 20);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "应保持 NO_CUP");
    CHECK_FLOAT(coaster_weight_g(s.h), 0.0f, 0.2f, "空载重量≈0");
    CHECK_INT(s.n, 0, "空载不应产生事件");
    coaster_destroy(s.h);
}

static void test_baseline_snap(void)
{
    TEST_CASE("基线快下学：初始基线偏高时快速向真实空载收敛");
    coaster_cfg_t c;
    default_cfg(&c);
    c.baseline_raw = BASE_RAW + 20000;   /* 初值偏高 20000 码 */
    sim_t s;
    sim_new(&s, &c);

    /* 真实空载 = BASE_RAW，固定喂它（不跟随内部基线） */
    for (int i = 0; i < 100; i++) {
        feed_raw(&s, BASE_RAW);
    }
    int32_t bl = coaster_baseline_raw(s.h);
    CHECK_FLOAT((double)bl, (double)BASE_RAW, 1200.0, "100 次采样后基线应收敛到真实空载");
    CHECK_TRUE(bl < BASE_RAW + 5000, "基线应明显下降");
    CHECK_TRUE(bl > BASE_RAW - 1000, "基线不应低于真实空载太多");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "无杯不应转状态");
    coaster_destroy(s.h);
}

static void test_baseline_drift(void)
{
    TEST_CASE("基线温漂跟漂：持续小幅正偏差时缓慢上移");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);

    int32_t before = coaster_baseline_raw(s.h);
    /* 真实空载比基线高 50 码的微小温漂 */
    for (int i = 0; i < 100; i++) {
        feed_raw(&s, BASE_RAW + 50);
    }
    int32_t after = coaster_baseline_raw(s.h);
    CHECK_TRUE(after > before, "温漂应使基线上移");
    coaster_destroy(s.h);
}

static void test_cup_placed(void)
{
    TEST_CASE("放杯 → SETTLING → STABLE → cup_placed");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    int n = feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_TRUE(n < 60, "应在有限采样内进入 STABLE");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_STABLE, "最终应 STABLE");

    coaster_event_t *placed = sim_last_of(&s, COASTER_EVT_CUP_PLACED);
    CHECK_TRUE(placed != NULL, "应有 cup_placed 事件");
    if (placed) {
        CHECK_FLOAT(placed->weight_g, 350.0f, 1.0f, "cup_placed 重量≈350g");
    }
    CHECK_FLOAT(coaster_last_stable_g(s.h), 350.0f, 1.0f, "last_stable≈350g");
    CHECK_FLOAT(coaster_min_cup_g(s.h), 350.0f, 1.0f, "min_cup≈350g（首次记录）");
    CHECK_TRUE(coaster_have_last_stable(s.h), "have_last_stable 应置位");
    coaster_destroy(s.h);
}

static void test_cup_removed(void)
{
    TEST_CASE("拿杯 → NO_CUP → cup_removed");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);

    int n = feed_until(&s, 0.0f, COASTER_STATE_NO_CUP, 40);
    CHECK_TRUE(n < 40, "应在有限采样内回到 NO_CUP");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "拿杯后应 NO_CUP");

    coaster_event_t *removed = sim_last_of(&s, COASTER_EVT_CUP_REMOVED);
    CHECK_TRUE(removed != NULL, "应有 cup_removed 事件");
    if (removed) {
        CHECK_FLOAT(removed->weight_g, 350.0f, 1.0f, "cup_removed 重量≈350g（拿起前重量）");
    }
    coaster_destroy(s.h);
}

static void test_drink_diff(void)
{
    TEST_CASE("差值法：上次稳定 350g → 放回 200g 结算喝水 150ml");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;     /* 模拟 NVS 恢复 */
    c.last_stable_g = 350.0f;
    c.min_cup_g = 215.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 200.0f, COASTER_STATE_STABLE, 60);

    coaster_event_t *drink = sim_last_of(&s, COASTER_EVT_DRINK);
    CHECK_TRUE(drink != NULL, "应有 drink 事件");
    if (drink) {
        CHECK_FLOAT(drink->drink_ml, 150.0f, 1.5f, "喝水量应为 150ml");
        CHECK_FALSE(drink->estimated, "非续杯估计，estimated 应为 false");
        CHECK_FLOAT(drink->weight_g, 200.0f, 1.0f, "drink 事件重量≈200g");
    }
    coaster_destroy(s.h);
}

static void test_no_bookentry_small_jitter(void)
{
    TEST_CASE("阈值内不记账：350g → 352g 无事件");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    int before = s.n;

    /* 352g 与上次 350g 差 2g，低于 drink 阈值 5g，也不足迁移阈值 6g */
    feed_until(&s, 352.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(s.n, before, "2g 抖动不应产生新事件");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_STABLE, "仍应 STABLE");
    coaster_destroy(s.h);
}

static void test_inplace_drink(void)
{
    TEST_CASE("在位喝水（吸管）：350g → 300g 结算 drink 50ml");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    int before = s.n;

    /* 杯不离手：喂 40 个采样（10 个迁移确认 + 10 个稳定窗口 + 余量） */
    feed_n(&s, 300.0f, 40);
    CHECK_TRUE(s.n > before, "在位迁移应产生事件");

    coaster_event_t *drink = sim_last_of(&s, COASTER_EVT_DRINK);
    CHECK_TRUE(drink != NULL, "应有 drink 事件");
    if (drink) {
        CHECK_FLOAT(drink->drink_ml, 50.0f, 1.5f, "应结算 50ml");
        CHECK_FALSE(drink->estimated, "非估算");
    }
    CHECK_INT(sim_count_of(&s, COASTER_EVT_REFILL), 0, "无加水，不应有 refill");
    coaster_destroy(s.h);
}

static void test_refill_estimate(void)
{
    TEST_CASE("续杯只报 refill，不按历史空杯重估算饮水");
    coaster_cfg_t c;
    default_cfg(&c);
    c.min_cup_g = 215.0f;   /* 历史空杯重；若上次喝光则喝了 350-215=135g */
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    int before = s.n;

    feed_n(&s, 500.0f, 40);
    CHECK_TRUE(s.n > before, "加水应产生事件");

    coaster_event_t *refill = sim_last_of(&s, COASTER_EVT_REFILL);
    CHECK_TRUE(refill != NULL, "应有 refill 事件");
    if (refill) {
        CHECK_FLOAT(refill->refill_ml, 150.0f, 1.5f, "加水量应为 150ml");
    }

    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0,
              "补水期间的饮水无法确认，不应产生 drink");
    coaster_destroy(s.h);
}

static void test_estimate_disabled(void)
{
    TEST_CASE("estimate_on_refill=false 时加水只记 refill，不估算 drink");
    coaster_cfg_t c;
    default_cfg(&c);
    c.min_cup_g = 215.0f;
    c.estimate_on_refill = false;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);

    feed_n(&s, 500.0f, 40);

    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_REFILL) != NULL, "仍应有 refill 事件");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "关闭估算后不应有 drink 事件");
    coaster_destroy(s.h);
}

static void test_set_estimate_runtime(void)
{
    TEST_CASE("旧估算开关即使开启，也不能凭续杯推算饮水");
    coaster_cfg_t c;
    default_cfg(&c);
    c.min_cup_g = 215.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);

    coaster_set_estimate_on_refill(s.h, true);
    feed_n(&s, 500.0f, 40);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "开启旧开关也不应估算 drink");
    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_REFILL) != NULL, "仍应有 refill 事件");
    coaster_destroy(s.h);
}

static void test_min_cup_learning(void)
{
    TEST_CASE("min_cup_g 自学习取历史最小稳定带杯重量");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_FLOAT(coaster_min_cup_g(s.h), 350.0f, 1.0f, "首先记录 350g");

    coaster_set_estimate_on_refill(s.h, false);
    feed_until(&s, 0.0f, COASTER_STATE_NO_CUP, 40);
    feed_until(&s, 300.0f, COASTER_STATE_STABLE, 60);
    CHECK_FLOAT(coaster_min_cup_g(s.h), 300.0f, 1.0f, "应更新到更小的 300g");
    coaster_destroy(s.h);
}

static void test_manual_baseline(void)
{
    TEST_CASE("manual set_baseline 清空稳定参考");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_TRUE(coaster_have_last_stable(s.h), "校准前应有稳定参考");

    coaster_set_baseline(s.h, BASE_RAW);
    CHECK_FALSE(coaster_have_last_stable(s.h), "校准后 have_last 应清空");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "校准后应重新识别放杯");
    CHECK_FLOAT(coaster_min_cup_g(s.h), 0.0f, 0.01f, "校准后 min_cup 应清空");
    CHECK_INT(coaster_baseline_raw(s.h), (int32_t)BASE_RAW, "校准后基线应设为给定值");
    coaster_destroy(s.h);
}

static void test_set_scale(void)
{
    TEST_CASE("set_scale 忽略非法值、接受合法值");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_FLOAT(coaster_weight_g(s.h), 350.0f, 1.5f, "基准：应读到 350g");

    coaster_set_scale(s.h, 0.0f);
    feed_n(&s, 350.0f, 5);
    CHECK_FLOAT(coaster_weight_g(s.h), 350.0f, 1.5f, "scale=0 非法，应被忽略");

    coaster_set_scale(s.h, -5.0f);
    feed_n(&s, 350.0f, 5);
    CHECK_FLOAT(coaster_weight_g(s.h), 350.0f, 1.5f, "scale<0 非法，应被忽略");

    /* 合法 scale：同一 raw (BASE + 350*384.7) 在新 scale 1000 下应读到 134.6g */
    coaster_set_scale(s.h, 1000.0f);
    CHECK_FALSE(coaster_have_last_stable(s.h), "改比例后旧稳定参考失效");
    CHECK_FLOAT(coaster_min_cup_g(s.h), 0.0f, 0.01f, "改比例后旧空杯重失效");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "改比例后重新识别重量");
    int32_t fixed_raw = (int32_t)lroundf(BASE_RAW + 350.0 * SCALE_COUNTS_PER_G);
    feed_raw(&s, fixed_raw);
    CHECK_FLOAT(coaster_weight_g(s.h), 350.0 * SCALE_COUNTS_PER_G / 1000.0f, 1.5f,
                "scale=1000 后同一 raw 读数应≈134.6g");
    feed_raw(&s, fixed_raw);
    feed_n(&s, 350.0f, 20);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "改比例不应产生假喝水事件");
    coaster_destroy(s.h);
}

static void test_destroy_safe(void)
{
    TEST_CASE("coaster_destroy 空指针安全");
    coaster_destroy(NULL);
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    coaster_destroy(s.h);
    CHECK_TRUE(1, "destroy 正常返回");
}

/* ================= 边界用例 =================
 * 围绕阈值/计数器/浮点换算的临界行为，防止改动时把"恰好等于阈值"
 * 或"少一个采样"的行为改坏。
 */

/* 放杯判定：连续 3 个采样超阈值才转 SETTLING */
static void test_place_confirm_needs_three(void)
{
    TEST_CASE("放杯确认：2 次超阈值不转状态，第 3 次才转");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed(&s, 40.0f);
    feed(&s, 40.0f);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "2 次超阈值仍应 NO_CUP");
    CHECK_INT(s.n, 0, "未确认放杯不应有事件");

    feed(&s, 40.0f);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "第 3 次应转 SETTLING");
    coaster_destroy(s.h);
}

/* SETTLING 中重量回落（误触发）应回到 NO_CUP，且不记账 */
static void test_settling_dropback(void)
{
    TEST_CASE("SETTLING 回退：重量失而复失（未判稳）回 NO_CUP 不记事件");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 350.0f, COASTER_STATE_SETTLING, 60);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "应先进入 SETTLING");

    /* 4 次低于阈值：第 3 次即回 NO_CUP */
    feed_n(&s, 0.0f, 4);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "SETTLING 回落应回 NO_CUP");
    CHECK_INT(s.n, 0, "未判稳不应有事件");
    coaster_destroy(s.h);
}

/* 拿杯判定：STABLE 中连续 3 次低于阈值才回 NO_CUP 并记 cup_removed */
static void test_cup_removed_needs_three(void)
{
    TEST_CASE("拿杯确认：2 次低于阈值仍 STABLE，第 3 次回 NO_CUP");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_STABLE, "应先 STABLE");

    int before = s.n;
    feed(&s, 24.0f);   /* 24 < cup_present 25 */
    feed(&s, 24.0f);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_STABLE, "2 次低于阈值仍 STABLE");
    CHECK_INT(s.n, before, "2 次不应产生事件");

    feed(&s, 24.0f);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "第 3 次应 NO_CUP");
    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_CUP_REMOVED) != NULL, "应记 cup_removed");
    coaster_destroy(s.h);
}

/* delta 正好小于 drink 阈值（5g）→ 不在阈值内但不足 5g，不记账 */
static void test_drink_just_below_threshold(void)
{
    TEST_CASE("喝水阈值下沿：old 350 → 347（delta 3g）不记账");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 350.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 347.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "delta 3g 不足 5g 不记 drink");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_REFILL), 0, "更不可能记 refill");
    /* 但仍然建立了新的稳定参考 */
    CHECK_FLOAT(coaster_last_stable_g(s.h), 347.0f, 1.0f, "last_stable 应更新为 347g");
    coaster_destroy(s.h);
}

/* delta 绝对值小于 refill 阈值（15g）→ 不记账 */
static void test_refill_just_below_threshold(void)
{
    TEST_CASE("加水阈值下沿：old 350 → 364（delta -14g）不记账");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 350.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 364.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_REFILL), 0, "delta -14g 不足 15g 不记 refill");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "也不应记 drink");
    coaster_destroy(s.h);
}

/* delta 正好等于 drink 阈值（5g）——严格大于才记账，故不记 */
static void test_drink_exact_threshold(void)
{
    TEST_CASE("喝水阈值临界：delta 恰好 5g（非严格大于）不记账");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 355.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "delta==5g 不触发（须 >5g）");
    coaster_destroy(s.h);
}

/* delta 刚好超过 refill 阈值但不超过 drink 阈值的组合 */
static void test_refill_delta_between_thresholds(void)
{
    TEST_CASE("加水阈值临界：old 350 → 367（delta -17g）记 refill 不记 drink");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 350.0f;
    c.min_cup_g = 0;
    c.estimate_on_refill = false;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 367.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_REFILL), 1, "delta -17g 记 refill");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "关闭估算时不记 drink");
    coaster_event_t *r = sim_last_of(&s, COASTER_EVT_REFILL);
    if (r) {
        CHECK_FLOAT(r->refill_ml, 17.0f, 1.5f, "加水量应为 17ml");
    }
    coaster_destroy(s.h);
}

/* 续杯估算：min_cup_g 未学习（0）时即使开启估算也不发 estimated drink */
static void test_refill_estimate_mincup_unlearned(void)
{
    TEST_CASE("续杯估算关闭：min_cup_g=0 时不在倒灌处强行估喝");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 300.0f;
    c.min_cup_g = 0.0f;              /* 从未学到空杯重 */
    c.estimate_on_refill = true;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 500.0f, COASTER_STATE_STABLE, 60);
    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_REFILL) != NULL, "仍应记 refill");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "min_cup=0 时不应估喝");
    coaster_destroy(s.h);
}

/* 续杯估算阈值：估算量 <= drink 阈值时不发 estimated drink */
static void test_refill_estimate_below_drink_threshold(void)
{
    TEST_CASE("续杯估算阈值：估算量 <5g 时不发 estimated drink");
    coaster_cfg_t c;
    default_cfg(&c);
    c.have_last_stable = true;
    c.last_stable_g = 300.0f;
    c.min_cup_g = 298.0f;              /* est = 300-298 = 2g < 5g */
    c.estimate_on_refill = true;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_until(&s, 500.0f, COASTER_STATE_STABLE, 60);
    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_REFILL) != NULL, "仍应记 refill");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "估算量 2g 过高阈值应被丢弃");
    coaster_destroy(s.h);
}

/* min_cup_g 只允许变小（历史最小），变大不应覆盖 */
static void test_min_cup_only_shrinks(void)
{
    TEST_CASE("min_cup_g 单调：重变不覆盖更小历史值");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 300.0f, COASTER_STATE_STABLE, 60);
    CHECK_FLOAT(coaster_min_cup_g(s.h), 300.0f, 1.0f, "min_cup=300");

    feed_until(&s, 500.0f, COASTER_STATE_STABLE, 60);
    CHECK_FLOAT(coaster_min_cup_g(s.h), 300.0f, 1.0f, "500g 不应把 min_cup 拉回");
    coaster_destroy(s.h);
}

/* 在位迁移阈值：|delta| <= stable_tol*1.5 不迁移 */
static void test_migration_below_threshold(void)
{
    TEST_CASE("迁移阈值下沿：+5g（<6g）不迁移、不记账");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    int before = s.n;

    feed_n(&s, 355.0f, 40);            /* |delta|=5 < 6 */
    CHECK_INT(coaster_state(s.h), COASTER_STATE_STABLE, "5g 迁移不足 6g 应保持 STABLE");
    CHECK_INT(s.n, before, "不应产生任何事件");
    coaster_destroy(s.h);
}

/* 在位迁移：刚好超阈值并稳定后结算 */
static void test_migration_above_threshold(void)
{
    TEST_CASE("迁移阈值上沿：+7g 迁移后按差值法结算 drink");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    int before = s.n;

    feed_n(&s, 343.0f, 40);            /* |delta|=7 > 6 */
    CHECK_TRUE(s.n > before, "7g 迁移应触发结算");

    coaster_event_t *drink = sim_last_of(&s, COASTER_EVT_DRINK);
    CHECK_TRUE(drink != NULL, "应记 drink 7ml");
    if (drink) {
        CHECK_FLOAT(drink->drink_ml, 7.0f, 1.5f, "喝水量应为 7ml");
        CHECK_FALSE(drink->estimated, "非续杯估算");
    }
    coaster_destroy(s.h);
}

/* 极差恰好等于 tol（4g）→ 不判稳定（严格小于） */
static void test_stable_range_exact_tolerance(void)
{
    TEST_CASE("稳定判据临界：窗口极差恰好 4g 不判稳");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    /* 先盖章到 SETTLING */
    feed_n(&s, 350.0f, 3);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "应先进入 SETTLING");

    /* 交替 350 / 354（差 4g），极差恒为 4g，不满足 <4g */
    for (int i = 0; i < 40; i++) {
        feed(&s, (i % 2 == 0) ? 350.0f : 354.0f);
    }
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "极差恰 4g 不应判稳");
    CHECK_INT(s.n, 0, "未判稳不应记事件");
    coaster_destroy(s.h);
}

/* 稳定窗口内容始终在波动（极差太大）→ 永不判稳 */
static void test_settling_never_stable(void)
{
    TEST_CASE("稳定判据上界：窗口内大幅抖动永不判稳");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_n(&s, 350.0f, 3);
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "应先进入 SETTLING");

    for (int i = 0; i < 60; i++) {
        feed(&s, (i % 2 == 0) ? 300.0f : 400.0f);   /* 极差 100g */
    }
    CHECK_INT(coaster_state(s.h), COASTER_STATE_SETTLING, "剧烈抖动不应判稳");
    CHECK_INT(s.n, 0, "不应有任何结算事件");
    coaster_destroy(s.h);
}

/* 负重量：基线被抬高到当前读数之上时换算为负，状态机不应崩或误判 */
static void test_negative_weight(void)
{
    TEST_CASE("负重量：raw 低于基线换算为负，不崩且保持 NO_CUP");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    feed_raw(&s, BASE_RAW - 50000);    /* 比基线低，g 为负 */
    CHECK_TRUE(coaster_weight_g(s.h) < 0.0f, "换算重量应为负");
    CHECK_INT(coaster_state(s.h), COASTER_STATE_NO_CUP, "负重量应为 NO_CUP");
    CHECK_INT(s.n, 0, "负重量不应记事件");
    coaster_destroy(s.h);
}

/* 状态名映射完整 */
static void test_state_names(void)
{
    TEST_CASE("状态名映射：no_cup / settling / stable");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);

    CHECK_STR(coaster_state_name(s.h), "no_cup", "NO_CUP 名");
    feed_until(&s, 350.0f, COASTER_STATE_SETTLING, 60);
    CHECK_STR(coaster_state_name(s.h), "settling", "SETTLING 名");
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);
    CHECK_STR(coaster_state_name(s.h), "stable", "STABLE 名");
    coaster_destroy(s.h);
}

/* set_baseline 重置 have_last/min_cup 后重新放杯：重新学习稳定参考 */
static void test_set_baseline_relearn(void)
{
    TEST_CASE("手动校准后重新建立稳定参考");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 350.0f, COASTER_STATE_STABLE, 60);

    coaster_set_baseline(s.h, BASE_RAW);
    /* 校准后旧的 350g 参考被清空但状态仍是 STABLE，需连续喂够样本走
     * 「迁移 → 重新稳定 → settle(400)」路径才能重新建立稳定参考 */
    feed_n(&s, 400.0f, 60);
    CHECK_TRUE(coaster_have_last_stable(s.h), "应重新建立稳定参考");
    CHECK_FLOAT(coaster_last_stable_g(s.h), 400.0f, 1.0f, "新参考应为 400g");
    CHECK_FLOAT(coaster_min_cup_g(s.h), 400.0f, 1.0f, "min_cup 也应重新学习");
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "校准后不应误算喝水");
    coaster_destroy(s.h);
}

static void test_calibrated_full_cup_counts_only_visible_net_loss(void)
{
    TEST_CASE("空杯+满杯标定：拿杯期间净减少可确认，补至满杯不猜饮水");
    coaster_cfg_t c;
    default_cfg(&c);
    c.empty_cup_g = 120.0f;
    c.full_cup_g = 620.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 600.0f, COASTER_STATE_STABLE, 60);
    feed_until(&s, 0.0f, COASTER_STATE_NO_CUP, 20);
    feed_until(&s, 570.0f, COASTER_STATE_STABLE, 60);
    coaster_event_t *drink = sim_last_of(&s, COASTER_EVT_DRINK);
    CHECK_TRUE(drink != NULL, "净减少 30g 应记饮水");
    if (drink) CHECK_FLOAT(drink->drink_ml, 30.0f, 1.5f, "确认 30ml");

    int drink_count = sim_count_of(&s, COASTER_EVT_DRINK);
    feed_until(&s, 0.0f, COASTER_STATE_NO_CUP, 20);
    feed_until(&s, 620.0f, COASTER_STATE_STABLE, 60);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), drink_count,
              "返回满杯时无法识别途中喝水，不应补记");
    CHECK_TRUE(sim_last_of(&s, COASTER_EVT_REFILL) != NULL, "应记录净加水");
    coaster_destroy(s.h);
}

static void test_drink_then_refill_before_return_has_no_confirmed_drink(void)
{
    TEST_CASE("拿杯喝完/喝一口后直接加满：只报净增加，不报饮水");
    const float before_ml[] = {200.0f, 400.0f};
    for (int i = 0; i < 2; i++) {
        coaster_cfg_t c;
        default_cfg(&c);
        c.empty_cup_g = 120.0f;
        c.full_cup_g = 620.0f;
        sim_t s;
        sim_new(&s, &c);
        sim_idle(&s, 5);
        feed_until(&s, 120.0f + before_ml[i], COASTER_STATE_STABLE, 60);
        feed_until(&s, 0.0f, COASTER_STATE_NO_CUP, 20);
        feed_until(&s, 620.0f, COASTER_STATE_STABLE, 60);
        CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0,
                  "途中没有空杯/喝后重量，不能确认喝水");
        CHECK_INT(sim_count_of(&s, COASTER_EVT_REFILL), 1,
                  "放回满杯只记录净增加");
        coaster_event_t *refill = sim_last_of(&s, COASTER_EVT_REFILL);
        if (refill) {
            CHECK_FLOAT(refill->refill_ml, 500.0f - before_ml[i], 1.5f,
                        "净增加量应正确");
        }
        coaster_destroy(s.h);
    }
}

static void test_calibrated_empty_only_and_out_of_range(void)
{
    TEST_CASE("仅空杯标定：净减少记账，低于空杯重拒绝，续杯不猜饮水");
    coaster_cfg_t c;
    default_cfg(&c);
    c.empty_cup_g = 120.0f;
    sim_t s;
    sim_new(&s, &c);
    sim_idle(&s, 5);
    feed_until(&s, 400.0f, COASTER_STATE_STABLE, 60);
    feed_n(&s, 350.0f, 40);
    coaster_event_t *drink = sim_last_of(&s, COASTER_EVT_DRINK);
    CHECK_TRUE(drink != NULL, "净减少 50g 应记饮水");
    if (drink) CHECK_FLOAT(drink->drink_ml, 50.0f, 1.5f, "确认 50ml");
    int count = sim_count_of(&s, COASTER_EVT_DRINK);
    feed_n(&s, 500.0f, 40);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), count, "续杯不应补记饮水");
    feed_n(&s, 80.0f, 40);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), count,
              "换成比标定空杯更轻的杯子时不应误记饮水");
    coaster_destroy(s.h);
}

static void test_full_cup_rejects_over_capacity_and_calibration_resets(void)
{
    TEST_CASE("满杯上界过滤其他物体；基线/比例改变后清除杯子标定");
    coaster_cfg_t c;
    default_cfg(&c);
    sim_t s;
    sim_new(&s, &c);
    CHECK_FALSE(coaster_set_cup_calibration(s.h, 120.0f, 150.0f),
                "满杯比空杯多不足 50g 应拒绝");
    CHECK_TRUE(coaster_set_cup_calibration(s.h, 120.0f, 620.0f), "有效标定应接受");
    sim_idle(&s, 5);
    feed_until(&s, 700.0f, COASTER_STATE_STABLE, 60);
    CHECK_TRUE(coaster_have_last_stable(s.h), "放杯后已有稳定参考");
    feed_n(&s, 500.0f, 40);
    CHECK_INT(sim_count_of(&s, COASTER_EVT_DRINK), 0, "超过满杯重量的物体不可算作饮水");
    CHECK_TRUE(coaster_set_cup_calibration(s.h, 121.0f, 621.0f), "换杯可重新标定");
    CHECK_FALSE(coaster_have_last_stable(s.h), "空杯重变更后清除旧杯稳定参考");
    coaster_set_baseline(s.h, BASE_RAW);
    CHECK_FLOAT(coaster_empty_cup_g(s.h), 0.0f, 0.01f, "基线变更清除空杯标定");
    CHECK_FLOAT(coaster_full_cup_g(s.h), 0.0f, 0.01f, "基线变更清除满杯标定");
    CHECK_TRUE(coaster_set_cup_calibration(s.h, 120.0f, 620.0f), "可重新标定");
    coaster_set_scale(s.h, SCALE_COUNTS_PER_G);
    CHECK_FLOAT(coaster_full_cup_g(s.h), 0.0f, 0.01f, "比例变更清除标定");
    coaster_destroy(s.h);
}

int main(void)
{
    test_create();
    test_no_cup_idle();
    test_baseline_snap();
    test_baseline_drift();
    test_cup_placed();
    test_cup_removed();
    test_drink_diff();
    test_no_bookentry_small_jitter();
    test_inplace_drink();
    test_refill_estimate();
    test_estimate_disabled();
    test_set_estimate_runtime();
    test_min_cup_learning();
    test_manual_baseline();
    test_set_scale();
    test_destroy_safe();

    /* 边界用例 */
    test_place_confirm_needs_three();
    test_settling_dropback();
    test_cup_removed_needs_three();
    test_drink_just_below_threshold();
    test_refill_just_below_threshold();
    test_drink_exact_threshold();
    test_refill_delta_between_thresholds();
    test_refill_estimate_mincup_unlearned();
    test_refill_estimate_below_drink_threshold();
    test_min_cup_only_shrinks();
    test_migration_below_threshold();
    test_migration_above_threshold();
    test_stable_range_exact_tolerance();
    test_settling_never_stable();
    test_negative_weight();
    test_state_names();
    test_set_baseline_relearn();
    test_calibrated_full_cup_counts_only_visible_net_loss();
    test_drink_then_refill_before_return_has_no_confirmed_drink();
    test_calibrated_empty_only_and_out_of_range();
    test_full_cup_rejects_over_capacity_and_calibration_resets();

    return test_report();
}
