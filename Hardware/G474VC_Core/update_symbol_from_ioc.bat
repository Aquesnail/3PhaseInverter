@echo off
chcp 65001 >nul
setlocal

rem ============================================================
rem  Update this project's KiCad symbol library from CubeMX .ioc
rem  ------------------------------------------------------------
rem  Double-click to update.  Extra arguments are passed through:
rem      update_symbol_from_ioc.bat --dry-run
rem      update_symbol_from_ioc.bat --strip-pin-suffix
rem      update_symbol_from_ioc.bat --reset-options
rem
rem  After it finishes: in KiCad's schematic editor click
rem      Tools  ->  Update Symbols from Library
rem  ...and pick the 3phase_inverter library.  Placed symbols keep
rem  their position, wires and net labels.
rem ============================================================

set "TOOL=C:\Projects\Simulink\dsh_mcp_test\tools\ioc2kicad\ioc2kicad.py"
set "PROJ=%~dp0"

if not exist "%TOOL%" (
    echo [ERROR] Converter not found:
    echo         %TOOL%
    pause
    exit /b 1
)

echo ============================================================
echo  ioc2kicad : update symbol library from CubeMX .ioc
echo  Project   : %PROJ%
echo ============================================================
echo.

python "%TOOL%" --update-project "%PROJ%." %*
if errorlevel 1 goto fail

echo.
echo ------------------------------------------------------------
echo  Next step in KiCad:
echo    Tools  -^>  Update Symbols from Library
echo    -^> check the 3phase_inverter library  -^> Update
echo ------------------------------------------------------------
pause
exit /b 0

:fail
echo.
echo [FAILED] see messages above.
pause
exit /b 1
