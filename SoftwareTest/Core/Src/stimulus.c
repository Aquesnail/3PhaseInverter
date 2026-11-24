/**
 * @file    stimulus.c
 * @brief   合成三相正弦激励实现
 */
#include "stimulus.h"
#include "fast_math.h"
#include <math.h>

#define STIM_N        1000          /* 每周期点数：fs/fsig = 50 kHz / 50 Hz */
#define STIM_PHASE_B  (STIM_N / 3)  /* 333 点 = 120 度 */
#define STIM_PHASE_C  (2 * STIM_N / 3)
#define TWO_PI_F      (2.0f * DROOP_PI)

#define STIM_VCAP_PK  20.0f         /* 相电压峰值（V），模型 E0 = 20 */
#define STIM_VGRID_PK 20.0f
#define STIM_I_PK     5.0f          /* 电流峰值（A） */

static float    s_tab[STIM_N];      /* 归一化正弦表 */
uint16_t        g_stim_index = 0u;

float g_stim_vcap_line[3];
float g_stim_vgrid_line[3];
float g_stim_i1[3];
float g_stim_i2[3];

void STIM_Init(void)
{
  for (uint32_t i = 0u; i < STIM_N; i++)
  {
    s_tab[i] = sinf(TWO_PI_F * (float)i / (float)STIM_N);
  }
  g_stim_index = 0u;
  STIM_Next();
}

void STIM_Next(void)
{
  uint16_t ia = g_stim_index;
  uint16_t ib = (uint16_t)(ia + STIM_PHASE_B);
  uint16_t ic = (uint16_t)(ia + STIM_PHASE_C);
  if (ib >= STIM_N) { ib = (uint16_t)(ib - STIM_N); }
  if (ic >= STIM_N) { ic = (uint16_t)(ic - STIM_N); }

  float sa = s_tab[ia];
  float sb = s_tab[ib];
  float sc = s_tab[ic];

  /* 相电压（用于派生线电压，交给算法里的 line2phase 还原） */
  float vca = STIM_VCAP_PK  * sa;
  float vcb = STIM_VCAP_PK  * sb;
  float vcc = STIM_VCAP_PK  * sc;
  float vga = STIM_VGRID_PK * sa;
  float vgb = STIM_VGRID_PK * sb;
  float vgc = STIM_VGRID_PK * sc;

  g_stim_vcap_line[0]  = vca - vcb;      /* Uab */
  g_stim_vcap_line[1]  = vcb - vcc;      /* Ubc */
  g_stim_vcap_line[2]  = vca - vcc;      /* Uac */

  g_stim_vgrid_line[0] = vga - vgb;
  g_stim_vgrid_line[1] = vgb - vgc;
  g_stim_vgrid_line[2] = vga - vgc;

  g_stim_i1[0] = STIM_I_PK * sa;
  g_stim_i1[1] = STIM_I_PK * sb;
  g_stim_i1[2] = STIM_I_PK * sc;

  g_stim_i2[0] = STIM_I_PK * sa;
  g_stim_i2[1] = STIM_I_PK * sb;
  g_stim_i2[2] = STIM_I_PK * sc;

  g_stim_index++;
  if (g_stim_index >= STIM_N) { g_stim_index = 0u; }
}
