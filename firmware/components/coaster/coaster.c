/*
 * 智能杯垫核心状态机实现
 */
#include "coaster.h"

#include <stdlib.h>
#include <math.h>

/* 基线自学习参数（单位：raw 码值） */
#define BASELINE_SNAP_ERR   (-500.0f)   /* 误差低于此值：发现新的空载低点，快速下学 */
#define BASELINE_SNAP_RATE  0.05f       /* 快速下学速率（每采样逼进 5%，~6s 收敛） */
#define BASELINE_DRIFT_RATE 0.001f      /* 慢速跟漂速率（温漂补偿） */
#define BASELINE_DRIFT_MAX  1.5f        /* 慢速跟漂每采样最大步进 */

/* 状态判定采样数（~10Hz 采样） */
#define PLACE_CONFIRM_SAMPLES   3       /* 放杯确认：连续 3 个采样超阈值 */
#define REMOVE_CONFIRM_SAMPLES  3       /* 拿杯确认：连续 3 个采样低于阈值 */

struct coaster {
    coaster_cfg_t       cfg;
    coaster_event_cb_t  cb;
    void               *ctx;

    coaster_state_t state;
    bool            came_from_nocup;    /* SETTLING 来源：区分"放上"和"在位迁移" */

    /* 稳定窗口（环形缓冲，存 g） */
    float *win;
    int    win_cap;
    int    win_count;
    int    win_head;

    int   above_cnt;    /* NO_CUP 中连续超阈值计数 */
    int   below_cnt;    /* 连续低于阈值计数 */
    int   migrate_cnt;  /* STABLE 中连续偏离计数 */

    float   baseline_f;     /* 空载基线（浮点累积，持久化时取整） */
    float   min_cup_g;      /* 历史最小带杯重量 */
    bool    have_last;
    float   last_stable_g;
    float   cur_g;          /* 最近瞬时重量 */
};

/* ---------- 稳定窗口 ---------- */

static void win_reset(struct coaster *h)
{
    h->win_count = 0;
    h->win_head = 0;
}

static void win_push(struct coaster *h, float g)
{
    h->win[h->win_head] = g;
    h->win_head = (h->win_head + 1) % h->win_cap;
    if (h->win_count < h->win_cap) {
        h->win_count++;
    }
}

static float win_range(const struct coaster *h)
{
    float lo = h->win[0], hi = h->win[0];
    for (int i = 1; i < h->win_count; i++) {
        if (h->win[i] < lo) lo = h->win[i];
        if (h->win[i] > hi) hi = h->win[i];
    }
    return hi - lo;
}

static float win_mean(const struct coaster *h)
{
    float sum = 0;
    for (int i = 0; i < h->win_count; i++) {
        sum += h->win[i];
    }
    return sum / h->win_count;
}

/* ---------- 事件 ---------- */

static void emit(struct coaster *h, coaster_event_type_t type,
                 float weight_g, float drink_ml, float refill_ml, bool estimated)
{
    if (h->cb == NULL) {
        return;
    }
    coaster_event_t evt = {
        .type = type,
        .weight_g = weight_g,
        .drink_ml = drink_ml,
        .refill_ml = refill_ml,
        .estimated = estimated,
    };
    h->cb(&evt, h->ctx);
}

/**
 * 重量达到新稳定值时的结算。
 * delta = 上次稳定 - 本次稳定：
 *   delta > drink 阈值  → 喝了 delta
 *   delta < -refill 阈值 → 只记录加水；离开杯垫时的饮水不可反推
 */
static void settle(struct coaster *h, float w)
{
    const coaster_cfg_t *c = &h->cfg;

    if (h->have_last) {
        float delta = h->last_stable_g - w;
        if (delta > c->drink_thresh_g) {
            bool plausible = true;
            float amount = delta;
            if (c->empty_cup_g > 0) {
                float available = h->last_stable_g - c->empty_cup_g;
                plausible = available > 0 &&
                            w >= c->empty_cup_g - c->stable_tol_g &&
                            delta <= available + c->stable_tol_g;
                if (amount > available) amount = available;
            }
            if (c->full_cup_g > 0) {
                plausible = plausible &&
                            h->last_stable_g <= c->full_cup_g + c->stable_tol_g &&
                            w <= c->full_cup_g + c->stable_tol_g;
            }
            if (plausible && amount > c->drink_thresh_g) {
                emit(h, COASTER_EVT_DRINK, w, amount, 0, false);
            }
        } else if (delta < -c->refill_thresh_g) {
            emit(h, COASTER_EVT_REFILL, w, 0, -delta, false);
        }
        /* |delta| 在阈值内：只是拿起又放下，不记账 */
    }

    if (h->came_from_nocup) {
        emit(h, COASTER_EVT_CUP_PLACED, w, 0, 0, false);
    }

    h->have_last = true;
    h->last_stable_g = w;

    /* 空杯重自学习：历史最小稳定带杯重量 */
    if (h->min_cup_g <= 0 || w < h->min_cup_g) {
        h->min_cup_g = w;
    }
}

/* ---------- 对外接口 ---------- */

coaster_handle_t coaster_create(const coaster_cfg_t *cfg, coaster_event_cb_t cb, void *ctx)
{
    if (cfg == NULL || cfg->stable_window < 3 || cfg->scale_counts_per_g <= 0 ||
        !isfinite(cfg->empty_cup_g) || !isfinite(cfg->full_cup_g) ||
        cfg->empty_cup_g < 0 || cfg->empty_cup_g > 5000 ||
        cfg->full_cup_g < 0 || cfg->full_cup_g > 8000) {
        return NULL;
    }
    if (cfg->full_cup_g > 0 && (cfg->empty_cup_g <= 0 ||
                                cfg->full_cup_g < cfg->empty_cup_g + 50)) {
        return NULL;
    }
    struct coaster *h = calloc(1, sizeof(struct coaster));
    if (h == NULL) {
        return NULL;
    }
    h->win = calloc(cfg->stable_window, sizeof(float));
    if (h->win == NULL) {
        free(h);
        return NULL;
    }
    h->cfg = *cfg;
    h->cb = cb;
    h->ctx = ctx;
    h->win_cap = cfg->stable_window;
    h->state = COASTER_STATE_NO_CUP;
    h->came_from_nocup = true;
    h->baseline_f = (float)cfg->baseline_raw;
    h->min_cup_g = cfg->min_cup_g;
    h->have_last = cfg->have_last_stable;
    h->last_stable_g = cfg->last_stable_g;
    return h;
}

void coaster_destroy(coaster_handle_t h)
{
    if (h) {
        free(h->win);
        free(h);
    }
}

void coaster_feed(coaster_handle_t h, int32_t raw)
{
    const coaster_cfg_t *c = &h->cfg;
    float g = ((float)raw - h->baseline_f) / c->scale_counts_per_g;
    h->cur_g = g;

    win_push(h, g);

    switch (h->state) {

    case COASTER_STATE_NO_CUP: {
        /* 空载基线自学习/跟漂（此时有杯重量被压在阈值以下才安全，
         * 所以只在 NO_CUP 状态做） */
        float err = (float)raw - h->baseline_f;
        if (err < BASELINE_SNAP_ERR) {
            h->baseline_f += err * BASELINE_SNAP_RATE;      /* 快速下学新低点 */
        } else {
            float step = err * BASELINE_DRIFT_RATE;         /* 慢速跟漂 */
            if (step >  BASELINE_DRIFT_MAX) step =  BASELINE_DRIFT_MAX;
            if (step < -BASELINE_DRIFT_MAX) step = -BASELINE_DRIFT_MAX;
            h->baseline_f += step;
        }

        if (g > c->cup_present_g) {
            if (++h->above_cnt >= PLACE_CONFIRM_SAMPLES) {
                h->state = COASTER_STATE_SETTLING;
                h->came_from_nocup = true;
                h->above_cnt = 0;
                win_reset(h);
            }
        } else {
            h->above_cnt = 0;
        }
        break;
    }

    case COASTER_STATE_SETTLING:
        if (g < c->cup_present_g) {
            /* 重量又掉回去了：误触发（如碰了一下杯垫），回到无杯 */
            if (++h->below_cnt >= REMOVE_CONFIRM_SAMPLES) {
                h->state = COASTER_STATE_NO_CUP;
                h->below_cnt = 0;
                win_reset(h);
            }
            break;
        }
        h->below_cnt = 0;
        if (h->win_count >= h->win_cap && win_range(h) < c->stable_tol_g) {
            h->state = COASTER_STATE_STABLE;
            h->migrate_cnt = 0;
            settle(h, win_mean(h));
            win_reset(h);   /* STABLE 期间窗口重新积累，用于迁移检测 */
        }
        break;

    case COASTER_STATE_STABLE:
        if (g < c->cup_present_g) {
            if (++h->below_cnt >= REMOVE_CONFIRM_SAMPLES) {
                h->state = COASTER_STATE_NO_CUP;
                h->below_cnt = 0;
                win_reset(h);
                emit(h, COASTER_EVT_CUP_REMOVED, h->last_stable_g, 0, 0, false);
            }
            break;
        }
        h->below_cnt = 0;
        /* 在位重量迁移检测：水壶直接加水、吸管喝水、杯里加茶包等。
         * 持续偏离上次稳定值 → 转入 SETTLING 重新稳定后按差值结算 */
        if (fabsf(g - h->last_stable_g) > c->stable_tol_g * 1.5f) {
            if (++h->migrate_cnt >= h->win_cap) {
                h->state = COASTER_STATE_SETTLING;
                h->came_from_nocup = false;
                h->migrate_cnt = 0;
                win_reset(h);
            }
        } else {
            h->migrate_cnt = 0;
        }
        break;
    }
}

coaster_state_t coaster_state(coaster_handle_t h)
{
    return h->state;
}

const char *coaster_state_name(coaster_handle_t h)
{
    switch (h->state) {
    case COASTER_STATE_NO_CUP:   return "no_cup";
    case COASTER_STATE_SETTLING: return "settling";
    case COASTER_STATE_STABLE:   return "stable";
    default:                     return "unknown";
    }
}

float coaster_weight_g(coaster_handle_t h)
{
    return h->cur_g;
}

int32_t coaster_baseline_raw(coaster_handle_t h)
{
    return (int32_t)lroundf(h->baseline_f);
}

float coaster_min_cup_g(coaster_handle_t h)
{
    return h->min_cup_g;
}

float coaster_empty_cup_g(coaster_handle_t h)
{
    return h->cfg.empty_cup_g;
}

float coaster_full_cup_g(coaster_handle_t h)
{
    return h->cfg.full_cup_g;
}

bool coaster_have_last_stable(coaster_handle_t h)
{
    return h->have_last;
}

float coaster_last_stable_g(coaster_handle_t h)
{
    return h->last_stable_g;
}

void coaster_set_scale(coaster_handle_t h, float scale_counts_per_g)
{
    if (isfinite(scale_counts_per_g) && scale_counts_per_g > 0) {
        h->cfg.scale_counts_per_g = scale_counts_per_g;
        h->have_last = false;
        h->min_cup_g = 0;
        h->cfg.empty_cup_g = 0;
        h->cfg.full_cup_g = 0;
        h->state = COASTER_STATE_NO_CUP;
        h->above_cnt = h->below_cnt = h->migrate_cnt = 0;
        win_reset(h);
    }
}

void coaster_set_baseline(coaster_handle_t h, int32_t raw)
{
    /* 手动空载校准后，旧的稳定重量参考失去意义，防止错误结算 */
    h->baseline_f = (float)raw;
    h->have_last = false;
    h->min_cup_g = 0;
    h->cfg.empty_cup_g = 0;
    h->cfg.full_cup_g = 0;
    h->state = COASTER_STATE_NO_CUP;
    h->above_cnt = h->below_cnt = h->migrate_cnt = 0;
    win_reset(h);
}

void coaster_set_estimate_on_refill(coaster_handle_t h, bool enable)
{
    h->cfg.estimate_on_refill = enable;
}

bool coaster_set_cup_calibration(coaster_handle_t h, float empty_g, float full_g)
{
    if (!isfinite(empty_g) || !isfinite(full_g) || empty_g < 0 || empty_g > 5000 ||
        full_g < 0 || full_g > 8000 ||
        (full_g > 0 && (empty_g <= 0 || full_g < empty_g + 50))) {
        return false;
    }
    if (empty_g != h->cfg.empty_cup_g) {
        h->have_last = false;  /* 换杯或重新标定时不跨杯结算 */
    }
    h->cfg.empty_cup_g = empty_g;
    h->cfg.full_cup_g = full_g;
    return true;
}
