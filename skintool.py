#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MC 皮肤工具箱 —— 统一命令行入口。

把原来分散的三件事合成一条命令（PNG 直读，不需要先手动转 hex 文本）：

    png2txt   PNG 皮肤      ->  hex 网格文本（喂给 LLM 改色）
    txt2png   hex 网格文本  ->  PNG 皮肤（LLM 改完转回来）
    base      PNG 或 hex    ->  底层 6 部位 × 6 面提取（Head/Torso/双臂/双腿）
    layers    PNG 或 hex    ->  第二层（overlay）6 部位 × 6 面提取
                                （Hat/Jacket/双袖/双裤）

示例（推荐用同目录的 skintool.cmd，免输 python 路径）:
    skintool png2txt Crow_35.png
    skintool txt2png Crow_35_hex.txt
    skintool base   Crow_35.png slim -c -a
    skintool layers Crow_35.png -s -c
    skintool                       # 不带参数 = 交互菜单

参数速记（base / layers）:
    位置参数 [wide|slim|steve|alex]   手臂类型，默认 wide（Steve）
    -s / -w     等同 slim / wide
    -c          调色板代号输出（透明 '.'，未知色 '?'）
    -p FILE     指定 GPL 调色板（-c 缺省自动探测脚本目录 / 当前目录里唯一的 .gpl）
    -a          附不透明统计（漏面 / 未绘制检查）
    -o FILE     完整输出写入文件（缺省打到屏幕）
    --size 64|128   强制尺寸（默认按输入自动探测）

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
}

MENU = """
================ MC 皮肤工具箱 skintool ================
  1) png2txt   PNG 皮肤   ->  hex 网格文本（给 LLM 改色）
  2) txt2png   hex 文本   ->  PNG 皮肤（改完转回来）
  3) base      底层部位 / 面提取（Head/Torso/双臂/双腿）
  4) layers    第二层部位 / 面提取（Hat/Jacket/双袖/双裤）
  d) 显示命令用法       0) 退出
========================================================
"""


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
    width, height = info["shape"]
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
              out=None, size=None):
    """kind = "base" / "layers"：提取部位并输出。返回报告文本。"""
    module = split_skin if kind == "base" else split_skin_layers
    text, meta = module.build_report(src, arm=arm, size=size, code=code,
                                     palette=palette, alpha=alpha)
    module.emit(text, meta, out)
    return text


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
                        help="调色板代号输出（透明 '.'，未知色 '?'）")
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
    else:
        run_split(command, args.file, arm=arm_of(args), code=args.code,
                  palette=args.palette, alpha=args.alpha, out=args.out,
                  size=args.size)
    return 0


# ---------------------------------------------------------------- 交互菜单
def ask(prompt, default=""):
    raw = input(prompt).strip().strip('"')
    return raw or default


def ask_yes_no(prompt, default=False):
    raw = input(prompt).strip().lower()
    if not raw:
        return default
    return raw[0] in ("y", "1", "是")


def pick_input(accept="both"):
    """列出当前目录候选文件供选择；也可直接粘贴路径。返回路径或 None。"""
    exts = {"png": (".png",), "txt": (".txt", ".hex"),
            "both": (".png", ".txt", ".hex")}[accept]
    folder = os.getcwd()
    files = sorted(f for f in os.listdir(folder)
                   if os.path.isfile(os.path.join(folder, f))
                   and f.lower().endswith(exts))
    print(f"\n当前目录: {folder}")
    if files:
        for i, name in enumerate(files, 1):
            print(f"  {i}) {name}")
    else:
        print("  （没有候选文件，直接粘贴完整路径即可）")
    while True:
        raw = input("选择文件（序号或路径，回车取消）: ").strip().strip('"')
        if not raw:
            return None
        if raw.isdigit() and files and 1 <= int(raw) <= len(files):
            return os.path.join(folder, files[int(raw) - 1])
        if os.path.isfile(raw):
            return raw
        print("  找不到该文件，请重试。")


def guard(func, *a, **kw):
    """菜单里执行动作：出错不退出程序，回到菜单。"""
    try:
        func(*a, **kw)
    except SystemExit as e:
        if e.code not in (0, None):
            print("[已取消，返回菜单]")
    except KeyboardInterrupt:
        print("\n[已取消]")
    except Exception as e:                       # 兜底：不让菜单崩掉
        print(f"[出错] {e}")
    print()


def menu_png2txt():
    src = pick_input("png")
    if not src:
        return
    default = skinio.default_out_path(src, "_hex", ".txt")
    out = ask(f"输出文本（回车 = {os.path.basename(default)}）: ", default)
    run_png2txt(src, out)


def menu_txt2png():
    src = pick_input("txt")
    if not src:
        return
    default = skinio.default_out_path(src, "_edited", ".png")
    out = ask(f"输出图片（回车 = {os.path.basename(default)}）: ", default)
    run_txt2png(src, out)


def menu_split(kind):
    src = pick_input("both")
    if not src:
        return
    arm = "slim" if ask("手臂类型 [w]ide(默认) / [s]lim(alex): ").lower().startswith("s") \
        else "wide"
    code = ask_yes_no("用调色板代号输出（-c）? [y/N]: ")
    palette = None
    if code:
        try:
            palette = skinio.find_palette()
            print(f"调色板: {palette}")
        except SystemExit:
            print("！未自动找到唯一 .gpl 调色板：请改用 hex 输出，"
                  "或把调色板放到脚本目录后重试。")
            return
    alpha = ask_yes_no("附不透明统计（-a）? [y/N]: ")
    out = ask("输出文件（回车 = 直接打印到屏幕）: ") or None
    run_split(kind, src, arm=arm, code=code, palette=palette, alpha=alpha, out=out)


def interactive():
    print(MENU)
    while True:
        try:
            choice = input("请选择: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("", "0", "q", "quit", "exit", "退出"):
            print("已退出。")
            return 0
        if choice in ("d", "help", "?", "-h", "--help"):
            build_parser().print_help()
            print(MENU)
            continue
        actions = {"1": menu_png2txt, "2": menu_txt2png,
                   "3": lambda: menu_split("base"),
                   "4": lambda: menu_split("layers")}
        action = actions.get(choice) or {
            "png2txt": menu_png2txt, "p2t": menu_png2txt,
            "txt2png": menu_txt2png, "t2p": menu_txt2png,
            "base": lambda: menu_split("base"), "b": lambda: menu_split("base"),
            "layers": lambda: menu_split("layers"), "l": lambda: menu_split("layers"),
        }.get(choice)
        if action is None:
            print("无效选择，请输入 1-4 / d / 0。")
            continue
        guard(action)


def main(argv=None):
    skinio.setup_console_encoding()
    return cli(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
