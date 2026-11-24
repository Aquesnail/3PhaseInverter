/**
 * @file    stats_uart.c
 * @brief   分环节耗时统计 -> USART1（115200-8N1）打印
 *
 * 数据来源：droop_control.c 的 g_cyc[ST_NUM][3]（DWT->CYCCNT 累计/最大/次数）
 * 发送方式：直接轮询 USART1 寄存器（不依赖 HAL_GetTick，避免 SysTick 被饿死时死等）
 *
 * 注意：如果在主循环打印且 CPU 被中断占满（uwTick 不涨），就看不到输出，
 *       此时把 STATS_PRINT_IN_ISR 改成 1（从 ISR 打印）即可拿到数据。
 */
#include "stats_uart.h"
#include "droop_control.h"
#include "main.h"

extern volatile uint32_t g_isr_count;

#define LINE_MAX 96

static char     s_line[LINE_MAX];
static uint16_t s_len;
static uint32_t s_last_isr;

static const char *const k_name[ST_NUM] =
{
  "PRE   ", "SOGI  ", "DROOP ", "QPR   ", "CURR  ", "PWM   "
};

/* ---------------- 寄存器级 USART1 发送（无 tick 依赖） ---------------- */

static void uart_send(const char *p, uint16_t n)
{
  for (uint16_t i = 0u; i < n; i++)
  {
    uint32_t guard = 0u;
    while (((USART1->ISR & USART_ISR_TXE_TXFNF) == 0u) && (guard++ < 200000u)) { }
    if (guard >= 200000u) { return; }
    USART1->TDR = (uint8_t)p[i];
  }
  uint32_t guard = 0u;
  while (((USART1->ISR & USART_ISR_TC) == 0u) && (guard++ < 200000u)) { }
}

/* ---------------- 简易格式化 ---------------- */

static void app_str(const char *s)
{
  while ((*s != '\0') && (s_len < (LINE_MAX - 1u))) { s_line[s_len++] = *s++; }
}

static void app_u32(uint32_t v)
{
  char t[10];
  int  n = 0;
  do { t[n++] = (char)('0' + (v % 10u)); v /= 10u; } while (v != 0u);
  while (n > 0)
  {
    if (s_len >= (LINE_MAX - 1u)) { break; }
    s_line[s_len++] = t[--n];
  }
}

static void app_u32_pad(uint32_t v, int width)
{
  uint32_t d = 1u, w = 1u;
  while ((v / d) >= 10u) { d *= 10u; w++; }
  while (w < (uint32_t)width)
  {
    if (s_len >= (LINE_MAX - 1u)) { break; }
    s_line[s_len++] = ' ';
    w++;
  }
  app_u32(v);
}

static void flush_line(void)
{
  if (s_len > 0u) { uart_send(s_line, s_len); s_len = 0u; }
}

/* ---------------- 打印一个窗口 ---------------- */

static void stats_print_window(uint32_t win, const uint32_t snap[ST_NUM][3])
{
  s_len = 0u;
  app_str("\r\n--- stage cycles @170MHz, window ISR=");
  app_u32(win);
  app_str(" ---\r\n");
  flush_line();

  uint32_t sum_max = 0u;
  for (uint32_t i = 0u; i < (uint32_t)ST_NUM; i++)
  {
    uint32_t runs = snap[i][2];
    uint32_t avg  = (runs != 0u) ? (snap[i][0] / runs) : 0u;

    s_len = 0u;
    app_str(k_name[i]);
    app_str(" mx=");
    app_u32_pad(snap[i][1], 6);
    app_str(" av=");
    app_u32_pad(avg, 6);
    app_str(" -> ");
    app_u32_pad(snap[i][1] / 170u, 3);
    app_str(" us  n=");
    app_u32(snap[i][2]);
    app_str("\r\n");
    flush_line();

    sum_max += snap[i][1];
  }

  s_len = 0u;
  app_str("SUM   mx=");
  app_u32_pad(sum_max, 6);
  app_str(" -> ");
  app_u32_pad(sum_max / 170u, 3);
  app_str(" us  (budget 20us @50kHz / 50us @20kHz)\r\n");
  flush_line();
}

/* ---------------- 对外接口 ---------------- */

void Stats_Task(void)
{
  if ((g_isr_count - s_last_isr) < STATS_WINDOW_ISR) { return; }

  uint32_t snap[ST_NUM][3];

  __disable_irq();
  for (uint32_t i = 0u; i < (uint32_t)ST_NUM; i++)
  {
    snap[i][0] = g_cyc[i][0];
    snap[i][1] = g_cyc[i][1];
    snap[i][2] = g_cyc[i][2];
    g_cyc[i][0] = 0u;
    g_cyc[i][1] = 0u;
    g_cyc[i][2] = 0u;
  }
  uint32_t win = g_isr_count - s_last_isr;
  s_last_isr = g_isr_count;
  __enable_irq();

  stats_print_window(win, snap);
}

void Stats_TaskISR(void)
{
  if ((g_isr_count - s_last_isr) < STATS_WINDOW_ISR) { return; }

  uint32_t snap[ST_NUM][3];

  for (uint32_t i = 0u; i < (uint32_t)ST_NUM; i++)
  {
    snap[i][0] = g_cyc[i][0];
    snap[i][1] = g_cyc[i][1];
    snap[i][2] = g_cyc[i][2];
    g_cyc[i][0] = 0u;
    g_cyc[i][1] = 0u;
    g_cyc[i][2] = 0u;
  }
  uint32_t win = g_isr_count - s_last_isr;
  s_last_isr = g_isr_count;

  stats_print_window(win, snap);
}
