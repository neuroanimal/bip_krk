# -*- mode: python ; coding: utf-8 -*-
# Plik konfiguracyjny PyInstaller dla scrapera BIP Kraków.
#
# Buduje pojedynczy plik wykonywalny (onefile) o nazwie bip_krk_raport.exe,
# który uruchamia cały potok (etapy 1-5) i otwiera raport HTML w przeglądarce.
#
# Budowanie (w Windows, z katalogu projektu):
#     pyinstaller bip_krk.spec
# Wynik: dist\bip_krk_raport.exe
#
# WAŻNE: pliki etapów mają nazwy zaczynające się od cyfry i są ładowane w
# czasie działania przez importlib po ścieżce (patrz run_report.py). Dlatego
# dołączamy je jako pliki danych (datas), a nie jako moduły do analizy importów.

block_cipher = None

# Moduły etapów oraz wspólny moduł — dołączane jako pliki danych, bo są
# ładowane dynamicznie z dysku (importlib), a nie zwykłym importem.
stage_files = [
    ('bip_common.py', '.'),
    ('report_html.py', '.'),          # moduł prezentacji HTML (wymagany przez etap 5)
    ('1_fetch_units.py', '.'),
    ('2_fetch_praca_links.py', '.'),
    ('3_fetch_offers.py', '.'),
    ('3b_fetch_offers_global.py', '.'),   # szybka ścieżka: globalna lista naborów
    ('src_nuzle.py', '.'),                # źródło zewnętrzne: nuzle.pl
    ('src_ofertypracy_edu.py', '.'),      # źródło zewnętrzne: ofertypracy.edu.pl
    ('src_kultura_instytucje.py', '.'),  # instytucje kultury poza BIP miasta
    ('profile_match.py', '.'),            # dopasowanie do profilu zawodowego
    ('4_fetch_offer_details.py', '.'),
    ('5_generate_report.py', '.'),
]

a = Analysis(
    ['run_report.py'],
    pathex=[],
    binaries=[],
    datas=stage_files,
    # Ukryte importy — biblioteki używane przez etapy i przez bip_common.
    hiddenimports=[
        'requests',
        'bs4',
        'bip_common',
        # report_html jest importowany przez etap 5 zwykłym importem
        # (nie przez importlib), więc PyInstaller musi o nim wiedzieć.
        'report_html',
        'profile_match',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bip_krk_raport',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # okno konsoli z logami; zmień na False dla trybu cichego
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
