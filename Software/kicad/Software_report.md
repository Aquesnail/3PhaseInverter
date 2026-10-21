# Software —— CubeMX → KiCad 符号生成报告

由 `ioc2kicad.py` 自动生成。

## 1. 数据来源

| 项 | 值 |
|---|---|
| 工程文件 | `D:\3phase_inverter\Software\Software.ioc` |
| 器件 | **STM32G474VCTx**（`STM32G474V(B-C-E)Tx`） |
| 封装 / 家族 | LQFP100 / STM32G4 |
| 订货型号 | STM32G474VCT6 |
| CubeMX 版本 | 6.18.0（器件库 DB.6.0.180） |
| 器件库 XML | `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db\mcu\STM32G474V(B-C-E)Tx.xml` |
| KiCad 符号库 | `C:\Program Files\KiCad\10.0\share\kicad\symbols\MCU_ST_STM32G4.kicad_sym` |
| 基线符号 | `STM32G474V_B-C-E_Tx` |
| **生成的符号** | **`STM32G474VCTx_Software`** |

## 2. 生成结果

| 项 | 值 |
|---|---|
| 符号库文件 | `D:\3phase_inverter\Software\kicad\Software.kicad_sym` |
| 引脚表 CSV | `D:\3phase_inverter\Software\kicad\Software_pintable.csv` |
| 符号引脚总数 | 100（与器件库一致） |
| .ioc 中已分配引脚 | 26 |
| 保留的 alternate functions | 870 条 |
| 符号体尺寸调整 | 左右加宽 3.81 / 22.86 mm（X: [-17.78, 17.78] → [-21.59, 40.64]）；上下拉高 3.81 / 3.81 mm（Y: [-66.04, 68.58] → [-69.85, 72.39]） |

## 3. 引脚对照表（已分配）

| 脚号 | CubeMX 引脚 | CubeMX 类型 | 分配功能 | 用户标签 | 生成引脚名 | 电气类型 | 依据 | 复用功能数 |
|---:|---|---|---|---|---|---|---|---:|
| 8 | PC14-OSC32_IN | I/O | RCC_OSC32_IN | — | `PC14-OSC32_IN-RCC_OSC32_IN` | **input** | signal:^RCC_OSC32_IN$ | 1 |
| 9 | PC15-OSC32_OUT | I/O | RCC_OSC32_OUT | — | `PC15-OSC32_OUT-RCC_OSC32_OUT` | **output** | signal:^RCC_OSC32_OUT$ | 3 |
| 15 | PC0 | I/O | ADC1_IN6 | — | `PC0-ADC1_IN6` | **input** | signal:^ADC\d+_IN\d*$ | 6 |
| 16 | PC1 | I/O | ADC1_IN7 | — | `PC1-ADC1_IN7` | **input** | signal:^ADC\d+_IN\d*$ | 8 |
| 17 | PC2 | I/O | ADC2_IN8 | — | `PC2-ADC2_IN8` | **input** | signal:^ADC\d+_IN\d*$ | 10 |
| 18 | PC3 | I/O | ADC2_IN9 | — | `PC3-ADC2_IN9` | **input** | signal:^ADC\d+_IN\d*$ | 13 |
| 20 | PA0 | I/O | ADC1_IN1 | — | `PA0-ADC1_IN1` | **input** | signal:^ADC\d+_IN\d*$ | 14 |
| 21 | PA1 | I/O | ADC1_IN2 | — | `PA1-ADC1_IN2` | **input** | signal:^ADC\d+_IN\d*$ | 16 |
| 22 | PA2 | I/O | ADC1_IN3 | — | `PA2-ADC1_IN3` | **input** | signal:^ADC\d+_IN\d*$ | 17 |
| 25 | PA3 | I/O | ADC1_IN4 | — | `PA3-ADC1_IN4` | **input** | signal:^ADC\d+_IN\d*$ | 21 |
| 28 | PA6 | I/O | ADC2_IN3 | — | `PA6-ADC2_IN3` | **input** | signal:^ADC\d+_IN\d*$ | 11 |
| 29 | PA7 | I/O | ADC2_IN4 | — | `PA7-ADC2_IN4` | **input** | signal:^ADC\d+_IN\d*$ | 15 |
| 31 | PC5 | I/O | ADC2_IN11 | — | `PC5-ADC2_IN11` | **input** | signal:^ADC\d+_IN\d*$ | 13 |
| 33 | PB1 | I/O | ADC3_IN1 | — | `PB1-ADC3_IN1` | **input** | signal:^ADC\d+_IN\d*$ | 15 |
| 34 | PB2 | I/O | ADC2_IN12 | — | `PB2-ADC2_IN12` | **input** | signal:^ADC\d+_IN\d*$ | 15 |
| 38 | PE7 | I/O | ADC3_IN4 | — | `PE7-ADC3_IN4` | **input** | signal:^ADC\d+_IN\d*$ | 6 |
| 40 | PE9 | I/O | ADC3_IN2 | — | `PE9-ADC3_IN2` | **input** | signal:^ADC\d+_IN\d*$ | 10 |
| 41 | PE10 | I/O | ADC3_IN14 | — | `PE10-ADC3_IN14` | **input** | signal:^ADC\d+_IN\d*$ | 12 |
| 42 | PE11 | I/O | ADC3_IN15 | — | `PE11-ADC3_IN15` | **input** | signal:^ADC\d+_IN\d*$ | 10 |
| 44 | PE13 | I/O | ADC3_IN3 | — | `PE13-ADC3_IN3` | **input** | signal:^ADC\d+_IN\d*$ | 6 |
| 65 | PC6 | I/O | HRTIM1_CHF1 | — | `PC6-HRTIM1_CHF1` | **bidirectional** | cubeType:I/O | 7 |
| 66 | PC7 | I/O | HRTIM1_CHF2 | — | `PC7-HRTIM1_CHF2` | **bidirectional** | cubeType:I/O | 7 |
| 67 | PC8 | I/O | HRTIM1_CHE1 | — | `PC8-HRTIM1_CHE1` | **bidirectional** | cubeType:I/O | 6 |
| 68 | PC9 | I/O | HRTIM1_CHE2 | — | `PC9-HRTIM1_CHE2` | **bidirectional** | cubeType:I/O | 10 |
| 69 | PA8 | I/O | HRTIM1_CHA1 | — | `PA8-HRTIM1_CHA1` | **bidirectional** | cubeType:I/O | 14 |
| 70 | PA9 | I/O | HRTIM1_CHA2 | — | `PA9-HRTIM1_CHA2` | **bidirectional** | cubeType:I/O | 16 |

## 4. 改动摘要

- 引脚名被改写：**26** 根（其余引脚保持官方原名）
- 电气类型被改写：**20** 根

| 脚号 | 原类型 | 新类型 |
|---:|---|---|
| 8 | bidirectional | input |
| 9 | bidirectional | output |
| 15 | bidirectional | input |
| 16 | bidirectional | input |
| 17 | bidirectional | input |
| 18 | bidirectional | input |
| 20 | bidirectional | input |
| 21 | bidirectional | input |
| 22 | bidirectional | input |
| 25 | bidirectional | input |
| 28 | bidirectional | input |
| 29 | bidirectional | input |
| 31 | bidirectional | input |
| 33 | bidirectional | input |
| 34 | bidirectional | input |
| 38 | bidirectional | input |
| 40 | bidirectional | input |
| 41 | bidirectional | input |
| 42 | bidirectional | input |
| 44 | bidirectional | input |

## 5. 工作模式

**引脚工作模式**（差分对信息在这里）

| 引脚 | 模式 |
|---|---|
| PA0 | IN1-Differential |
| PA1 | IN1-Differential |
| PA2 | IN3-Differential |
| PA3 | IN3-Differential |
| PA6 | IN3-Differential |
| PA7 | IN3-Differential |
| PA8 | Output_TA1TA2 |
| PA9 | Output_TA1TA2 |
| PB1 | IN1-Differential |
| PB2 | IN11-Differential |
| PC0 | IN6-Differential |
| PC1 | IN6-Differential |
| PC14-OSC32_IN | LSE-External-Oscillator |
| PC15-OSC32_OUT | LSE-External-Oscillator |
| PC2 | IN8-Differential |
| PC3 | IN8-Differential |
| PC5 | IN11-Differential |
| PC6 | Output_TF1TF2 |
| PC7 | Output_TF1TF2 |
| PC8 | Output_TE1TE2 |
| PC9 | Output_TE1TE2 |
| PE10 | IN14-Differential |
| PE11 | IN14-Differential |
| PE13 | IN3-Differential |
| PE7 | IN3-Differential |
| PE9 | IN1-Differential |

## 6. 自检

通过 **6** 项，警告 1 项，失败 0 项。

### 警告

- ⚠️ 电源引脚电气类型不统一：passive × 4（48(VSS), 63(VSS), 74(VSS), 99(VSS)）；power_in × 9（6(VBAT), 23(VSS), 24(VDD), 35(VSSA), 37(VDDA), 49(VDD), 64(VDD), 75(VDD), 100(VDD)） —— ERC 抓不到缺失的电源连线，可用 --power-as-power-in 统一

## 7. 复现命令

```powershell
python ioc2kicad.py --ioc "D:\3phase_inverter\Software\Software.ioc" --out "D:\3phase_inverter\Software\kicad" --preview
```

> `.ioc` 改动后重跑一次即可让符号与 CubeMX 保持同步；
> 生成的符号是独立的（不 `extends` 官方库），KiCad 升级不会影响它。
