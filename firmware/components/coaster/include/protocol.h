/*
 * 杯垫与上位机的通信协议（USB 串口，JSON Lines）
 *
 * 设备 → PC（每条一行 JSON，与 ESP_LOG 日志混排，上位机按 '{' 开头过滤）：
 *   {"event":"cup_placed","weight_g":350.2}
 *   {"event":"cup_removed","weight_g":350.2}
 *   {"event":"drink","ml":148.0,"estimated":0,"weight_g":202.2}
 *   {"event":"refill","ml":210.5,"weight_g":412.7}
 *   {"event":"remind","since_drink_min":46}
 *   {"status":{"weight_g":350.2,"state":"stable","session_ml":450.0,"since_drink_min":3}}
 *   {"ack":"set_reminder","ok":1}
 *   {"config":{...}}
 *
 * PC → 设备（一行一个 JSON，以 \n 结尾）：
 *   {"cmd":"set_reminder","minutes":45}
 *   {"cmd":"set_scale","value":384.7}
 *   {"cmd":"set_cup_calibration","empty_g":120.0,"full_g":620.0}
 *   {"cmd":"calibrate_empty"}      // 空杯垫时调用，手动校准基线
 *   {"cmd":"get_config"}
 */
#ifndef COASTER_PROTOCOL_H
#define COASTER_PROTOCOL_H

#include <stdint.h>
#include "coaster.h"
#include "cJSON.h"

typedef void (*protocol_cmd_cb_t)(const cJSON *root, void *ctx);

void protocol_send_event(const coaster_event_t *evt);
void protocol_send_remind(uint32_t since_drink_min);
void protocol_send_status(float weight_g, const char *state,
                          float session_ml, uint32_t since_drink_min);
void protocol_send_ack(const char *cmd, bool ok);
void protocol_send_config(float scale, uint32_t reminder_min, bool estimate_on_refill,
                          int32_t baseline_raw, float min_cup_g,
                          float empty_cup_g, float full_cup_g);

/** 创建串口命令接收任务（stdin 行读 + cJSON 解析），命令通过回调分发 */
void protocol_start_rx(protocol_cmd_cb_t cb, void *ctx);

#endif /* COASTER_PROTOCOL_H */
