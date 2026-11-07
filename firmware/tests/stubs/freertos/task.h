/* 宿主单测用的 FreeRTOS task 桩 */
#ifndef TEST_STUB_TASK_H
#define TEST_STUB_TASK_H

typedef void *TaskHandle_t;

void vTaskDelay(int ticks);
void vTaskDelete(void *task);
int  xTaskCreate(void (*fn)(void *), const char *name, int stack_depth,
                 void *arg, int priority, TaskHandle_t *out_handle);

#endif /* TEST_STUB_TASK_H */
