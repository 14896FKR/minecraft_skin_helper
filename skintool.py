#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MC 皮肤工具箱 —— 统一命令行入口。

把原来分散的三件事合成一条命令（PNG 直读，不需要先手动转 hex 文本）：

    png2txt   PNG 皮肤      ->  hex 网格文本（喂给 LLM 改色）
    txt2png   hex 网格文本  ->  PNG 皮肤（LLM 改完转回来）
    base      PNG 或 hex    ->  底层 6 部位 × 6 面提取（Head/Torso/双臂/双腿）
    layers    PNG 或 hex    ->  第二层（overlay）6 部位 × 6 面提取
                                （Hat/Jacket/双袖/双裤）

示例（文件名换成你自己的皮肤即可；推荐用同目录的 skintool.cmd，免输 python 路径）:
    skintool png2txt skin.png                     # -> skin_hex.txt
    skintool txt2png skin_hex.txt                 # -> skin_edited.png
    skintool base    skin.png slim -a             # 底层提取（纤细手臂 + 漏面统计）
    skintool layers  skin.png -s                  # 第二层提取（-s = slim）
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
    }
    while True:
        clear_screen()
        show_menu()
        try:
            choice = input("\n请选择 [1-4 / d / 0]: ").strip().lower()
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
            print("  ！无效选择，请输入 1-4 / d / 0。")
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
