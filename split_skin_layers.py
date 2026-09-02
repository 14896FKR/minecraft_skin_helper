#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warning：Only compatiable with Blockbench
MC 皮肤第二层（Layers / Overlay）Hex 提取工具（64×64 默认 / 128×128，Wide / Slim 手臂）

与 split_skin.py（基础层 Base）配套：本脚本只提取「第二层」（overlay）区域——
64×64 贴图中帽子 / 外套 / 袖子 / 裤层的部分：

    Hat          头饰层（Head 的第二层，Blockbench 里叫 Hat）
    Jacket       外套层（Torso 的第二层）
    RightSleeve  右袖层（Right Arm 的第二层）
    LeftSleeve   左袖层（Left Arm 的第二层）
    RightPants   右裤层（Right Leg 的第二层）
    LeftPants    左裤层（Left Leg 的第二层）

用法:
    python split_skin_layers.py <皮肤Hex文件> [wide|slim] [选项]

示例:
    python split_skin_layers.py Fin_hex_32.txt                 # 经典手臂，hex 输出
    python split_skin_layers.py Fin_hex_32.txt slim --code     # 纤细手臂，调色板代号输出
    python split_skin_layers.py Fin_hex_32.txt --size 128      # 128×128 皮肤
    python split_skin_layers.py Fin_hex_32.txt --alpha         # 附带不透明统计（空面检查）
    python split_skin_layers.py Fin_hex_32.txt --code --palette 我的调色板.gpl
    python split_skin_layers.py Fin_hex_32.txt --out 输出.txt  # 完整输出写入文件

输入格式: 每行 <贴图宽> 个颜色，形如 #RRGGBBAA（Fin1_hex_32.txt 同款），
         空行自动跳过；UTF-8 有 BOM / 无 BOM 均可（utf-8-sig 读取）。

调色板: --code 模式从外部 GPL 文件读取代号映射（缺省自动探测脚本同目录下
         唯一的 .gpl 文件；存在多个或零个时自动退出并提示用 --palette 指定），
         GPL 行格式:
           R G B <tab> 名称 [代号]      （如 "  8   8  12\tVoid Black [0]"）
         修改 / 增删 GPL 文件即可生效，无需改脚本。

--alpha 的语义与基础层版不同：
    overlay 层的面「部分透明」是正常的（如 Hat 底面不画、Hat 前面要露脸），
    因此只标记「全透明 = 该面未绘制」（opaque==0），不做“透明过多”警告。

第二层坐标（64×64 标准布局，--size 128 时自动 ×2）:
    Hat         top(40,0)  bottom(48,0)  right(32,8)  front(40,8)  left(48,8)  back(56,8)
    Jacket      top(20,32) bottom(28,32) right(16,36) front(20,36) left(28,36) back(32,36)
    RightSleeve top(44,32) bottom(48,32) right(40,36) front(44,36) left(48,36) back(52,36)
    LeftSleeve  top(52,48) bottom(56,48) right(48,52) front(52,52) left(56,52) back(60,52)
    RightPants  top(4,32)  bottom(8,32)  right(0,36)  front(4,36)  left(8,36)  back(12,36)
    LeftPants   top(4,48)  bottom(8,48)  right(0,52)  front(4,52)  left(8,52)  back(12,52)
    Slim（Alex）手臂 overlay 与基础层同样为紧凑式布局：right→front→left→back 紧贴，
    left/bottom/back 的 x 起点比 wide 前移 1px（见 build_layers）。
"""
import argparse
import copy
import os
import re
import sys

# Windows 下强制 UTF-8 输出，避免 GBK 控制台/管道乱码（PyCharm、pwsh 均正常）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- 透明色
# 调色板从外部 GPL 文件读取（--palette），不硬编码；透明单独定义
TRANSPARENT = "#00000000"

# ---------------------------------------------------------------- 64×64 第二层 UV 坐标
# 面名 -> (x, y, w, h)；--size 128 时坐标自动 ×2
LAYERS_64 = {
    "Hat": {
        "top": (40, 0, 8, 8), "bottom": (48, 0, 8, 8),
        "right": (32, 8, 8, 8), "front": (40, 8, 8, 8),
        "left": (48, 8, 8, 8), "back": (56, 8, 8, 8),
    },
    "Jacket": {
        "top": (20, 32, 8, 4), "bottom": (28, 32, 8, 4),
        "right": (16, 36, 4, 12), "front": (20, 36, 8, 12),
        "left": (28, 36, 4, 12), "back": (32, 36, 8, 12),
    },
    "RightSleeve": {
        "top": (44, 32, 4, 4), "bottom": (48, 32, 4, 4),
        "right": (40, 36, 4, 12), "front": (44, 36, 4, 12),
        "left": (48, 36, 4, 12), "back": (52, 36, 4, 12),
    },
    "LeftSleeve": {
        "top": (52, 48, 4, 4), "bottom": (56, 48, 4, 4),
        "right": (48, 52, 4, 12), "front": (52, 52, 4, 12),
        "left": (56, 52, 4, 12), "back": (60, 52, 4, 12),
    },
    "RightPants": {
        "top": (4, 32, 4, 4), "bottom": (8, 32, 4, 4),
        "right": (0, 36, 4, 12), "front": (4, 36, 4, 12),
        "left": (8, 36, 4, 12), "back": (12, 36, 4, 12),
    },
    "LeftPants": {
        "top": (4, 48, 4, 4), "bottom": (8, 48, 4, 4),
        "right": (0, 52, 4, 12), "front": (4, 52, 4, 12),
        "left": (8, 52, 4, 12), "back": (12, 52, 4, 12),
    },
}

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")


def load_palette(filename):
    """读取 GPL 调色板文件，返回 {颜色: 代号}（供 to_code 直接查表）。

    GPL 行格式: R G B <tab> 名称 [代号]
    （RGB 十进制；名称尾部带 [代号]，如 "Void Black [0]"；
     兼容 "[代号] 名称" 前置写法；无 [代号] 时整行名字作代号）。
    注释（# 开头）与空行忽略。
    """
    palette = {}
    try:
        with open(filename, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                except ValueError:
                    continue
                name = " ".join(parts[3:])
                m = re.search(r"\[([^\]]+)\]", name)
                code = m.group(1) if m else name
                color = "#{:02X}{:02X}{:02X}".format(r, g, b)
                palette[color] = code
    except OSError as e:
        sys.exit(f"错误：无法读取调色板 {filename}：{e}")
    return palette


def find_palette(script_dir):
    """自动探测脚本同目录下的 GPL 调色板文件（--code 模式的缺省映射源）。

    - 恰好一个 .gpl  -> 返回其路径
    - 多个 .gpl      -> 退出并提示用 --palette 指定
    - 零个 .gpl      -> 退出并提示用 --palette 提供
    """
    try:
        candidates = sorted(f for f in os.listdir(script_dir)
                            if f.lower().endswith(".gpl"))
    except OSError as e:
        sys.exit(f"错误：无法扫描调色板目录 {script_dir}：{e}")
    if len(candidates) == 1:
        return os.path.join(script_dir, candidates[0])
    if len(candidates) > 1:
        names = "、".join(candidates)
        sys.exit(f"错误：目录 {script_dir} 下有多个 GPL 调色板文件（{names}），"
                 f"无法自动选择，请用 --palette 指定其中一个。")
    sys.exit(f"错误：目录 {script_dir} 下未找到 .gpl 调色板文件，"
             f"请用 --palette 指定。")


def read_data(filename, width=64):
    """读取皮肤 TXT，返回二维列表 data[y][x]（颜色字符串）。

    - 每行期望 width 个颜色；空行、行首尾空白自动忽略
    - utf-8-sig 读取，兼容 BOM / 无 BOM
    - 行宽不符、颜色格式非法时收集警告（不中断）
    """
    data, warnings = [], []
    try:
        with open(filename, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except OSError as e:
        sys.exit(f"错误：无法打开文件 {filename}：{e}")

    for idx, line in enumerate(lines, 1):
        colors = line.strip().split()
        if not colors:
            continue
        if len(colors) != width:
            warnings.append(f"第 {idx} 行有 {len(colors)} 个颜色（期望 {width}），已跳过")
            continue
        for c in colors:
            if not COLOR_RE.match(c):
                warnings.append(f"第 {idx} 行颜色格式非法：{c}")
        data.append(colors)

    if not data:
        sys.exit("错误：文件中没有有效的颜色数据。")
    if len(data) != width:
        sys.exit(f"错误：有效行数为 {len(data)}（期望 {width}）。")
    return data, warnings


def build_layers(arm_type, size):
    """按手臂类型与贴图尺寸生成各第二层面坐标。

    Slim（Alex）的袖子 overlay 与基础层手臂同样为“紧凑式”排列：
    深 4 不变、宽 4→3，right 之后紧跟 front、再 left、再 back，
    top/bottom 分别与 front/left 对齐，因此 left/bottom/back 的
    x 起点前移 1px（Wide: left 从 x48 起 / Slim: left 从 x47 起）。
    """
    layers = copy.deepcopy(LAYERS_64)
    if arm_type == "slim":
        for sleeve in ("RightSleeve", "LeftSleeve"):
            f = layers[sleeve]
            rx, ry, rw, rh = f["right"]       # right 面 = 手臂深 4，宽不变
            f["front"] = (rx + rw, ry, 3, rh)              # 紧贴 right 之后，宽 3
            f["left"] = (f["front"][0] + 3, ry, 4, rh)     # 紧贴 front，宽 4
            f["back"] = (f["left"][0] + 4, ry, 3, rh)      # 紧贴 left，宽 3
            f["top"] = (f["front"][0], f["top"][1], 3, 4)  # 与 front 对齐
            f["bottom"] = (f["left"][0], f["bottom"][1], 3, 4)  # 与 left 对齐
    if size != 64:
        scale = size // 64
        for layer in layers.values():
            for face, (x, y, w, h) in layer.items():
                layer[face] = (x * scale, y * scale, w * scale, h * scale)
    return layers


def extract_face(data, x, y, w, h):
    """提取矩形区域像素矩阵。"""
    return [row[x:x + w] for row in data[y:y + h]]


def to_code(color, palette):
    """颜色字符串 -> 调色板代号；透明 -> '.'；未知颜色 -> '?'。

    输入为 8 位 #RRGGBBAA（或 6 位 #RRGGBB）：透明按 8 位判，
    查表时截断 alpha 只取 #RRGGBB 与调色板 key 匹配。
    """
    key = color.upper()
    if key == TRANSPARENT:
        return "."
    return palette.get(key[:7], "?")


def format_face(face, code_mode, palette=None):
    """面矩阵 -> 文本行列表。code_mode 时用 palette 映射代号。"""
    if code_mode:
        return ["".join(to_code(c, palette) for c in row) for row in face]
    return [" ".join(row) for row in face]


def face_stats(face):
    """统计该面不透明像素比例，返回 (不透明数, 总数)。

    overlay 语义：部分透明属正常（底面/开口），只对“全透明”标未绘制。
    """
    total = len(face) * len(face[0]) if face else 0
    opaque = sum(1 for row in face for c in row if c.upper() != TRANSPARENT)
    return opaque, total


def main():
    parser = argparse.ArgumentParser(
        description="提取 MC 皮肤第二层（Layers/Overlay）Hex 数据到各部位/面"
                    "（64×64 默认，支持 128×128、Wide/Slim 手臂）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", help="皮肤 Hex 文本文件（每行 64 或 128 个 #RRGGBBAA）")
    parser.add_argument("arm", nargs="?", default="wide", choices=["wide", "slim"],
                        help="手臂类型：wide（经典 4px，默认）/ slim（纤细 3px）")
    parser.add_argument("--size", type=int, default=64, choices=[64, 128],
                        help="贴图尺寸（默认 64；128 时坐标自动放大）")
    parser.add_argument("--code", action="store_true",
                        help="用调色板代号输出（紧凑，透明为 '.'，未知色为 '?'）")
    parser.add_argument("--palette", metavar="FILE",
                        help="调色板 GPL 文件（--code 模式的映射源；"
                             "缺省自动探测脚本同目录下唯一的 .gpl 文件，"
                             "存在多个或零个时退出并提示指定）")
    parser.add_argument("--alpha", action="store_true",
                        help="每个面附加不透明统计（全透明标记未绘制）")
    parser.add_argument("--out", metavar="FILE",
                        help="完整输出写入文件（stdout 仍打印摘要）")
    args = parser.parse_args()

    data, warnings = read_data(args.file, width=args.size)
    layers = build_layers(args.arm, args.size)

    palette = None
    palette_path = ""
    if args.code:
        palette_path = args.palette or find_palette(
            os.path.dirname(os.path.abspath(__file__)))
        palette = load_palette(palette_path)
        if not palette:
            sys.exit(f"错误：调色板 {palette_path} 中没有解析到任何颜色行。")

    lines = []
    lines.append(f"# 文件: {args.file}")
    lines.append(f"# 手臂: {args.arm}   尺寸: {args.size}x{args.size}   层: 第二层（Layers/Overlay）")
    lines.append(f"# 输出: {'调色板代号' if args.code else 'Hex 颜色'}"
                 + (f"   调色板: {palette_path}" if args.code else "")
                 + ("   附: 不透明统计" if args.alpha else ""))
    lines.append("")

    part_totals = []
    for part_name, faces in layers.items():
        part_opaque = part_total = 0
        lines.append(f"========== {part_name}（第二层） ==========")
        for face_name, (x, y, w, h) in faces.items():
            face = extract_face(data, x, y, w, h)
            lines.append("")
            lines.append(f"--- {part_name} {face_name} ({x},{y} {w}x{h}) ---")
            lines.extend(format_face(face, args.code, palette))
            if args.alpha:
                opaque, total = face_stats(face)
                part_opaque += opaque
                part_total += total
                pct = 100.0 * opaque / total if total else 0.0
                flag = "  <-- 全透明（该面未绘制）" if opaque == 0 else ""
                lines.append(f"[不透明 {opaque}/{total} ({pct:.0f}%)]{flag}")
            lines.append("")
        if args.alpha:
            part_totals.append((part_name, part_opaque, part_total))

    if args.alpha:
        lines.append("========== 层合计（--alpha） ==========")
        for part_name, opaque, total in part_totals:
            pct = 100.0 * opaque / total if total else 0.0
            mark = "  <-- 整层未绘制" if opaque == 0 else ""
            lines.append(f"{part_name}: 不透明 {opaque}/{total} ({pct:.0f}%){mark}")
        lines.append("")

    output = "\n".join(lines)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8-sig") as f:
                f.write(output + "\n")
            print(f"已写入: {args.out}")
        except OSError as e:
            sys.exit(f"错误：无法写入 {args.out}：{e}")
        for part_name in layers:
            print(f"[部位] {part_name}")
    else:
        print(output)

    if warnings:
        print(f"\n[警告 {len(warnings)} 条]")
        for w in warnings[:10]:
            print("  " + w)
        if len(warnings) > 10:
            print(f"  ... 其余 {len(warnings) - 10} 条省略")


if __name__ == "__main__":
    main()
