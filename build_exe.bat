@echo off
:: ==========================================================================
:: build_exe.bat - buduje bip_krk_raport.exe w Windows (bez potrzeby WSL).
::
:: Wymaga JEDNORAZOWO zainstalowanego Pythona (do zbudowania .exe).
:: Gotowy .exe dziala juz BEZ Pythona.
::
:: Uruchom: kliknij dwukrotnie ten plik LUB w cmd:  build_exe.bat
:: Wynik:   dist\bip_krk_raport.exe
:: ==========================================================================

setlocal

:: Wybor interpretera: preferujemy launcher "py" (niezawodny), z fallbackiem.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
) else (
    set "PY=python"
)

echo.
echo === Instaluje zaleznosci (requests, beautifulsoup4, pyinstaller) ===
%PY% -m pip install --upgrade pip
%PY% -m pip install requests beautifulsoup4 pyinstaller
if errorlevel 1 (
    echo.
    echo [BLAD] Nie udalo sie zainstalowac zaleznosci.
    pause
    exit /b 1
)

echo.
echo === Buduje plik wykonywalny (PyInstaller, onefile) ===
%PY% -m PyInstaller --clean --noconfirm bip_krk.spec
if errorlevel 1 (
    echo.
    echo [BLAD] Budowanie .exe nie powiodlo sie.
    pause
    exit /b 1
)

echo.
echo === GOTOWE ===
echo Plik wykonywalny: dist\bip_krk_raport.exe
echo Kliknij go dwukrotnie, aby pobrac dane i otworzyc raport za dzis.
echo.
pause
