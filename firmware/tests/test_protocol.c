/*
 * protocol 通信协议（JSON Lines）宿主单元测试
 *
 * 直接编译 components/coaster/protocol.c，把 stdout 重定向到内存缓冲，
 * 校验设备 → PC 的每一条 JSON 行与 README/协议文档完全一致。
 * 桩：cJSON / FreeRTOS task / ESP_LOG 由 tests/stubs 提供。
 */
#include "coaster.h"
#include "protocol.h"
#include "test_util.h"
#include "freertos/task.h"

#include <stdio.h>
#include <string.h>

/* ---------- protocol.c 需要的桩 ---------- */

cJSON *cJSON_Parse(const char *value)
{
    (void)value;
    return NULL;
}

void cJSON_Delete(cJSON *item)
{
    (void)item;
}

void vTaskDelay(int ticks) { (void)ticks; }
void vTaskDelete(void *task) { (void)task; }
int xTaskCreate(void (*fn)(void *), const char *name, int stack_depth,
                void *arg, int priority, TaskHandle_t *out_handle)
{
    (void)fn; (void)name; (void)stack_depth; (void)arg; (void)priority;
    (void)out_handle;
    return 0;
}

/* ---------- stdout 重定向到内存/管道 ---------- */

#define CAP_MAX 512

static char cap_buf[CAP_MAX];

#ifdef _WIN32
  #include <io.h>
  #define CAP_dup       _dup
  #define CAP_dup2      _dup2
  #define CAP_close     _close
  #define CAP_read(fd,b,n) _read((fd), (b), (n))
  static int cap_pipe_open(int fds[2]) { return _pipe(fds, 2048, 0); }
#else
  #include <unistd.h>
  #define CAP_dup       dup
  #define CAP_dup2      dup2
  #define CAP_close     close
  #define CAP_read(fd,b,n) read((fd), (b), (n))
  static int cap_pipe_open(int fds[2]) { return pipe(fds); }
#endif

static const char *capture(void (*fn)(void))
{
    int pipes[2] = { -1, -1 };
    cap_buf[0] = '\0';

    if (cap_pipe_open(pipes) != 0) {
        return cap_buf;
    }

    fflush(stdout);
    int saved = CAP_dup(1);
    CAP_dup2(pipes[1], 1);
    fn();
    fflush(stdout);
    CAP_dup2(saved, 1);
    CAP_close(saved);
    CAP_close(pipes[1]);

    int n = CAP_read(pipes[0], cap_buf, (int)sizeof(cap_buf) - 1);
    if (n > 0) {
        cap_buf[n] = '\0';
    } else {
        cap_buf[0] = '\0';
    }
    CAP_close(pipes[0]);
    return cap_buf;
}

/* ---------- 用例 ---------- */

static void send_cup_placed_helper(void)
{
    coaster_event_t evt = {
        .type = COASTER_EVT_CUP_PLACED,
        .weight_g = 350.2f,
    };
    protocol_send_event(&evt);
}

static void send_cup_removed_helper(void)
{
    coaster_event_t evt = {
        .type = COASTER_EVT_CUP_REMOVED,
        .weight_g = 348.7f,
    };
    protocol_send_event(&evt);
}

static void send_drink_estimated_helper(void)
{
    coaster_event_t evt = {
        .type = COASTER_EVT_DRINK,
        .weight_g = 202.2f,
        .drink_ml = 148.0f,
        .estimated = true,
    };
    protocol_send_event(&evt);
}

static void send_drink_plain_helper(void)
{
    coaster_event_t evt = {
        .type = COASTER_EVT_DRINK,
        .weight_g = 202.2f,
        .drink_ml = 148.0f,
        .estimated = false,
    };
    protocol_send_event(&evt);
}

static void send_refill_helper(void)
{
    coaster_event_t evt = {
        .type = COASTER_EVT_REFILL,
        .weight_g = 412.7f,
        .refill_ml = 210.5f,
    };
    protocol_send_event(&evt);
}

static void send_status_helper(void)
{
    protocol_send_status(350.2f, "stable", 450.0f, 3);
}

static void send_ack_ok_helper(void)
{
    protocol_send_ack("set_reminder", true);
}

static void send_ack_fail_helper(void)
{
    protocol_send_ack("set_reminder", false);
}

static void send_remind_helper(void)
{
    protocol_send_remind(46);
}

static void send_config_helper(void)
{
    protocol_send_config(384.70f, 45, false, 845123, 215.0f, 120.0f, 620.0f);
}

/* 边界：负 baseline_raw、0 提醒、关闭估算、负 min_cup_g */
static void send_config_boundary_helper(void)
{
    protocol_send_config(1.0f, 0, false, -2147483648, -99.9f, 0.0f, 0.0f);
}

/* 边界：大 since_drink_min（UINT32_MAX）、负 session_ml、非 stable 状态名 */
static void send_status_boundary_helper(void)
{
    protocol_send_status(0.0f, "settling", -1.0f, 4294967295u);
}

int main(void)
{
    TEST_CASE("protocol JSON Lines 逐条格式");
    {
        CHECK_STR(capture(send_cup_placed_helper),
                  "{\"event\":\"cup_placed\",\"weight_g\":350.2}\n",
                  "cup_placed JSON 行");

        CHECK_STR(capture(send_cup_removed_helper),
                  "{\"event\":\"cup_removed\",\"weight_g\":348.7}\n",
                  "cup_removed JSON 行");

        CHECK_STR(capture(send_drink_estimated_helper),
                  "{\"event\":\"drink\",\"ml\":148.0,\"estimated\":1,\"weight_g\":202.2}\n",
                  "drink(estimated=true) JSON 行");

        CHECK_STR(capture(send_drink_plain_helper),
                  "{\"event\":\"drink\",\"ml\":148.0,\"estimated\":0,\"weight_g\":202.2}\n",
                  "drink(estimated=false) JSON 行");

        CHECK_STR(capture(send_refill_helper),
                  "{\"event\":\"refill\",\"ml\":210.5,\"weight_g\":412.7}\n",
                  "refill JSON 行");

        CHECK_STR(capture(send_status_helper),
                  "{\"status\":{\"weight_g\":350.2,\"state\":\"stable\",\"session_ml\":450.0,"
                  "\"since_drink_min\":3}}\n",
                  "status JSON 行");

        CHECK_STR(capture(send_remind_helper),
                  "{\"event\":\"remind\",\"since_drink_min\":46}\n",
                  "remind JSON 行");

        CHECK_STR(capture(send_ack_ok_helper),
                  "{\"ack\":\"set_reminder\",\"ok\":1}\n",
                  "ack(ok=true) JSON 行");

        CHECK_STR(capture(send_ack_fail_helper),
                  "{\"ack\":\"set_reminder\",\"ok\":0}\n",
                  "ack(ok=false) JSON 行");

        CHECK_STR(capture(send_config_helper),
                  "{\"config\":{\"scale\":384.70,\"reminder_min\":45,"
                  "\"estimate_on_refill\":0,\"baseline_raw\":845123,"
                  "\"min_cup_g\":215.0,\"empty_cup_g\":120.0,\"full_cup_g\":620.0}}\n",
                  "config JSON 行");

        /* 边界：负 base line / UINT32_MAX / 负浮点 / 非法状态名 */
        CHECK_STR(capture(send_config_boundary_helper),
                  "{\"config\":{\"scale\":1.00,\"reminder_min\":0,"
                  "\"estimate_on_refill\":0,\"baseline_raw\":-2147483648,"
                  "\"min_cup_g\":-99.9,\"empty_cup_g\":0.0,\"full_cup_g\":0.0}}\n",
                  "config 边界 JSON 行");

        CHECK_STR(capture(send_status_boundary_helper),
                  "{\"status\":{\"weight_g\":0.0,\"state\":\"settling\",\"session_ml\":-1.0,"
                  "\"since_drink_min\":4294967295}}\n",
                  "status 边界 JSON 行");
    }

    return test_report();
}
