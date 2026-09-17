@echo off
rem ============================================================
rem  skintool.cmd - MC 皮肤工具箱包装器（免输 python 全路径）
rem  用法: skintool <命令> [参数...]      例: skintool base 皮肤.png slim -c
rem        直接双击 / 不带参数 = 进入交互菜单
rem  注意: 本文件必须保持 GBK(936) 编码 + CRLF（cmd.exe 不认 BOM/UTF-8）
rem ============================================================
setlocal
set "HERE=%~dp0"
set "PYCMD="

if exist "%HERE%.venv\Scripts\python.exe" set "PYCMD="%HERE%.venv\Scripts\python.exe""
if not defined PYCMD if exist "%HERE%..\.venv\Scripts\python.exe" set "PYCMD="%HERE%..\.venv\Scripts\python.exe""
if not defined PYCMD where python.exe >nul 2>nul && set "PYCMD=python"
if not defined PYCMD where py.exe >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD where uv.exe >nul 2>nul && set "PYCMD=uv run python"

if not defined PYCMD (
    echo [X] 没找到 Python。
    echo     方式一：在本目录执行  uv sync   生成 .venv 后重试；
    echo     方式二：安装 Python 3 并在安装时勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)

%PYCMD% "%HERE%skintool.py" %*
set "RC=%ERRORLEVEL%"

rem 双击运行时（无参数）留个窗口，别一闪而过
if "%~1"=="" pause
exit /b %RC%