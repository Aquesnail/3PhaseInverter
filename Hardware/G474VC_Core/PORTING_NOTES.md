# G474VC_Core 原理图移植说明

新工程：`D:\3phase_inverter\Hardware\G474VC_Core`
旧工程：`D:\Hardware\Hardware`（STM32G474 **LQFP64**，用错封装的原工程）

目标：**MCU 换成 STM32G474VxT（LQFP100）+ 重新分配引脚，其余模块（主电源/DCDC、CAN、调试电源）照抄旧工程**。

---

## 1. 结论

5 张图纸全部完整、可解析、网表自洽：

| 图纸 | 器件数 | 说明 |
|---|---|---|
| `G474VC_Core.kicad_sch`（根） | 30 | 从旧工程移植；3 个 PH2.0x6 采样座子各带 3 对差分 |
| `G474_MCU.kicad_sch` | 66 | 新 MCU U2 + 9 组差分滤波 + 电源/复位/BOOT |
| `Power.kicad_sch` | 51 | 旧工程 DCDC 模块照抄 |
| `CAN.kicad_sch` | 7 | 旧工程 CAN 模块照抄 |
| `DebugerPower.kicad_sch` | 7 | 旧工程调试电源照抄 |

预览：`G474VC_Core.pdf`。

---

## 2. 引脚分配（U2 / LQFP100）— 当前版本

三个 PH2.0x6 座子各带 3 对差分，**每个座子都是一对 ADC1 + 一对 ADC2 + 一对 ADC3**，可以三路同时采样；
**同一对里 ADC 通道号大的接 `+`，小的接 `-`**。

### 座子 1 — `CURRENT1`（3 相电流）
| 对 | 通道 | `+` 引脚 | `-` 引脚 | 滤波 |
|---|---|---|---|---|
| Pair1 | ADC1_IN6 / IN7 | PC1 (16) | PC0 (15) | C26 + C40/C41 |
| Pair2 | ADC2_IN8 / IN9 | PC3 (18) | PC2 (17) | C27 + C36/C37 |
| Pair3 | ADC3_IN3 / IN4 | PE7 (38) | PE13 (44) | C25 + C38/C39 |

### 座子 2 — `VOLTAGE1`（3 相电压）
| 对 | 通道 | `+` 引脚 | `-` 引脚 | 滤波 |
|---|---|---|---|---|
| Pair4 | ADC1_IN1 / IN2 | PA1 (21) | PA0 (20) | C28 + C34/C35 |
| Pair5 | ADC2_IN3 / IN4 | PA7 (29) | PA6 (28) | C29 + C42/C43 |
| Pair6 | ADC3_IN1 / IN2 | PE9 (40) | PB1 (33) | C30 + C32/C31 |

### 座子 3 — `VOLTAGE2`（DC 母线/第二组）
| 对 | 通道 | `+` 引脚 | `-` 引脚 | 滤波 |
|---|---|---|---|---|
| Pair7 | ADC1_IN3 / IN4 | PA3 (25) | PA2 (22) | C46 + C49/C50 |
| Pair8 | ADC2_IN11 / IN12 | PB2 (34) | PC5 (31) | C51 + C52/C53 |
| Pair9 | ADC3_IN14 / IN15 | PE11 (42) | PE10 (41) | C54 + C55/C56 |

### 数字部分
| 功能 | 网络 | U2 引脚 |
|---|---|---|
| PWM1H/L（`J4.6/.5`） | PWM1P/PWM1N | PA8 (69) = HRTIM1_CHA1 / PA9 (70) = CHA2 |
| PWM2H/L（`J4.1/.2`） | PWM2P/PWM2N | PB14 (53) = CHD1 / PB15 (54) = CHD2 |
| PWM3H/L（`J4.3/.4`） | PWM3P/PWM3N | PC6 (65) = CHF1 / PC7 (66) = CHF2 |
| CAN（`J5`→U10） | CAN_TX / CAN_RX / CAN_STB | PA12 (73) / PA11 (72) / PA10 (71) |
| 串口（`J2.5/.6`） | USART_TX / USART_RX | PD5 (87) / PD6 (88)，USART2 |
| SWD/JTAG（`J2.1..4`） | SWDIO / SWCLK / JTDI / JTDO | PA13 (76) / PA14 (77) / PA15 (78) / PB3 (90) |
| 复位（`R9/SW1/C1`） | NRST | PG10 (14) |
| BOOT（`R8` 下拉） | BOOT | PB8 (95) |
| 电源 | VDD/VBAT 6,24,49,64,75,100 → +3.3V；VDDA 37 + VREF+ 36 → +3.3VA；VSS 23,48,63,74,99 → GND；VSSA 35 → GNDA |

---

## 3. 根图纸做了什么

根图纸整张照抄旧工程 `G474_Core_Board.kicad_sch`（32 器件、99 导线、18 连接点、4 子图实例），只改：

1. MCU 子图引用 `MCu.kicad_sch` → `G474_MCU.kicad_sch`，Sheetname `MCU` → `G474_MCU`。
2. 子图纸引脚：删掉 4 个单端 `ADC1..ADC4`，加 `ADC_Diff_Pair7± / 8± / 9±`（放在原 ADC1..4 槽位，复用原有走线）。
3. 根图纸 `C45/C46` 与新子图重名 → 改名 `C57/C58`（后由你删除）。
4. 工程标识：实例项目名 → `G474VC_Core`，根/子图 UUID 与 `.kicad_pro` 对齐，删除旧工程遗留的 `symbol_instances` 表。
5. 补齐 `fp-lib-table`（新工程原来缺失，导致封装库告警）。
6. 清理 `DC_CURRENT_VOLTAGE` 删除后遗留的孤儿电源符号 `#PWR064`(+3.3VA) / `#PWR044`(GNDA) 及其 2 根悬空导线。

## 4. MCU 子图做了什么

1. 15 路信号打通：JTAG×4、CAN×3、USART×2、PWM×6（补丁标签列 ↔ 边界 hier label ↔ U2 引脚）。
2. 9 组差分对：每组 2 个滤波电容 + 1 个 U2 ADC 引脚，18 个网络全部闭合。
3. 电源/复位：`VSS(23/48/63/74/99)→GND`、`VSSA(35)→GNDA`、`VREF+(36)→+3.3VA`、`PG10(14)→NRST`、`PB8(95)→BOOT0`。
4. 新增 `NRST / BOOT / VREF / +3.3V / +3.3VA / GND / GNDA` 7 个 hier label，与根图纸 40 个 sheet pin 一一对应。
5. 51 个未使用 GPIO 加 no-connect 标记。

### 标签排版修复（第二版）

工具生成的标签原来**不带 `(justify …)`**，KiCad 会把文字按锚点居中 → 文字一半压在导线上、一半飘在外面，看起来"错位"；9 组差分对还多贴了一个同名普通标签盖在 hier label 上（显示成 `ADC_Diff_Pair1+ADC_Diff_Pair1+`）。已修：

* 全部 88 个标签补 `(justify …)`，文字统一朝无导线一侧；
* 删掉 18 个叠在 hier label 上的重复普通标签；
* 18 个引脚侧 `ADC_Diff_PairN±` 普通标签改为同名 hierarchical label（已验证同图同名 hier label 属于同一网络），每个名字在每处只出现一次；
* 估算文字碰撞：0 处；改前/改后网表逐网络比对：**0 差异**。

## 5. 校验

* 9 组差分对网表成员核对：每对 = 1 个连接器引脚 + 1 个 MCU 引脚 + 2 个滤波电容（+ 对地电容）✅
* 全链路：`J2→ESD/排阻→U2`、`J4→RN2/R5/R6→HRTIM`、`J5→U10→FDCAN`、复位/BOOT 均通 ✅
* 无重复位号；ERC 见下。

## 6. 顺手修掉的旧工程问题

1. **`R9`（10K NRST 上拉）原来悬空**：它接的只是普通网络标签 `+3.3V`，KiCad 里普通标签不会连到同名电源网络 → 已换成真正的 `+3.3V` 电源符号。
2. **`MainPower` 的 `+5V`/`+12V` 图纸引脚原来悬空**（旧工程 2 条 error）→ 各补一个电源符号。

## 7. 剩余 ERC 提示（均为继承问题，未改）

| 数量 | 类型 | 说明 |
|---|---|---|
| 2 | error | `RN1.6/RN1.7` 排阻引脚声明为 Input 且无驱动源 —— 符号引脚类型问题 |
| 1 | error | `U9.1 VIN` 无 power_out 驱动 —— 由 `J2.8 Debuger_5V` 外部供电 |
| 3 | error | `#PWR016 / #PWR010 / #PWR05` 同类"电源无驱动"，加 `PWR_FLAG` 可清 |
| 6 | warning | 根图纸 `y=55.245` 处导线 off-grid（旧工程遗留） |
| 其余 | warning | `multiple_net_names`（`PWM1P↔HRTIM1_CHA1`、`CAN_TX↔FDCAN1_TX` 这类刻意的别名）、局部标签与全局电源同名、`pin_to_pin` 引脚类型提示 |

需要的话可以补 `PWR_FLAG` 把这 4 条 error 清掉。

## 8. 文件与备份

* 改动：`G474VC_Core.kicad_sch`、`G474_MCU.kicad_sch`、`G474VC_Core.kicad_pro`、新增 `fp-lib-table`
* 备份：
  * `G474VC_Core.kicad_sch.bak-before-port`
  * `G474_MCU.kicad_sch.bak-before-label-fix`
  * `G474_MCU.kicad_sch.bak-before-pairreorder`
* 导出：`G474VC_Core.pdf`
