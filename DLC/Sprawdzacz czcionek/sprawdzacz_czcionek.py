#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyQt6 ASS Font Checker & Copier (Linux only) — UI po polsku, poprawione wykrywanie czcionek.
Autor: Twój Nick
Wersja: 1.0
"""
import sys
import base64
import argparse
import subprocess
import re
from pathlib import Path
from collections import defaultdict
from PyQt6 import QtGui, QtWidgets
from PyQt6.QtWidgets import QApplication, QMessageBox, QStyleFactory

def apply_theme(app):
    """
    Parsuje argumenty wiersza poleceń i aplikuje motyw przekazany
    z aplikacji głównej.
    """
    parser = argparse.ArgumentParser(description="Uruchomienie dodatku DLC z motywem.")
    parser.add_argument('--style-name', type=str, help='Nazwa stylu Qt do zastosowania.')
    parser.add_argument('--stylesheet-b64', type=str, help='Arkusz stylów QSS zakodowany w Base64.')

    args, _ = parser.parse_known_args()

    if args.style_name:
        QApplication.setStyle(QStyleFactory.create(args.style_name))

    if args.stylesheet_b64:
        try:
            decoded_bytes = base64.b64decode(args.stylesheet_b64)
            stylesheet = decoded_bytes.decode('utf-8')
            app.setStyleSheet(stylesheet)
        except Exception as e:
            print(f"Nie udało się zastosować motywu: {e}")

def run_cmd(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, ''

def normalize_font_name(name):
    return re.sub(r"\s+", " ", name.strip()).casefold()

def build_font_index():
    code, out = run_cmd(["fc-list", "--format=%{family}|%{file}\\n"])
    index = defaultdict(list)
    if code != 0:
        return index
    for line in out.splitlines():
        if not line.strip():
            continue
        if '|' in line:
            families_str, file_path = line.split('|', 1)
            families = [f.strip() for f in families_str.split(',') if f.strip()]
            for fam in families:
                index[normalize_font_name(fam)].append(file_path.strip())
    return index

def parse_ass_fonts(file_path):
    fonts = set()
    in_styles = False
    font_col_idx = None
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            for raw in f:
                line = raw.strip()
                if line.startswith('['):
                    in_styles = (line.casefold() == '[v4+ styles]'.casefold())
                    continue
                if in_styles and line.lower().startswith('format:'):
                    cols = [c.strip().casefold() for c in line.split(':', 1)[1].split(',')]
                    if 'fontname' in cols:
                        font_col_idx = cols.index('fontname')
                    continue
                if in_styles and line.lower().startswith('style:'):
                    vals = [v.strip() for v in line.split(':', 1)[1].split(',')]
                    if font_col_idx is not None and font_col_idx < len(vals):
                        fonts.add(vals[font_col_idx])
                    elif len(vals) >= 2:
                        fonts.add(vals[1])
                    continue
                if line.lower().startswith('dialogue:'):
                    for blk in re.findall(r"\{([^}]*)\}", line):
                        for m in re.finditer(r"\\fn([^\\}]+)", blk):
                            fonts.add(m.group(1).strip())
    except Exception as e:
        print(f"Błąd przy parsowaniu {file_path}: {e}")
    return set(f.strip() for f in fonts if f.strip())


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sprawdzanie czcionek ASS")
        self.resize(1000, 600)
        self.ass_files = []
        self.per_file_fonts = {}
        self.font_to_files = defaultdict(set)
        self.font_index = build_font_index()
        self._build_ui()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)

        # --- LEWA KOLUMNA ---
        # 1. Stwórz widżet-pojemnik dla lewej kolumny
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container) # Ustaw layout w pojemniku
        left_layout.setContentsMargins(0, 0, 0, 0) # Opcjonalnie: usuń marginesy

        # 2. Dodaj widżety do wewnętrznego layoutu
        left_layout.addWidget(QtWidgets.QLabel("Czcionki (✔=zainstalowana)"))
        self.list_fonts = QtWidgets.QListWidget()
        self.list_fonts.itemClicked.connect(self.show_files_for_font)
        left_layout.addWidget(self.list_fonts)
        self.details_left = QtWidgets.QTextEdit()
        self.details_left.setReadOnly(True)
        left_layout.addWidget(self.details_left)

        # --- PRAWA KOLUMNA ---
        # 1. Stwórz widżet-pojemnik dla prawej kolumny
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container) # Ustaw layout w pojemniku
        right_layout.setContentsMargins(0, 0, 0, 0) # Opcjonalnie: usuń marginesy

        # 2. Dodaj widżety do wewnętrznego layoutu
        right_layout.addWidget(QtWidgets.QLabel("Pliki ASS"))
        self.list_files = QtWidgets.QListWidget()
        self.list_files.itemClicked.connect(self.show_fonts_for_file)
        right_layout.addWidget(self.list_files)
        self.details_right = QtWidgets.QTextEdit()
        self.details_right.setReadOnly(True)
        right_layout.addWidget(self.details_right)

        # --- DODANIE DO GŁÓWNEGO UKŁADU ---
        # 3. Dodaj gotowe widżety-pojemniki do głównego layoutu
        layout.addWidget(left_container)
        layout.addWidget(right_container)

        # Pasek narzędzi (bez zmian)
        toolbar = self.addToolBar("Główne")
        btn_add = QtGui.QAction("Dodaj .ass", self)
        btn_add.triggered.connect(self.add_files)
        toolbar.addAction(btn_add)
        btn_scan = QtGui.QAction("Skanuj", self)
        btn_scan.triggered.connect(self.scan_fonts)
        toolbar.addAction(btn_scan)
        btn_remove = QtGui.QAction("Usuń plik", self)
        btn_remove.triggered.connect(self.remove_selected_file)
        toolbar.addAction(btn_remove)
        btn_remove_all = QtGui.QAction("Usuń wszystkie", self)
        btn_remove_all.triggered.connect(self.remove_all_files)
        toolbar.addAction(btn_remove_all)
        btn_info = QtGui.QAction("O programie", self)
        btn_info.triggered.connect(self.show_info)
        toolbar.addAction(btn_info)


    def add_files(self):
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Wybierz pliki ASS", str(Path.home()), "ASS (*.ass)")
        for f in files:
            p = Path(f)
            if p.exists() and p not in self.ass_files:
                self.ass_files.append(p)
                self.list_files.addItem(str(p))

    def remove_selected_file(self):
        for item in self.list_files.selectedItems():
            path = Path(item.text())
            if path in self.ass_files:
                self.ass_files.remove(path)
            self.list_files.takeItem(self.list_files.row(item))

    def remove_all_files(self):
        self.ass_files.clear()
        self.list_files.clear()
        self.list_fonts.clear()
        self.details_left.clear()
        self.details_right.clear()

    def show_info(self):
        QtWidgets.QMessageBox.information(self, "O programie", "Sprawdzanie czcionek ASS\nWersja 1.0\nBy kacper12gry")

    def scan_fonts(self):
        self.per_file_fonts.clear()
        self.font_to_files.clear()
        for f in self.ass_files:
            fonts = parse_ass_fonts(f)
            self.per_file_fonts[f] = fonts
            for font in fonts:
                self.font_to_files[font].add(f.name)
        self.update_font_list()

    def update_font_list(self):
        self.list_fonts.clear()
        for font in sorted(self.font_to_files.keys(), key=lambda x: x.casefold()):
            mark = "✔" if normalize_font_name(font) in self.font_index else "✖"
            self.list_fonts.addItem(f"{mark} {font}")

    def show_files_for_font(self, item):
        font = item.text()[2:].strip()
        files = sorted(self.font_to_files.get(font, []))
        self.details_left.setPlainText(f"Pliki używające '{font}':\n" + "\n".join(files))

    def show_fonts_for_file(self, item):
        file_path = Path(item.text())
        fonts = sorted(self.per_file_fonts.get(file_path, []))
        self.details_right.setPlainText(f"Czcionki wymagane przez '{file_path.name}':\n" + "\n".join(fonts))

# --- KLUCZOWA ZMIANA JEST TUTAJ ---
def main():
    # Krok 1: Utwórz aplikację
    app = QtWidgets.QApplication(sys.argv)

    # Krok 2: Zastosuj motyw przekazany z aplikacji głównej
    apply_theme(app)

    # Krok 3: Dopiero teraz stwórz główne okno i je pokaż
    w = MainWindow()
    w.show()

    # Krok 4: Uruchom pętlę zdarzeń
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
