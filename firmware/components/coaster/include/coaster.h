/*
 * 智能杯垫核心状态机
 *
 * 设计原则：用户零校准、零操作。
 *  - 喝水量 = 拿起前稳定重量 - 放回后稳定重量（差值法，与零点无关）
 *  - 空杯垫基线自学习：杯子被拿起时天然暴露空载，基线自动跟踪/学习
 *  - 空杯重自学习：历史最小稳定重量，用于"喝完续杯"场景的喝水量估算
 *
 * 状态机：
 *   NO_CUP  --放杯-->  SETTLING --稳定-->  STABLE
 *   NO_CUP  <--拿起--  SETTLING           STABLE --重量迁移(在位加水/吸管喝)--> SETTLING
 */
#ifndef COASTER_H
#define COASTER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    COASTER_STATE_NO_CUP = 0,   /*!< 杯垫上无杯 */
    COASTER_STATE_SETTLING,     /*!< 重量跳变后等待稳定 */
    COASTER_STATE_STABLE,       /*!< 杯子在位且重量稳定 */
} coaster_state_t;

typedef enum {
    COASTER_EVT_CUP_PLACED = 0, /*!< 杯子放上（weight_g 有效） */
    COASTER_EVT_CUP_REMOVED,    /*!< 杯子被拿起（weight_g 为拿起前重量） */
    COASTER_EVT_DRINK,          /*!< 确认喝水（drink_ml 有效；estimated=续杯估算值） */
    COASTER_EVT_REFILL,         /*!< 确认加水（refill_ml 有效） */
} coaster_event_type_t;

typedef struct {
    coaster_event_type_t type;
    float weight_g;     /*!< 当前（或拿起前）杯+水总重 */
    float drink_ml;     /*!< COASTER_EVT_DRINK: 本次喝水量(ml≈g) */
    float refill_ml;    /*!< COASTER_EVT_REFILL: 本次加水量 */
    bool  estimated;    /*!< DRINK 事件：true=续杯时按"已喝光"估算的值 */
} coaster_event_t;

typedef void (*coaster_event_cb_t)(const coaster_event_t *evt, void *user_ctx);

typedef struct {
    float    scale_counts_per_g;  /*!< HX711 校准系数（每克码值） */
    int32_t  baseline_raw;        /*!< 空杯垫基线 raw 初值（自学习会修正） */
    float    min_cup_g;           /*!< 历史最小带杯重量初值（<=0 表示未学习） */
    bool     have_last_stable;    /*!< 是否有上次稳定重量（NVS 恢复） */
    float    last_stable_g;       /*!< 上次稳定重量(g)，用于跨重启结算 */

    float    cup_present_g;       /*!< 判定有杯的重量阈值，建议 25g */
    float    stable_tol_g;        /*!< 稳定判据：窗口内极差，建议 4g */
    int      stable_window;       /*!< 稳定窗口采样数（~10Hz 采样，10≈1秒） */
    float    drink_thresh_g;      /*!< 喝水最小记账量，建议 5g */
    float    refill_thresh_g;     /*!< 加水最小记账量，建议 15g */
    bool     estimate_on_refill;  /*!< 续杯时是否按"已喝光"估算喝水量 */
} coaster_cfg_t;

typedef struct coaster *coaster_handle_t;

coaster_handle_t coaster_create(const coaster_cfg_t *cfg, coaster_event_cb_t cb, void *ctx);
void coaster_destroy(coaster_handle_t h);

/** 每个 HX711 原始采样喂一次（~10Hz），状态机内部完成滤波与事件判定 */
void coaster_feed(coaster_handle_t h, int32_t raw);

coaster_state_t coaster_state(coaster_handle_t h);
const char     *coaster_state_name(coaster_handle_t h);
float           coaster_weight_g(coaster_handle_t h);   /*!< 最近一次换算后的重量 */

/* 供持久化/状态上报读取 */
int32_t coaster_baseline_raw(coaster_handle_t h);
float   coaster_min_cup_g(coaster_handle_t h);
bool    coaster_have_last_stable(coaster_handle_t h);
float   coaster_last_stable_g(coaster_handle_t h);

/* 运行时配置修改（上位机命令） */
void coaster_set_scale(coaster_handle_t h, float scale_counts_per_g);
void coaster_set_baseline(coaster_handle_t h, int32_t raw);  /*!< 手动空载校准 */
void coaster_set_estimate_on_refill(coaster_handle_t h, bool enable);

#ifdef __cplusplus
}
#endif

#endif /* COASTER_H */
