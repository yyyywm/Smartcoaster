#include "storage.h"

#include <string.h>
#include "nvs.h"
#include "esp_log.h"
#include "esp_check.h"

static const char *TAG = "storage";

#define NVS_NAMESPACE   "coaster"

#define KEY_BASELINE    "baseline"
#define KEY_MINCUP      "mincup"
#define KEY_HAVE_LAST   "havelast"
#define KEY_LAST_G      "lastg"
#define KEY_SCALE       "scale"
#define KEY_REMIND      "remind"
#define KEY_EST_REFILL  "estrefill"

/* float 以位模式存 u32 */
static esp_err_t nvs_get_float(nvs_handle_t nvs, const char *key, float *out)
{
    uint32_t bits;
    esp_err_t err = nvs_get_u32(nvs, key, &bits);
    if (err == ESP_OK) {
        memcpy(out, &bits, sizeof(float));
    }
    return err;
}

static esp_err_t nvs_set_float(nvs_handle_t nvs, const char *key, float v)
{
    uint32_t bits;
    memcpy(&bits, &v, sizeof(float));
    return nvs_set_u32(nvs, key, bits);
}

esp_err_t storage_load(coaster_persist_t *out)
{
    memset(out, 0, sizeof(*out));
    out->estimate_on_refill = true;

    nvs_handle_t nvs;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (err != ESP_OK) {
        ESP_LOGI(TAG, "no saved state (first boot), err=%s", esp_err_to_name(err));
        return err;
    }

    uint8_t u8;
    /* 任一关键键缺失都视为无有效历史 */
    err = nvs_get_i32(nvs, KEY_BASELINE, &out->baseline_raw);
    if (err == ESP_OK) err = nvs_get_float(nvs, KEY_MINCUP, &out->min_cup_g);
    if (err == ESP_OK) err = nvs_get_float(nvs, KEY_LAST_G, &out->last_stable_g);
    if (err == ESP_OK) err = nvs_get_u8(nvs, KEY_HAVE_LAST, &u8);
    if (err == ESP_OK) out->have_last_stable = (u8 != 0);
    /* 配置项缺失不致命，用默认值由调用方兜底 */
    if (nvs_get_float(nvs, KEY_SCALE, &out->scale_counts_per_g) != ESP_OK) {
        out->scale_counts_per_g = 0;    /* 0 = 未设置 */
    }
    out->reminder_set = (nvs_get_u32(nvs, KEY_REMIND, &out->reminder_min) == ESP_OK);
    if (nvs_get_u8(nvs, KEY_EST_REFILL, &u8) == ESP_OK) {
        out->estimate_on_refill = (u8 != 0);
    }

    nvs_close(nvs);

    out->valid = (err == ESP_OK);
    ESP_LOGI(TAG, "load: valid=%d baseline=%" PRId32 " min_cup=%.1f have_last=%d last=%.1f",
             out->valid, out->baseline_raw, out->min_cup_g,
             out->have_last_stable, out->last_stable_g);
    return ESP_OK;
}

esp_err_t storage_save_state(int32_t baseline_raw, float min_cup_g,
                             bool have_last_stable, float last_stable_g)
{
    nvs_handle_t nvs;
    ESP_RETURN_ON_ERROR(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs), TAG, "nvs_open failed");

    esp_err_t err = nvs_set_i32(nvs, KEY_BASELINE, baseline_raw);
    if (err == ESP_OK) err = nvs_set_float(nvs, KEY_MINCUP, min_cup_g);
    if (err == ESP_OK) err = nvs_set_u8(nvs, KEY_HAVE_LAST, have_last_stable ? 1 : 0);
    if (err == ESP_OK) err = nvs_set_float(nvs, KEY_LAST_G, last_stable_g);
    if (err == ESP_OK) err = nvs_commit(nvs);

    nvs_close(nvs);
    return err;
}

esp_err_t storage_save_config(float scale_counts_per_g, uint32_t reminder_min,
                              bool estimate_on_refill)
{
    nvs_handle_t nvs;
    ESP_RETURN_ON_ERROR(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs), TAG, "nvs_open failed");

    esp_err_t err = nvs_set_float(nvs, KEY_SCALE, scale_counts_per_g);
    if (err == ESP_OK) err = nvs_set_u32(nvs, KEY_REMIND, reminder_min);
    if (err == ESP_OK) err = nvs_set_u8(nvs, KEY_EST_REFILL, estimate_on_refill ? 1 : 0);
    if (err == ESP_OK) err = nvs_commit(nvs);

    nvs_close(nvs);
    return err;
}
