@echo off
setlocal
cd /d "%~dp0"

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

flet pack main.py --name PinterestSaver

echo.
echo Done. Check dist\PinterestSaver.exe
pause

