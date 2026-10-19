@echo off
setlocal
:: Raport ofert pracy - profil DANE I AI (Applied DS / AI Engineering).
:: Dwuklik uruchamia pobieranie danych i otwiera swiezy raport.
:: Dane i raporty: data_it\ i reports_it\ (osobno od profilu kultury)

cd /d "%~dp0"
if not exist bip_krk_raport.exe (
    echo [BLAD] Nie znaleziono bip_krk_raport.exe w tym katalogu.
    echo Zbuduj go najpierw skryptem build_exe.bat
    pause
    exit /b 1
)
bip_krk_raport.exe --profile it
