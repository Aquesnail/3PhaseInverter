/**
 * @file    stimulus.h
 * @brief   无硬件时的合成三相正弦激励（50 Hz，50 kHz 采样 -> 每周期 1000 点）
 *
 * 用途：把 ADC 采样替换成本地合成信号，使 ISR 里的计算量与真实工况一致，
 *       而 ISR 之外不引入额外测量开销。
 *
 * 幅值取模型 InitFcn 的工况：相电压峰值 E0 = 20 V，电流峰值 5 A。
 */
#ifndef __STIMULUS_H
#define __STIMULUS_H

#include <stdint.h>

/** @brief 生成正弦表并复位相位（main 里调用一次，用 sinf 计算，不进 ISR） */
void STIM_Init(void);

/** @brief 推进一个采样点并刷新下面 4 组缓冲（ISR 里、PA8 打点窗口之外调用） */
void STIM_Next(void);

/* 供 ISR 读取的合成激励（每周期更新一次） */
extern float g_stim_vcap_line[3];   /* 电容侧线电压 [Uab Ubc Uac] */
extern float g_stim_vgrid_line[3];  /* 网侧线电压   [Uab Ubc Uac] */
extern float g_stim_i1[3];          /* 逆变侧电流   [ia ib ic]     */
extern float g_stim_i2[3];          /* 输出侧电流   [ia ib ic]     */

/** @brief 当前激励相位索引（0..999），调试用 */
extern uint16_t g_stim_index;

#endif /* __STIMULUS_H */
