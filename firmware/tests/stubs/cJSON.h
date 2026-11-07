/* 宿主单测用的 cJSON 极简桩：只提供 protocol.c 需要的符号 */
#ifndef TEST_STUB_CJSON_H
#define TEST_STUB_CJSON_H

typedef struct cJSON {
    int dummy;
} cJSON;

cJSON *cJSON_Parse(const char *value);
void   cJSON_Delete(cJSON *item);

#endif /* TEST_STUB_CJSON_H */
