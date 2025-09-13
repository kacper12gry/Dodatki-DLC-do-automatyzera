import sys, requests, webbrowser, os, time, json, argparse, base64
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox, QFileDialog, QComboBox,
    QListWidget, QListWidgetItem, QProgressBar, QSplitter, QStyleFactory
)
from PyQt6.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject

INFO_URL = "https://earnvidsapi.com/api/account/info"
SERVER_URL = "https://earnvidsapi.com/api/upload/server"
FOLDERS_URL = "https://earnvidsapi.com/api/folder/list"
FILES_URL = "https://earnvidsapi.com/api/file/list"
CONFIG_FILE = "config.json"

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

class WorkerSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)

class UploadWorker(QRunnable):
    def __init__(self, key, fld_id, file_path):
        super().__init__()
        self.key = key
        self.fld_id = fld_id
        self.file_path = file_path
        self.signals = WorkerSignals()

    def run(self):
        try:
            r = requests.get(SERVER_URL, params={"key": self.key})
            upload_url = r.json().get("result")
            if not upload_url:
                self.signals.finished.emit({"error": "Brak serwera upload."})
                return

            with open(self.file_path, 'rb') as f:
                files = {'file': f}
                data = {'key': self.key, 'fld_id': self.fld_id}

                # symulacja progresu przed uploadem
                timer = 0
                while timer < 80:
                    time.sleep(0.05)
                    timer += 2
                    self.signals.progress.emit(timer)

                resp = requests.post(upload_url, files=files, data=data)
                result = resp.json()

            self.signals.progress.emit(100)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.finished.emit({"error": str(e)})

class FileUploadWidget(QWidget):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.link = ""
        self.embed = ""
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5,5,5,5)

        self.title_label = QLabel(f"⏳ {self.file_path.split('/')[-1]}")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress)

        hl = QHBoxLayout()
        self.link_btn = QPushButton("🔗 Otwórz link")
        self.link_btn.setEnabled(False)
        self.link_btn.clicked.connect(self.open_link)
        self.embed_btn = QPushButton("📎 Kopiuj embed")
        self.embed_btn.setEnabled(False)
        self.embed_btn.clicked.connect(self.copy_embed)
        hl.addWidget(self.link_btn)
        hl.addWidget(self.embed_btn)
        layout.addLayout(hl)
        self.setLayout(layout)

    def open_link(self):
        if self.link:
            webbrowser.open(self.link)

    def copy_embed(self):
        if self.embed:
            QApplication.clipboard().setText(self.embed)

class EarnVidsApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EarnVids API Panel v1.0")
        self.setGeometry(150, 150, 950, 750)
        self.selected_files = []
        self.folders = []
        self.threadpool = QThreadPool()
        self.upload_widgets = []
        self.setup_ui()
        self.load_api_key()

    def load_api_key(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    api_key = data.get("api_key", "")
                    self.api_key_input.setText(api_key)
            except:
                pass

    def save_api_key(self):
        key = self.api_key_input.text().strip()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"api_key": key}, f)
        except Exception as e:
            self.output.append(f"⚠️ Nie udało się zapisać API key: {e}")

    def setup_ui(self):
# --- Lewy panel ---
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Wpisz swój API key...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)  # ukrywa klucz

        # Przycisk pokaż/ukryj klucz
        self.show_key_btn = QPushButton("👁️")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(
            lambda checked: self.api_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )

        # Układ poziomy dla pola API Key i przycisku
        hl_key = QHBoxLayout()
        hl_key.addWidget(self.api_key_input)
        hl_key.addWidget(self.show_key_btn)

        self.info_btn = QPushButton("Pobierz info o koncie")
        self.info_btn.clicked.connect(self.get_account_info)

        self.folder_combo = QComboBox()
        self.load_folders_btn = QPushButton("Załaduj foldery")
        self.load_folders_btn.clicked.connect(self.load_folders)
        self.show_files_btn = QPushButton("Pokaż pliki w folderze")
        self.show_files_btn.clicked.connect(self.show_files_in_folder)

        self.choose_btn = QPushButton("Wybierz pliki…")
        self.choose_btn.clicked.connect(self.choose_files)
        self.upload_btn = QPushButton("Wyślij pliki")
        self.upload_btn.clicked.connect(self.upload_files)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("API Key:"))
        left_panel.addLayout(hl_key)  # <-- tutaj dodajemy układ z polem i przyciskiem
        left_panel.addWidget(self.info_btn)
        left_panel.addSpacing(20)
        left_panel.addWidget(QLabel("Foldery:"))
        hl_folders = QHBoxLayout()
        hl_folders.addWidget(self.folder_combo)
        hl_folders.addWidget(self.load_folders_btn)
        left_panel.addLayout(hl_folders)
        left_panel.addWidget(self.show_files_btn)
        left_panel.addSpacing(20)
        left_panel.addWidget(QLabel("Upload:"))
        hl_upload = QHBoxLayout()
        hl_upload.addWidget(self.choose_btn)
        hl_upload.addWidget(self.upload_btn)
        left_panel.addLayout(hl_upload)
        left_panel.addStretch()


        # Prawy panel z QSplitter
        log_widget = QWidget()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0,0,0,0)
        log_layout.addWidget(QLabel("Logi / Wyniki:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        log_layout.addWidget(self.output)
        log_widget.setLayout(log_layout)

        upload_widget = QWidget()
        upload_layout = QVBoxLayout()
        upload_layout.setContentsMargins(0,0,0,0)
        upload_layout.addWidget(QLabel("Upload plików:"))
        self.file_list = QListWidget()
        upload_layout.addWidget(self.file_list)
        upload_widget.setLayout(upload_layout)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(log_widget)
        splitter.addWidget(upload_widget)
        splitter.setSizes([200, 500])

        right_panel = QVBoxLayout()
        right_panel.addWidget(splitter)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left_panel, 2)
        main_layout.addLayout(right_panel, 5)
        self.setLayout(main_layout)

    # --- API METHODS ---
    def get_account_info(self):
        key = self.api_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Błąd", "Podaj API key!")
            return
        self.save_api_key()
        try:
            r = requests.get(INFO_URL, params={"key": key})
            data = r.json()
            if data.get("status") == 200:
                res = data["result"]
                self.output.setText(
                    f"Login: {res.get('login')}\n"
                    f"Email: {res.get('email')}\n"
                    f"Premium do: {res.get('premium_expire')}\n"
                    f"Saldo: {res.get('balance')}\n"
                    f"Liczba plików: {res.get('files_total')}\n"
                )
            else:
                self.output.setText(f"Błąd API: {data}")
        except Exception as e:
            self.output.setText(f"Błąd: {e}")

    def load_folders(self):
        key = self.api_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Błąd", "Podaj API key!")
            return
        try:
            r = requests.get(FOLDERS_URL, params={"key": key, "fld_id": 0})
            data = r.json()
            if data.get("status") == 200:
                self.folders = data["result"].get("folders", [])
                self.folder_combo.clear()
                self.folder_combo.addItem("Brak folderu (root)", "0")
                for f in self.folders:
                    self.folder_combo.addItem(f["name"], f["fld_id"])
                self.output.append("📁 Foldery załadowane.")
            else:
                self.output.append(f"Błąd: {data}")
        except Exception as e:
            self.output.setText(f"Błąd: {e}")

    def show_files_in_folder(self):
        key = self.api_key_input.text().strip()
        fld_id = self.folder_combo.currentData()
        if not key:
            QMessageBox.warning(self, "Błąd", "Podaj API key!")
            return
        try:
            r = requests.get(FILES_URL, params={"key": key, "fld_id": fld_id})
            data = r.json()
            if data.get("status") == 200:
                files = data["result"].get("files", [])
                self.file_list.clear()
                if not files:
                    self.output.append("📂 Ten folder jest pusty.")
                    return
                for f in files:
                    self.add_file_to_list(f)
                self.output.append(f"📄 Załadowano {len(files)} plików.")
            else:
                self.output.append(f"Błąd: {data}")
        except Exception as e:
            self.output.setText(f"Błąd: {e}")

    def add_file_to_list(self, f):
        file_code = f.get("file_code")
        title = f.get("title") or "(brak nazwy)"
        link = f"https://vidhideplus.com/file/{file_code}"
        embed = f'https://vidhideplus.com/embed/{file_code}'

        item_widget = QWidget()
        item_layout = QVBoxLayout()
        item_layout.setContentsMargins(5, 5, 5, 5)
        title_label = QLabel(f"📄 {title}")
        hl = QHBoxLayout()
        hl.setSpacing(10)
        link_btn = QPushButton("🔗 Otwórz link")
        link_btn.clicked.connect(lambda _, l=link: webbrowser.open(l))
        copy_btn = QPushButton("📎 Kopiuj embed")
        copy_btn.clicked.connect(lambda _, e=embed: QApplication.clipboard().setText(e))
        hl.addWidget(link_btn)
        hl.addWidget(copy_btn)
        item_layout.addWidget(title_label)
        item_layout.addLayout(hl)
        item_widget.setLayout(item_layout)

        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())
        self.file_list.addItem(list_item)
        self.file_list.setItemWidget(list_item, item_widget)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Wybierz pliki wideo", "", "Video Files (*.mp4 *.avi *.mkv)")
        if paths:
            self.selected_files = paths
            self.output.append(f"Wybrano {len(paths)} plików.")

    def upload_files(self):
        key = self.api_key_input.text().strip()
        if not key or not self.selected_files:
            QMessageBox.warning(self, "Błąd", "Podaj API key i wybierz pliki!")
            return
        fld_id = self.folder_combo.currentData()
        self.file_list.clear()
        for file_path in self.selected_files:
            widget = FileUploadWidget(file_path)
            list_item = QListWidgetItem()
            list_item.setSizeHint(widget.sizeHint())
            self.file_list.addItem(list_item)
            self.file_list.setItemWidget(list_item, widget)
            self.upload_widgets.append(widget)

            worker = UploadWorker(key, fld_id, file_path)
            worker.signals.progress.connect(widget.progress.setValue)
            worker.signals.finished.connect(lambda res, w=widget: self.upload_finished(res, w))
            self.threadpool.start(worker)

    def upload_finished(self, result, widget):
        if result.get("status") == 200:
            uploaded = result.get("files", [])[0]
            file_code = uploaded.get("filecode")
            link = f"https://vidhideplus.com/file/{file_code}"
            embed = f'https://vidhideplus.com/embed/{file_code}'
            widget.title_label.setText(f"✅ {widget.file_path.split('/')[-1]}")
            widget.progress.setValue(100)
            widget.link = link
            widget.embed = embed
            widget.link_btn.setEnabled(True)
            widget.embed_btn.setEnabled(True)
            self.output.append(f"✅ Wysłano: {widget.file_path.split('/')[-1]}")
        else:
            err = result.get("error") or str(result)
            widget.title_label.setText(f"❌ {widget.file_path.split('/')[-1]}")
            self.output.append(f"❌ Błąd przy wysyłaniu {widget.file_path.split('/')[-1]}: {err}")
            widget.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app)
    window = EarnVidsApp()
    window.show()
    sys.exit(app.exec())
