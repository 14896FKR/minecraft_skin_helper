#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warning：Only compatiable with Blockbench
MC 皮肤第二层（Layers / Overlay）部位 / 面提取。

只提取「第二层」（overlay）区域——64×64 贴图中帽子 / 外套 / 袖子 / 裤层：

    Hat          头饰层（Head 的第二层，Blockbench 里叫 Hat）
    Jacket       外套层（Torso 的第二层）
    RightSleeve  右袖层（Right Arm 的第二层）
    LeftSleeve   左袖层（Left Arm 的第二层）
    RightPants   右裤层（Right Leg 的第二层）
    LeftPants    左裤层（Left Leg 的第二层）

推荐入口是统一命令行 skintool.py：
    skintool layers 皮肤.png slim -c        # 纤细手臂 + 调色板代号
    skintool layers 皮肤.png -s -c -a -o 输出.txt
本文件仍可独立运行（兼容旧用法），也作为被 skintool 调用的库模块。

用法:
    python split_skin_layers.py <PNG 或 hex 文本> [wide|slim] [选项]

示例:
    python split_skin_layers.py skin.png                 # 经典手臂，hex 输出
    python split_skin_layers.py skin.png slim --code     # 纤细手臂，调色板代号输出
    python split_skin_layers.py skin_hex.txt -s -c -a    # 短参数写法
    python split_skin_layers.py skin.png --size 128      # 指定尺寸（默认自动探测）
    python split_skin_layers.py skin.png --out 输出.txt   # 完整输出写入文件

输入: PNG 图片（64x64 / 128x128，直接读）或 hex 网格文本（每行 <贴图宽> 个
      #RRGGBBAA，空行跳过，BOM / 无 BOM / GBK 均可）。

调色板: --code 模式从外部 GPL 文件读取代号映射（缺省自动探测脚本目录 /
      当前目录下唯一的 .gpl 文件；零个或多个时退出并提示用 --palette 指定）。

--alpha 的语义与基础层版不同：
    overlay 层的面「部分透明」是正常的（如 Hat 底面不画、Hat 前面要露脸），
    因此只标记「全透明 = 该面未绘制」（opaque==0），不做“透明过多”警告。

第二层坐标（64×64 标准布局，128×128 时自动 ×2）:
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

import skinio

# ---------------------------------------------------------------- 64×64 第二层 UV 坐标
# 面名 -> (x, y, w, h)；size 128 时坐标自动 ×2
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


def build_report(path, arm="wide", size=None, code=False, palette=None, alpha=False):
    """读取皮肤并生成第二层各部件的报告文本。

    返回 (text, meta)：
      text = 完整报告（含表头 / 各层矩阵 / 可选不透明统计与层合计）
      meta = {"kind", "size", "arm", "code", "palette", "warnings", "parts"}
    """
    info = skinio.load_input(path, size=size)
    tex_size = skinio.square_size(info["data"], path)
    layers = build_layers(arm, tex_size)

    palette_path = ""
    color_map = None
    if code:
        palette_path = skinio.find_palette(palette)
        color_map = skinio.load_palette(palette_path)
        if not color_map:
            skinio.die(f"错误：调色板 {palette_path} 中没有解析到任何颜色行。")

    lines = [
        f"# 文件: {path}",
        f"# 手臂: {arm}   尺寸: {tex_size}x{tex_size}   层: 第二层（Layers/Overlay）",
    ]
    header_out = "调色板代号" if code else "Hex 颜色"
    if code:
        header_out += f"   调色板: {palette_path}"
    if alpha:
        header_out += "   附: 不透明统计"
    lines.append(f"# 输出: {header_out}")
    lines.append("")

    part_totals = []
    for part_name, faces in layers.items():
        part_opaque = part_total = 0
        lines.append(f"========== {part_name}（第二层） ==========")
        for face_name, (x, y, w, h) in faces.items():
            face = skinio.extract_face(info["data"], x, y, w, h)
            lines.append("")
            lines.append(f"--- {part_name} {face_name} ({x},{y} {w}x{h}) ---")
            lines.extend(skinio.format_face(face, code, color_map))
            if alpha:
                opaque, total = skinio.face_stats(face)
                part_opaque += opaque
                part_total += total
                pct = 100.0 * opaque / total if total else 0.0
                flag = "  <-- 全透明（该面未绘制）" if opaque == 0 else ""
                lines.append(f"[不透明 {opaque}/{total} ({pct:.0f}%)]{flag}")
            lines.append("")
        if alpha:
            part_totals.append((part_name, part_opaque, part_total))

    if alpha:
        lines.append("========== 层合计（--alpha） ==========")
        for part_name, opaque, total in part_totals:
            pct = 100.0 * opaque / total if total else 0.0
            mark = "  <-- 整层未绘制" if opaque == 0 else ""
            lines.append(f"{part_name}: 不透明 {opaque}/{total} ({pct:.0f}%){mark}")
        lines.append("")

    meta = {"kind": info["kind"], "size": tex_size, "arm": arm, "code": code,
            "palette": palette_path, "warnings": info["warnings"],
            "parts": list(layers)}
    return "\n".join(lines), meta


def emit(text, meta, out_path=None):
    """统一输出：写文件或打印到 stdout，并打印警告。"""
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8-sig", newline="\n") as f:
                f.write(text + "\n")
        except OSError as e:
            skinio.die(f"错误：无法写入 {out_path}：{e}")
        print(f"已写入: {out_path}")
        for part_name in meta["parts"]:
            print(f"[部位] {part_name}")
    else:
        print(text)
    skinio.print_warnings(meta["warnings"])


def resolve_arm_arg(args):
    """合并位置参数 arm 与 -s/--slim / -w/--wide 短开关。"""
    arm = None
    if getattr(args, "slim", False):
        arm = "slim"
    if getattr(args, "wide", False):
        if arm == "slim":
            skinio.die("错误：--slim 与 --wide 不能同时使用。")
        arm = "wide"
    if args.arm:
        chosen = skinio.resolve_arm(args.arm)
        if arm is not None and chosen != arm:
            skinio.die(f"错误：位置参数 {args.arm} 与 --slim/--wide 冲突。")
        arm = chosen
    return arm or "wide"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="split_skin_layers.py",
        description="提取 MC 皮肤第二层（Layers/Overlay）到各部位 / 面。输入可以是 PNG 或 hex 文本。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("file", help="皮肤 PNG 或 hex 网格文本")
    parser.add_argument("arm", nargs="?", default=None,
                        choices=["wide", "slim", "steve", "alex"],
                        help="手臂类型：wide/steve（默认）或 slim/alex")
    parser.add_argument("-s", "--slim", action="store_true", help="等同于位置参数 slim")
    parser.add_argument("-w", "--wide", action="store_true", help="等同于位置参数 wide")
    parser.add_argument("--size", type=int, default=None, choices=[64, 128],
                        help="贴图尺寸（默认按输入自动探测；仅在需要强制校验时给）")
    parser.add_argument("-c", "--code", action="store_true",
                        help="用调色板代号输出（紧凑，透明为 '.'，未知色为 '?'）")
    parser.add_argument("-p", "--palette", metavar="FILE",
                        help="调色板 GPL 文件（-c 模式的映射源；缺省自动探测）")
    parser.add_argument("-a", "--alpha", action="store_true",
                        help="每个面附加不透明统计（全透明标记未绘制）")
    parser.add_argument("-o", "--out", metavar="FILE",
                        help="完整输出写入文件（stdout 仍打印摘要）")
    return parser


def main():
    skinio.setup_console_encoding()
    args = build_parser().parse_args()
    text, meta = build_report(args.file, arm=resolve_arm_arg(args), size=args.size,
                              code=args.code, palette=args.palette, alpha=args.alpha)
    emit(text, meta, args.out)


if __name__ == "__main__":
    main()
