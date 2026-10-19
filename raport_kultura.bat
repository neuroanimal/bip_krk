@echo off
setlocal
:: Raport ofert pracy - profil KULTURA I SZTUKA (domyslny).
:: Dwuklik uruchamia pobieranie danych i otwiera swiezy raport.
:: Dane i raporty: data\ i reports\

cd /d "%~dp0"
if not exist bip_krk_raport.exe (
    echo [BLAD] Nie znaleziono bip_krk_raport.exe w tym katalogu.
    echo Zbuduj go najpierw skryptem build_exe.bat
    pause
    exit /b 1
)
bip_krk_raport.exe
