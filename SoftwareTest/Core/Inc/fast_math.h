/**
 * @file    fast_math.h
 * @brief   CORDIC 加速的三角函数接口（STM32G4 CORDIC 协处理器）
 *
 * 供 DSOGI-FLL / 下垂控制使用：
 *   - FM_Atan2(y, x)      : atan2，返回弧度（Q1.31 + CORDIC PHASE）
 *   - FM_SinCos(th, &s,&c): 一次调用同时得到 sin / cos（Q1.31 + CORDIC SINE）
 *
 * 说明：
 *   1) CORDIC 是 Q1.31 定点，内部做 float <-> Q1.31 转换，误差 ~1 LSB（角度 ~1e-6 rad 量级）。
 *   2) 参数顺序 / 输出顺序在 FastMath_Init() 里用已知角度**自动标定**，不依赖手册约定。
 *   3) DROOP_USE_CORDIC_TRIG 置 0 时退化为 libm（sinf/cosf/atan2f），用于对比。
 */
#ifndef __FAST_MATH_H
#define __FAST_MATH_H

#include <stdint.h>

#ifndef DROOP_PI
#define DROOP_PI  3.14159265358979323846f
#endif

/* 1 = 用 CORDIC 硬件；0 = 用 libm（对比用） */
#define DROOP_USE_CORDIC_TRIG   1

/** @brief 初始化 CORDIC 并自动标定参数/输出顺序（main 里调用一次） */
void  FastMath_Init(void);

/** @brief atan2(y, x)，返回弧度，范围 (-pi, pi] */
float FM_Atan2(float y, float x);

/** @brief 同时返回 sin(theta) / cos(theta)，theta 单位弧度 */
void  FM_SinCos(float theta, float *sin_out, float *cos_out);

/** @brief 标定结果（0=正常, 1=已交换），供调试查看 */
extern uint8_t g_fm_atan2_swap;
extern uint8_t g_fm_sincos_swap;

#endif /* __FAST_MATH_H */
