import base64
import argparse
import sys
import json
import os
import re
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QProgressBar, QMenuBar,
    QVBoxLayout, QComboBox, QListWidget, QFileDialog, QTextEdit, QMessageBox, QStyleFactory, QGroupBox, QHBoxLayout
)
from PyQt6.QtCore import QObject, pyqtSignal, QProcess
from PyQt6.QtGui import QTextCursor


def apply_theme(app):
    """
    Parsuje argumenty wiersza poleceń i aplikuje motyw przekazany z aplikacji głównej.
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


class MegaUploader(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MEGA Uploader")
        self.setMinimumWidth(600)

        # Ustalenie ścieżki bazowej (dla PyInstallera)
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        # Wczytanie wersji z plugin.json
        self.plugin_version = "N/A"
        try:
            plugin_path = os.path.join(self.base_path, 'plugin.json')
            with open(plugin_path, 'r', encoding='utf-8') as f:
                plugin_info = json.load(f)
                self.plugin_version = plugin_info.get("version", "N/A")
        except Exception:
            pass # Ignoruj błąd, jeśli nie można wczytać wersji

        # Inicjalizacja stanu i procesu
        self.dane = {}
        self.file_path = ""
        self.is_uploading = False
        self.process = None

        # --- UI Setup ---
        main_layout = QVBoxLayout(self)
        main_layout.setMenuBar(self._create_menu())

        # Krok 1: Wybór konta i serii
        self.account_group = QGroupBox("Krok 1: Wybierz konto i serię")
        account_layout = QVBoxLayout(self.account_group)
        
        self.sezon_box = QComboBox()
        self.sezon_box.currentTextChanged.connect(self.update_series_list)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Wpisz frazę, aby filtrować listę serii...")
        self.search_input.textChanged.connect(self.search_series)

        self.series_list = QListWidget()

        account_layout.addWidget(QLabel("Sezon:"))
        account_layout.addWidget(self.sezon_box)
        account_layout.addWidget(QLabel("Wyszukaj serię:"))
        account_layout.addWidget(self.search_input)
        account_layout.addWidget(self.series_list)
        main_layout.addWidget(self.account_group)

        # Krok 2: Wybór pliku
        self.file_group = QGroupBox("Krok 2: Wybierz plik do wysłania")
        file_layout = QHBoxLayout(self.file_group)
        self.choose_file_btn = QPushButton("Wybierz plik...")
        self.choose_file_btn.clicked.connect(self.choose_file)
        self.file_path_label = QLabel("Nie wybrano pliku.")
        self.file_path_label.setStyleSheet("font-style: italic; color: #888;")
        file_layout.addWidget(self.file_path_label, 1)
        file_layout.addWidget(self.choose_file_btn)
        main_layout.addWidget(self.file_group)

        # Krok 3: Wysyłanie
        self.upload_group = QGroupBox("Krok 3: Rozpocznij wysyłanie")
        upload_layout = QVBoxLayout(self.upload_group)
        self.upload_btn = QPushButton("Wyślij do MEGA")
        self.upload_btn.clicked.connect(self.start_upload)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Oczekuje na rozpoczęcie.")
        upload_layout.addWidget(self.upload_btn)
        upload_layout.addWidget(self.status_label)
        upload_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.upload_group)

        # Logi i wynik
        log_group = QGroupBox("Logi i Wynik")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        log_layout.addWidget(self.log_output)
        main_layout.addWidget(log_group)

        # Wczytanie danych i aktualizacja UI
        self._load_data()

    def _create_menu(self):
        menu_bar = QMenuBar(self)
        
        # Menu Plik
        file_menu = menu_bar.addMenu("&Plik")
        open_action = file_menu.addAction("Otwórz plik z danymi...")
        open_action.triggered.connect(lambda: self._load_data(manual_selection=True))
        file_menu.addSeparator()
        close_action = file_menu.addAction("Zamknij")
        close_action.triggered.connect(self.close)

        # Menu Pomoc
        help_menu = menu_bar.addMenu("&Pomoc")
        structure_action = help_menu.addAction("Struktura pliku `dane.json`")
        structure_action.triggered.connect(self._show_structure_help)
        help_menu.addSeparator()
        about_action = help_menu.addAction("O programie")
        about_action.triggered.connect(self._show_about_dialog)

        return menu_bar

    def _load_data(self, manual_selection=False):
        filepath = ''
        if manual_selection:
            filepath, _ = QFileDialog.getOpenFileName(self, "Wybierz plik z danymi", self.base_path, "JSON Files (*.json)")
            if not filepath:
                return
        else:
            # Domyślnie szukaj obok pliku .exe lub .py
            filepath = os.path.join(self.base_path, 'dane.json')

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.dane = json.load(f)
            self.log_output.setText(f"Pomyślnie załadowano plik: {os.path.basename(filepath)}")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.dane = {}
            error_msg = "Nie znaleziono pliku `dane.json`." if isinstance(e, FileNotFoundError) else "Plik z danymi jest uszkodzony."
            self.log_output.setText(f"BŁĄD: {error_msg}\n\nUżyj menu 'Plik -> Otwórz plik z danymi...', aby wczytać poprawny plik.")
        
        self.sezon_box.clear()
        self.sezon_box.addItems(self.dane.keys())
        self.update_series_list()
        self._update_ui_state()

    def _update_ui_state(self):
        has_data = bool(self.dane)
        self.account_group.setEnabled(has_data)
        self.file_group.setEnabled(has_data)
        self.upload_group.setEnabled(has_data)
        if not has_data:
            self.status_label.setText("Wczytaj plik z danymi, aby rozpocząć.")
        else:
            self.status_label.setText("Oczekuje na rozpoczęcie.")

    def _show_structure_help(self):
        help_text = """
        <h4>Struktura pliku <code>dane.json</code></h4>
        <p>Plik powinien mieć następującą strukturę JSON:</p>
        <pre><code>{
  "Nazwa Sezonu 1": [
    {
      "Seria": "Nazwa Serii 1",
      "Mail": "email1@example.com",
      "Haslo": "haslo1"
    },
    {
      "Seria": "Nazwa Serii 2",
      "Mail": "email2@example.com",
      "Haslo": "haslo2"
    }
  ],
  "Nazwa Sezonu 2": [
    ...
  ]
}</code></pre>
        """
        QMessageBox.information(self, "Pomoc - Struktura Pliku", help_text)

    def _show_about_dialog(self):
        QMessageBox.about(self, "O programie", f"MEGA Uploader\n\nWersja: {self.plugin_version}\n\nDodatek do Automatyzera by kacper12gry.")

    def update_series_list(self):
        self.series_list.clear()
        sezon = self.sezon_box.currentText()
        if sezon in self.dane:
            for item in self.dane[sezon]:
                self.series_list.addItem(item["Seria"])

    def search_series(self):
        self.series_list.clear()
        sezon = self.sezon_box.currentText()
        text = self.search_input.text().lower()
        if sezon in self.dane:
            for item in self.dane[sezon]:
                if text in item["Seria"].lower():
                    self.series_list.addItem(item["Seria"])

    def choose_file(self):
        file, _ = QFileDialog.getOpenFileName(self, "Wybierz plik")
        if file:
            self.file_path = file
            self.file_path_label.setText(os.path.basename(file))
            self.file_path_label.setStyleSheet("") # Reset stylu

    def start_upload(self):
        if self.is_uploading:
            QMessageBox.warning(self, "Informacja", "Wysyłanie jest już w toku.")
            return

        if not self.file_path:
            QMessageBox.warning(self, "Błąd", "Nie wybrano pliku.")
            return

        if not self.series_list.currentItem():
            QMessageBox.warning(self, "Błąd", "Nie wybrano serii.")
            return

        # Zapisz wybraną serię
        self.current_seria_name = self.series_list.currentItem().text()

        self.is_uploading = True
        self.upload_btn.setEnabled(False)
        self.choose_file_btn.setEnabled(False)
        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.run_logout() # Rozpoczynamy sekwencję

    def run_command(self, command, args, on_finished_slot):
        if self.process is None:
            self.process = QProcess(self)
            self.process.readyReadStandardOutput.connect(self.handle_process_output)
            self.process.readyReadStandardError.connect(self.handle_process_output)
            self.process.errorOccurred.connect(self.handle_error)

        # Odłącz stary slot, jeśli istnieje
        try: self.process.finished.disconnect()
        except TypeError: pass

        self.process.finished.connect(on_finished_slot)
        self.process.start(command, args)

    def run_logout(self):
        self.status_label.setText("Wylogowywanie (na wszelki wypadek)...")
        self.run_command('mega-logout', [], self.run_login)

    def run_login(self, exit_code=0, exit_status=None): # Dodano domyślne argumenty
        sezon = self.sezon_box.currentText()
        # Użyj zapisanej nazwy serii
        seria_obj = next((s for s in self.dane[sezon] if s["Seria"] == self.current_seria_name), None)
        
        if not seria_obj:
            self.on_upload_finished(error="Nie znaleziono danych serii.")
            return

        mail = seria_obj["Mail"]
        haslo = seria_obj["Haslo"]

        self.status_label.setText(f"Logowanie na konto: {mail}...")
        self.run_command('mega-login', [mail, haslo], self.run_put)

    def run_put(self, exit_code, exit_status):
        if exit_code != 0:
            self.on_upload_finished(error="Logowanie nie powiodło się. Sprawdź dane i status serwera.")
            return

        self.status_label.setText(f"Wysyłanie pliku: {os.path.basename(self.file_path)}...")
        # Specjalne podłączenie do odczytu postępu
        try: self.process.readyReadStandardOutput.disconnect()
        except TypeError: pass
        self.process.readyReadStandardOutput.connect(self.update_progress)

        self.run_command('mega-put', [self.file_path], self.run_export)

    def run_export(self, exit_code, exit_status):
        # Przywrócenie normalnego odczytu logów
        try: self.process.readyReadStandardOutput.disconnect()
        except TypeError: pass
        self.process.readyReadStandardOutput.connect(self.handle_process_output)

        if exit_code != 0:
            self.on_upload_finished(error="Wysyłanie pliku nie powiodło się.")
            return

        self.status_label.setText("Generowanie linku publicznego...")
        filename = os.path.basename(self.file_path)
        self.run_command('mega-export', ['-a', filename], self.run_final_logout)

    def run_final_logout(self, exit_code, exit_status):
        if exit_code != 0:
            self.on_upload_finished(error="Nie udało się wygenerować linku.")
            return
        
        self.status_label.setText("Wylogowywanie...")
        self.run_command('mega-logout', [], self.on_upload_finished)

    def on_upload_finished(self, exit_code=0, exit_status=None, error=None):
        if error:
            self.status_label.setText(f"Błąd: {error}")
            self.log_output.append(f"\n--- BŁĄD ---\n{error}")
        else:
            self.status_label.setText("Zakończono pomyślnie!")
            self.log_output.append("\n--- SUKCES ---")
            # Wyszukiwanie linku w logach
            log_content = self.log_output.toPlainText()
            match = re.search(r'(https://mega.nz/file/\S+)', log_content)
            if match:
                link = match.group(1).replace('/file/', '/embed/')
                self.log_output.append(f"\nSeria: {self.current_seria_name}")
                self.log_output.append(f"Link do osadzenia (embed): {link}")
            else:
                self.log_output.append("\nNie udało się odnaleźć linku w logach.")

        self.is_uploading = False
        self.upload_btn.setEnabled(True)
        self.choose_file_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

    def handle_process_output(self):
        if not self.process:
            return
        output = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        error_output = self.process.readAllStandardError().data().decode('utf-8', errors='ignore')
        self.log_output.append(output.strip())
        self.log_output.append(error_output.strip())
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)

    def update_progress(self):
        output = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        self.log_output.append(output.strip())
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)

        # Proste parsowanie postępu z mega-put
        match = re.search(r'(\d+)/\d+ %\s*\((\d+)', output)
        if match:
            progress_percent = int(match.group(2))
            self.progress_bar.setValue(progress_percent)

    def handle_error(self, error):
        error_map = {
            QProcess.ProcessError.FailedToStart: "Nie udało się uruchomić procesu. Sprawdź, czy `mega-cmd` jest zainstalowane i dostępne w PATH.",
            QProcess.ProcessError.Crashed: "Proces `mega-cmd` uległ awarii.",
            QProcess.ProcessError.Timedout: "Przekroczono limit czasu.",
            QProcess.ProcessError.ReadError: "Błąd odczytu.",
            QProcess.ProcessError.WriteError: "Błąd zapisu.",
            QProcess.ProcessError.UnknownError: "Wystąpił nieznany błąd."
        }
        self.on_upload_finished(error=error_map.get(error, "Nieznany błąd procesu."))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app)  # <<< WYWOŁANIE TWOJEJ FUNKCJI
    window = MegaUploader()
    window.show()
    sys.exit(app.exec())
