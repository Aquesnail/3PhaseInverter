# 3PhaseInverter

三相逆变器项目：**硬件（KiCad + 立创EDA）+ 软件（STM32G474 固件）+ CubeMX 配置 + Simulink 仿真**放在同一个仓库里，保证引脚改动、符号重生成和固件改动能一次性提交、一起回退。

## 目录结构

```
3PhaseInverter/
├── Hardware/
│   ├── G474VC_Core/                 # KiCad 工程（STM32G474VCTx 核心板，出板以此为准）
│   │   ├── G474VC_Core.kicad_pro    # 工程文件
│   │   ├── G474VC_Core.kicad_sch    # 根图纸（连接器 / 采样口 / 复位）
│   │   ├── G474_MCU.kicad_sch       # MCU 页（U2 + 9 组差分采样 + 晶振 + 电源）
│   │   ├── Power.kicad_sch          # 电源页（12V→5V 降压 SY8368QNC、LDO）
│   │   ├── CAN.kicad_sch            # CAN 收发页
│   │   ├── DebugerPower.kicad_sch   # 调试供电页
│   │   ├── *.kicad_sch              # 其它子图纸（PWM/ADC 引出等）
│   │   ├── G474VC_Core.kicad_pcb    # PCB
│   │   └── libs/                    # 工程自带符号库 / 封装库 / 3D 模型
│   │       ├── project/             # 由 CubeMX 配置生成的 STM32 符号
│   │       └── lcsc/                # LCSC 导入的符号与封装
│   └── 逆变器.eprj2                 # 立创EDA专业版工程（含完整立创商城物料/封装，供采购与下单）
├── Simulink/
│   ├── DroopControl.slx             # 下垂控制模型
│   ├── OnlyCurrent.slx              # 电流环模型
│   └── THD.m                        # 总谐波畸变分析脚本
└── Software/
    ├── G474_Software.ioc            # STM32CubeMX 工程（引脚/时钟/外设配置的唯一源头）
    ├── ioc2kicad.py                 # 从 .ioc 生成 KiCad 符号 + 引脚表
    └── kicad/                       # 生成物：引脚表、报告、预览
```

## 引脚/符号的更新流程

`.ioc` 是引脚配置的**唯一权威**（software 和 hardware 共用）：

1. 在 STM32CubeMX 里修改 `Software/G474_Software.ioc`；
2. 运行 `Hardware/G474VC_Core/update_symbol_from_ioc.bat`（内部调用 `Software/ioc2kicad.py`），
   重新生成 `Hardware/G474VC_Core/libs/project/3phase_inverter.kicad_sym`；
3. 原理图里更新 U2 符号，同步改接线；
4. 固件按新引脚表调整；
5. **上述改动放在同一次提交里**，回退时不会出现"符号和 .ioc 不一致"的状态。

## 硬件要点

- MCU：STM32G474VCTx（LQFP100）
- 9 组差分 ADC 输入，分成 3 个 PH2.0x6 接口，每组 = ADC1 + ADC2 + ADC3 各一对（可三相同步采样）
- 每个差分对中 **通道号小的一侧为 `+`**
- PWM：HRTIM1 CHA / CHE / CHF 三对互补输出
- 通信：FDCAN1（经 TCAN1044 收发器）、USART2、SWD
- 电源：12V → 5V（SY8368QNC 同步降压）→ 3.3V（TPS74801）/ 3.3V 模拟（LP5907）

## 仿真（Simulink）

| 文件 | 说明 |
|---|---|
| `Simulink/OnlyCurrent.slx` | 电流环（内环）模型 |
| `Simulink/DroopControl.slx` | 下垂控制（外环）模型 |
| `Simulink/THD.m` | 输出波形 THD 分析脚本 |

## 立创EDA 工程

`Hardware/逆变器.eprj2` 是立创EDA专业版工程（SQLite 单文件），用于**采购/下单/物料核对**；
PCB 出板仍以 `Hardware/G474VC_Core/G474VC_Core.kicad_pcb` 为准，两边改动请保持同步并一起提交。

## 备注

- KiCad 10 自带 Git 集成（工程管理器里 Version Control → Commit / Push / Pull），
  本仓库根目录即仓库根，KiCad 会自动向上发现 `.git`；但它的提交是**整仓库**范围的，
  日常建议用命令行 / VS Code 按路径提交，避免把固件半成品一起提交。
- `.history/` 是 KiCad 自己的本地历史仓库，已在 `.gitignore` 中排除。
