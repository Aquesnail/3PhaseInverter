/**
 * @file    droop_control.c
 * @brief   DroopControl.slx 控制链 C 移植（float32）+ 分环节开关/分频/耗时统计
 *
 * 六个环节各是一个 static 函数，由 DroopCtl_Step() 按分频/开关调度：
 *   PRE -> SOGI -> DROOP -> QPR -> CURR -> PWM
 *
 * measure-only 说明：分频不改变离散化系数（Ts 仍是 DROOP_TS），
 * 控制律数值会失真，本工程只用于测量各环节耗时。
 */
#include "droop_control.h"
#include "fast_math.h"
#include <math.h>

#if MEASURE_PER_STAGE
#include "stm32g4xx_hal.h"    /* DWT->CYCCNT */
#endif

DroopCtl_t g_droop;

#if MEASURE_PER_STAGE
volatile uint32_t g_cyc[ST_NUM][3];

/* 统计宏：只在统计段内读 DWT，开销 ~6 周期/环节 */
/* 注意：stage 函数会被 -O3 内联，必须用 "memory" 屏障把计时点和计算体隔开，
 * 否则编译器会把两次 CYCCNT 读调度到一起 -> dt 恒为 0。 */
#define STAGE_TIMED(id, ...)                    \
  do {                                          \
    uint32_t _t0 = DWT->CYCCNT;                 \
    __asm volatile ("" ::: "memory");           \
    __VA_ARGS__;                                \
    __asm volatile ("" ::: "memory");           \
    uint32_t _d = DWT->CYCCNT - _t0;            \
    g_cyc[id][0] += _d;                         \
    if (_d > g_cyc[id][1]) { g_cyc[id][1] = _d; } \
    g_cyc[id][2]++;                             \
  } while (0)
#else
#define STAGE_TIMED(id, ...) do { __VA_ARGS__; } while (0)
#endif

/* 各环节倒计数器（初值在 Init 里设为分频系数） */
static uint16_t s_cnt[ST_NUM];

#define SQRT3      1.7320508075688772f
#define TWO_PI     (2.0f * DROOP_PI)
#define SQRT2      1.4142135623730951f

/* ---------------- 基础变换 ---------------- */

static inline void line2phase(const float u_line[3], float u_abc[3])
{
  float Uab = u_line[0], Ubc = u_line[1], Uac = u_line[2];
  u_abc[0] = ( Uab + Uac) * (1.0f / 3.0f);
  u_abc[1] = ( Ubc - Uab) * (1.0f / 3.0f);
  u_abc[2] = -(Ubc + Uac) * (1.0f / 3.0f);
}

static inline void clarke(const float abc[3], float *alpha, float *beta)
{
  float a = abc[0], b = abc[1], c = abc[2];
  *alpha = (2.0f / 3.0f) * (a - 0.5f * b - 0.5f * c);
  *beta  = (2.0f / 3.0f) * ((SQRT3 * 0.5f) * (b - c));
}

static inline float wrap_2pi(float th)
{
  if (th >= TWO_PI)   { th -= TWO_PI; }
  else if (th < 0.0f) { th += TWO_PI; }
  return th;
}

/* ---------------- 初始化 ---------------- */

void DroopCtl_Init(DroopCtl_t *s)
{
  float Ts = DROOP_TS;
  float w0 = DROOP_W0;
  float xi = 2.0f * DROOP_WC;         /* 模型：xi = 2*wc */
  float w0Ts2 = w0 * w0 * Ts * Ts;
  float den = 4.0f + 2.0f * xi * Ts + w0Ts2;

  s->qpr_a1 = 2.0f * (w0Ts2 - 4.0f) / den;
  s->qpr_a2 = (4.0f - 2.0f * xi * Ts + w0Ts2) / den;
  s->qpr_b0 = 4.0f * DROOP_UC_KR_CODE * xi * Ts / den;
  s->Ts = Ts;
  s->Ts_slow = DROOP_TS_SLOW;

  s->ur1a = s->ur2a = s->e1a = s->e2a = 0.0f;
  s->ur1b = s->ur2b = s->e1b = s->e2b = 0.0f;

  s->x1a = s->x2a = s->x1b = s->x2b = 0.0f;
  s->sogi_omega    = TWO_PI * 50.0f;
  s->sogi_lock_cnt = 0u;
  s->theta_pll = 0.0f;
  s->omega_pll = TWO_PI * 50.0f;

  s->P_filt = s->Q_filt = 0.0f;
  s->theta  = 0.0f;
  s->w_out  = w0;
  s->E_out  = DROOP_E0;
  s->P_inst = s->Q_inst = 0.0f;
  s->breaker_cmd = 1u;

  s->vg_abc[0] = s->vg_abc[1] = s->vg_abc[2] = 0.0f;
  s->vc_a = s->vc_b = 0.0f;
  s->i1_a = s->i1_b = 0.0f;
  s->i2_a = s->i2_b = 0.0f;
  s->vr_a = s->vr_b = 0.0f;
  s->iref_a = s->iref_b = 0.0f;
  s->u_a = s->u_b = 0.0f;
  s->duty[0] = s->duty[1] = s->duty[2] = 0.0f;

  /* 分频计数器初值 */
  s_cnt[ST_PRE]   = DIV_PRE;
  s_cnt[ST_QPR]   = DIV_QPR;
  s_cnt[ST_CURR]  = DIV_CURR;
  s_cnt[ST_PWM]   = DIV_PWM;
}

/* ---------------- 环节 1：采样预处理 ---------------- */

#if EN_PRE
DROOP_RAMFUNC static void stage_pre(DroopCtl_t *s,
                      const float vcap_line[3], const float i1_abc[3],
                      const float i2_abc[3], const float vgrid_line[3])
{
  float vcap_abc[3], vgrid_abc[3];

  line2phase(vcap_line, vcap_abc);
  line2phase(vgrid_line, vgrid_abc);

  clarke(vcap_abc,  &s->vc_a, &s->vc_b);
  clarke(vgrid_abc, &s->vg_alpha, &s->vg_beta);   /* 模型里也做这一步，保留其开销 */
  clarke(i1_abc,    &s->i1_a, &s->i1_b);
  clarke(i2_abc,    &s->i2_a, &s->i2_b);

  /* SOGI 需要三相电压 */
  s->vg_abc[0] = vgrid_abc[0];
  s->vg_abc[1] = vgrid_abc[1];
  s->vg_abc[2] = vgrid_abc[2];
}
#else
DROOP_RAMFUNC static void stage_pre(DroopCtl_t *s,
                      const float vcap_line[3], const float i1_abc[3],
                      const float i2_abc[3], const float vgrid_line[3])
{
  (void)vcap_line; (void)i1_abc; (void)i2_abc; (void)vgrid_line;
  s->vc_a = s->vc_b = 0.0f;
  s->i1_a = s->i1_b = 0.0f;
  s->i2_a = s->i2_b = 0.0f;
  s->vg_abc[0] = s->vg_abc[1] = s->vg_abc[2] = 0.0f;
}
#endif

/* ---------------- 环节 2：DSOGI-FLL ---------------- */

void DroopCtl_SOGI_FLL(DroopCtl_t *s, const float uabc[3],
                       float *theta, float *omega, uint8_t *locked)
{
  const float k        = SQRT2;
  const float Gamma    = 100.0f;
  const float eps_lock = 5.0f;
  const uint32_t lock_hold = (uint32_t)(0.02f / s->Ts_slow + 0.5f);

  float Ua = uabc[0], Ub = uabc[1], Uc = uabc[2];
  float ualpha = (2.0f / 3.0f) * (Ua - 0.5f * Ub - 0.5f * Uc);
  float ubeta  = (2.0f / 3.0f) * ((SQRT3 * 0.5f) * Ub - (SQRT3 * 0.5f) * Uc);

  float om = s->sogi_omega;
  if (om > TWO_PI * 65.0f) { om = TWO_PI * 65.0f; }
  if (om < TWO_PI * 45.0f) { om = TWO_PI * 45.0f; }

  float err_a = ualpha - s->x1a;
  s->x1a = s->x1a + s->Ts_slow * (k * err_a - s->x2a) * om;
  s->x2a = s->x2a + s->Ts_slow * (s->x1a * om);

  float err_b = ubeta - s->x1b;
  s->x1b = s->x1b + s->Ts_slow * (k * err_b - s->x2b) * om;
  s->x2b = s->x2b + s->Ts_slow * (s->x1b * om);

  float va_pos = 0.5f * (s->x1a - s->x2b);
  float vb_pos = 0.5f * (s->x1b + s->x2a);

  float eps_f = va_pos * (s->x1b - ubeta) - vb_pos * (s->x1a - ualpha);
  float norm  = va_pos * va_pos + vb_pos * vb_pos;
  if (norm > 1e-6f) { eps_f = eps_f / norm; }
  om = om - Gamma * eps_f * s->Ts_slow;
  s->sogi_omega = om;

  float th;
#if (DROOP_ANGLE_MODE_CORDIC == 1)
  th = FM_Atan2(vb_pos, va_pos);
#else
  s->theta_pll = wrap_2pi(s->theta_pll + om * s->Ts_slow);
  th = s->theta_pll;
#endif
  s->theta_pll = th;
  s->omega_pll = om;

  if (fabsf(eps_f) < eps_lock)
  {
    if (s->sogi_lock_cnt < lock_hold) { s->sogi_lock_cnt++; }
  }
  else
  {
    s->sogi_lock_cnt = 0u;
  }

  *theta  = th;
  *omega  = om;
  *locked = (s->sogi_lock_cnt >= lock_hold) ? 1u : 0u;
}

#if EN_SOGI
static void stage_sogi(DroopCtl_t *s)
{
  float th, om;
  uint8_t locked;
  DroopCtl_SOGI_FLL(s, s->vg_abc, &th, &om, &locked);
  (void)th; (void)locked;
}
#else
static void stage_sogi(DroopCtl_t *s)
{
  s->theta_pll = wrap_2pi(s->theta_pll + DROOP_W0 * s->Ts_slow);
  s->omega_pll = DROOP_W0;
}
#endif

/* ---------------- 环节 3：下垂控制 ---------------- */

#if EN_DROOP
static void stage_droop(DroopCtl_t *s)
{
  float p_inst = 1.5f * (s->vc_a * s->i2_a + s->vc_b * s->i2_b);
  float q_inst = 1.5f * (s->vc_b * s->i2_a - s->vc_a * s->i2_b);
  s->P_inst = p_inst;
  s->Q_inst = q_inst;

  float alpha_lpf = (DROOP_GRID_WC * s->Ts_slow) / (1.0f + DROOP_GRID_WC * s->Ts_slow);
  s->P_filt = (1.0f - alpha_lpf) * s->P_filt + alpha_lpf * p_inst;
  s->Q_filt = (1.0f - alpha_lpf) * s->Q_filt + alpha_lpf * q_inst;

  s->w_out = DROOP_W0 - DROOP_GRID_MP * (s->P_filt - DROOP_GRID_P0);
  float E = DROOP_E0 - DROOP_GRID_NQ * (s->Q_filt - DROOP_GRID_Q0);
  if (E < 0.8f * DROOP_E0)      { E = 0.8f * DROOP_E0; }
  else if (E > 1.2f * DROOP_E0) { E = 1.2f * DROOP_E0; }
  s->E_out = E;

  s->theta = wrap_2pi(s->theta + s->w_out * s->Ts_slow);

  float sn, cs;
  FM_SinCos(s->theta, &sn, &cs);
  s->vr_a = E * cs;
  s->vr_b = E * sn;
}
#else
static void stage_droop(DroopCtl_t *s)
{
  s->P_inst = s->Q_inst = s->P_filt = s->Q_filt = 0.0f;
  s->w_out = DROOP_W0;
  s->E_out = DROOP_E0;
  s->vr_a = s->vr_b = 0.0f;
}
#endif

/* ---------------- 环节 4：QPR 电压外环 ---------------- */

static inline float qpr_step(float e,
                             float *ur1, float *ur2, float *e1, float *e2,
                             float Kp, float a1, float a2, float b0)
{
  float ur = b0 * e - b0 * (*e2) - a1 * (*ur1) - a2 * (*ur2);
  *e2  = *e1;  *e1  = e;
  *ur2 = *ur1; *ur1 = ur;
  return Kp * e + ur;
}

#if EN_QPR
DROOP_RAMFUNC static void stage_qpr(DroopCtl_t *s)
{
  s->iref_a = qpr_step(s->vr_a - s->vc_a, &s->ur1a, &s->ur2a, &s->e1a, &s->e2a,
                       DROOP_UC_KP, s->qpr_a1, s->qpr_a2, s->qpr_b0);
  s->iref_b = qpr_step(s->vr_b - s->vc_b, &s->ur1b, &s->ur2b, &s->e1b, &s->e2b,
                       DROOP_UC_KP, s->qpr_a1, s->qpr_a2, s->qpr_b0);
}
#else
DROOP_RAMFUNC static void stage_qpr(DroopCtl_t *s)
{
  s->iref_a = 0.0f;
  s->iref_b = 0.0f;
}
#endif

/* ---------------- 环节 5：电流内环 ---------------- */

#if EN_CURR
DROOP_RAMFUNC static void stage_curr(DroopCtl_t *s)
{
  s->u_a = DROOP_I1_KPI * (s->iref_a - s->i1_a) + s->vc_a;
  s->u_b = DROOP_I1_KPI * (s->iref_b - s->i1_b) + s->vc_b;
}
#else
DROOP_RAMFUNC static void stage_curr(DroopCtl_t *s)
{
  s->u_a = s->vc_a;
  s->u_b = s->vc_b;
}
#endif

/* ---------------- 环节 6：SVPWM ---------------- */

#if EN_PWM
DROOP_RAMFUNC static void stage_pwm(DroopCtl_t *s)
{
  float Udc = DROOP_UDC;
  if (Udc <= 1e-6f) { s->duty[0] = s->duty[1] = s->duty[2] = 0.0f; return; }

  float Va = s->u_a * DROOP_PWM_VBASE;
  float Vb = s->u_b * DROOP_PWM_VBASE;

  float v0v = Va;
  float v1v = (-Va + SQRT3 * Vb) * 0.5f;
  float v2v = (-Va - SQRT3 * Vb) * 0.5f;

  float vmax = v0v, vmin = v0v;
  if (v1v > vmax) { vmax = v1v; }
  if (v1v < vmin) { vmin = v1v; }
  if (v2v > vmax) { vmax = v2v; }
  if (v2v < vmin) { vmin = v2v; }

  float span = vmax - vmin;
  if (span > Udc)
  {
    float g = Udc / span;
    v0v *= g; v1v *= g; v2v *= g;
    vmax *= g; vmin *= g;
  }

  float vz = (vmax + vmin) * 0.5f;
  float d0 = 0.5f + (v0v - vz) / Udc;
  float d1 = 0.5f + (v1v - vz) / Udc;
  float d2 = 0.5f + (v2v - vz) / Udc;

  if (d0 < 0.0f) { d0 = 0.0f; } else if (d0 > 1.0f) { d0 = 1.0f; }
  if (d1 < 0.0f) { d1 = 0.0f; } else if (d1 > 1.0f) { d1 = 1.0f; }
  if (d2 < 0.0f) { d2 = 0.0f; } else if (d2 > 1.0f) { d2 = 1.0f; }

  s->duty[0] = 2.0f * d0 - 1.0f;
  s->duty[1] = 2.0f * d1 - 1.0f;
  s->duty[2] = 2.0f * d2 - 1.0f;
}
#else
DROOP_RAMFUNC static void stage_pwm(DroopCtl_t *s)
{
  s->duty[0] = s->duty[1] = s->duty[2] = 0.0f;
}
#endif

/* ---------------- 调度器：一个 tick ---------------- */

/* ---------------- 慢环调度：1 kHz（TIM1 更新中断） ---------------- */

void DroopCtl_StepSlow(DroopCtl_t *s)
{
#if EN_SOGI
  STAGE_TIMED(ST_SOGI, stage_sogi(s));
#else
  stage_sogi(s);
#endif

#if EN_DROOP
  STAGE_TIMED(ST_DROOP, stage_droop(s));
#else
  stage_droop(s);
#endif
}
DROOP_RAMFUNC void DroopCtl_Step(DroopCtl_t *s,
                   const float vcap_line[3],
                   const float i1_abc[3],
                   const float i2_abc[3],
                   const float vgrid_line[3],
                   float duty[3])
{
  /* 0 PRE */
#if EN_PRE
  if (--s_cnt[ST_PRE] == 0u)
  {
    s_cnt[ST_PRE] = DIV_PRE;
    STAGE_TIMED(ST_PRE, stage_pre(s, vcap_line, i1_abc, i2_abc, vgrid_line));
  }
#else
  stage_pre(s, vcap_line, i1_abc, i2_abc, vgrid_line);
#endif


  /* 3 QPR */
#if EN_QPR
  if (--s_cnt[ST_QPR] == 0u)
  {
    s_cnt[ST_QPR] = DIV_QPR;
    STAGE_TIMED(ST_QPR, stage_qpr(s));
  }
#else
  stage_qpr(s);
#endif

  /* 4 CURR */
#if EN_CURR
  if (--s_cnt[ST_CURR] == 0u)
  {
    s_cnt[ST_CURR] = DIV_CURR;
    STAGE_TIMED(ST_CURR, stage_curr(s));
  }
#else
  stage_curr(s);
#endif

  /* 5 PWM */
#if EN_PWM
  if (--s_cnt[ST_PWM] == 0u)
  {
    s_cnt[ST_PWM] = DIV_PWM;
    STAGE_TIMED(ST_PWM, stage_pwm(s));
  }
#else
  stage_pwm(s);
#endif

  duty[0] = s->duty[0];
  duty[1] = s->duty[1];
  duty[2] = s->duty[2];
}
