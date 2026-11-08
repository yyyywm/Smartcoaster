/*
 * 智能杯垫固件 — ESP32-C3 + HX711
 *
 * 功能：
 *  - 差值法统计每次喝水量（拿起前稳定重量 - 放回后稳定重量）
 *  - 长时间未喝水 → 上报提醒事件（间隔可由上位机配置）
 *  - 空载基线自学习；可由上位机标定空杯和满杯重量
 *  - NVS 持久化：断电续接，跨重启仍可结算喝水量
 *  - USB 串口 JSON Lines 协议与上位机通信（见 components/coaster/include/protocol.h）
 *
 * 接线：
 *  - HX711 DOUT(DT) -> GPIO4, SCK -> GPIO5, VCC -> 3.3V, GND -> GND
 */
#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include <math.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "hx711.h"
#include "coaster.h"
#include "storage.h"
#include "protocol.h"

static const char *TAG = "coaster";

/* ---------- 默认参数（NVS 中有历史配置时以 NVS 为准） ---------- */
#define DEFAULT_SCALE_COUNTS_PER_G    384.7f   /* 校准系数（每克码值） */
#define DEFAULT_REMINDER_MIN          45       /* 喝水提醒间隔（分钟） */
#define CUP_PRESENT_G                 25.0f    /* 有杯判定阈值 */
#define STABLE_TOL_G                  4.0f     /* 稳定窗口极差阈值 */
#define STABLE_WINDOW                 10       /* 稳定窗口采样数（~10Hz，≈1秒） */
#define DRINK_THRESH_G                5.0f     /* 喝水最小记账量 */
#define REFILL_THRESH_G               15.0f    /* 加水最小记账量 */

#define STATUS_EVERY_SAMPLES          20       /* 每 ~2s 广播一次状态 */
#define REMIND_CHECK_SAMPLES          10       /* 每 ~1s 检查一次提醒 */
#define BASELINE_SAVE_INTERVAL_US     (15LL * 60 * 1000000)
#define BASELINE_SAVE_DELTA_G         10.0f

static coaster_handle_t s_coaster;
static SemaphoreHandle_t s_state_mutex;
static float    s_scale = DEFAULT_SCALE_COUNTS_PER_G;
static uint32_t s_reminder_min = DEFAULT_REMINDER_MIN;
static bool     s_estimate_on_refill = false;  /* 旧协议字段，始终关闭 */

static float    s_session_ml = 0;              /* 本次上电累计喝水量 */
static int64_t  s_last_drink_us;               /* 上次喝水时间（上电即重置） */
static int64_t  s_last_remind_us;
static int32_t  s_last_raw;                    /* 最近采样（供 calibrate_empty 用） */
static int32_t  s_saved_baseline_raw;          /* 最近写入 NVS 的空载基线 */
static int64_t  s_last_baseline_save_us;

/** 把当前状态机内部量存入 NVS */
static esp_err_t persist_state(void)
{
    return storage_save_state(coaster_baseline_raw(s_coaster),
                              coaster_min_cup_g(s_coaster),
                              coaster_have_last_stable(s_coaster),
                              coaster_last_stable_g(s_coaster));
}

static esp_err_t persist_config(void)
{
    return storage_save_config(s_scale, s_reminder_min, s_estimate_on_refill,
                               coaster_empty_cup_g(s_coaster),
                               coaster_full_cup_g(s_coaster));
}

/** 状态机事件 → 串口上报 + 提醒计时维护 */
static void on_coaster_event(const coaster_event_t *evt, void *ctx)
{
    protocol_send_event(evt);

    if (evt->type == COASTER_EVT_DRINK) {
        s_session_ml += evt->drink_ml;
        s_last_drink_us = esp_timer_get_time();
        ESP_LOGI(TAG, "drink %.1f ml (estimated=%d), session total %.1f ml",
                 evt->drink_ml, evt->estimated, s_session_ml);
    }
}

/** 上位机命令处理 */
static void on_command(const cJSON *root, void *ctx)
{
    const cJSON *cmd = cJSON_GetObjectItem(root, "cmd");
    if (!cJSON_IsString(cmd)) {
        return;
    }
    const char *c = cmd->valuestring;
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);

    if (strcmp(c, "set_reminder") == 0) {
        const cJSON *min = cJSON_GetObjectItem(root, "minutes");
        if (cJSON_IsNumber(min) && isfinite(min->valuedouble) &&
            min->valuedouble >= 0 && min->valuedouble <= UINT32_MAX &&
            floor(min->valuedouble) == min->valuedouble) {
            s_reminder_min = (uint32_t)min->valuedouble;
            persist_config();
            ESP_LOGI(TAG, "reminder set to %" PRIu32 " min", s_reminder_min);
            protocol_send_ack(c, true);
        } else {
            protocol_send_ack(c, false);
        }
    } else if (strcmp(c, "set_scale") == 0) {
        const cJSON *v = cJSON_GetObjectItem(root, "value");
        if (cJSON_IsNumber(v) && isfinite(v->valuedouble) &&
            v->valuedouble > 0 && v->valuedouble <= 1000000.0) {
            s_scale = (float)v->valuedouble;
            coaster_set_scale(s_coaster, s_scale);
            persist_state();
            persist_config();
            ESP_LOGI(TAG, "scale set to %.2f", s_scale);
            protocol_send_ack(c, true);
        } else {
            protocol_send_ack(c, false);
        }
    } else if (strcmp(c, "estimate_on_refill") == 0) {
        protocol_send_ack(c, false);  /* 无法由补水后的重量推断期间饮水量 */
    } else if (strcmp(c, "calibrate_empty") == 0) {
        /* 用户已确认杯垫空载；旧基线误判为有杯时也必须允许恢复。 */
        coaster_set_baseline(s_coaster, s_last_raw);
        bool ok = (persist_state() == ESP_OK && persist_config() == ESP_OK);
        if (ok) {
            s_saved_baseline_raw = coaster_baseline_raw(s_coaster);
            s_last_baseline_save_us = esp_timer_get_time();
            ESP_LOGI(TAG, "manual baseline calibrate: %" PRId32, s_last_raw);
        }
        protocol_send_ack(c, ok);
    } else if (strcmp(c, "set_cup_calibration") == 0) {
        const cJSON *empty = cJSON_GetObjectItem(root, "empty_g");
        const cJSON *full = cJSON_GetObjectItem(root, "full_g");
        bool ok = cJSON_IsNumber(empty) && cJSON_IsNumber(full) &&
                  coaster_set_cup_calibration(s_coaster, (float)empty->valuedouble,
                                              (float)full->valuedouble);
        if (ok) {
            ok = (persist_state() == ESP_OK && persist_config() == ESP_OK);
        }
        protocol_send_ack(c, ok);
    } else if (strcmp(c, "get_config") == 0) {
        protocol_send_config(s_scale, s_reminder_min, s_estimate_on_refill,
                             coaster_baseline_raw(s_coaster),
                             coaster_min_cup_g(s_coaster),
                             coaster_empty_cup_g(s_coaster),
                             coaster_full_cup_g(s_coaster));
    } else {
        protocol_send_ack(c, false);
    }
    xSemaphoreGive(s_state_mutex);
}

void app_main(void)
{
    ESP_LOGI(TAG, "smart coaster starting");

    /* NVS */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    /* 恢复持久化状态 */
    coaster_persist_t persist;
    storage_load(&persist);
    if (persist.scale_counts_per_g > 0) {
        s_scale = persist.scale_counts_per_g;
    }
    if (persist.reminder_set) {
        s_reminder_min = persist.reminder_min;
    }
    s_estimate_on_refill = false;

    /* HX711 */
    ESP_ERROR_CHECK(hx711_init(HX711_GAIN_128));

    /* 首次启动无基线：先用当前读数当初值，自学习会在杯子被拿起时自动修正 */
    int32_t first_raw = 0;
    while (hx711_read_average(&first_raw, 5) != ESP_OK) {
        ESP_LOGW(TAG, "HX711 not responding, check wiring (DOUT=GPIO%d, SCK=GPIO%d)",
                 CONFIG_HX711_GPIO_DOUT, CONFIG_HX711_GPIO_SCK);
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    s_last_raw = first_raw;

    float saved_empty = persist.valid && isfinite(persist.empty_cup_g) &&
                        persist.empty_cup_g > 0 && persist.empty_cup_g <= 5000
                        ? persist.empty_cup_g : 0;
    float saved_full = saved_empty > 0 && isfinite(persist.full_cup_g) &&
                       persist.full_cup_g >= saved_empty + 50 &&
                       persist.full_cup_g <= 8000 ? persist.full_cup_g : 0;

    coaster_cfg_t cfg = {
        .scale_counts_per_g = s_scale,
        .baseline_raw   = persist.valid ? persist.baseline_raw : first_raw,
        .min_cup_g      = persist.valid ? persist.min_cup_g : 0,
        .empty_cup_g    = saved_empty,
        .full_cup_g     = saved_full,
        .have_last_stable = persist.valid && persist.have_last_stable,
        .last_stable_g  = persist.last_stable_g,
        .cup_present_g  = CUP_PRESENT_G,
        .stable_tol_g   = STABLE_TOL_G,
        .stable_window  = STABLE_WINDOW,
        .drink_thresh_g = DRINK_THRESH_G,
        .refill_thresh_g = REFILL_THRESH_G,
        .estimate_on_refill = s_estimate_on_refill,
    };
    s_coaster = coaster_create(&cfg, on_coaster_event, NULL);
    if (s_coaster == NULL) {
        ESP_LOGE(TAG, "coaster_create failed");
        return;
    }

    s_last_drink_us = esp_timer_get_time();
    s_last_remind_us = s_last_drink_us;
    s_saved_baseline_raw = coaster_baseline_raw(s_coaster);
    s_last_baseline_save_us = s_last_drink_us;

    s_state_mutex = xSemaphoreCreateMutex();
    if (s_state_mutex == NULL) {
        ESP_LOGE(TAG, "state mutex allocation failed");
        return;
    }
    protocol_start_rx(on_command, NULL);
    ESP_LOGI(TAG, "ready. reminder=%" PRIu32 "min scale=%.2f", s_reminder_min, s_scale);

    /* 采样主循环：hx711_read_raw 阻塞等待转换完成，天然 ~10Hz 节拍 */
    uint32_t sample = 0;
    while (1) {
        int32_t raw;
        if (hx711_read_raw(&raw) != ESP_OK) {
            ESP_LOGW(TAG, "HX711 read timeout");
            vTaskDelay(pdMS_TO_TICKS(200));
            continue;
        }
        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
        s_last_raw = raw;
        coaster_state_t previous_state = coaster_state(s_coaster);
        coaster_feed(s_coaster, raw);
        /* settle() emits events before it updates its stable reference. Save only
         * after the feed returns, including quiet settles with no event. */
        if (previous_state == COASTER_STATE_SETTLING &&
            coaster_state(s_coaster) == COASTER_STATE_STABLE) {
            if (persist_state() == ESP_OK) {
                s_saved_baseline_raw = coaster_baseline_raw(s_coaster);
            }
        }
        /* 空载慢速跟漂也要定期持久化，避免重启后恢复过旧零点。 */
        int64_t now_us = esp_timer_get_time();
        if (coaster_state(s_coaster) == COASTER_STATE_NO_CUP &&
            now_us - s_last_baseline_save_us >= BASELINE_SAVE_INTERVAL_US) {
            int32_t current_baseline = coaster_baseline_raw(s_coaster);
            if (fabsf((float)((int64_t)current_baseline - s_saved_baseline_raw) / s_scale)
                    >= BASELINE_SAVE_DELTA_G && persist_state() == ESP_OK) {
                s_saved_baseline_raw = current_baseline;
            }
            s_last_baseline_save_us = now_us;
        }
        xSemaphoreGive(s_state_mutex);
        sample++;

        /* 定期状态广播（上位机实时显示） */
        if (sample % STATUS_EVERY_SAMPLES == 0) {
            xSemaphoreTake(s_state_mutex, portMAX_DELAY);
            uint32_t since_min = (uint32_t)((esp_timer_get_time() - s_last_drink_us) / 60000000LL);
            protocol_send_status(coaster_weight_g(s_coaster),
                                 coaster_state_name(s_coaster),
                                 s_session_ml, since_min);
            xSemaphoreGive(s_state_mutex);
        }

        /* 喝水提醒检查：距上次喝水超过阈值 → 上报提醒（重复间隔=提醒间隔） */
        if (s_reminder_min > 0 && sample % REMIND_CHECK_SAMPLES == 0) {
            int64_t now = esp_timer_get_time();
            int64_t interval_us = (int64_t)s_reminder_min * 60 * 1000000LL;
            if (now - s_last_drink_us > interval_us &&
                now - s_last_remind_us > interval_us) {
                s_last_remind_us = now;
                uint32_t since_min = (uint32_t)((now - s_last_drink_us) / 60000000LL);
                ESP_LOGI(TAG, "remind: %" PRIu32 " min since last drink", since_min);
                protocol_send_remind(since_min);
            }
        }
    }
}
