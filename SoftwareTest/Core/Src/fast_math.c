/**
 * @file    fast_math.c
 * @brief   CORDIC 三角函数实现（Q1.31 定点 + 自动标定）
 *
 * CORDIC 用法（依据 ST 官方例程 CORDIC_SinCos_DMA_Perf）：
 *   SINE : NbWrite=1（角度）, NbRead=2（先 sin 后 cos），Precision=6CYCLES 为 q1.31 满精度
 *   PHASE: NbWrite=2（两个直角分量）, NbRead=1（角度/pi）
 * 角度输入以 pi 为 1.0（即 angle_q31 = theta/pi * 2^31），输出同理。
 */
#include "fast_math.h"
#include <math.h>

#if DROOP_USE_CORDIC_TRIG
#include "stm32g4xx_hal.h"

#define Q31_MAXF   2147483647.0f
#define Q31_SCALEF 2147483648.0f
#define Q31_INVF   4.6566128730773926e-10f   /* 1/2^31 */

uint8_t g_fm_atan2_swap  = 0u;
uint8_t g_fm_sincos_swap = 0u;

/* CSR 配置：函数 + 精度 + 缩放 + 参数个数 + 结果个数 + 位宽（与 HAL_CORDIC_Configure 一致） */
#define CORDIC_CFG_PHASE  (CORDIC_FUNCTION_PHASE | CORDIC_PRECISION_6CYCLES | CORDIC_SCALE_0 | \
                           CORDIC_NBWRITE_2 | CORDIC_NBREAD_1 | \
                           CORDIC_INSIZE_32BITS | CORDIC_OUTSIZE_32BITS)
#define CORDIC_CFG_SINE   (CORDIC_FUNCTION_SINE  | CORDIC_PRECISION_6CYCLES | CORDIC_SCALE_0 | \
                           CORDIC_NBWRITE_1 | CORDIC_NBREAD_2 | \
                           CORDIC_INSIZE_32BITS | CORDIC_OUTSIZE_32BITS)

static inline int32_t f2q31(float v)
{
  float t = v * Q31_SCALEF;
  if (t >= Q31_MAXF)        { return (int32_t)0x7FFFFFFF; }
  if (t <= -Q31_SCALEF)     { return (int32_t)0x80000000; }
  return (int32_t)t;
}

static inline float q312f(int32_t q)
{
  return (float)q * Q31_INVF;
}

/* 写两个参数，读一个角度结果（单位 pi） */
static inline float cordic_phase_raw(int32_t first, int32_t second)
{
  CORDIC->CSR   = CORDIC_CFG_PHASE;
  CORDIC->WDATA = first;
  CORDIC->WDATA = second;
  while ((CORDIC->CSR & CORDIC_CSR_RRDY) == 0u) { }
  return q312f((int32_t)CORDIC->RDATA);
}

/* 写一个角度，读两个结果（写死硬件顺序：先 sin 后 cos） */
static inline void cordic_sincos_raw(int32_t angle, int32_t *first, int32_t *second)
{
  CORDIC->CSR   = CORDIC_CFG_SINE;
  CORDIC->WDATA = angle;
  while ((CORDIC->CSR & CORDIC_CSR_RRDY) == 0u) { }
  *first  = (int32_t)CORDIC->RDATA;
  *second = (int32_t)CORDIC->RDATA;
}

void FastMath_Init(void)
{
  /* ---- 1) sin/cos 输出顺序标定：角度 0 -> sin=0, cos=1 ---- */
  int32_t a, b;
  cordic_sincos_raw(0, &a, &b);
  /* 若第一个结果更接近 1（cos），说明顺序是 cos 在前，需要交换 */
  g_fm_sincos_swap = (fabsf(q312f(a) - 1.0f) < fabsf(q312f(b) - 1.0f)) ? 1u : 0u;

  /* ---- 2) atan2 参数顺序标定 ----
   * 参考：atan2(y=0, x=1) = 0
   * 先按 (first=x=1, second=y=0) 试算：
   *   若得 0   -> 硬件把第一个参数当 x，即 atan2(second, first)
   *   若得 pi/2-> 硬件把第一个参数当 y，需要交换写入顺序
   */
  float r = cordic_phase_raw(f2q31(1.0f), f2q31(0.0f));
  g_fm_atan2_swap = (fabsf(r) > 0.5f) ? 1u : 0u;

  /* 角速度积分模式（DROOP_ANGLE_MODE=0）不需要 atan2，标定失败也无影响 */
}

float FM_Atan2(float y, float x)
{
  float r;
  {
    /* Q1.31 只表示 [-1, 1)，atan2 的两个直角分量需要等比归一化到该范围（等比缩放不改变角度） */
    float ax = fabsf(x), ay = fabsf(y);
    float m  = (ax > ay) ? ax : ay;
    float nx, ny;
    if (m < 1e-9f) { return 0.0f; }
    nx = x / m;   /* [-1, 1] */
    ny = y / m;
    if (nx >  0.9999999f) { nx =  0.9999999f; }
    if (nx < -1.0f)       { nx = -1.0f; }
    if (ny >  0.9999999f) { ny =  0.9999999f; }
    if (ny < -1.0f)       { ny = -1.0f; }

    if (g_fm_atan2_swap == 0u) {
      r = cordic_phase_raw(f2q31(nx), f2q31(ny));   /* x 先, y 后 = atan2(y,x) */
    } else {
      r = cordic_phase_raw(f2q31(ny), f2q31(nx));   /* y 先, x 后 */
    }
    r *= DROOP_PI;
  }
  return r;
}

void FM_SinCos(float theta, float *sin_out, float *cos_out)
{
  int32_t a, b;
  /* CORDIC 角度输入以 pi 为 1.0，范围 [-pi, pi]（Q1.31 只能表示 [-1,1)），
     所以先把 [0, 2pi) 的相角卷绕到 (-pi, pi]，否则后半周期会饱和出错。 */
  float th = theta;
  if (th > DROOP_PI)       { th -= (2.0f * DROOP_PI); }
  else if (th < -DROOP_PI) { th += (2.0f * DROOP_PI); }

  int32_t ang = f2q31(th * (1.0f / DROOP_PI));
  cordic_sincos_raw(ang, &a, &b);
  if (g_fm_sincos_swap == 0u) {
    *sin_out = q312f(a);
    *cos_out = q312f(b);
  } else {
    *sin_out = q312f(b);
    *cos_out = q312f(a);
  }
}

#else  /* ---------------- libm 对比实现 ---------------- */

uint8_t g_fm_atan2_swap  = 0u;
uint8_t g_fm_sincos_swap = 0u;

void FastMath_Init(void) { }

float FM_Atan2(float y, float x) { return atan2f(y, x); }

void FM_SinCos(float theta, float *sin_out, float *cos_out)
{
  *sin_out = sinf(theta);
  *cos_out = cosf(theta);
}

#endif /* DROOP_USE_CORDIC_TRIG */
