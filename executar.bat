@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Encontrei - Achados e Perdidos

echo ==========================================
echo  Encontrei - Achados e Perdidos
echo ==========================================
echo.

REM Tenta primeiro o comando python (evita um launcher py com caminho antigo).
where python >nul 2>&1
if not errorlevel 1 (
    python --version >nul 2>&1
    if not errorlevel 1 (
        echo Iniciando com Python...
        python app.py
        goto :fim
    )
)

REM Se python nao funcionar, tenta o launcher py.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        echo Iniciando com o launcher py...
        py -3 app.py
        goto :fim
    )
)

echo ERRO: nao foi possivel encontrar uma instalacao funcional do Python.
echo O projeto precisa do Python 3.10 ou mais recente.
echo.
echo 1. Baixe em https://www.python.org/downloads/windows/
echo 2. Rode o instalador e marque Add python.exe to PATH.
echo 3. Feche esta janela e abra o executar.bat novamente.
echo.
echo Para diagnosticar, abra CMD e execute:
echo   python --version
echo   py -0p
pause
exit /b 1

:fim
if errorlevel 1 pause
