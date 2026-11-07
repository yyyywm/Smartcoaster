idf_component_register(SRCS "coaster.c" "storage.c" "protocol.c"
                       INCLUDE_DIRS "include"
                       REQUIRES nvs_flash json esp_timer)
