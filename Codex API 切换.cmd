@echo off
chcp 65001 >nul
title Codex API 切换
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-api-switch-gui.ps1"
