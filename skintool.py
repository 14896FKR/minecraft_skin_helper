#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MC 皮肤工具箱 —— 统一命令行入口。

把原来分散的几件事合成一条命令（PNG 直读，不需要先手动转 hex 文本）：

    png2txt   PNG 皮肤      ->  hex 网格文本（喂给 LLM 改色）
    txt2png   hex 网格文本  ->  PNG 皮肤（LLM 改完转回来）
    base      PNG 或 hex    ->  底层 6 部位 × 6 面提取（Head/Torso/双臂/双腿）
    layers    PNG 或 hex    ->  第二层（overlay）6 部位 × 6 面提取
                                （Hat/Jacket/双袖/双裤）
    merge     两份部位 TXT  ->  一张完整皮肤 PNG（按前缀找 前缀_base + 前缀_layers）

示例（文件名换成你自己的皮肤即可；推荐用同目录的 skintool.cmd，免输 python 路径）:
    skintool png2txt skin.png                     # -> skin_hex.txt
    skintool txt2png skin_hex.txt                 # -> skin_edited.png
    skintool base    skin.png slim -a -o skin_base.txt
    skintool layers  skin.png -s    -o skin_layers.txt
    skintool merge   skin                         # -> skin_merged.png
    skintool base    skin.png -c -p palette.gpl   # 调色板代号输出（需自备 .gpl）
    skintool                                      # 不带参数 = 交互菜单

参数速记（base / layers）:
    位置参数 [wide|slim|steve|alex]   手臂类型，默认 wide（Steve）
    -s / -w     等同 slim / wide
    -c          调色板代号输出（透明 '.'，未知色 '?'）——需要 .gpl 调色板
    -p FILE     指定 GPL 调色板（-c 缺省自动探测脚本目录 / 当前目录里唯一的 .gpl）
    -a          附不透明统计（漏面 / 未绘制检查）
    -o FILE     完整输出写入文件（缺省打到屏幕）
    --size 64|128   强制尺寸（默认按输入自动探测）

参数速记（merge）:
    skintool merge <前缀>            按前缀找 前缀_base.txt + 前缀_layers.txt
    skintool merge 甲.txt 乙.txt     直接给两份报告（按顺序叠加，后写覆盖先写）
    -o FILE     输出 PNG（默认 前缀_merged.png）
    --fill PNG  未覆盖区域从该 PNG 保留原样（默认留透明）
    -p FILE     代号报告的调色板；--size 强制画布尺寸

约定: 皮肤尺寸 64x64 / 128x128（部位提取）；颜色 "#RRGGBBAA"；透明 = #00000000。
"""
import argparse
import os
import sys

import skinio
import split_skin
import split_skin_layers

ALIASES = {
    "p2t": "png2txt", "png2hex": "png2txt", "png": "png2txt",
    "t2p": "txt2png", "hex2png": "txt2png", "hex": "txt2png",
    "b": "base", "base": "base", "底层": "base",
    "l": "layers", "layer": "layers", "layers": "layers", "第二层": "layers",
    "m": "merge", "merge": "merge", "合并": "merge", "hebing": "merge",
}

# 合并时按前缀找文件用的后缀（大小写不敏感）
BASE_SUFFIXES = ("_base", "base", "-base", "_bottom")
LAYER_SUFFIXES = ("_layers", "_layer", "layers", "-layers", "_overlay", "overlay")
TEXT_EXTS = (".txt", ".hex")


class Cancelled(Exception):
    """菜单里用户按 0 / 返回，取消当前动作。"""


# ---------------------------------------------------------------- 终端小工具
def clear_screen():
    """清屏（只在真正的交互终端里做；管道 / 重定向时保持输出可读）。"""
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def hr(char="=", width=64):
    print(char * width)


def title(text):
    print()
    hr("=")
    print("  " + text)
    hr("=")


def pause(text="\n按回车返回菜单…"):
    try:
        input(text)
    except (EOFError, KeyboardInterrupt):
        print()


def echo_cmd(cmd):
    print(f"\n  等价命令: {cmd}\n")


def ask_yes_no(prompt, default=False):
    raw = input(prompt).strip().lower()
    if not raw:
        return default
    if raw in ("n", "no", "不", "否"):
        return False
    return raw[0] in ("y", "1", "是")


def ask_choice(prompt, options, default, extra=None):
    """编号选择：options = [(键, 说明), ...]；返回键；0/回车之外非法输入会重问。

    回车 = 默认项；0 / q / 返回 = 取消当前动作（返回 None）。
    说明里写清楚每项干什么，避免「输入 N 被当成文件名」这类误操作。
    """
    print()
    for key, label in options:
        mark = "   <- 默认" if key == default else ""
        print(f"    [{key}] {label}{mark}")
    keys = [k for k, _ in options]
    while True:
        try:
            raw = input(f"\n{prompt}（回车 = {default}，0 = 返回）: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            return default
        if raw in ("0", "q", "back", "return", "返回", "取消"):
            return None
        if extra and raw in extra:
            return extra[raw]
        if raw in keys:
            return raw
        print(f"  ！请输入 {' / '.join(keys)}，或 0 返回。")


def pick_input(accept, prompt="选择文件"):
    """列出当前目录候选文件供挑选（也可直接粘完整路径）。返回路径；取消返回 None。"""
    exts = {"png": (".png",), "txt": (".txt", ".hex"),
            "both": (".png", ".txt", ".hex")}[accept]
    folder = os.getcwd()
    try:
        files = sorted(n for n in os.listdir(folder)
                       if os.path.isfile(os.path.join(folder, n))
                       and n.lower().endswith(exts))
    except OSError:
        files = []
    print()
    print(f"  当前目录: {folder}")
    if files:
        for i, name in enumerate(files, 1):
            print(f"    {i}) {name}")
    else:
        print("    （本目录没有候选文件，可直接粘贴完整路径）")
    while True:
        try:
            raw = input(f"\n{prompt}（序号 / 完整路径，0 = 返回）: ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in ("", "0", "q", "back", "返回"):
            return None
        if raw.isdigit() and files and 1 <= int(raw) <= len(files):
            return os.path.join(folder, files[int(raw) - 1])
        if os.path.isfile(raw):
            return os.path.abspath(raw)
        print("  ！找不到这个文件，请重输（0 = 返回）。")


def ask_output_file(default, allow_skip=False):
    """问输出文件名：回车 = 默认名；已存在则问是否覆盖；取消抛 Cancelled。

    allow_skip=True 时输入 n/no 表示「不写文件」（只打印到屏幕）；
    两者都会拦下「n」这类不像文件名的输入，避免误建奇怪的文件。
    """
    folder = os.path.dirname(default) or os.getcwd()
    while True:
        hint = "（回车 = {}{}）".format(
            os.path.basename(default), "，n = 不写文件" if allow_skip else "")
        try:
            raw = input(f"\n输出文件名{hint}: ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            print()
            raise Cancelled()
        if raw in ("0", "q", "back", "返回"):
            raise Cancelled()
        if allow_skip and raw.lower() in ("n", "no", "不", "否"):
            print("  -> 不写文件，结果只打印到屏幕。")
            return None
        path = raw or default
        if not os.path.isabs(path) and os.sep not in path and "/" not in path:
            path = os.path.join(folder, path)
        name = os.path.basename(path)
        # 防误建：像 "n" / "no" / 无扩展名的短词，多半不是想建的文件名
        if "." not in name or name.lower() in ("n", "no", "y", "yes", "是", "不"):
            print(f"  ！「{name}」不像文件名（没有扩展名）—— 请确认要新建的就是它。")
            if not ask_yes_no("     仍要新建这个文件? [y/N]: "):
                continue
        if os.path.isfile(path) and not ask_yes_no(
                f"  ！{os.path.basename(path)} 已存在，覆盖? [y/N]: "):
            continue
        print(f"  -> 将写入: {path}")
        return path


# ---------------------------------------------------------------- 四个动作
def run_png2txt(src, out=None, quiet=False):
    """PNG -> hex 网格文本。返回输出路径。"""
    info = skinio.load_input(src)
    if info["kind"] != "png":
        skinio.die(f"错误：png2txt 需要 PNG 图片输入，{src} 是 hex 文本"
                   f"（若想转回图片请用 txt2png）。")
    width, height = info["shape"]
    out = out or skinio.default_out_path(src, "_hex", ".txt")
    existed = os.path.isfile(out)
    rows = skinio.save_grid(info["data"], out)
    if not quiet:
        print(f"图片: {src}  ({width}x{height})")
        print(f"{'已覆盖' if existed else '已写入'}: {out}"
              f"  （{rows} 行 × {width} 列 #RRGGBBAA）")
        print("下一步: 把该文本发给 LLM 改色，改完用  skintool txt2png "
              + os.path.basename(out) + "  转回 PNG。")
    return out


def run_txt2png(src, out=None, quiet=False):
    """hex 网格文本 -> PNG。返回输出路径。"""
    info = skinio.load_input(src)
    if info["kind"] != "txt":
        skinio.die(f"错误：txt2png 需要 hex 文本输入，{src} 是 PNG 图片"
                   f"（若想导出 hex 请用 png2txt）。")
    out = out or skinio.default_out_path(src, "_edited", ".png")
    existed = os.path.isfile(out)
    width, height, bad = skinio.write_png(info["data"], out)
    if not quiet:
        print(f"文本: {src}  ({width}x{height})")
        print(f"{'已覆盖' if existed else '已写入'}: {out}")
        if bad:
            print(f"[注意] {bad} 个像素颜色非法，已填透明色。")
    skinio.print_warnings(info["warnings"])
    return out


def run_split(kind, src, arm="wide", code=False, palette=None, alpha=False,
              out=None, also_print=None):
    """kind = "base" / "layers"：提取部位并输出。返回报告文本。"""
    module = split_skin if kind == "base" else split_skin_layers
    text, meta = module.build_report(src, arm=arm, code=code,
                                     palette=palette, alpha=alpha)
    module.emit(text, meta, out, also_print)
    return text


# ------------------------------------------------- 合并两份报告（或网格）成 PNG
def prefix_of(path):
    """从文件名推断皮肤前缀：Crown_optimized_base.txt -> Crown_optimized。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    low = stem.lower()
    for suffix in BASE_SUFFIXES + LAYER_SUFFIXES:
        if low.endswith(suffix) and len(stem) > len(suffix):
            return stem[:len(stem) - len(suffix)]
    return stem


def find_prefix_pair(folder, prefix):
    """按前缀找出 <前缀>_base.txt + <前缀>_layers.txt（大小写不敏感，容忍 -base/overlay 等写法）。

    返回 [base_path, layers_path]；找不到就报错并说明找过什么。
    """
    try:
        names = os.listdir(folder)
    except OSError as e:
        skinio.die(f"错误：无法读取目录 {folder}：{e}")
    lower = {n.lower(): n for n in names}

    def pick(suffixes):
        for ext in TEXT_EXTS:
            for suffix in suffixes:
                key = (prefix + suffix + ext).lower()
                if key in lower:
                    return os.path.join(folder, lower[key])
        return None

    base, layers = pick(BASE_SUFFIXES), pick(LAYER_SUFFIXES)
    if base and layers:
        return [base, layers]
    wanted = [prefix + BASE_SUFFIXES[0] + ".txt", prefix + LAYER_SUFFIXES[0] + ".txt"]
    missing = [w for w, got in zip(wanted, (base, layers)) if not got]
    skinio.die("错误：在 " + folder + " 里按前缀 " + repr(prefix) + " 找不到 "
               + " 和 ".join(missing) + "。\n"
               + "      两种用法：① 两份报告命名为「前缀_base.txt / 前缀_layers.txt」后只给前缀；\n"
               + "                ② 直接给两个文件：skintool merge 甲.txt 乙.txt")


def list_prefix_pairs(folder):
    """扫描目录里成对的 <前缀>_base + <前缀>_layers，返回 [(前缀, base, layers)]。"""
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    lower = {n.lower(): n for n in names}
    pairs, seen = [], set()
    for name in names:
        stem, ext = os.path.splitext(name)
        low = stem.lower()
        if ext.lower() not in TEXT_EXTS:
            continue
        for suffix in BASE_SUFFIXES:
            if not low.endswith(suffix) or len(stem) <= len(suffix):
                continue
            prefix = stem[:len(stem) - len(suffix)]
            if prefix.lower() in seen:
                break
            for lext in TEXT_EXTS:
                hit = None
                for lsuffix in LAYER_SUFFIXES:
                    key = (prefix + lsuffix + lext).lower()
                    if key in lower:
                        hit = os.path.join(folder, lower[key])
                        break
                if hit:
                    pairs.append((prefix, os.path.join(folder, name), hit))
                    seen.add(prefix.lower())
                    break
            break
    return pairs


def resolve_merge_inputs(raw):
    """merge 的输入：单个前缀 / 单个文件 / 两个文件 -> 路径列表（按叠加顺序）。"""
    raw = [p for p in raw if p]
    if len(raw) >= 2:
        return list(raw[:2])
    one = raw[0]
    if os.path.isfile(one):
        folder = os.path.dirname(os.path.abspath(one))
        prefix = prefix_of(one)
    else:
        folder = os.path.dirname(one) or os.getcwd()
        prefix = os.path.basename(one.rstrip("\\/"))
        if not prefix:                       # 只给了目录
            skinio.die("错误：请给前缀（如 Crown_optimized）、一个文件，或两个文件路径。")
    return find_prefix_pair(folder, prefix)


def merge_inputs(paths, out=None, size=None, palette=None, fill=None, quiet=False):
    """把 1~2 份输入（部位报告 / hex 网格 / PNG）按坐标合并成一张皮肤 PNG。

    规则：按输入顺序写入画布，后写覆盖先写；报告里的透明记号不覆盖已有像素
    （这样 --fill 的原图内容能保留在未绘制/透明的区域）。
    """
    items = [skinio.read_merge_input(path) for path in paths]
    known = {it["size"] for it in items if it["size"]}
    if len(known) > 1:
        skinio.die("错误：输入的尺寸不一致（"
                   + "、".join(f"{os.path.basename(it['path'])}={it['size']}" for it in items)
                   + "），请确认拿的是同一张皮肤的报告。")
    tex = size or (known.pop() if known else 64)
    if tex not in skinio.SKIN_SIDES:
        skinio.die(f"错误：画布尺寸必须是 64 或 128（得到 {tex}）。")

    for item in items:
        if item["grid"]:
            item["size"] = skinio.square_size(item["grid"], item["path"])
        for face in item["faces"]:
            if (face["x"] < 0 or face["y"] < 0
                    or face["x"] + face["w"] > tex or face["y"] + face["h"] > tex):
                skinio.die(f"错误：{os.path.basename(item['path'])} 的 "
                           f"{face['part']} {face['face']} 坐标 "
                           f"({face['x']},{face['y']} {face['w']}x{face['h']}) 超出 "
                           f"{tex}x{tex} 画布 —— 报告与画布尺寸对不上（可加 --size 指定）。")
    arms = {it["arm"] for it in items if it["arm"]}
    if len(arms) > 1:
        print("  [警告] 两份报告的手臂类型不一致（" + "、".join(sorted(arms))
              + "）—— 仍按各自报告里的坐标写入，请确认没有拿错文件。")

    if fill:
        finfo = skinio.load_input(fill)
        if finfo["size"] != tex:
            skinio.die(f"错误：--fill {fill} 是 {finfo['shape'][0]}x{finfo['shape'][1]}，"
                       f"与画布 {tex}x{tex} 不符。")
        canvas = [row[:] for row in finfo["data"]]
    else:
        canvas = [[skinio.TRANSPARENT] * tex for _ in range(tex)]

    reverse, palette_path = None, ""
    if any(it["code"] for it in items):
        palette_path = skinio.find_palette(palette)
        palette_map = skinio.load_palette(palette_path)
        if not palette_map:
            skinio.die(f"错误：调色板 {palette_path} 中没有解析到任何颜色行。")
        reverse, dup = skinio.palette_reverse(palette_map)
        if dup:
            print("  [警告] 调色板里多个颜色共用代号（" + "、".join(sorted(set(dup)))
                  + "）—— 这些代号按第一个颜色还原。")

    covered, stats = set(), []
    for item in items:
        filled = transparent = unknown = 0
        missing_codes = {}
        if item["grid"]:
            for y, row in enumerate(item["grid"]):
                for x, color in enumerate(row):
                    canvas[y][x] = color
                    covered.add((x, y))
                    filled += 1
        for face in item["faces"]:
            matrix = skinio.report_face_tokens(face, item["code"], reverse, item["path"])
            for dy, row in enumerate(matrix):
                for dx, token in enumerate(row):
                    if item["code"]:
                        if token in (".", "-", "_"):
                            transparent += 1
                            continue
                        color = (reverse or {}).get(token)
                        if color is None:
                            unknown += 1
                            missing_codes[token] = missing_codes.get(token, 0) + 1
                            continue
                    else:
                        if token.upper() == skinio.TRANSPARENT:
                            transparent += 1
                            continue
                        color = token.upper()
                    canvas[face["y"] + dy][face["x"] + dx] = color
                    covered.add((face["x"] + dx, face["y"] + dy))
                    filled += 1
        stats.append((item, filled, transparent, unknown, missing_codes))

    if out is None:
        folder = os.path.dirname(os.path.abspath(paths[0]))
        out = os.path.join(folder, prefix_of(paths[0]) + "_merged.png")
    existed = os.path.isfile(out)
    width, height, bad = skinio.write_png(canvas, out)

    if not quiet:
        print("  画布: {}x{}   输入: {}".format(
            tex, tex, " + ".join(os.path.basename(p) for p in paths)))
        for item, filled, transparent, unknown, missing in stats:
            notes = []
            if transparent:
                notes.append(f"透明记号 {transparent} 个（不覆盖已有像素）")
            if unknown:
                notes.append(f"调色板里没有的代号 {unknown} 个（留透明）")
            print(f"    {os.path.basename(item['path'])}: 写入 {filled} 像素"
                  + ("（" + "，".join(notes) + "）" if notes else ""))
        for item, filled, transparent, unknown, missing in stats:
            if missing:
                top = "、".join(f"{code}×{n}" for code, n
                                in sorted(missing.items(), key=lambda kv: -kv[1])[:5])
                print(f"  [警告] {os.path.basename(item['path'])} 里有 {unknown} 个像素的代号"
                      f"不在调色板中（{top}"
                      + ("…" if len(missing) > 5 else "") + "）—— 这些位置留透明。")
                print("         代号报告必须用当初提取时的同一份调色板："
                      "加 -p 你的调色板.gpl，或改用 hex 报告（提取时不加 -c）。")
        uncovered = tex * tex - len(covered)
        if uncovered and fill:
            tail = f"；未覆盖 {uncovered} 个已保留 --fill 原图内容"
        elif uncovered:
            tail = (f"；未覆盖 {uncovered} 个留透明"
                    f"（想保留原图这些位置：加 --fill {prefix_of(paths[0])}.png）")
        else:
            tail = "（整幅覆盖）"
        print(f"  覆盖: {len(covered)}/{tex * tex} 像素" + tail)
        if palette_path:
            print(f"  调色板: {palette_path}")
        print(f"{'已覆盖' if existed else '已写入'}: {out}")
        if bad:
            print(f"[注意] {bad} 个像素颜色非法，已填透明色。")
        skinio.print_warnings([w for it in items for w in it["warnings"]])
    return out


# ---------------------------------------------------------------- 命令行
def add_split_args(parser):
    """base / layers 共用的参数集合（短参数优先）。"""
    parser.add_argument("file", help="皮肤 PNG 图片或 hex 网格文本")
    parser.add_argument("arm", nargs="?", default=None,
                        choices=["wide", "slim", "steve", "alex"],
                        help="手臂类型：wide/steve（默认）或 slim/alex")
    parser.add_argument("-s", "--slim", action="store_true", help="纤细手臂（Alex）")
    parser.add_argument("-w", "--wide", action="store_true", help="经典手臂（Steve）")
    parser.add_argument("-c", "--code", action="store_true",
                        help="调色板代号输出（透明 '.'，未知色 '?'）——需 .gpl 调色板")
    parser.add_argument("-p", "--palette", metavar="FILE", help="GPL 调色板文件")
    parser.add_argument("-a", "--alpha", action="store_true", help="附不透明统计")
    parser.add_argument("-o", "--out", metavar="FILE", help="输出写入文件")
    parser.add_argument("--size", type=int, default=None, choices=[64, 128],
                        help="强制尺寸（默认自动探测）")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="skintool",
        description="MC 皮肤工具箱：PNG ↔ hex 文本、底层 / 第二层部位提取。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="<命令>")

    p1 = sub.add_parser("png2txt", aliases=["p2t"], help="PNG -> hex 网格文本")
    p1.add_argument("file", help="PNG 皮肤文件")
    p1.add_argument("-o", "--out", metavar="FILE", help="输出文本（默认 皮肤名_hex.txt）")

    p2 = sub.add_parser("txt2png", aliases=["t2p"], help="hex 网格文本 -> PNG")
    p2.add_argument("file", help="hex 网格文本文件")
    p2.add_argument("-o", "--out", metavar="FILE", help="输出图片（默认 皮肤名_edited.png）")

    p3 = sub.add_parser("base", aliases=["b"], help="底层部位 / 面提取",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    add_split_args(p3)

    p4 = sub.add_parser("layers", aliases=["l"], help="第二层部位 / 面提取",
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    add_split_args(p4)

    p5 = sub.add_parser("merge", aliases=["m"],
                        help="两份部位 TXT（前缀_base + 前缀_layers）-> 一张 PNG",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        description="按报告里的 UV 坐标把两份部位报告合并回一张皮肤 PNG；"
                                    "也接受 hex 网格或 PNG 作为其中一份。")
    p5.add_argument("inputs", nargs="+", metavar="前缀|文件",
                    help="皮肤前缀（如 Crown_optimized，自动找 前缀_base.txt + 前缀_layers.txt），"
                         "或一个文件（按前缀配另一个），或直接给两个文件（按顺序叠加）")
    p5.add_argument("-o", "--out", metavar="FILE",
                    help="输出 PNG（默认 前缀_merged.png）")
    p5.add_argument("--size", type=int, default=None, choices=[64, 128],
                    help="画布尺寸（默认取报告表头 / 输入的尺寸）")
    p5.add_argument("-p", "--palette", metavar="FILE",
                    help="代号报告用的 GPL 调色板（缺省自动探测）")
    p5.add_argument("--fill", metavar="PNG",
                    help="未覆盖区域从该 PNG 保留原样（默认留透明）")
    return parser


def arm_of(args):
    arm = None
    if args.slim:
        arm = "slim"
    if args.wide:
        if arm == "slim":
            skinio.die("错误：--slim 与 --wide 不能同时使用。")
        arm = "wide"
    if args.arm:
        chosen = skinio.resolve_arm(args.arm)
        if arm is not None and chosen != arm:
            skinio.die(f"错误：位置参数 {args.arm} 与 --slim/--wide 冲突。")
        arm = chosen
    return arm or "wide"


def cli(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return interactive()

    command = ALIASES.get(args.command, args.command)
    if command == "png2txt":
        run_png2txt(args.file, args.out)
    elif command == "txt2png":
        run_txt2png(args.file, args.out)
    elif command == "merge":
        merge_inputs(resolve_merge_inputs(args.inputs), out=args.out, size=args.size,
                     palette=args.palette, fill=args.fill)
    else:
        run_split(command, args.file, arm=arm_of(args), code=args.code,
                  palette=args.palette, alpha=args.alpha, out=args.out)
    return 0


# ---------------------------------------------------------------- 交互菜单
def show_menu():
    print()
    hr("=")
    print("  MC 皮肤工具箱 skintool")
    print(f"  当前目录: {os.getcwd()}")
    hr("=")
    print("   1) png2txt   PNG 皮肤  ->  hex 文本（发给 LLM 改色）")
    print("   2) txt2png   hex 文本  ->  PNG 皮肤（改完转回来）")
    print("   3) base      底层部位 / 面提取（头 / 躯干 / 双臂 / 双腿）")
    print("   4) layers    第二层部位 / 面提取（帽 / 外套 / 双袖 / 双裤）")
    print("   5) merge     两份部位 TXT（前缀_base + 前缀_layers）  ->  一张 PNG")
    print("   d) 命令用法与示例            0) 退出")
    hr("-")
    print("  提示: 皮肤 PNG 可直接选，不用先转成 hex 文本；每步都可用 0 返回。")


def act_png2txt():
    title("png2txt —— PNG 皮肤  ->  hex 网格文本")
    src = pick_input("png", "选择 PNG 皮肤文件")
    if not src:
        return
    default = skinio.default_out_path(src, "_hex", ".txt")
    out = ask_output_file(default)                 # png2txt 的输出必须是文件
    echo_cmd(f'skintool png2txt "{os.path.basename(src)}" -o "{os.path.basename(out)}"')
    run_png2txt(src, out)


def act_txt2png():
    title("txt2png —— hex 网格文本  ->  PNG 皮肤")
    src = pick_input("txt", "选择 hex 文本文件")
    if not src:
        return
    default = skinio.default_out_path(src, "_edited", ".png")
    out = ask_output_file(default)
    echo_cmd(f'skintool txt2png "{os.path.basename(src)}" -o "{os.path.basename(out)}"')
    run_txt2png(src, out)


def act_split(kind):
    label = "base —— 底层部位 / 面提取" if kind == "base" \
        else "layers —— 第二层（overlay）部位 / 面提取"
    title(label)
    src = pick_input("both", "选择皮肤（PNG 图片或 hex 文本）")
    if not src:
        return

    arm = ask_choice("手臂类型（决定手臂/袖子面的坐标布局）",
                     [("1", "wide / Steve —— 经典 4px 手臂"),
                      ("2", "slim / Alex —— 纤细 3px 手臂")],
                     "1", extra={"w": "1", "wide": "1", "steve": "1",
                                 "s": "2", "slim": "2", "alex": "2"})
    if arm is None:
        return
    arm = "wide" if arm == "1" else "slim"

    palette_path = skinio.lookup_palette()
    code = False
    if palette_path:
        color = ask_choice("颜色输出方式",
                           [("1", "hex 颜色 #RRGGBBAA（信息全，长）"),
                            ("2", f"调色板代号（用 {os.path.basename(palette_path)}，紧凑）")],
                           "1", extra={"h": "1", "hex": "1", "c": "2", "code": "2"})
        if color is None:
            return
        code = color == "2"
    else:
        print("\n  提示: 脚本目录 / 当前目录里没有 .gpl 调色板 -> 只输出 hex 颜色。")
        print("        要调色板代号输出（-c）：放一个 .gpl 到本目录，或用 -p 指定。")

    alpha = ask_choice("不透明统计（-a）",
                       [("1", "不要"),
                        ("2", "要 —— 标出漏面 / 未绘制的面")],
                       "1", extra={"y": "2", "yes": "2", "n": "1", "no": "1"})
    if alpha is None:
        return

    mode = ask_choice("输出方式",
                      [("1", "打印到屏幕"),
                       ("2", "打印到屏幕 + 写入文件"),
                       ("3", "只写入文件")],
                      "1", extra={"s": "1", "screen": "1", "b": "2", "both": "2",
                                  "f": "3", "file": "3"})
    if mode is None:
        return

    out = None
    if mode in ("2", "3"):
        out = ask_output_file(skinio.default_out_path(src, "_" + kind, ".txt"),
                              allow_skip=True)

    cmd = f'skintool {kind} "{os.path.basename(src)}" {arm}'
    if code:
        cmd += " -c"
    if alpha == "2":
        cmd += " -a"
    if out:
        cmd += f' -o "{os.path.basename(out)}"'
    echo_cmd(cmd)
    run_split(kind, src, arm=arm, code=code, alpha=(alpha == "2"), out=out,
              also_print=(mode != "3"))


def act_merge():
    title("merge —— 两份部位 TXT（前缀_base + 前缀_layers）  ->  一张 PNG")
    folder = os.getcwd()
    pairs = list_prefix_pairs(folder)
    print()
    if pairs:
        print(f"  在当前目录找到 {len(pairs)} 组可合并的报告对（按前缀）:")
        for i, (prefix, base, layers) in enumerate(pairs, 1):
            print(f"    {i}) {prefix}    （{os.path.basename(base)} + {os.path.basename(layers)}）")
        print("    （也可以直接输入别的前缀，或粘两个文件路径）")
    else:
        print("  （本目录没有 *_base.txt + *_layers.txt 成对的文件）")
        print("    请直接输入前缀，或粘两个文件路径（用空格分隔）")
    try:
        raw = input("\n选择前缀（序号 / 前缀 / 两个文件路径，0 = 返回）: ").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if raw in ("", "0", "q", "back", "返回"):
        return
    if raw.isdigit() and pairs and 1 <= int(raw) <= len(pairs):
        prefix, base, layers = pairs[int(raw) - 1]
        paths = [base, layers]
    else:
        paths = resolve_merge_inputs(raw.replace(",", " ").split())
    prefix = prefix_of(paths[0])
    folder = os.path.dirname(os.path.abspath(paths[0]))
    print("\n  将合并: " + "  +  ".join(os.path.basename(p) for p in paths))

    fill = None
    fill_default = os.path.join(folder, prefix + ".png")
    options = [("1", "未覆盖区域留透明"),
               ("2", f"从 {prefix}.png 保留原样"
                     + ("" if os.path.isfile(fill_default) else "（该文件不存在，会退回留透明）")),
               ("3", "指定另一个 PNG 来保留")]
    mode = ask_choice("未覆盖区域怎么处理（就是没被任何面覆盖的像素）", options, "1",
                      extra={"n": "1", "no": "1", "t": "1"})
    if mode is None:
        return
    if mode == "2":
        fill = fill_default if os.path.isfile(fill_default) else None
        if fill is None:
            print(f"  ！{prefix}.png 不存在 -> 未覆盖区域留透明。")
    elif mode == "3":
        try:
            raw_png = input("\n补齐用的 PNG 路径（0 = 返回）: ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if raw_png in ("", "0", "q", "返回"):
            return
        if not os.path.isfile(raw_png):
            print("  ！找不到这个 PNG，已改为留透明。")
        else:
            fill = raw_png

    out = ask_output_file(os.path.join(folder, prefix + "_merged.png"))
    cmd = f'skintool merge "{os.path.basename(paths[0])}" "{os.path.basename(paths[1])}"'
    if fill:
        cmd += f' --fill "{os.path.basename(fill)}"'
    cmd += f' -o "{os.path.basename(out)}"'
    echo_cmd(cmd)
    merge_inputs(paths, out=out, fill=fill)


def guard(func, *a, **kw):
    """菜单里执行动作：出错 / 取消都不退出程序，回到菜单。"""
    try:
        func(*a, **kw)
    except Cancelled:
        print("\n  -> 已取消，返回菜单。")
    except SystemExit as e:
        if e.code not in (0, None):
            print("\n  -> 已取消，返回菜单。")
    except KeyboardInterrupt:
        print("\n  -> 已中断，返回菜单。")
    except Exception as e:                       # 兜底：不让菜单崩掉
        print(f"\n  [出错] {e}")


def interactive():
    actions = {
        "1": act_png2txt, "png2txt": act_png2txt, "p2t": act_png2txt,
        "2": act_txt2png, "txt2png": act_txt2png, "t2p": act_txt2png,
        "3": lambda: act_split("base"), "base": lambda: act_split("base"),
        "b": lambda: act_split("base"),
        "4": lambda: act_split("layers"), "layers": lambda: act_split("layers"),
        "l": lambda: act_split("layers"),
        "5": act_merge, "merge": act_merge, "m": act_merge,
    }
    while True:
        clear_screen()
        show_menu()
        try:
            choice = input("\n请选择 [1-5 / d / 0]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return 0
        if choice in ("", "0", "q", "quit", "exit", "退出"):
            print("已退出。")
            return 0
        if choice in ("d", "help", "?", "-h", "--help"):
            clear_screen()
            build_parser().print_help()
            pause()
            continue
        action = actions.get(choice)
        if action is None:
            print("  ！无效选择，请输入 1-5 / d / 0。")
            pause("\n按回车继续…")
            continue
        clear_screen()
        guard(action)
        pause()


def main(argv=None):
    skinio.setup_console_encoding()
    return cli(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
