#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ioc2kicad.py —— 把 STM32CubeMX 工程 (.ioc) 转换成项目专属的 KiCad 原理图符号

三方数据按 **封装引脚号(Position)** 合并，不依赖任何 "第几个引脚" 的顺序：
    1. <project>.ioc                    CubeMX 工程：每根引脚分配的功能(Signal) / 用户标签(GPIO_Label)
    2. <CubeMX>/db/mcu/<Mcu.Name>.xml   器件库：引脚号(Position) / 电气类型(Type) / 全部可选功能
    3. KiCad MCU_ST_<family>.kicad_sym  官方符号：基线几何、引脚号、alternate functions

生成结果是一个 **独立（不 (extends)）** 的符号，官方库升级不会影响它。

用法：
    python ioc2kicad.py --ioc D:\\3phase_inverter\\Software\\Software.ioc \\
                        --out D:\\3phase_inverter\\Software\\kicad

主要选项：
    --name-sep   "-"      引脚名各段之间的分隔符
    --no-label            不把 GPIO_Label 拼进引脚名
    --width-scale 1.10    估算引脚名字宽时每个字符的宽度系数（以 1.27mm 字号为基准）
    --no-widen            不自动加宽符号体
    --power-as-power-in   把 CubeMX 判定为 Power 的引脚统一成 power_in
                          （官方 ST 库里 VSS 被写成 passive，与其 VDD 不一致）
    --lib                 指定 KiCad 符号库文件（默认按 Mcu.Family 自动查找）
    --cubemx-db           指定 CubeMX db/mcu 目录
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
#  s-expression：最小解析器 / 输出器
# --------------------------------------------------------------------------- #

class Sym(str):
    """未加引号的原子"""
    __slots__ = ()


class QStr(str):
    """带引号的字符串"""
    __slots__ = ()


class SList(list):
    """括号列表"""
    __slots__ = ()


_TOKEN_RE = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse_sexpr(text: str) -> SList:
    """把 s-expression 文本解析成 SList / Sym / QStr 树。"""
    stack: list[SList] = []
    root: SList | None = None
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("无法解析的位置 %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        if m.group(1):                                   # (
            node = SList()
            if stack:
                stack[-1].append(node)
            else:
                root = node
            stack.append(node)
        elif m.group(2):                                 # )
            if not stack:
                raise ValueError("括号不匹配于 %d" % pos)
            stack.pop()
        elif m.group(3) is not None:                     # "string"
            raw = m.group(3)
            raw = raw.replace('\\"', '"').replace("\\\\", "\\")
            node = QStr(raw)
            if not stack:
                raise ValueError("字符串不在列表内")
            stack[-1].append(node)
        else:                                            # atom
            if not stack:
                raise ValueError("原子不在列表内")
            stack[-1].append(Sym(m.group(4)))
    if root is None:
        raise ValueError("空输入")
    return root


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def render_sexpr(node, indent: int = 0) -> str:
    """按 KiCad 的排版习惯输出。"""
    pad = "\t" * indent
    if isinstance(node, QStr):
        return pad + '"' + _esc(node) + '"'
    if isinstance(node, Sym):
        return pad + str(node)

    head = pad + "("
    i = 0
    while i < len(node) and not isinstance(node[i], SList):
        head += ('"' + _esc(node[i]) + '"') if isinstance(node[i], QStr) else str(node[i])
        if i + 1 < len(node) and not isinstance(node[i + 1], SList):
            head += " "
        i += 1
    if i >= len(node):
        return head + ")"

    out = [head]
    for child in node[i:]:
        out.append(render_sexpr(child, indent + 1))
    out.append(pad + ")")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  小工具
# --------------------------------------------------------------------------- #

def head(node) -> str:
    """列表的第一个原子"""
    return str(node[0]) if node else ""


def children(node, tag: str) -> list:
    return [c for c in node if isinstance(c, SList) and head(c) == tag]


def child(node, tag: str):
    cs = children(node, tag)
    return cs[0] if cs else None


def find_deep(node, tag: str):
    """深度优先找第一个 tag 列表"""
    if isinstance(node, SList):
        if head(node) == tag:
            return node
        for c in node:
            r = find_deep(c, tag)
            if r is not None:
                return r
    return None


def extract_balanced(text: str, start: int) -> str:
    """从 start 处的 '(' 起，取出配平的括号块（正确跳过字符串）。"""
    depth = 0
    i = start
    in_str = False
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    raise ValueError("括号未配平")


def find_symbol_block(text: str, symbol_name: str) -> str | None:
    """在 .kicad_sym 文本里定位某个顶层符号并取出其块。"""
    pat = re.compile(r'\n\s*\(symbol\s+"' + re.escape(symbol_name) + r'"')
    m = pat.search(text)
    if not m:
        return None
    start = text.index("(", m.start())
    return extract_balanced(text, start)


# --------------------------------------------------------------------------- #
#  CubeMX .ioc
# --------------------------------------------------------------------------- #

_UNICODE_ESC_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _ioc_unescape(s: str) -> str:
    """还原 .ioc 里的转义。

    CubeMX 会把非 ASCII 的工程名写成 `Tof\\u9A71\\u52A8...`，冒号写成 `\\:`。
    注意只处理这两种，**不要**动普通反斜杠（Windows 路径原样保留）。
    """
    if "\\" not in s:
        return s
    s = _UNICODE_ESC_RE.sub(lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace("\\:", ":")
    return s


_SYMBOL_BAD_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_name(s: str, fallback: str = "symbol") -> str:
    """符号名 / 文件名安全化：KiCad 不允许这些字符，也避免被当成路径。"""
    out = _SYMBOL_BAD_RE.sub("_", (s or "").strip()).strip("._ ")
    return out or fallback


@dataclass
class IocProject:
    path: Path
    entries: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "IocProject":
        entries: dict[str, str] = {}
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                entries[k.strip()] = v.strip()
        return cls(path=path, entries=entries)

    def get(self, key: str, default: str = "") -> str:
        return _ioc_unescape(self.entries.get(key, default))

    # ---- 器件信息 ----
    @property
    def mcu_name(self) -> str:
        """CubeMX 器件库里的型号（带括号通配，如 STM32G474V(B-C-E)Tx）"""
        return self.get("Mcu.Name")

    @property
    def user_name(self) -> str:
        """CubeMX 界面上的具体型号（如 STM32G474VCTx）——通常与 KiCad 符号名一致"""
        return self.get("Mcu.UserName") or self.get("ProjectManager.DeviceId")

    @property
    def family(self) -> str:
        return self.get("Mcu.Family")

    @property
    def package(self) -> str:
        return self.get("Mcu.Package")

    @property
    def project_name(self) -> str:
        return self.get("ProjectManager.ProjectName")

    @property
    def cpn(self) -> str:
        return self.get("Mcu.CPN")

    @property
    def cubemx_version(self) -> str:
        return self.get("MxCube.Version")

    @property
    def mxdb_version(self) -> str:
        return self.get("MxDb.Version")

    # ---- 引脚分配 ----
    _PIN_KEY_RE = re.compile(r"^(P[A-Z]\d+(?:-[A-Za-z0-9_]+)?)\.(Signal|GPIO_Label|Mode)$")

    def pin_assignments(self) -> dict[str, dict[str, str]]:
        """{ 引脚名: {"signal":..., "label":..., "mode":...} }"""
        out: dict[str, dict[str, str]] = {}
        for k, v in self.entries.items():
            m = self._PIN_KEY_RE.match(k)
            if not m:
                continue
            pin, attr = m.group(1), m.group(2)
            slot = out.setdefault(pin, {})
            key = {"Signal": "signal", "GPIO_Label": "label", "Mode": "mode"}[attr]
            slot[key] = _ioc_unescape(v)
        # 只保留真正有信号分配的引脚
        return {p: a for p, a in out.items() if a.get("signal")}

    def peripheral_modes(self) -> dict[str, str]:
        """{ 外设实例: 工作模式 }，例如 SPI2 -> SPI_MODE_MASTER

        注意要排除引脚键（PA0.Mode=IN1-Differential 这种），
        引脚名形如 P<端口><序号>，和外设实例名（SPI2/USART1/TIM3）容易混淆。
        """
        out = {}
        for k, v in self.entries.items():
            m = re.match(r"^([A-Z][A-Z0-9]*\d+)\.Mode$", k)
            if not m:
                continue
            name = m.group(1)
            if re.match(r"^P[A-Z]\d+$", name):      # 引脚键，不是外设
                continue
            out[name] = v
        return out

    def pin_modes(self) -> dict[str, str]:
        """{ 引脚名: 工作模式 }，例如 PA0 -> IN1-Differential（差分对信息在这里）"""
        out = {}
        for k, v in self.entries.items():
            m = re.match(r"^(P[A-Z]\d+(?:-[A-Za-z0-9_]+)?)\.Mode$", k)
            if m:
                out[m.group(1)] = v
        return out


# --------------------------------------------------------------------------- #
#  CubeMX 器件数据库 XML
# --------------------------------------------------------------------------- #

NS = "{http://mcd.rou.st.com/modules.php?name=mcu}"


@dataclass
class McuPin:
    name: str           # 例如 PB13 / PF0-OSC_IN / VSS
    position: int       # 封装引脚号
    cube_type: str      # Power / I/O / Input / Output ...
    signals: list[str]  # 该引脚全部可选功能


@dataclass
class McuDb:
    path: Path
    ref_name: str = ""
    package: str = ""
    by_position: dict[int, McuPin] = field(default_factory=dict)
    by_name: dict[str, list[McuPin]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "McuDb":
        tree = ET.parse(str(path))
        root = tree.getroot()
        db = cls(path=path,
                 ref_name=root.get("RefName", "") or "",
                 package=root.get("Package", "") or "")
        for el in root.iter(NS + "Pin"):
            name = (el.get("Name") or "").strip()
            pos_s = (el.get("Position") or "").strip()
            if not name or not pos_s.isdigit():
                continue
            pin = McuPin(
                name=name,
                position=int(pos_s),
                cube_type=(el.get("Type") or "").strip(),
                signals=[(s.get("Name") or "").strip()
                         for s in el.findall(NS + "Signal")
                         if (s.get("Name") or "").strip()],
            )
            db.by_position[pin.position] = pin
            db.by_name.setdefault(pin.name, []).append(pin)
        return db


# --------------------------------------------------------------------------- #
#  电气类型映射
# --------------------------------------------------------------------------- #

CUBE_TYPE_MAP = {
    "Power": "power_in",
    "I/O": "bidirectional",
    "Input": "input",
    "Output": "output",
    "Reset": "input",
    "Boot": "input",
}

# 依据 CubeMX 的 Signal 名字细化电气类型（按顺序匹配，第一条命中即用）。
# 官方 ST 符号里 284 个 alternate 全是 bidirectional，所以这一层是 ERC 真正可用的关键。
SIGNAL_TYPE_RULES = [
    (r"^ADC\d+_IN\d*$",        "input"),
    (r"^ADC\d+_EXTI\d*$",      "input"),
    (r"^OPAMP\d+_VIN",         "input"),
    (r"^OPAMP\d+_VOUT$",       "output"),
    (r"^COMP\d+_IN",           "input"),
    (r"^COMP\d+_OUT$",         "output"),
    (r"^DAC\d+_OUT\d*$",       "output"),
    (r"^(USART|UART|LPUART)\d+_TX$",  "output"),
    (r"^(USART|UART|LPUART)\d+_RX$",  "input"),
    (r"^(SPI|I2S)\d+_MOSI$",   "output"),
    (r"^(SPI|I2S)\d+_MISO$",   "input"),
    (r"^(SPI|I2S)\d+_SCK$",    "output"),
    (r"^(SPI|I2S)\d+_NSS$",    "output"),
    (r"^I2C\d+_SDA$",          "bidirectional"),
    (r"^I2C\d+_SCL$",          "output"),
    (r"^SYS_JTMS-SWDIO$",      "bidirectional"),
    (r"^SYS_JTCK-SWCLK$",      "input"),
    (r"^SYS_JTDO-SWO$",        "output"),
    (r"^SYS_JTDI$",            "input"),
    (r"^SYS_NJTRST$",          "input"),
    (r"^SYS_WKUP\d*$",         "input"),
    (r"^RCC_OSC_IN$",          "input"),
    (r"^RCC_OSC_OUT$",         "output"),
    (r"^RCC_OSC32_IN$",        "input"),
    (r"^RCC_OSC32_OUT$",       "output"),
    (r"^GPIO_Output$",         "output"),
    (r"^GPIO_Input$",          "input"),
    (r"^GPIO_Analog$",         "input"),
    (r"^GPIO_EXTI",            "input"),
]


def resolve_electrical_type(cube_type: str, signal: str,
                            extra_rules: list | None = None) -> tuple[str, str]:
    """返回 (kicad_type, 依据说明)"""
    rules = list(extra_rules or []) + SIGNAL_TYPE_RULES
    for pat, ktype in rules:
        if re.search(pat, signal or ""):
            return ktype, "signal:%s" % pat
    return CUBE_TYPE_MAP.get(cube_type, "passive"), "cubeType:%s" % cube_type


# --------------------------------------------------------------------------- #
#  KiCad 符号库
# --------------------------------------------------------------------------- #

@dataclass
class KicadPin:
    number: str
    name: str
    etype: str
    style: str
    node: SList          # 原始的 (pin ...) 列表，便于原地改写
    at: SList            # (at x y angle)
    length: float
    alternates: list[tuple[str, str]] = field(default_factory=list)

    @property
    def x(self) -> float:
        return float(self.at[1])

    @property
    def y(self) -> float:
        return float(self.at[2])

    @property
    def angle(self) -> float:
        return float(self.at[3]) if len(self.at) > 3 else 0.0


@dataclass
class KicadSymbol:
    lib_path: Path
    lib_version: str
    lib_generator: str
    lib_generator_version: str
    name: str                      # 要生成的符号名
    source_name: str               # 基线符号名
    tree: SList                    # 基线符号的 (symbol ...) 树
    units: list[SList] = field(default_factory=list)
    pins: list[KicadPin] = field(default_factory=list)


def locate_kicad_lib(family: str, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise SystemExit("指定的符号库不存在: %s" % p)
        return p

    candidates = []
    if os.environ.get("KICAD10_SYMBOL_DIR"):
        candidates.append(Path(os.environ["KICAD10_SYMBOL_DIR"]))
    candidates += [
        Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols"),
        Path(r"C:\Program Files\KiCad\9.0\share\kicad\symbols"),
        Path("/usr/share/kicad/symbols"),
        Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
    ]
    fname = "MCU_ST_%s.kicad_sym" % family
    for d in candidates:
        p = d / fname
        if p.is_file():
            return p
    raise SystemExit(
        "找不到符号库 %s。请用 --lib 指定，或设置环境变量 KICAD10_SYMBOL_DIR。\n"
        "已尝试: %s" % (fname, ", ".join(str(c) for c in candidates)))


def load_kicad_symbol(lib_path: Path, symbol_name: str, new_name: str) -> KicadSymbol:
    text = lib_path.read_text(encoding="utf-8", errors="strict")

    m = re.search(r"\(version\s+(\d+)\)", text)
    lib_version = m.group(1) if m else "20211014"
    m = re.search(r'\(generator\s+"([^"]*)"\)', text)
    lib_generator = m.group(1) if m else "kicad_symbol_editor"
    m = re.search(r'\(generator_version\s+"([^"]*)"\)', text)
    lib_generator_version = m.group(1) if m else ""

    # 具体型号符号（可能 extends 基线符号）
    block = find_symbol_block(text, symbol_name)
    if block is None:
        raise SystemExit("符号库里找不到符号 '%s'（库: %s）" % (symbol_name, lib_path))
    concrete_tree = parse_sexpr(block)

    ext = child(concrete_tree, "extends")
    if ext is not None:
        source_name = str(ext[1])
        base_block = find_symbol_block(text, source_name)
        if base_block is None:
            raise SystemExit("基线符号 '%s' 不在库中（KiCad 要求 extends 的同库存在）" % source_name)
        base_tree = parse_sexpr(base_block)
    else:
        source_name = symbol_name
        base_tree = concrete_tree

    sym = KicadSymbol(
        lib_path=lib_path, lib_version=lib_version,
        lib_generator=lib_generator, lib_generator_version=lib_generator_version,
        name=new_name, source_name=source_name, tree=base_tree,
    )

    # 收集单位子符号里的引脚
    for unit in children(base_tree, "symbol"):
        sym.units.append(unit)
        for pin_node in children(unit, "pin"):
            at = child(pin_node, "at")
            length = child(pin_node, "length")
            name_node = child(pin_node, "name")
            num_node = child(pin_node, "number")
            if at is None or name_node is None or num_node is None:
                continue
            alts = []
            for a in children(pin_node, "alternate"):
                alts.append((str(a[1]), str(a[2]) if len(a) > 2 else "bidirectional"))
            sym.pins.append(KicadPin(
                number=str(num_node[1]),
                name=str(name_node[1]),
                etype=str(pin_node[1]),
                style=str(pin_node[2]) if len(pin_node) > 2 else "line",
                node=pin_node,
                at=at,
                length=float(length[1]) if length is not None else 2.54,
                alternates=alts,
            ))

    # 子符号重命名为 <新符号名>_<unit>_<demorgan>
    for unit in sym.units:
        unit_name = str(unit[1])
        mm = re.match(re.escape(source_name) + r"_(.+)$", unit_name)
        suffix = mm.group(1) if mm else unit_name
        unit[1] = QStr("%s_%s" % (new_name, suffix))

    sym.tree[1] = QStr(new_name)
    _carry_over_properties(sym.tree, concrete_tree)
    return sym


_PROP_CARRY = ("Footprint", "Datasheet", "Description", "ki_keywords", "ki_fp_filters")


def _carry_over_properties(target_tree: SList, concrete_tree: SList) -> None:
    """把具体型号符号上更精确的属性搬到基线符号树上。"""
    for tag in _PROP_CARRY:
        src = None
        for p in children(concrete_tree, "property"):
            if str(p[1]) == tag:
                src = p
                break
        if src is None:
            continue
        dst = None
        for p in children(target_tree, "property"):
            if str(p[1]) == tag:
                dst = p
                break
        if dst is None:
            continue
        dst[2] = src[2]
    # Value 属性 = 新符号名
    for p in children(target_tree, "property"):
        if str(p[1]) == "Value":
            p[2] = QStr(str(target_tree[1]))


def set_property(tree: SList, name: str, value: str, hidden: bool = True) -> None:
    for p in children(tree, "property"):
        if str(p[1]) == name:
            p[2] = QStr(value)
            return
    # 新建一个
    node = SList([Sym("property"), QStr(name), QStr(value),
                  SList([Sym("at"), Sym("0"), Sym("0"), Sym("0")]),
                  SList([Sym("show_name"), Sym("no")]),
                  SList([Sym("do_not_autoplace"), Sym("no")])])
    if hidden:
        node.append(SList([Sym("hide"), Sym("yes")]))
    node.append(SList([Sym("effects"),
                       SList([Sym("font"), SList([Sym("size"), Sym("1.27"), Sym("1.27")])])]))
    # 插到最后一个 property 之后
    last = -1
    for i, c in enumerate(tree):
        if isinstance(c, SList) and head(c) == "property":
            last = i
    tree.insert(last + 1, node)


# --------------------------------------------------------------------------- #
#  几何：自动加宽符号体
# --------------------------------------------------------------------------- #

def widen_body(sym: KicadSymbol, width_scale: float, gap: float = 2.54,
               grid: float = 1.27) -> dict:
    """按最长引脚名调整符号体尺寸，并同步平移对应边上的引脚。

    * 左右方向：侧边引脚名向符号体内延伸，两侧加起来放不下就左右各加宽。
    * 上下方向：上下排引脚的**名字是竖着写的**，会伸进符号体；
      如果伸得比最靠边的侧边引脚还深，就把符号体上下拉高，
      否则会和侧边引脚名压在一起（实测 100 脚 G474 就出现了这个问题）。

    只在需要时才调整，返回改动摘要。
    """
    rect = None
    for unit in sym.units:
        r = child(unit, "rectangle")
        if r is not None:
            rect = r
            break
    if rect is None:
        return {"widened": False, "reason": "符号里没有 rectangle"}

    start = child(rect, "start")
    end = child(rect, "end")
    x_left, y_bottom = float(start[1]), float(start[2])
    x_right, y_top = float(end[1]), float(end[2])
    char_w = 1.27 * width_scale

    info: dict = {"widened": False, "old_body_x": [x_left, x_right],
                  "old_body_y": [y_bottom, y_top]}

    # ---------------- 左右 ----------------
    left_req = right_req = 0.0
    left_names: list[str] = []
    right_names: list[str] = []

    for p in sym.pins:
        if not p.name:
            continue
        w = len(p.name) * char_w
        # 角度 0 且 x 在左侧 → 引脚朝右，名字在符号体内向右延伸
        if p.angle == 0 and p.x <= x_left:
            left_req = max(left_req, w)
            left_names.append(p.name)
        elif p.angle == 180 and p.x >= x_right:
            right_req = max(right_req, w)
            right_names.append(p.name)

    cur_left = abs(x_left)
    cur_right = abs(x_right)
    extra_left = max(0.0, (left_req + gap / 2) - cur_left)
    extra_right = max(0.0, (right_req + gap / 2) - cur_right)
    extra_left = math.ceil(extra_left / grid) * grid
    extra_right = math.ceil(extra_right / grid) * grid

    if extra_left > 0 or extra_right > 0:
        for p in sym.pins:
            if p.angle == 0 and p.x <= x_left:
                p.at[1] = Sym(_fmt(p.x - extra_left))
            elif p.angle == 180 and p.x >= x_right:
                p.at[1] = Sym(_fmt(p.x + extra_right))
        start[1] = Sym(_fmt(x_left - extra_left))
        end[1] = Sym(_fmt(x_right + extra_right))
        x_left -= extra_left
        x_right += extra_right
        info.update(widened=True, extra_left=extra_left, extra_right=extra_right,
                    left_longest=max(left_names, key=len) if left_names else "",
                    right_longest=max(right_names, key=len) if right_names else "")

    # ---------------- 上下 ----------------
    top_names = [p.name for p in sym.pins if p.angle == 270.0 and p.name]
    bot_names = [p.name for p in sym.pins if p.angle == 90.0 and p.name]
    side_pins = [p for p in sym.pins if p.angle in (0.0, 180.0)]

    extra_top = extra_bot = 0.0
    if side_pins and (top_names or bot_names):
        top_w = max((len(n) * char_w for n in top_names), default=0.0)
        bot_w = max((len(n) * char_w for n in bot_names), default=0.0)
        topmost = max(p.y for p in side_pins)
        bottommost = min(p.y for p in side_pins)
        req_top = topmost + 0.635 + gap + top_w
        req_bot = bottommost - 0.635 - gap - bot_w
        extra_top = math.ceil(max(0.0, req_top - y_top) / grid) * grid
        extra_bot = math.ceil(max(0.0, y_bottom - req_bot) / grid) * grid

    if extra_top > 0 or extra_bot > 0:
        for p in sym.pins:
            if p.angle == 270.0:
                p.at[2] = Sym(_fmt(p.y + extra_top))
            elif p.angle == 90.0:
                p.at[2] = Sym(_fmt(p.y - extra_bot))
        end[2] = Sym(_fmt(y_top + extra_top))
        start[2] = Sym(_fmt(y_bottom - extra_bot))
        # Reference / Value / Footprint 等属性跟着符号体走，别落进体内
        for prop in children(sym.tree, "property"):
            at = child(prop, "at")
            if at is None or len(at) < 3:
                continue
            py = float(at[2])
            if py > y_top:
                at[2] = Sym(_fmt(py + extra_top))
            elif py < y_bottom:
                at[2] = Sym(_fmt(py - extra_bot))
        y_top += extra_top
        y_bottom -= extra_bot
        info.update(widened=True, extra_top=extra_top, extra_bottom=extra_bot)

    info["new_body_x"] = [round(x_left, 3), round(x_right, 3)]
    info["new_body_y"] = [round(y_bottom, 3), round(y_top, 3)]
    return info


def _fmt(v: float) -> str:
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# --------------------------------------------------------------------------- #
#  转换主体
# --------------------------------------------------------------------------- #

@dataclass
class PinRow:
    position: int
    db_name: str
    cube_type: str
    kicad_name: str
    new_name: str
    kicad_etype: str
    new_etype: str
    new_style: str
    signal: str
    label: str
    alt_count: int
    type_reason: str
    changed_name: bool
    changed_type: bool


def convert(args) -> int:
    ioc_path = Path(args.ioc).resolve()
    if not ioc_path.is_file():
        raise SystemExit("找不到 .ioc 文件: %s" % ioc_path)
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. CubeMX 工程 ----
    ioc = IocProject.load(ioc_path)
    if not ioc.mcu_name:
        raise SystemExit(".ioc 里没有 Mcu.Name，无法确定器件")
    print("[1/6] CubeMX 工程 : %s" % ioc_path.name)
    print("      器件        : %s  (UserName=%s)" % (ioc.mcu_name, ioc.user_name))
    print("      封装/家族   : %s / %s" % (ioc.package, ioc.family))
    print("      CubeMX      : %s  (DB %s)" % (ioc.cubemx_version, ioc.mxdb_version))

    # ---- 2. CubeMX 器件库 ----
    db_dir = Path(args.cubemx_db) if args.cubemx_db else Path(
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db\mcu")
    xml_path = db_dir / ("%s.xml" % ioc.mcu_name)
    if not xml_path.is_file():
        raise SystemExit("找不到器件库文件: %s" % xml_path)
    db = McuDb.load(xml_path)
    print("[2/6] 器件库      : %s  (%d 个封装引脚)" % (xml_path.name, len(db.by_position)))

    # ---- 3. KiCad 符号库 ----
    lib_path = locate_kicad_lib(ioc.family, args.lib)
    # 工程名可能带中文 / 被 CubeMX 转义，符号名和文件名都要安全化
    proj = safe_name(ioc.project_name or ioc_path.stem, "CubeMX")
    new_symbol_name = (safe_name(args.symbol_name) if args.symbol_name
                       else "%s_%s" % (safe_name(ioc.user_name), proj))
    sym = load_kicad_symbol(lib_path, ioc.user_name, new_symbol_name)
    print("[3/6] KiCad 符号库: %s" % lib_path.name)
    print("      基线符号    : %s  → 生成 %s" % (sym.source_name, sym.name))
    print("      引脚数      : %d" % len(sym.pins))

    # ---- 4. 三方合并 ----
    assignments = ioc.pin_assignments()
    extra_rules = []
    if args.rules and Path(args.rules).is_file():
        raw = json.loads(Path(args.rules).read_text(encoding="utf-8"))
        extra_rules = [(r["pattern"], r["type"]) for r in raw.get("rules", [])]
        print("      附加规则    : %s" % args.rules)

    # 按引脚号索引 KiCad 引脚
    pin_by_number: dict[str, KicadPin] = {}
    for p in sym.pins:
        pin_by_number.setdefault(p.number, p)

    matched_pins: set[str] = set()
    rows: list[PinRow] = []
    warnings: list[str] = []

    mode_hint = ioc.peripheral_modes()

    for number in sorted(pin_by_number, key=lambda s: (len(s), s)):
        kp = pin_by_number[number]
        dbpin = db.by_position.get(int(number))
        if dbpin is None:
            warnings.append("引脚 %s 在 CubeMX 器件库里没有对应 Position" % number)
            continue

        assign = assignments.get(dbpin.name, {})
        if not assign:
            continue

        matched_pins.add(dbpin.name)
        signal = assign.get("signal", "")
        label = assign.get("label", "")

        # ---- 引脚名 ----
        pin_label = dbpin.name
        if args.strip_pin_suffix and "-" in pin_label:
            # PA0-WKUP → PA0，PD0-OSC_IN → PD0（CubeMX 把复用功能写进了引脚名）
            pin_label = pin_label.split("-")[0]
        parts = [pin_label]
        if signal:
            parts.append(signal)
        if label and not args.no_label:
            parts.append(label)
        new_name = args.name_sep.join(parts)

        # ---- 电气类型 ----
        new_etype, reason = resolve_electrical_type(dbpin.cube_type, signal, extra_rules)

        rows.append(PinRow(
            position=int(number),
            db_name=dbpin.name,
            cube_type=dbpin.cube_type,
            kicad_name=kp.name,
            new_name=new_name,
            kicad_etype=kp.etype,
            new_etype=new_etype,
            new_style=kp.style,
            signal=signal,
            label=label,
            alt_count=len(kp.alternates),
            type_reason=reason,
            changed_name=(new_name != kp.name),
            changed_type=(new_etype != kp.etype),
        ))

    # .ioc 里有、但 KiCad 符号里没配到引脚号的
    missing = sorted(set(assignments) - matched_pins)
    for name in missing:
        warnings.append(".ioc 里分配的引脚 '%s' 未能在 KiCad 符号中找到（未写入符号）" % name)

    # ---- 5. 改写符号 ----
    by_number = {r.position: r for r in rows}
    power_fixed: list[str] = []
    for p in sym.pins:
        if not p.number.isdigit():
            continue
        num = int(p.number)
        r = by_number.get(num)
        if r is not None:
            name_node = child(p.node, "name")
            if name_node is not None:
                name_node[1] = QStr(r.new_name)
            p.node[1] = Sym(r.new_etype)
            p.name = r.new_name
            p.etype = r.new_etype
            continue

        # 未分配的引脚：可选地把 CubeMX 判定的电源脚统一成 power_in。
        # 官方 ST 符号里 VDD/VDDA 是 power_in，但 VSS 却是 passive，前后不一致，
        # 会让 ERC 漏掉接地缺失；--power-as-power-in 用来抹平这个差异。
        if args.power_as_power_in:
            dbpin = db.by_position.get(num)
            if (dbpin is not None and dbpin.cube_type == "Power"
                    and p.etype != "power_in"
                    and not re.match(r"^VCAP", p.name)):
                # 注意：VCAP* 是芯片内部稳压器的**输出**电容脚，官方写成 power_out 是对的，
                # 不能一起改成 power_in，否则 ERC 会误报。
                power_fixed.append("%s(%s: %s→power_in)" % (p.number, p.name, p.etype))
                p.node[1] = Sym("power_in")
                p.etype = "power_in"

    # ---- 6. 加宽 + 溯源属性 ----
    widen_info = {"widened": False, "reason": "--no-widen"}
    if not args.no_widen:
        widen_info = widen_body(sym, args.width_scale)
    print("[4/6] 几何调整    : %s" % (json.dumps(widen_info, ensure_ascii=False)))

    set_property(sym.tree, "CubeMX_Project", "%s.ioc" % proj)
    set_property(sym.tree, "CubeMX_Version", ioc.cubemx_version or "?")
    set_property(sym.tree, "CubeMX_Config",
                 "pins=%d assigned, ioc=%s, mxdb=%s"
                 % (len(db.by_position), ioc_path.name, ioc.mxdb_version))

    # ---- 输出库文件 ----
    lib_out = out_dir / ("%s.kicad_sym" % proj)
    header = (
        "(kicad_symbol_lib\n"
        "\t(version %s)\n"
        '\t(generator "%s")\n'
        '%s'
    ) % (sym.lib_version, sym.lib_generator,
         ('\t(generator_version "%s")\n' % sym.lib_generator_version)
         if sym.lib_generator_version else "")
    body = render_sexpr(sym.tree, indent=1)
    text = header + body + "\n)\n"
    lib_out.write_text(text, encoding="utf-8")
    print("[5/6] 生成符号库  : %s" % lib_out)

    # ---- 渲染预览（同时也是符号结构是否合法的硬验证） ----
    preview_info = None
    if args.preview:
        preview_info = render_preview(lib_out, sym.name, out_dir, args.preview_width)
        if preview_info.get("ok"):
            print("      预览        : %s" % (preview_info.get("png") or preview_info.get("svg")))
            if preview_info.get("note"):
                print("      （%s）" % preview_info["note"])
        else:
            print("      预览失败    : %s" % preview_info.get("error"))
            print("      ⚠ kicad-cli 打不开这个符号文件，通常意味着生成的 .kicad_sym 有结构问题")

    # ---- 引脚表 CSV（供 KiCad 符号编辑器粘贴） ----
    csv_out = out_dir / ("%s_pintable.csv" % proj)
    with csv_out.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("number,name,electrical_type\n")
        for p in sym.pins:
            f.write('%s,"%s",%s\n' % (p.number, p.name, p.etype))

    # ---- 报告 ----
    report_out = out_dir / ("%s_report.md" % proj)
    checks = _self_check(sym, db, assignments, rows, warnings, power_fixed)
    report_out.write_text(
        _render_report(ioc, ioc_path, db, xml_path, lib_path, sym,
                       rows, warnings, checks, widen_info, mode_hint,
                       lib_out, csv_out, preview_info, power_fixed),
        encoding="utf-8")

    print("[6/6] 报告        : %s" % report_out.name)
    print()
    print("自检: %d 项通过, %d 项警告, %d 项失败"
          % (checks["pass"], len(checks["warn"]), len(checks["fail"])))
    for w in checks["warn"]:
        print("  [警告] %s" % w)
    for f_ in checks["fail"]:
        print("  [失败] %s" % f_)
    return 0 if not checks["fail"] else 2


# --------------------------------------------------------------------------- #
#  自检 + 报告
# --------------------------------------------------------------------------- #

def _self_check(sym: KicadSymbol, db: McuDb, assignments: dict,
                rows: list[PinRow], warnings: list[str],
                power_fixed: list[str] | None = None) -> dict:
    ok, warn, fail = 0, [], []

    # 1) 引脚总数与器件库一致
    if len(sym.pins) == len(db.by_position):
        ok += 1
    else:
        fail.append("符号引脚数 %d ≠ 器件库引脚数 %d" % (len(sym.pins), len(db.by_position)))

    # 2) 引脚号唯一
    nums = [p.number for p in sym.pins]
    dup = {n for n in nums if nums.count(n) > 1}
    if dup:
        fail.append("引脚号重复: %s" % ", ".join(sorted(dup)))
    else:
        ok += 1

    # 3) 引脚名非空
    empties = [p.number for p in sym.pins if not p.name.strip()]
    if empties:
        fail.append("引脚名为空: %s" % ", ".join(empties))
    else:
        ok += 1

    # 4) 所有 .ioc 已分配引脚都写进了符号
    written = {r.db_name for r in rows}
    missed = sorted(set(assignments) - written)
    if missed:
        fail.append("以下 .ioc 分配未写入符号: %s" % ", ".join(missed))
    else:
        ok += 1

    # 5) 引脚号与 CubeMX 器件库一一对应
    mismatch = []
    for p in sym.pins:
        if not p.number.isdigit():
            continue
        if int(p.number) not in db.by_position:
            mismatch.append(p.number)
    if mismatch:
        fail.append("以下符号引脚号在器件库中不存在: %s" % ", ".join(mismatch))
    else:
        ok += 1

    # 6) 已分配引脚的类型不再是清一色 bidirectional
    assigned_types = {r.new_etype for r in rows}
    if len(assigned_types) >= 1 and all(t == "bidirectional" for t in assigned_types) and rows:
        warn.append("所有已分配引脚的电气类型仍是 bidirectional，请检查规则")
    else:
        ok += 1

    # 7) 上下排引脚名过长（名字竖向书写，太长会压到符号体中部）
    body_h = 0.0
    for unit in sym.units:
        rect = child(unit, "rectangle")
        if rect is not None:
            body_h = abs(float(child(rect, "end")[2]) - float(child(rect, "start")[2]))
            break
    long_vertical = []
    if body_h > 0:
        limit = body_h / 2 - 2.54
        for p in sym.pins:
            if p.angle in (90.0, 270.0) and len(p.name) * 1.27 * 1.10 > limit:
                long_vertical.append("%s(%s)" % (p.number, p.name))
    if long_vertical:
        warn.append("上下排引脚名较长、可能竖向挤压: %s" % ", ".join(long_vertical))

    # 8) 电源引脚的电气类型是否统一（官方库里 VSS 常被写成 passive）
    num_to_pin = {p.number: p for p in sym.pins}
    power_types: dict[str, list[str]] = {}
    for num, dbpin in db.by_position.items():
        if dbpin.cube_type != "Power":
            continue
        kp = num_to_pin.get(str(num))
        if kp is None:
            continue
        if re.match(r"^VCAP", kp.name):
            continue      # 内部稳压器输出脚，power_out 本身就是正确的
        power_types.setdefault(kp.etype, []).append("%s(%s)" % (kp.number, kp.name))
    if len(power_types) > 1:
        detail = "；".join("%s × %d（%s）" % (t, len(v), ", ".join(v))
                          for t, v in sorted(power_types.items()))
        hint = "" if power_fixed else "，可用 --power-as-power-in 统一"
        warn.append("电源引脚电气类型不统一：%s —— ERC 抓不到缺失的电源连线%s"
                    % (detail, hint))
    else:
        ok += 1

    if power_fixed:
        warn.append("已按 --power-as-power-in 统一为 power_in: %s" % ", ".join(power_fixed))

    warn.extend(warnings)
    return {"pass": ok, "warn": warn, "fail": fail}


def find_kicad_cli() -> str | None:
    cands = [
        os.environ.get("KICAD_CLI"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
        r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
        "/usr/bin/kicad-cli",
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    ]
    for c in cands:
        if c and Path(c).is_file():
            return c
    from shutil import which
    return which("kicad-cli")


def find_browser() -> str | None:
    cands = [
        os.environ.get("KICAD_PREVIEW_BROWSER"),
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


def render_preview(lib_file: Path, symbol_name: str, out_dir: Path,
                   px_width: int = 1240) -> dict:
    """用 kicad-cli 把符号导出成 SVG，再用无头浏览器截一张 PNG 便于目视校验。

    kicad-cli 能成功导出，本身就说明符号文件结构合法、KiCad 能正常加载。
    """
    import subprocess
    import tempfile

    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        return {"ok": False, "error": "找不到 kicad-cli"}

    r = subprocess.run([kicad_cli, "sym", "export", "svg",
                        "--symbol", symbol_name, "--black-and-white",
                        "-o", str(out_dir), str(lib_file)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return {"ok": False, "error": "kicad-cli 导出失败（exit %d）: %s"
                % (r.returncode, (r.stderr or r.stdout).strip()[:400])}

    svg = out_dir / ("%s_unit1.svg" % symbol_name)
    if not svg.is_file():
        return {"ok": False, "error": "没有生成 SVG: %s" % svg}

    txt = svg.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', txt) or \
        re.search(r'width="([\d.]+)mm"[^>]*?height="([\d.]+)mm"', txt)
    if not m:
        return {"ok": True, "svg": str(svg), "png": None, "note": "读不出 SVG 尺寸"}
    w_mm, h_mm = float(m.group(1)), float(m.group(2))

    browser = find_browser()
    if not browser:
        return {"ok": True, "svg": str(svg), "png": None,
                "width_mm": w_mm, "height_mm": h_mm, "note": "没找到 Edge/Chrome，只出了 SVG"}

    px_h = int(math.ceil(px_width * h_mm / w_mm)) + 40
    html = Path(tempfile.gettempdir()) / "kicad_symbol_preview.html"
    html.write_text(
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        'html,body{margin:0;padding:0;background:#fff}'
        'img{display:block;width:%dpx}</style></head><body>'
        '<img src="%s"></body></html>' % (px_width, svg.resolve().as_uri()),
        encoding="utf-8")

    png = out_dir / ("%s_preview.png" % symbol_name)
    if png.exists():
        png.unlink()
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--virtual-time-budget=4000",
                    "--window-size=%d,%d" % (px_width, px_h),
                    "--screenshot=%s" % png, html.resolve().as_uri()],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"ok": True, "svg": str(svg),
            "png": str(png) if png.is_file() else None,
            "width_mm": w_mm, "height_mm": h_mm,
            "px": "%d x %d" % (px_width, px_h)}


def _describe_geometry(info: dict) -> str:
    if not info.get("widened"):
        return "无需调整（%s）" % info.get("reason", "引脚名放得下")
    bits = []
    if info.get("extra_left") or info.get("extra_right"):
        bits.append("左右加宽 %s / %s mm（X: %s → %s）"
                    % (info.get("extra_left", 0), info.get("extra_right", 0),
                       info.get("old_body_x"), info.get("new_body_x")))
    if info.get("extra_top") or info.get("extra_bottom"):
        bits.append("上下拉高 %s / %s mm（Y: %s → %s）"
                    % (info.get("extra_top", 0), info.get("extra_bottom", 0),
                       info.get("old_body_y"), info.get("new_body_y")))
    return "；".join(bits) if bits else "无需调整"


def _render_report(ioc: IocProject, ioc_path: Path, db: McuDb, xml_path: Path,
                   lib_path: Path, sym: KicadSymbol, rows: list[PinRow],
                   warnings: list[str], checks: dict, widen_info: dict,
                   mode_hint: dict, lib_out: Path, csv_out: Path,
                   preview_info: dict | None = None,
                   power_fixed: list[str] | None = None) -> str:
    L: list[str] = []
    ap = L.append
    ap("# %s —— CubeMX → KiCad 符号生成报告\n" % (ioc.project_name or ioc_path.stem))
    ap("由 `ioc2kicad.py` 自动生成。\n")

    ap("## 1. 数据来源\n")
    ap("| 项 | 值 |")
    ap("|---|---|")
    ap("| 工程文件 | `%s` |" % ioc_path)
    ap("| 器件 | **%s**（`%s`） |" % (ioc.user_name, ioc.mcu_name))
    ap("| 封装 / 家族 | %s / %s |" % (ioc.package, ioc.family))
    if ioc.cpn:
        ap("| 订货型号 | %s |" % ioc.cpn)
    ap("| CubeMX 版本 | %s（器件库 %s） |" % (ioc.cubemx_version, ioc.mxdb_version))
    ap("| 器件库 XML | `%s` |" % xml_path)
    ap("| KiCad 符号库 | `%s` |" % lib_path)
    ap("| 基线符号 | `%s` |" % sym.source_name)
    ap("| **生成的符号** | **`%s`** |" % sym.name)
    ap("")

    ap("## 2. 生成结果\n")
    ap("| 项 | 值 |")
    ap("|---|---|")
    ap("| 符号库文件 | `%s` |" % lib_out)
    ap("| 引脚表 CSV | `%s` |" % csv_out)
    ap("| 符号引脚总数 | %d（与器件库一致） |" % len(sym.pins))
    ap("| .ioc 中已分配引脚 | %d |" % len(rows))
    ap("| 保留的 alternate functions | %d 条 |"
       % sum(len(p.alternates) for p in sym.pins))
    ap("| 符号体尺寸调整 | %s |" % _describe_geometry(widen_info))
    if preview_info and preview_info.get("ok"):
        ap("| 预览图 | `%s` |" % (preview_info.get("png") or preview_info.get("svg")))
    ap("")

    ap("## 3. 引脚对照表（已分配）\n")
    ap("| 脚号 | CubeMX 引脚 | CubeMX 类型 | 分配功能 | 用户标签 | 生成引脚名 | 电气类型 | 依据 | 复用功能数 |")
    ap("|---:|---|---|---|---|---|---|---|---:|")
    for r in sorted(rows, key=lambda x: x.position):
        ap("| %d | %s | %s | %s | %s | `%s` | **%s** | %s | %d |"
           % (r.position, r.db_name, r.cube_type, r.signal or "—", r.label or "—",
              r.new_name, r.new_etype, r.type_reason, r.alt_count))
    ap("")

    changed_names = [r for r in rows if r.changed_name]
    changed_types = [r for r in rows if r.changed_type]
    ap("## 4. 改动摘要\n")
    ap("- 引脚名被改写：**%d** 根（其余引脚保持官方原名）" % len(changed_names))
    ap("- 电气类型被改写：**%d** 根" % len(changed_types))
    if power_fixed:
        ap("- 电源引脚统一为 `power_in`：**%d** 根（%s）"
           % (len(power_fixed), ", ".join(power_fixed)))
    if changed_types:
        ap("")
        ap("| 脚号 | 原类型 | 新类型 |")
        ap("|---:|---|---|")
        for r in sorted(changed_types, key=lambda x: x.position):
            ap("| %d | %s | %s |" % (r.position, r.kicad_etype, r.new_etype))
    ap("")

    pin_modes = ioc.pin_modes()
    periph_modes = ioc.peripheral_modes()
    if periph_modes or pin_modes:
        ap("## 5. 工作模式\n")
        if periph_modes:
            ap("**外设实例**（判断信号方向的依据）\n")
            for k in sorted(periph_modes):
                ap("- `%s` → `%s`" % (k, periph_modes[k]))
            ap("")
        if pin_modes:
            ap("**引脚工作模式**（差分对信息在这里）\n")
            ap("| 引脚 | 模式 |")
            ap("|---|---|")
            for k in sorted(pin_modes):
                ap("| %s | %s |" % (k, pin_modes[k]))
            ap("")

    ap("## 6. 自检\n")
    ap("通过 **%d** 项，警告 %d 项，失败 %d 项。\n"
       % (checks["pass"], len(checks["warn"]), len(checks["fail"])))
    if checks["fail"]:
        ap("### 失败\n")
        for f_ in checks["fail"]:
            ap("- ❌ %s" % f_)
        ap("")
    if checks["warn"]:
        ap("### 警告\n")
        for w in checks["warn"]:
            ap("- ⚠️ %s" % w)
        ap("")
    if not checks["fail"] and not checks["warn"]:
        ap("全部通过。\n")

    ap("## 7. 复现命令\n")
    ap("```powershell")
    ap('python ioc2kicad.py --ioc "%s" --out "%s" --preview%s'
       % (ioc_path, lib_out.parent, " --power-as-power-in" if power_fixed else ""))
    ap("```\n")
    ap("> `.ioc` 改动后重跑一次即可让符号与 CubeMX 保持同步；")
    ap("> 生成的符号是独立的（不 `extends` 官方库），KiCad 升级不会影响它。")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把 STM32CubeMX .ioc 工程转成项目专属的 KiCad 符号",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ioc", required=True, help="CubeMX 工程文件 (*.ioc)")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--symbol-name", default=None, help="生成的符号名（默认 <UserName>_<工程名>）")
    ap.add_argument("--name-sep", default="-", help="引脚名各段分隔符（默认 -）")
    ap.add_argument("--no-label", action="store_true", help="不把 GPIO_Label 拼进引脚名")
    ap.add_argument("--strip-pin-suffix", action="store_true",
                    help="剥掉引脚名里的复用功能后缀（PA0-WKUP → PA0）")
    ap.add_argument("--width-scale", type=float, default=1.10,
                    help="引脚名字宽系数（相对 1.27mm 字号，默认 1.10）")
    ap.add_argument("--no-widen", action="store_true", help="不自动加宽符号体")
    ap.add_argument("--power-as-power-in", action="store_true",
                    help="把 CubeMX 判定为 Power 的引脚统一成 power_in（官方库里 VSS 常是 passive）")
    ap.add_argument("--preview", action="store_true",
                    help="生成后用 kicad-cli 导出 SVG 并截图 PNG，便于目视校验")
    ap.add_argument("--preview-width", type=int, default=1240, help="预览图宽度（像素）")
    ap.add_argument("--lib", default=None, help="KiCad 符号库文件（默认按家族自动查找）")
    ap.add_argument("--cubemx-db", default=None, help="CubeMX db/mcu 目录")
    ap.add_argument("--rules", default=None, help="附加的电气类型规则 JSON")
    args = ap.parse_args(argv)
    return convert(args)


if __name__ == "__main__":
    sys.exit(main())
