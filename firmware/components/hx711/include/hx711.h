/*
 * HX711 24-bit load cell ADC driver for ESP32-C3 (ESP-IDF)
 *
 * Protocol reference: AVIA Semiconductor HX711 datasheet
 *  - DOUT high  : converter not ready, PD_SCK must stay low
 *  - DOUT low   : 24-bit data ready, MSB first, two's complement
 *  - 25/26/27 extra PD_SCK pulses select next conversion channel/gain:
 *        25 -> channel A, gain 128
 *        26 -> channel B, gain 32
 *        27 -> channel A, gain 64
 *  - PD_SCK high for more than 60us powers the chip down
 */
#ifndef HX711_H
#define HX711_H

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/** Channel/gain selection, encoded as the required number of PD_SCK pulses */
typedef enum {
    HX711_GAIN_128 = 25,    /*!< Channel A, gain 128 (default) */
    HX711_GAIN_32  = 26,    /*!< Channel B, gain 32  */
    HX711_GAIN_64  = 27,    /*!< Channel A, gain 64  */
} hx711_gain_t;

/**
 * @brief Initialize GPIOs used by the HX711 (DOUT input, PD_SCK output).
 *
 * @param gain  Channel/gain to select after every conversion.
 * @return ESP_OK on success.
 */
esp_err_t hx711_init(hx711_gain_t gain);

/**
 * @brief Check whether a new conversion result is available (DOUT low).
 */
bool hx711_is_ready(void);

/**
 * @brief Read one raw 24-bit signed conversion result.
 *
 * Blocks until DOUT goes low (timeout: CONFIG_HX711_READ_TIMEOUT_MS),
 * then clocks out 24 bits plus the extra pulses for the configured gain.
 *
 * @param[out] value  Signed 24-bit ADC value (sign-extended to int32_t).
 * @return ESP_OK, or ESP_ERR_TIMEOUT if the chip never became ready.
 */
esp_err_t hx711_read_raw(int32_t *value);

/**
 * @brief Read the arithmetic average of @p times raw conversions.
 */
esp_err_t hx711_read_average(int32_t *value, uint8_t times);

/**
 * @brief Power down the HX711 (PD_SCK high > 60us). Stops conversions.
 */
void hx711_power_down(void);

/**
 * @brief Power the HX711 back up (PD_SCK low). The next read uses the
 *        gain set by hx711_init(); the first result after power-up
 *        should be discarded.
 */
void hx711_power_up(void);

#ifdef __cplusplus
}
#endif

#endif /* HX711_H */
