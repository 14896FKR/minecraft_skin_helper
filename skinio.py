#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skintool 共享 IO 层 —— PNG ↔ hex 网格、尺寸校验、调色板解析、代号映射。

被三个脚本共用，不单独作为命令入口：

    skintool.py            统一入口（子命令 png2txt / txt2png / base / layers + 交互菜单）
    split_skin.py          底层（Base）部位 / 面提取
    split_skin_layers.py   第二层（Layers / Overlay）部位 / 面提取

约定
    * 尺寸：合法 MC 皮肤贴图 = 64x32（Java 旧版）/ 64x64（Java）/ 128x128（Bedrock）；
      部位提取类工具只接受方形 64x64 或 128x128。
    * 颜色：统一 "#RRGGBBAA"（大写，读入时归一化）；透明 = #00000000。
    * 输入自适应：PNG 图片与 hex 网格文本都能直接当输入（按文件内容判定，不看扩展名）。
    * 文本编码：写出用 utf-8-sig（带 BOM）；读取兼容 utf-8-sig / utf-8 / GBK。
    * 调色板：GPL 文本，格式 `R G B <tab> 名称 [代号]`；不硬编码任何颜色表。
"""
import os
import re
import sys

# ---------------------------------------------------------------- 基本常量
VALID_SIZES = [(64, 32), (64, 64), (128, 128)]   # 合法皮肤尺寸
SKIN_SIDES = (64, 128)                           # 部位提取支持的方形边长
TRANSPARENT = "#00000000"
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def die(message, code=1):
    """统一错误出口：信息写 stderr，以非零码退出。"""
    sys.stderr.write(str(message).rstrip() + "\n")
    sys.exit(code)


def setup_console_encoding():
    """让中文在交互控制台与重定向 / 管道里都能正确输出。

    * 交互控制台：Python 3.6+ 用 UTF-8 走 Windows 控制台 API，保持原样即可；
    * 重定向 / 管道：stdout.encoding 取系统 ANSI 代码页（中文 Windows = cp936），
      会写出 GBK 字节而让按 UTF-8 解读的上游（pwsh 捕获、CI 日志、PyCharm
      运行窗口）读成乱码 —— 这种情况统一切到 UTF-8。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                continue
            enc = (stream.encoding or "").lower().replace("-", "")
            if enc not in ("utf8", "cp65001"):
                stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _pil():
    """延迟导入 Pillow，缺失时给出可操作的提示。"""
    try:
        from PIL import Image
    except ImportError:
        die("错误：未安装 Pillow。请先执行  pip install Pillow  或  uv sync。")
    return Image


# ---------------------------------------------------------------- 颜色互转
def rgba_to_hex(rgba):
    """RGBA 元组 -> "#RRGGBBAA"。"""
    r, g, b, a = rgba
    return f"#{r:02X}{g:02X}{b:02X}{a:02X}"


def hex_to_rgba(code):
    """ "#RRGGBBAA" -> RGBA 元组；格式非法抛 ValueError。"""
    code = code.strip()
    if len(code) == 7:                      # 容忍 6 位写法，视为不透明
        code += "FF"
    if not code.startswith("#") or len(code) != 9:
        raise ValueError(f"Invalid hex code format: {code}. Expected #RRGGBBAA")
    try:
        return (int(code[1:3], 16), int(code[3:5], 16),
                int(code[5:7], 16), int(code[7:9], 16))
    except ValueError:
        raise ValueError(f"Invalid characters in hex code: {code}")


# ---------------------------------------------------------------- PNG 读写
def read_png(path):
    """读取 PNG -> (data, (w, h))；data[y][x] 为 "#RRGGBBAA"。"""
    Image = _pil()
    try:
        with Image.open(path) as img:
            img = img.convert("RGBA")
            width, height = img.size
            if (width, height) not in VALID_SIZES:
                die(f"错误：{path} 为 {width}x{height}，不是合法 MC 皮肤尺寸"
                    f"（64x32 / 64x64 / 128x128）。")
            pixels = img.load()
            data = [[rgba_to_hex(pixels[x, y]) for x in range(width)]
                    for y in range(height)]
    except OSError as e:
        die(f"错误：无法读取图片 {path}：{e}")
    return data, (width, height)


def write_png(data, path):
    """二维网格 -> PNG；非法颜色填透明并计数。返回 (w, h, 非法色个数)。"""
    Image = _pil()
    height = len(data)
    width = len(data[0]) if height else 0
    if (width, height) not in VALID_SIZES:
        die(f"错误：网格为 {width}x{height}，不是合法 MC 皮肤尺寸"
            f"（64x32 / 64x64 / 128x128）。")
    img = Image.new("RGBA", (width, height))
    pixels = img.load()
    bad = 0
    for y, row in enumerate(data):
        for x, code in enumerate(row):
            try:
                pixels[x, y] = hex_to_rgba(code)
            except ValueError:
                pixels[x, y] = (0, 0, 0, 0)
                bad += 1
    try:
        img.save(path, "PNG")
    except OSError as e:
        die(f"错误：无法写入 {path}：{e}")
    return width, height, bad


# ---------------------------------------------------------------- hex 网格读写
def grid_shape(data):
    """网格 -> (width, height)。"""
    return (len(data[0]) if data else 0), len(data)


def read_text(path):
    """读取文本（utf-8-sig / utf-8 / GBK 依次尝试），返回 str。"""
    for enc in ("utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except OSError as e:
            die(f"错误：无法打开文件 {path}：{e}")
    die(f"错误：无法识别 {path} 的文本编码（已试 utf-8 与 GBK）。")


def read_grid(path):
    """读取 hex 网格文本 -> (data, warnings)。

    * 行宽按第一条有效行的颜色数推断；
    * 空行跳过；行宽不符 / 颜色格式非法只记警告不中断；
    * 编码兼容 utf-8-sig / utf-8 / GBK。
    """
    text = read_text(path)

    data, warnings = [], []
    width = None
    for idx, line in enumerate(text.splitlines(), 1):
        colors = line.split()
        if not colors:
            continue
        if width is None:
            width = len(colors)
        elif len(colors) != width:
            warnings.append(f"第 {idx} 行有 {len(colors)} 个颜色（期望 {width}），已跳过")
            continue
        for color in colors:
            if not COLOR_RE.match(color):
                warnings.append(f"第 {idx} 行颜色格式非法：{color}")
        data.append([c.upper() for c in colors])

    if not data:
        die(f"错误：{path} 中没有有效的颜色数据。")
    return data, warnings


def save_grid(data, path):
    """二维网格 -> hex 文本（utf-8-sig，一行一贴图行）。返回写入行数。"""
    text = "\n".join(" ".join(row) for row in data) + "\n"
    try:
        with open(path, "w", encoding="utf-8-sig", newline="\n") as f:
            f.write(text)
    except OSError as e:
        die(f"错误：无法写入 {path}：{e}")
    return len(data)


# ---------------------------------------------------------------- 输入自适应
def load_input(path, size=None):
    """自适应读取输入（PNG 图片 / hex 网格文本）。

    返回 dict: {"kind", "path", "data", "shape", "size", "warnings"}
      kind   = "png" / "txt"（按文件内容判定，不看扩展名）
      size   = 方形边长；非方形（64x32）时为 None
    size 参数给出时做严格校验（不符直接报错）。
    """
    if not os.path.isfile(path):
        die(f"错误：找不到文件 {path}")
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError as e:
        die(f"错误：无法读取文件 {path}：{e}")

    if head == PNG_MAGIC:
        data, shape = read_png(path)
        warnings, kind = [], "png"
    elif os.path.splitext(path)[1].lower() == ".png":
        die(f"错误：{path} 的扩展名是 .png，但内容不是 PNG 图片。")
    else:
        data, warnings = read_grid(path)
        shape = grid_shape(data)
        kind = "txt"

    if shape not in VALID_SIZES:
        die(f"错误：{path} 解析为 {shape[0]}x{shape[1]}，不是合法 MC 皮肤尺寸"
            f"（64x32 / 64x64 / 128x128）。")
    if size is not None and shape != (size, size):
        die(f"错误：{path} 实际为 {shape[0]}x{shape[1]}，与 --size {size} 不符。")

    return {"kind": kind, "path": path, "data": data, "shape": shape,
            "size": shape[0] if shape[0] == shape[1] else None,
            "warnings": warnings}


def square_size(data, path=""):
    """部位提取用：确认为方形 64/128，返回边长。"""
    width, height = grid_shape(data)
    if width != height or width not in SKIN_SIDES:
        die(f"错误：{path or '输入'} 为 {width}x{height}，部位提取只支持"
            f" 64x64 或 128x128 方形贴图。")
    return width


def default_out_path(input_path, suffix, ext):
    """由输入路径推出默认输出路径。

    png2txt: skin.png      -> skin_hex.txt
    txt2png: skin_hex.txt  -> skin_edited.png（结尾的 _hex 自动去掉）
    """
    stem = os.path.splitext(os.path.basename(input_path))[0]
    if stem.lower().endswith("_hex"):
        stem = stem[:-4]
    folder = os.path.dirname(os.path.abspath(input_path))
    return os.path.join(folder, stem + suffix + ext)


def resolve_arm(value):
    """手臂类型归一化：wide / steve -> wide；slim / alex -> slim。"""
    text = (value or "").strip().lower()
    if text in ("wide", "steve", "w", "经典", "粗"):
        return "wide"
    if text in ("slim", "alex", "s", "纤细", "细"):
        return "slim"
    die(f"错误：无法识别的手臂类型 {value!r}，请用 wide/steve 或 slim/alex。")


# ---------------------------------------------------------------- 调色板
def load_palette(path):
    """读取 GPL 调色板 -> { "#RRGGBB": 代号 }。

    GPL 行格式 R G B <tab> 名称 [代号]；兼容 "[代号] 名称" 前置写法；
    无 [代号] 时整行名字当代号；# 开头注释与空行忽略。
    """
    palette = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(path, "r", encoding="gbk") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError) as e:
            die(f"错误：无法读取调色板 {path}：{e}")
    except OSError as e:
        die(f"错误：无法读取调色板 {path}：{e}")

    for line in lines:
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
        palette["#{:02X}{:02X}{:02X}".format(r, g, b)] = code
    return palette


def palette_search_dirs():
    """调色板自动探测目录：脚本所在目录优先，其次当前工作目录。"""
    dirs = [os.path.dirname(os.path.abspath(__file__))]
    cwd = os.path.abspath(os.getcwd())
    if cwd not in dirs:
        dirs.append(cwd)
    return dirs


def palette_candidates(explicit=None):
    """列出可用调色板候选路径（explicit 给出时只校验它本身）。不报错、不退出。"""
    if explicit:
        return [explicit] if os.path.isfile(explicit) else []
    found = []
    for folder in palette_search_dirs():
        try:
            found += [os.path.join(folder, n) for n in sorted(os.listdir(folder))
                      if n.lower().endswith(".gpl")]
        except OSError:
            continue
    return found


def lookup_palette(explicit=None):
    """唯一可用调色板路径；找不到或多个时返回 None（供菜单等场景自行决定）。"""
    found = palette_candidates(explicit)
    return found[0] if len(found) == 1 else None


def find_palette(explicit=None):
    """确定 GPL 调色板路径（命令行用，失败即报错退出）。

    * 显式给出 -> 校验存在后使用；
    * 未给出   -> 在脚本目录 / 当前目录里数 .gpl：
                   恰好一个用那个；零个或多个都报错并提示 --palette。
    """
    found = palette_candidates(explicit)
    if len(found) == 1:
        return found[0]
    if explicit:
        die(f"错误：找不到调色板文件 {explicit}")
    if not found:
        die("错误：" + "、".join(palette_search_dirs()) + " 下都没有 .gpl 调色板文件，"
            "请用 --palette 指定，或改用 hex 输出（不加 -c/--code）。")
    die("错误：找到多个 GPL 调色板文件（"
        + "、".join(os.path.basename(p) for p in found)
        + "），请用 --palette 指定其中一个。")


def to_code(color, palette):
    """颜色 -> 调色板代号；透明 '.'；表中没有 '?'。"""
    key = color.upper()
    if key == TRANSPARENT:
        return "."
    return palette.get(key[:7], "?")


def format_face(face, code_mode, palette=None):
    """面矩阵 -> 文本行列表（code_mode 用调色板代号，否则 hex）。"""
    if code_mode:
        return ["".join(to_code(c, palette) for c in row) for row in face]
    return [" ".join(row) for row in face]


def face_stats(face):
    """面不透明统计 -> (不透明像素数, 总像素数)。"""
    total = len(face) * len(face[0]) if face else 0
    opaque = sum(1 for row in face for c in row if c.upper() != TRANSPARENT)
    return opaque, total


def extract_face(data, x, y, w, h):
    """提取矩形区域像素矩阵。"""
    return [row[x:x + w] for row in data[y:y + h]]


def print_warnings(warnings, limit=10):
    """打印读取阶段的警告（最多 limit 条）。"""
    if not warnings:
        return
    print(f"\n[警告 {len(warnings)} 条]")
    for item in warnings[:limit]:
        print("  " + item)
    if len(warnings) > limit:
        print(f"  ... 其余 {len(warnings) - limit} 条省略")


# ---------------------------------------------------------------- 部位报告解析
# 面头行：--- Head top (8,0 8x8) ---（允许空格/大小写等 LLM 改写后的差异）
FACE_RE = re.compile(r"^---\s*(\S+)\s+(\S+)\s*\(\s*(-?\d+)\s*,\s*(-?\d+)\s+"
                     r"(\d+)\s*[xX*]\s*(\d+)\s*\)\s*---$")
SIZE_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+)")


def _row_tokens(line, width):
    """一行的记号：hex 模式是空格分隔；代号模式常连写成 "1221"。"""
    tokens = line.split()
    if len(tokens) == width:
        return tokens
    if len(tokens) == 1 and len(tokens[0]) == width:
        return list(tokens[0])
    return tokens


def split_code_row(text, width, codes):
    """把一行代号切成正好 width 个记号；切不出来返回 None。

    * 空格分隔（"1 2 2 1"）直接采用；
    * 连写（"1221"）且刚好 width 个字符 -> 按单字符切；
    * 连写但代号可能是多字符 -> 动态规划精确切成 width 段（代号最长 8 字符内）。
    """
    tokens = text.split()
    if len(tokens) == width:
        return tokens
    joined = "".join(tokens)
    if len(joined) == width:
        return list(joined)
    total = len(joined)
    if total < width or not codes:
        return None
    longest = min(max(len(c) for c in codes), 8)
    reach = [[False] * (width + 1) for _ in range(total + 1)]
    back = [[0] * (width + 1) for _ in range(total + 1)]
    reach[0][0] = True
    for i in range(total):
        for k in range(width):
            if not reach[i][k]:
                continue
            for j in range(i + 1, min(total, i + longest) + 1):
                if joined[i:j] in codes and not reach[j][k + 1]:
                    reach[j][k + 1] = True
                    back[j][k + 1] = i
    if not reach[total][width]:
        return None
    out, i, k = [], total, width
    while k:
        prev = back[i][k]
        out.append(joined[prev:i])
        i, k = prev, k - 1
    out.reverse()
    return out


def _is_structural(line):
    """判断是不是报告里的结构性行（表头 / 分隔 / 统计），而非像素行。

    注意：hex 颜色行本身以 '#' 开头（"#050505FF …"），不能一律当注释跳过 ——
    只有 "# 文件: …" 这类「# + 空白」或「#词:」才算表头。
    """
    if line.startswith(("[", "=")):
        return True
    if line.startswith("#"):
        return len(line) < 2 or line[1] in " \t" or ":" in line.split()[0]
    return False


def read_report(path):
    """解析部位提取报告（skintool base / layers 的 -o 输出）。

    容错点（这类文件常被 LLM 编辑过）：BOM、行首尾空白、表头空格变化
    （`# 手臂: slim 尺寸: 64x64`）、多余的 `[不透明 …]` 统计行、hex 与代号两种输出。

    返回 dict(kind="report", path, faces, size, arm, code, warnings)；
    文件里一个面头都没有时返回 None（由调用方决定是否按整幅网格再试）。
    """
    lines = read_text(path).splitlines()
    size, arm = None, None
    for line in lines[:10]:
        if not line.lstrip().startswith("#"):
            continue
        m = SIZE_RE.search(line)
        if m and m.group(1) == m.group(2):
            size = int(m.group(1))
        m = re.search(r"\b(wide|slim|steve|alex)\b", line, re.I)
        if m and "手臂" in line:
            arm = "slim" if m.group(1).lower() in ("slim", "alex") else "wide"

    faces = []
    index = 0
    while index < len(lines):
        m = FACE_RE.match(lines[index].strip())
        if not m:
            index += 1
            continue
        part, face = m.group(1), m.group(2)
        x, y, w, h = (int(g) for g in m.groups()[2:])
        rows, cursor = [], index + 1
        while cursor < len(lines) and len(rows) < h:
            text = lines[cursor].strip()
            if text and not _is_structural(text):
                rows.append(text)
            cursor += 1
        if len(rows) != h:
            die(f"错误：{path} 里 {part} {face} 只有 {len(rows)} 行，报告声明 {w}x{h}"
                f"（面数据不完整；先修好这一面再合并）。")
        faces.append({"part": part, "face": face, "x": x, "y": y,
                      "w": w, "h": h, "rows_raw": rows})
        index = cursor

    if not faces:
        return None

    # 模式判定：hex 要求每一行都能切成 w 个 #RRGGBB(AA)，否则按代号行处理
    code = False
    for item in faces:
        for raw in item["rows_raw"]:
            tokens = raw.split()
            if len(tokens) != item["w"] or not all(COLOR_RE.match(t) for t in tokens):
                code = True
                break
        if code:
            break
    return {"kind": "report", "path": path, "faces": faces, "size": size,
            "arm": arm, "code": code, "warnings": []}


def report_face_tokens(face, code_mode, reverse=None, path=""):
    """把某一面的原始行切成记号矩阵（合并时调用，此时才知道调色板）。

    切不出来就报错并指出是哪一面第几行，避免糊里糊涂合并出错图。
    """
    width = face["w"]
    codes = set(reverse or {}) | {".", "?", "-", "_"}
    matrix = []
    for offset, raw in enumerate(face["rows_raw"], 1):
        if code_mode:
            tokens = split_code_row(raw, width, codes)
            if tokens is None:
                die(f"错误：{path} 的 {face['part']} {face['face']} 第 {offset} 行切不出 "
                    f"{width} 个代号：{raw[:48]}{'…' if len(raw) > 48 else ''}\n"
                    f"      代号模式需要与提取时相同的那份调色板（-p 你的调色板.gpl）。")
        else:
            tokens = raw.split()
            if len(tokens) != width:
                die(f"错误：{path} 的 {face['part']} {face['face']} 第 {offset} 行有 "
                    f"{len(tokens)} 个像素，应为 {width}（面数据不整齐；先修好这一面）。")
            for token in tokens:
                if not COLOR_RE.match(token):
                    die(f"错误：{path} 的 {face['part']} {face['face']} 第 {offset} 行出现"
                        f"非法颜色 {token!r}（hex 报告每格应为 #RRGGBB 或 #RRGGBBAA）。")
        matrix.append(tokens)
    return matrix


def read_merge_input(path):
    """合并用统一读取：PNG / 整幅 hex 网格 / 部位报告 都接受。

    返回 dict(kind, path, size, arm, code, grid, faces, warnings)；
    grid 非空 = 整幅像素（PNG 或 hex 网格），faces 非空 = 逐个面（报告）。
    """
    if not os.path.isfile(path):
        die(f"错误：找不到文件 {path}")
    with open(path, "rb") as f:
        head = f.read(8)

    if head == PNG_MAGIC:
        info = load_input(path)
        return {"kind": "png", "path": path, "size": info["size"], "arm": None,
                "code": False, "grid": info["data"], "faces": [],
                "warnings": info["warnings"]}

    report = read_report(path)
    if report is not None:
        report["grid"] = None
        return report

    data, warnings = read_grid(path)
    width, height = grid_shape(data)
    if width != height or width not in SKIN_SIDES:
        die(f"错误：{path} 既不是部位报告，也不是 64x64 / 128x128 的 hex 网格"
            f"（解析为 {width}x{height}）。")
    return {"kind": "grid", "path": path, "size": width, "arm": None, "code": False,
            "grid": data, "faces": [], "warnings": warnings}


def palette_reverse(palette):
    """{颜色: 代号} -> ({代号: 颜色}, 重复代号列表)。

    代号模式把面写成连写字符串（如 "1221"），因此要求代号是单字符；
    多字符代号会被 read_report 拦下。
    """
    reverse, dup = {}, []
    for color, code in palette.items():
        if code in reverse and reverse[code] != color:
            dup.append(code)
            continue
        reverse[code] = color
    return reverse, dup
