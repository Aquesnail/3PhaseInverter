/**
 * @file    droop_control.h
 * @brief   DroopControl.slx 控制链 C 移植（float32）+ 分环节开关/分频/耗时统计
 *
 * 链序（固定顺序，同一 tick 内依次执行）：
 *   0 PRE   : 线电压->相电压 + Clarke（4 路）
 *   1 SOGI  : DSOGI-FLL（PLL）
 *   2 DROOP : 下垂控制（P/Q 低通 + 下垂方程 + θ 积分 + sin/cos）
 *   3 QPR   : 电压外环 QPR ×2（α/β）
 *   4 CURR  : 电流内环（P + 电容电压前馈）
 *   5 PWM   : SVPWM
 *
 * 注意（measure-only 模式）：
 *   - 分频只影响"执行频率"，不改任何离散化系数（Ts 恒为 DROOP_TS），
 *     因此控制律数值是错的 —— 本工程只用于测量各环节耗时，不追求正确性。
 *   - 上游环节被禁时输出置 0，避免 NaN/denormal 传到下游污染计时。
 */
#ifndef __DROOP_CONTROL_H
#define __DROOP_CONTROL_H

#include <stdint.h>

/* ==================== 环节开关（1=启用，0=编译期移除） ==================== */
#define EN_PRE      1
#define EN_SOGI     1
#define EN_DROOP    1
#define EN_QPR      1
#define EN_CURR     1
#define EN_PWM      1

/* ==================== 环节分频（1=每 tick 跑，N=每 N 个 tick 跑一次） ========= */
/* 注意：SOGI 与 DROOP 已改由 TIM1 的 1 kHz 中断驱动，不再用分频。 */
#define DIV_PRE     1
#define DIV_QPR     1
#define DIV_CURR    1
#define DIV_PWM     1

/* ==================== 每环节耗时统计（DWT，主循环经串口打印） ============= */
#define MEASURE_PER_STAGE  0   /* DWT 统计关闭：改用 PA8/PA4 + 逻辑分析仪 */

typedef enum
{
  ST_PRE = 0,
  ST_SOGI,
  ST_DROOP,
  ST_QPR,
  ST_CURR,
  ST_PWM,
  ST_NUM
} StageId;

#if MEASURE_PER_STAGE
/** [0]=累计周期 [1]=最大周期 [2]=执行次数 */
extern volatile uint32_t g_cyc[ST_NUM][3];
#endif

/* ==================== 参数（模型 InitFcn 原值） ==================== */
/* Functions tagged with this run from CCM SRAM (0 wait state, no flash cache
 * dependency) - used for the 50 kHz fast chain so its timing is deterministic. */
#if defined(__GNUC__)
#define DROOP_RAMFUNC   __attribute__((section(".ccmram")))
#else
#define DROOP_RAMFUNC
#endif

#define DROOP_TS            2.0e-5f      /* 50 kHz 快环步长：PRE/QPR/CURR/PWM */
#define DROOP_TS_SLOW       1.0e-3f      /* 1 kHz 慢环步长：SOGI-FLL / DROOP (TIM1) */
#define DROOP_W0            314.159265f  /* 2*pi*50 */
#define DROOP_WC            1.884955592f /* 2*pi*0.3 */
#define DROOP_UC_KP         0.010579843f
#define DROOP_UC_KR_CODE    0.282722874f /* = Uc_Kr/2 */
#define DROOP_I1_KPI        1.73f
#define DROOP_UDC           48.0f
#define DROOP_PWM_VBASE     1.0f
#define DROOP_U_MEAS_BASE   1.0f
#define DROOP_I_MEAS_BASE   1.0f

#define DROOP_E0            20.0f
#define DROOP_GRID_MP       3.490658504e-4f
#define DROOP_GRID_NQ       1.111111111e-4f
#define DROOP_GRID_WC       25.0f
#define DROOP_GRID_P0       0.0f
#define DROOP_GRID_Q0       0.0f

/* 相角生成：1 = CORDIC atan2（模型原样）；0 = omega 积分 */
#define DROOP_ANGLE_MODE_CORDIC  1

/* ==================== 状态与接口 ==================== */

typedef struct
{
  float Ts;        /* 50 kHz 快环步长 */
  float Ts_slow;   /* 1 kHz 慢环步长（SOGI / DROOP） */

  /* QPR 系数与状态 */
  float qpr_a1, qpr_a2, qpr_b0;
  float ur1a, ur2a, e1a, e2a;
  float ur1b, ur2b, e1b, e2b;

  /* DSOGI-FLL */
  float x1a, x2a, x1b, x2b;
  float sogi_omega;
  uint32_t sogi_lock_cnt;
  float theta_pll, omega_pll;

  /* 下垂控制 */
  float P_filt, Q_filt;
  float theta;
  float w_out, E_out, P_inst, Q_inst;
  uint8_t breaker_cmd;

  /* 跨分频保持的中间量（上游算、下游可能在别的 tick 用） */
  float vg_abc[3];
  float vg_alpha, vg_beta;
  float vc_a, vc_b;
  float i1_a, i1_b;
  float i2_a, i2_b;
  float vr_a, vr_b;
  float iref_a, iref_b;
  float u_a, u_b;

  float duty[3];
} DroopCtl_t;

extern DroopCtl_t g_droop;

void DroopCtl_Init(DroopCtl_t *s);

/** @brief DSOGI-FLL 单独一步（便于单独测试/开关） */
void DroopCtl_SOGI_FLL(DroopCtl_t *s, const float uabc[3],
                       float *theta, float *omega, uint8_t *locked);

/** @brief 一个快环 tick（50 kHz，ADC 中断里调用）：PRE -> QPR -> CURR -> PWM */
DROOP_RAMFUNC void DroopCtl_Step(DroopCtl_t *s,
                   const float vcap_line[3],
                   const float i1_abc[3],
                   const float i2_abc[3],
                   const float vgrid_line[3],
                   float duty[3]);

/** @brief 一个慢环 tick（1 kHz，TIM1 更新中断里调用）：SOGI-FLL -> DROOP */
void DroopCtl_StepSlow(DroopCtl_t *s);

#endif /* __DROOP_CONTROL_H */
