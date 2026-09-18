# Minecraft Skin Tool (`skintool`)

> **Fork note:** derived from
> [EinMaulwurf/minecraft_skin_helper](https://github.com/EinMaulwurf/minecraft_skin_helper) (MIT).
> Upstream's `skin_editor.py` (PNG ↔ hex text) has been **merged into this fork's unified
> entry point `skintool.py`** — it is no longer shipped as a separate script. On top of it
> this fork adds body-part / face extraction (base + overlay layers), palette-code output
> and a Windows wrapper. See [License](#license).

Convert Minecraft skin textures between **PNG** and a **hex text grid**, and split a skin
texture into its individual **body-part faces** for quick inspection.

## Use case

Editing Minecraft skins by hand is painful; describing pixel changes to an LLM is easier
when the texture is text:

1. `skintool png2txt` turns a skin into a grid of `#RRGGBBAA` codes.
2. You give that text to an LLM (ChatGPT, Claude, Gemini, …) and describe the change
   ("make the armor purple", "add texture to the hair").
3. `skintool txt2png` turns the edited grid back into a valid PNG — dimensions and pixel
   structure guaranteed, so the usual LLM image-generation pitfalls are avoided.

For checking *what is actually painted where*, `skintool base` / `skintool layers` cut the
texture into per-part faces (optionally as palette codes), which is the fastest way to spot
a missing / transparent region.

## Requirements

- Python 3.10+ (developed against 3.13)
- [Pillow](https://pypi.org/project/Pillow/)
- optional: [`uv`](https://docs.astral.sh/uv/) — with it no manual install is needed

## Installation

```bash
uv sync                       # creates .venv + installs Pillow (recommended)
# or
pip install Pillow
```

## Quick start

On Windows the bundled wrapper `skintool.cmd` finds the interpreter for you (`.venv`, then
`python`, `py -3`, `uv run python`) — no full python path, no activation. Replace `skin.png`
with your own skin file name:

```bat
skintool png2txt skin.png                  :: -> skin_hex.txt
skintool txt2png skin_hex.txt              :: -> skin_edited.png
skintool base    skin.png slim -a          :: 底层 6 部位 × 6 面（纤细手臂 + 漏面统计）
skintool layers  skin.png -s               :: 第二层 6 部位 × 6 面（-s = slim/Alex）
skintool base    skin.png -c -p palette.gpl :: 调色板代号输出（需自备 .gpl 调色板）
skintool                                   :: 双击 = 交互菜单
```

Without the wrapper, or on Linux/macOS, the same commands work through `skintool.py`
(PNG input is read directly — converting to hex text first is **not** required):

```bash
python skintool.py base skin.png slim -c
python skintool.py layers skin_hex.txt alex -a --out report.txt
```

## Commands

| Command | Input | Output | Notes |
|---|---|---|---|
| `png2txt` (`p2t`) | skin PNG | hex grid text (default `<name>_hex.txt`) | feeds the LLM workflow |
| `txt2png` (`t2p`) | hex grid text | PNG (default `<name>_edited.png`) | `_hex` suffix is stripped |
| `base` (`b`) | PNG **or** hex text | 6 base parts × 6 faces | Head / Torso / arms / legs |
| `layers` (`l`) | PNG **or** hex text | 6 overlay parts × 6 faces | Hat / Jacket / sleeves / pants |
| `merge` (`m`) | a prefix, or 1–2 reports | one skin PNG | a prefix lists every `.txt` starting with it (no `_base`/`_layers` requirement); `--scan` = default suffix set, `--any` = all txt; every face is written back at its UV coordinates |

Run `skintool <command> -h` for everything, or `skintool` with no arguments for the
interactive menu (pick a command, then pick a file from the current directory by number).

### Options for `base` / `layers`

| Option | Meaning |
|---|---|
| positional `wide\|slim\|steve\|alex` | arm model; default `wide` (Steve) |
| `-s` / `-w` | shorthand for `slim` / `wide` |
| `-c`, `--code` | palette-code output (transparent `.`, unknown `?`); needs a palette |
| `-p`, `--palette FILE` | explicit GIMP `.gpl` palette (otherwise auto-detected) |
| `-a`, `--alpha` | per-face opacity statistics (find unpainted / transparent faces) |
| `-o`, `--out FILE` | write the full report to a file instead of stdout |
| `--size 64\|128` | force the texture size (auto-detected from the input by default) |

Without `-c` the faces are printed as raw `#RRGGBBAA` hex.

### Interactive menu

Running `skintool` with no arguments (or double-clicking `skintool.cmd`) walks through the
same five commands:

1. choose a command (1-5), then pick a file from the current directory **by number** (a full
   path works too); `merge` instead lists the report pairs it detected in the current
   directory and lets you pick one by number; `0` always goes back;
2. answer numbered questions — arm model, colour output, opacity stats, output mode
   (`1` screen, `2` screen + file, `3` file only), and for `merge` what to do with pixels no
   face covers. Every question shows its default, and the palette-code option is only offered
   when a `.gpl` palette is actually available;
3. the menu prints the **equivalent CLI command** before running it, then waits for Enter to
   return to a cleared screen — results are never silently scrolled away.

Stray input can not silently become a file: a name without an extension (like `n`) is
confirmed first, and an existing output file is never overwritten without a yes.

## Input formats

- **PNG**: standard Minecraft skin sizes `64x32` (legacy Java), `64x64` (Java) or
  `128x128` (Bedrock). Part extraction needs a square texture (`64x64` / `128x128`).
- **Hex text**: one texture row per line, one `#RRGGBBAA` code per pixel, blank lines
  skipped. Encoding may be UTF-8 with/without BOM, or GBK. Written output is UTF-8 (BOM).
- The format is detected from the **file content**, so a wrongly named file still works —
  and a PNG input never needs a manual hex conversion step.

## Palettes

No palette is bundled (palettes are personal content). Drop your own GIMP palette next to
the scripts — if exactly one `.gpl` exists in the script directory or the current working
directory it is used automatically; with zero or several, pass `--palette FILE`.

GPL line format:

```
R G B <tab> Name [CODE]        e.g.   8   8  12<TAB>Void Black [0]
```

Codes are read from `[CODE]` (leading `[CODE] Name` also works). With `-c`:

- `.` = fully transparent pixel
- `?` = color not present in the palette
- otherwise = your code, one character per pixel

## Editing the hex text with an LLM

- Each line = one row of the texture, each `#RRGGBBAA` = one pixel.
- **Crucial:** keep the grid structure — same number of codes per line, same number of
  lines, only valid 8-digit hex codes prefixed with `#`. Broken structure is reported when
  converting back.

A prompt that works well:

```txt
I need your help customizing my minecraft skin. I attached it as an PNG.
Also, below I will give you the HEX representation of that skin where you can see
the color of each pixel. You will give me the HEX representation back and only
change the values in it. Make sure to use the `#RRGGBBAA` format.
You do not change the number of rows or columns. The result should have the same dimensions!

Currently, the skin has the character wearing a typical diamond minecraft armor.
I'd like you to change the color to purple.

(and then the HEX representation of the skin)
```

## Part / face layout

`base` extracts Head / Torso / RightArm / LeftArm / RightLeg / LeftLeg;
`layers` extracts the overlay (second layer): Hat / Jacket / RightSleeve / LeftSleeve /
RightPants / LeftPants. Each part is printed as its six faces (`top`, `bottom`, `right`,
`front`, `left`, `back`) with the source coordinates in the heading.

`wide` (Steve, 4 px arms) and `slim` (Alex, 3 px arms) are **not** just a width change:
the slim arm texture is packed compactly, so the `left` / `bottom` / `back` faces start
1 px earlier (`x47` instead of `x48`). Pass the correct model or the arm faces will be
offset by one pixel. The layout matches Blockbench's display.

`-a` semantics differ per layer: `base` flags faces that are not fully painted
(suspected missing face), while `layers` only flags faces that are **entirely**
transparent (partial transparency is normal for overlays).

## Merging the two reports back into a PNG

`base` + `layers` reports are the other half of the round trip: edit them (by hand or with
an LLM) and rebuild one complete skin PNG from both — selected by **file prefix**:

```bat
skintool base   skin.png slim -o skin_base.txt
skintool layers skin.png slim -o skin_layers.txt
skintool merge  skin                    :: -> skin_merged.png
skintool merge  skin --fill skin.png    :: keep the original pixels where no face covers them
```

- **Nothing is paired up for you, and nothing is hard-coded.** The menu lists every `.txt` in the
  folder and you pick two by number; typing anything first just **narrows the range**. A prefix, a
  suffix, a wildcard — they are all the same kind of filter, used only to keep the list short:

  ```
  txt 共 4 个（可输入前缀 / 后缀 / 通配缩小范围）
    [ 1] Crow_35_base.txt     36 面
    [ 2] Crow_35_layers.txt   36 面
    [ 3] Crown_base.txt       36 面
    [ 4] Crown_layers.txt     36 面

  第一个文件（序号 / 缩小范围 / a=全部 / 0=返回）: Crow_35      <- 缩小到 2 个
  第一个文件（序号 / 缩小范围 / a=全部 / 0=返回）: 1
  第二个文件（序号 / 缩小范围 / a=全部 / 0=返回）: 2            <- 第二个重新从全部开始
  ```

  - Filtering by suffix alone would only ever offer two files *of the same kind* (two base reports,
    or two overlay reports) — that cannot rebuild a complete skin, so the tool never proposes such
    a pair: you always make the two picks yourself.
  - Picking two reports of the same kind is still allowed when you mean it (e.g. building a
    base-only texture) and is flagged: `[注意] 两份都是底层（base）报告 —— 合并结果只有这一层`.
  - Each line shows what the file is (`36 面` / `36 面（代号）` / `整幅 64x64`), the file already
    chosen is marked `<- 已选作第一个` and cannot be picked twice, and every prompt reprints the
    list it numbers. `a` returns to the full list, `0` goes back.
  - CLI equivalents are shortcuts for the same narrowing: `skintool merge <prefix>`,
    `--scan` (default suffix set), `--suffix _a,_b` (your own), `--any` (every txt); each takes
    effect only when exactly two files match, otherwise the candidates are listed.
- Every face is written at the coordinates in its own `--- Part face (x,y wxh) ---` heading,
  so the report always wins over any assumption about the layout. Reports whose arm models
  disagree still merge, but a warning is printed.
- Both report flavours are accepted: hex (`#RRGGBBAA`) and palette codes (`-c`), the latter
  reconstructed through the same `.gpl` palette (codes of any length, matched exactly).
  A PNG or a plain hex grid can be one of the inputs as well.
- Pixels no face covers stay transparent by default; `--fill skin.png` keeps the original
  content there instead. Palette codes missing from the palette are reported loudly with
  their counts and left transparent — never silently turned into black.
- The round trip is lossless: rebuilding from reports extracted out of a skin reproduces that
  skin **pixel for pixel** (verified on 64x64 and 128x128, hex and code mode, wide and slim).

## Limitations

LLM editing works best on the smaller textures: a `64x64` skin is roughly 35k tokens, and
models have been observed to stop early while regenerating it. If your model truncates,
edit only the rows you need, or use a `64x32` texture.

## Repository layout

| File | Role |
|---|---|
| `skintool.py` | unified CLI (`png2txt` / `txt2png` / `base` / `layers`) + interactive menu |
| `skintool.cmd` | Windows wrapper: locates Python, passes arguments, menu on double-click |
| `skinio.py` | shared IO layer: PNG ↔ hex grid, size detection, palette parsing, code mapping |
| `split_skin.py` | base-layer part extraction (also usable standalone) |
| `split_skin_layers.py` | overlay-layer part extraction (also usable standalone) |

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE).
Original `skin_editor.py` and upstream docs © 2025 EinMaulwurf; `skintool.py` / `skinio.py` /
`split_skin*.py` and this fork's docs © this fork's author.

---

## 中文速查

```bat
skintool png2txt 皮肤.png                 :: PNG → hex 文本（发 LLM 改色）
skintool txt2png 皮肤_hex.txt             :: 改完的文本 → PNG
skintool base    皮肤.png slim -a -o 前缀_base.txt   :: 底层各部位/面（-a = 漏面统计）
skintool layers  皮肤.png -s    -o 前缀_layers.txt     :: 第二层（-s = 纤细/Alex 手臂）
skintool merge   前缀                     :: 列出以该前缀开头的 txt，挑两份 → 前缀_merged.png
skintool base    皮肤.png -c -p 调色板.gpl :: 调色板代号输出（需自备 .gpl）
skintool                                  :: 不带参数 = 交互菜单（双击 skintool.cmd）
```

- **合并（merge）**：把两份部位报告按报告里写的 UV 坐标写回一张皮肤 PNG。
  菜单里**一屏列出目录里所有 txt**，直接选号挑两份；想省事就先输一段字**缩小范围**
  （前缀、后缀、通配都行，`a` 回全部），比如输 `Crow_35` 再选 1、2。
  工具**不会替你配好一对**（后缀筛出来的两份是同形态文本，凑一起也生成不出完整皮肤），
  两份都由你自己挑；真挑了两份同形态的会提醒「合并结果只有这一层」。
  CLI 只是同一种缩小范围的快捷写法：`skintool merge 前缀` / `--scan`（默认后缀集合）/
  `--suffix 后缀` / `--any`（全部 txt），各自恰好命中 2 个文件时才自动使用。只认 `.txt`。
  没被任何面覆盖的像素默认留透明，加 `--fill 前缀.png` 就保留原图那些位置；
  代号报告用当初那份 `.gpl`（加 `-p`），调色板里没有的代号会**明确报出数量**并留透明。
  实测：从皮肤提取出的两份报告再合并，能**逐像素还原原皮肤**。
- **菜单怎么走**：选命令（1-5）→ 按序号选当前目录里的文件 / 报告前缀（也可粘完整路径）→
  手臂类型 → 颜色输出 → 不透明统计 → 输出方式（`1` 打印到屏幕 / `2` 屏幕+写文件 /
  `3` 只写文件）。每题都标了默认值，**任何一步输 `0` 都能返回**；跑之前会打印
  「等价命令」，跑完按回车清屏回菜单，结果不会被刷掉。
- **不会误建文件**：文件名处输入 `n` 这类没扩展名的内容会先确认；已存在的输出文件
  覆盖前会问一声；没有 `.gpl` 调色板时菜单不会问代号输出，直接给 hex 颜色。
- 调色板：把自己的 `.gpl` 放在脚本目录或当前目录（唯一一个即自动使用，否则用 `-p 文件` 指定）。
- 输入可直接是 PNG，**不需要**先手工转成 hex 文本。
