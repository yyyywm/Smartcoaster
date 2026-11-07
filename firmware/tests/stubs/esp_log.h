/* 宿主单测用的 ESP_LOG 桩（variadic 安全，避免无参数时格式告警） */
#ifndef TEST_STUB_ESP_LOG_H
#define TEST_STUB_ESP_LOG_H

#include <stdio.h>

#define ESP_LOGE(tag, ...) do { printf("[E/%s] ", tag); printf(__VA_ARGS__); } while (0)
#define ESP_LOGW(tag, ...) do { printf("[W/%s] ", tag); printf(__VA_ARGS__); } while (0)
#define ESP_LOGI(tag, ...) do { printf("[I/%s] ", tag); printf(__VA_ARGS__); } while (0)
#define ESP_LOGD(...)      ((void)0)
#define ESP_LOGV(...)      ((void)0)

#endif /* TEST_STUB_ESP_LOG_H */
