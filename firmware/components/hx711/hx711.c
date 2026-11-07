/*
 * HX711 24-bit load cell ADC driver for ESP32-C3 (ESP-IDF)
 */
#include "hx711.h"

#include "sdkconfig.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "hx711";

#define HX711_DOUT_GPIO   ((gpio_num_t)CONFIG_HX711_GPIO_DOUT)
#define HX711_SCK_GPIO    ((gpio_num_t)CONFIG_HX711_GPIO_SCK)

/*
 * Datasheet timing: PD_SCK high/low pulse width >= 0.2us.
 * 1us is safe and well within the chip's limits, while keeping
 * a full 24+3 clock read well below the 60us power-down threshold
 * is NOT required — the threshold applies to a single continuous
 * high level of PD_SCK, and each pulse here is only ~1us wide.
 */
#define HX711_HALF_CLOCK_US   1

static hx711_gain_t s_gain = HX711_GAIN_128;
static portMUX_TYPE s_clock_mux = portMUX_INITIALIZER_UNLOCKED;

esp_err_t hx711_init(hx711_gain_t gain)
{
    s_gain = gain;

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << HX711_SCK_GPIO),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "SCK gpio_config failed: %s", esp_err_to_name(ret));
        return ret;
    }
    /* PD_SCK must be low while the converter is idle */
    gpio_set_level(HX711_SCK_GPIO, 0);

    io_conf.pin_bit_mask = (1ULL << HX711_DOUT_GPIO);
    io_conf.mode = GPIO_MODE_INPUT;
    /* Weak pull-up so a disconnected module reads as "not ready"
     * instead of producing garbage conversions. */
    io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
    ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "DOUT gpio_config failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "initialized: DOUT=GPIO%d, PD_SCK=GPIO%d, gain pulses=%d",
             CONFIG_HX711_GPIO_DOUT, CONFIG_HX711_GPIO_SCK, (int)s_gain);
    return ESP_OK;
}

bool hx711_is_ready(void)
{
    /* DOUT low => conversion result ready to be read */
    return gpio_get_level(HX711_DOUT_GPIO) == 0;
}

esp_err_t hx711_read_raw(int32_t *value)
{
    if (value == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Wait for DOUT to go low (data ready). At the default 10 SPS rate a
     * new result arrives at most ~100ms after the previous read.
     * NOTE: use esp_timer for the timeout — pdMS_TO_TICKS(1) rounds down
     * to 0 at the default 100Hz tick rate, so a per-ms vTaskDelay loop
     * would not actually wait at all. */
    int64_t deadline = esp_timer_get_time() + (int64_t)CONFIG_HX711_READ_TIMEOUT_MS * 1000;
    while (!hx711_is_ready()) {
        if (esp_timer_get_time() >= deadline) {
            ESP_LOGW(TAG, "timeout waiting for DOUT low (chip not ready?)");
            return ESP_ERR_TIMEOUT;
        }
        vTaskDelay(1);  /* 1 tick (10ms @ 100Hz) — well below the 100ms conversion period */
    }

    uint32_t raw = 0;

    /* A task switch while SCK is high can exceed the 60us power-down
     * threshold and corrupt the conversion. Keep the clock train atomic. */
    taskENTER_CRITICAL(&s_clock_mux);

    /* 24 data bits, MSB first */
    for (int i = 0; i < 24; i++) {
        gpio_set_level(HX711_SCK_GPIO, 1);
        esp_rom_delay_us(HX711_HALF_CLOCK_US);
        raw = (raw << 1) | (uint32_t)gpio_get_level(HX711_DOUT_GPIO);
        gpio_set_level(HX711_SCK_GPIO, 0);
        esp_rom_delay_us(HX711_HALF_CLOCK_US);
    }

    /* Extra pulses select the channel/gain of the NEXT conversion */
    for (int i = 0; i < (int)s_gain - 24; i++) {
        gpio_set_level(HX711_SCK_GPIO, 1);
        esp_rom_delay_us(HX711_HALF_CLOCK_US);
        gpio_set_level(HX711_SCK_GPIO, 0);
        esp_rom_delay_us(HX711_HALF_CLOCK_US);
    }
    taskEXIT_CRITICAL(&s_clock_mux);

    /* Convert 24-bit two's complement to signed 32-bit */
    if (raw & 0x00800000UL) {
        raw |= 0xFF000000UL;
    }
    *value = (int32_t)raw;
    return ESP_OK;
}

esp_err_t hx711_read_average(int32_t *value, uint8_t times)
{
    if (value == NULL || times == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    int64_t sum = 0;
    for (uint8_t i = 0; i < times; i++) {
        int32_t v;
        esp_err_t ret = hx711_read_raw(&v);
        if (ret != ESP_OK) {
            return ret;
        }
        sum += v;
    }
    *value = (int32_t)(sum / times);
    return ESP_OK;
}

void hx711_power_down(void)
{
    /* PD_SCK held high for more than 60us powers the chip down */
    gpio_set_level(HX711_SCK_GPIO, 1);
    esp_rom_delay_us(80);
}

void hx711_power_up(void)
{
    gpio_set_level(HX711_SCK_GPIO, 0);
    esp_rom_delay_us(10);
}
