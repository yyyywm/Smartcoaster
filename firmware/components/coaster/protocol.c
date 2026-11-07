#include "protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"

static const char *TAG = "protocol";

void protocol_send_event(const coaster_event_t *evt)
{
    switch (evt->type) {
    case COASTER_EVT_CUP_PLACED:
        printf("{\"event\":\"cup_placed\",\"weight_g\":%.1f}\n", evt->weight_g);
        break;
    case COASTER_EVT_CUP_REMOVED:
        printf("{\"event\":\"cup_removed\",\"weight_g\":%.1f}\n", evt->weight_g);
        break;
    case COASTER_EVT_DRINK:
        printf("{\"event\":\"drink\",\"ml\":%.1f,\"estimated\":%d,\"weight_g\":%.1f}\n",
               evt->drink_ml, evt->estimated ? 1 : 0, evt->weight_g);
        break;
    case COASTER_EVT_REFILL:
        printf("{\"event\":\"refill\",\"ml\":%.1f,\"weight_g\":%.1f}\n",
               evt->refill_ml, evt->weight_g);
        break;
    }
}

void protocol_send_remind(uint32_t since_drink_min)
{
    printf("{\"event\":\"remind\",\"since_drink_min\":%" PRIu32 "}\n", since_drink_min);
}

void protocol_send_status(float weight_g, const char *state,
                          float session_ml, uint32_t since_drink_min)
{
    printf("{\"status\":{\"weight_g\":%.1f,\"state\":\"%s\",\"session_ml\":%.1f,"
           "\"since_drink_min\":%" PRIu32 "}}\n",
           weight_g, state, session_ml, since_drink_min);
}

void protocol_send_ack(const char *cmd, bool ok)
{
    printf("{\"ack\":\"%s\",\"ok\":%d}\n", cmd, ok ? 1 : 0);
}

void protocol_send_config(float scale, uint32_t reminder_min, bool estimate_on_refill,
                          int32_t baseline_raw, float min_cup_g)
{
    printf("{\"config\":{\"scale\":%.2f,\"reminder_min\":%" PRIu32
           ",\"estimate_on_refill\":%d,\"baseline_raw\":%" PRId32
           ",\"min_cup_g\":%.1f}}\n",
           scale, reminder_min, estimate_on_refill ? 1 : 0, baseline_raw, min_cup_g);
}

/* ---------- 命令接收 ---------- */

#define RX_LINE_MAX     256
#define RX_TASK_STACK   4096
#define RX_TASK_PRIO    5

static protocol_cmd_cb_t s_cmd_cb;
static void *s_cmd_ctx;

static void rx_task(void *arg)
{
    (void)arg;
    char *line = malloc(RX_LINE_MAX);
    if (line == NULL) {
        ESP_LOGE(TAG, "rx buffer alloc failed");
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        if (fgets(line, RX_LINE_MAX, stdin) == NULL) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }
        cJSON *root = cJSON_Parse(line);
        if (root == NULL) {
            /* 非 JSON 行：忽略（可能是日志或杂散输入） */
            continue;
        }
        if (s_cmd_cb) {
            s_cmd_cb(root, s_cmd_ctx);
        }
        cJSON_Delete(root);
    }
}

void protocol_start_rx(protocol_cmd_cb_t cb, void *ctx)
{
    s_cmd_cb = cb;
    s_cmd_ctx = ctx;
    xTaskCreate(rx_task, "proto_rx", RX_TASK_STACK, NULL, RX_TASK_PRIO, NULL);
}
