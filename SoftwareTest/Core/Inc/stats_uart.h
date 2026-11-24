/**
 * @file    stats_uart.h
 * @brief   各环节耗时统计 -> USART1 打印
 *
 * 打印位置可切换：
 *   STATS_PRINT_IN_ISR = 0 : 在主循环里打印（推荐；但 CPU 被中断占满时会被饿死）
 *   STATS_PRINT_IN_ISR = 1 : 在中断末尾每 N 次打印一次（保证有输出，仅测量用，
 *                            打印期间会丢掉若干次触发/拉长一次 PA8 脉宽）
 */
#ifndef __STATS_UART_H
#define __STATS_UART_H

/** 统计窗口（每累计多少个 ISR 打印一次） */
#ifndef STATS_WINDOW_ISR
#define STATS_WINDOW_ISR   20000u
#endif

/** 打印位置：0 = 主循环（cpu 有余量时可用）；1 = 中断里（cpu 被占满时备用） */
#ifndef STATS_PRINT_IN_ISR
#define STATS_PRINT_IN_ISR 0
#endif

/** @brief 主循环里调用（未到窗口立即返回，非阻塞） */
void Stats_Task(void);

/** @brief 中断末尾调用（仅 STATS_PRINT_IN_ISR=1 时使用） */
void Stats_TaskISR(void);

#endif /* __STATS_UART_H */
