/*
 * 杯垫状态持久化（NVS Flash）
 *
 * 持久化内容：
 *  - 空载基线 baseline_raw（自学习结果，断电不丢）
 *  - 历史最小重量 min_cup_g（旧状态兼容）
 *  - 上次稳定重量 last_stable_g（跨重启也能结算喝水量）
 *  - 配置：校准系数、提醒间隔、空杯重和满杯重
 */
#ifndef COASTER_STORAGE_H
#define COASTER_STORAGE_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

typedef struct {
    bool     valid;              /* NVS 中是否已有历史数据（false=首次启动） */
    int32_t  baseline_raw;
    float    min_cup_g;
    float    empty_cup_g;
    float    full_cup_g;
    bool     have_last_stable;
    float    last_stable_g;
    float    scale_counts_per_g;
    uint32_t reminder_min;
    bool     reminder_set;       /* 区分未配置与显式关闭提醒（0） */
    bool     estimate_on_refill;
} coaster_persist_t;

esp_err_t storage_load(coaster_persist_t *out);
esp_err_t storage_save_state(int32_t baseline_raw, float min_cup_g,
                             bool have_last_stable, float last_stable_g);
esp_err_t storage_save_config(float scale_counts_per_g, uint32_t reminder_min,
                              bool estimate_on_refill, float empty_cup_g,
                              float full_cup_g);

#endif /* COASTER_STORAGE_H */
