@echo off
chcp 65001 >nul
:: 自动切换到批处理文件所在文件夹，避免找不到py文件
cd /d %~dp0

echo ==================== 粒子模拟器启动器 ====================
echo 正在检查Pygame依赖库...
python -c "import pygame" >nul 2>&1
if %errorlevel% neq 0 (
    echo 未安装pygame，自动执行安装：pip install pygame
    python -m pip install pygame --user
)

echo 开始运行 sim.py
python sim.py

:: 运行结束后暂停，窗口唔会直接闪退
echo.
echo 程序执行完毕，按任意键关闭窗口
pause >nul