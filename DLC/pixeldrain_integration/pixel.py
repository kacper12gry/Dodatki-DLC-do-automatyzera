import sys, os, requests, webbrowser, json, time, argparse, base64, datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QMessageBox, QFileDialog,
    QListWidget, QListWidgetItem, QProgressBar, QStyleFactory, QSplitter,
    QFrame
)
from PyQt6.QtCore import Qt, QRunnable, QThreadPool, pyqtSignal, QObject

CONFIG_FILE = "pixeldrain_config.json"
USER_INFO_URL = "https://pixeldrain.com/api/user"
FILES_URL = "https://pixeldrain.com/api/user/files"
UPLOAD_URL = "https://pixeldrain.com/api/file/{}"
VIEW_URL = "https://pixeldrain.com/u/{}"
EMBED_URL = "https://pixeldrain.com/u/{}"

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"

def apply_theme(app):
    parser = argparse.ArgumentParser()
    parser.add_argument('--style-name', type=str)
    parser.add_argument('--stylesheet-b64', type=str)
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
    def __init__(self, file_path, api_key):
        super().__init__()
        self.file_path = file_path
        self.api_key = api_key
        self.signals = WorkerSignals()
    def run(self):
        try:
            file_name = os.path.basename(self.file_path)
            url = UPLOAD_URL.format(file_name)
            with open(self.file_path, 'rb') as f:
                total_size = os.path.getsize(self.file_path)
                uploaded_size = 0
                chunk_size = 8192
                def gen():
                    nonlocal uploaded_size
                    while True:
                        data = f.read(chunk_size)
                        if not data: break
                        uploaded_size += len(data)
                        prog = int((uploaded_size / total_size) * 100)
                        self.signals.progress.emit(prog)
                        yield data
                
                headers = {'Content-Type': 'application/octet-stream'}
                resp = requests.put(url, data=gen(), auth=('', self.api_key), headers=headers)

            if resp.status_code not in (201, 200):
                self.signals.finished.emit({"error": resp.text or f"HTTP Error {resp.status_code}"})
                return

            rj = resp.json()
            file_id = rj.get('id')
            if not file_id:
                self.signals.finished.emit({"error": f"Brak ID w odpowiedzi: {rj}"})
                return

            self.signals.progress.emit(100)
            self.signals.finished.emit({
                "status": 200, "file_id": file_id,
                "viewer_url": VIEW_URL.format(file_id),
                "direct_url": EMBED_URL.format(file_id)
            })
        except Exception as e:
            self.signals.finished.emit({"error": str(e)})

class FileUploadWidget(QWidget):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.viewer_url = ""
        self.direct_url = ""
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        self.title_label = QLabel(f"⏳ {os.path.basename(self.file_path)}")
        self.progress = QProgressBar()
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress)
        hl = QHBoxLayout()
        self.viewer_btn = QPushButton("🔗 Otwórz link")
        self.viewer_btn.setEnabled(False)
        self.viewer_btn.clicked.connect(lambda: webbrowser.open(self.viewer_url) if self.viewer_url else None)
        self.direct_btn = QPushButton("📋 Kopiuj link file")
        self.direct_btn.setEnabled(False)
        self.direct_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.direct_url) if self.direct_url else None)
        hl.addWidget(self.viewer_btn)
        hl.addWidget(self.direct_btn)
        layout.addLayout(hl)

class PixeldrainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pixeldrain Uploader V2")
        self.setGeometry(150, 150, 1100, 750)
        self.selected_files = []
        self.remote_files = [] # Cache for fetched files
        self.threadpool = QThreadPool()
        self.setup_ui()
        self.load_api_key()

    def setup_ui(self):
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Wpisz swój Pixeldrain API key...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_key_btn = QPushButton("👁️")
        self.show_key_btn.setCheckable(True)
        self.show_key_btn.toggled.connect(lambda c: self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        
        hl_key = QHBoxLayout()
        hl_key.addWidget(self.api_key_input)
        hl_key.addWidget(self.show_key_btn)

        self.info_btn = QPushButton("Pobierz info o koncie")
        self.info_btn.clicked.connect(self.get_account_info)

        self.choose_btn = QPushButton("Wybierz pliki do wysłania…")
        self.choose_btn.clicked.connect(self.choose_files)
        self.upload_btn = QPushButton("Wyślij pliki")
        self.upload_btn.clicked.connect(self.upload_files)
        
        # --- Sekcja plików zdalnych i wyszukiwania ---
        self.show_files_btn = QPushButton("Odśwież listę plików")
        self.show_files_btn.clicked.connect(self.show_remote_files)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Szukaj plików...")
        self.search_input.textChanged.connect(self.filter_file_list)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("<b>Konfiguracja:</b>"))
        left_panel.addLayout(hl_key)
        left_panel.addWidget(self.info_btn)
        left_panel.addSpacing(15)
        
        left_panel.addWidget(QLabel("<b>Wysyłanie:</b>"))
        hl_upload = QHBoxLayout()
        hl_upload.addWidget(self.choose_btn)
        hl_upload.addWidget(self.upload_btn)
        left_panel.addLayout(hl_upload)
        left_panel.addSpacing(15)
        
        left_panel.addWidget(QLabel("<b>Zarządzanie plikami:</b>"))
        left_panel.addWidget(self.search_input)
        left_panel.addWidget(self.show_files_btn)
        left_panel.addStretch()

        # --- Logi ---
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0,0,0,0)
        log_layout.addWidget(QLabel("Logi / Wyniki:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        log_layout.addWidget(self.output)

        # --- Lista plików ---
        upload_widget = QWidget()
        upload_layout = QVBoxLayout(upload_widget)
        upload_layout.setContentsMargins(0,0,0,0)
        upload_layout.addWidget(QLabel("Lista plików:"))
        self.file_list = QListWidget()
        upload_layout.addWidget(self.file_list)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(log_widget)
        splitter.addWidget(upload_widget)
        splitter.setSizes([150, 550])

        right_panel = QVBoxLayout()
        right_panel.addWidget(splitter)

        main_layout = QHBoxLayout(self)
        
        # Kontener dla lewego panelu (stała szerokość)
        left_sidebar = QWidget()
        left_sidebar.setFixedWidth(300)
        left_sidebar.setLayout(left_panel)
        
        main_layout.addWidget(left_sidebar)
        main_layout.addLayout(right_panel, 1) # Prawa strona zajmuje resztę miejsca

    def load_api_key(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    self.api_key_input.setText(json.load(f).get("api_key", ""))
            except: pass

    def save_api_key(self):
        key = self.api_key_input.text().strip()
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"api_key": key}, f)
        except Exception as e:
            self.output.append(f"⚠️ Nie udało się zapisać API key: {e}")

    def get_account_info(self):
        key = self.api_key_input.text().strip()
        if not key: return QMessageBox.warning(self, "Błąd", "Podaj API key!")
        self.save_api_key()
        self.output.setText("Pobieranie informacji o koncie...")
        try:
            r = requests.get(USER_INFO_URL, auth=('', key))
            data = r.json()
            if r.status_code == 200:
                self.output.setText(json.dumps(data, indent=2))
            else:
                self.output.setText(f"Błąd API (Status: {r.status_code}):\n{json.dumps(data, indent=2)}")
        except Exception as e:
            self.output.setText(f"Błąd połączenia: {e}")

    def show_remote_files(self):
        key = self.api_key_input.text().strip()
        if not key: return QMessageBox.warning(self, "Błąd", "Podaj API key!")
        
        self.file_list.clear()
        self.file_list.addItem("Ładowanie listy plików...")
        QApplication.processEvents()

        try:
            r = requests.get(FILES_URL, auth=('', key))
            data = r.json()
            
            if r.status_code == 200 and "files" in data:
                self.remote_files = data.get("files", [])
                if not self.remote_files:
                    self.file_list.clear()
                    self.output.append("📂 Twoje konto Pixeldrain jest puste.")
                    self.file_list.addItem("Brak plików na koncie")
                    return
                
                self.output.append(f"📄 Pobrano listę {len(self.remote_files)} plików.")
                self.filter_file_list() # Wywołuje wyświetlenie z uwzględnieniem filtra
            else:
                self.file_list.clear()
                self.output.append(f"Błąd API (Status: {r.status_code}):\n{json.dumps(data, indent=2)}")
                self.file_list.addItem("Nie udało się załadować plików.")
        except Exception as e:
            self.file_list.clear()
            self.output.append(f"Błąd połączenia: {e}")
            self.file_list.addItem("Błąd połączenia.")

    def filter_file_list(self):
        """Filtruje i wyświetla pliki z cache (self.remote_files) na podstawie search_input."""
        query = self.search_input.text().lower()
        self.file_list.clear()

        if not self.remote_files:
            return

        filtered_files = [f for f in self.remote_files if query in f.get("name", "").lower()]
        
        for f in filtered_files:
            self.add_remote_file_to_list(f)
            
        if not filtered_files and query:
            self.file_list.addItem("Brak wyników wyszukiwania.")

    def add_remote_file_to_list(self, f):
        file_id = f.get("id")
        name = f.get("name", "(brak nazwy)")
        size = f.get("size", 0)
        views = f.get("views", 0)
        downloads = f.get("downloads", 0)
        date_upload = f.get("date_upload", "")
        
        # Formatowanie daty
        date_str = date_upload
        try:
            # Próba parsowania daty (zależy od formatu API Pixeldrain, zazwyczaj ISO)
            dt = datetime.datetime.fromisoformat(date_upload.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except:
            pass

        view_url, embed_url = VIEW_URL.format(file_id), EMBED_URL.format(file_id)
        
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        item_layout.setContentsMargins(5, 5, 5, 5)
        item_layout.setSpacing(2)
        
        # Górny wiersz: Nazwa i Data
        top_row = QHBoxLayout()
        name_label = QLabel(f"<b>{name}</b>")
        name_label.setStyleSheet("font-size: 14px;")
        date_label = QLabel(f"<span style='color: gray; font-size: 10px;'>{date_str}</span>")
        top_row.addWidget(name_label)
        top_row.addStretch()
        top_row.addWidget(date_label)
        item_layout.addLayout(top_row)

        # Środkowy wiersz: Statystyki
        stats_row = QHBoxLayout()
        stats_style = "color: #DDD; font-size: 11px;" # Jasny tekst dla ciemnego motywu, ale uniwersalny
        
        size_lbl = QLabel(f"💾 {format_size(size)}")
        views_lbl = QLabel(f"👁️ {views}")
        downloads_lbl = QLabel(f"⬇️ {downloads}")
        
        # Dodajemy trochę odstępu między statystykami
        stats_row.addWidget(size_lbl)
        stats_row.addSpacing(15)
        stats_row.addWidget(views_lbl)
        stats_row.addSpacing(15)
        stats_row.addWidget(downloads_lbl)
        stats_row.addStretch()
        item_layout.addLayout(stats_row)

        # Dolny wiersz: Przyciski
        buttons_layout = QHBoxLayout()
        view_btn = QPushButton("🔗 Otwórz")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.clicked.connect(lambda: webbrowser.open(view_url))
        
        embed_btn = QPushButton("📋 Kopiuj Link")
        embed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        embed_btn.clicked.connect(lambda: QApplication.clipboard().setText(embed_url))
        
        buttons_layout.addWidget(view_btn)
        buttons_layout.addWidget(embed_btn)
        buttons_layout.addStretch()
        item_layout.addLayout(buttons_layout)
        
        # Linia oddzielająca (opcjonalnie, ale QListWidget ma swoje)
        
        list_item = QListWidgetItem()
        list_item.setSizeHint(item_widget.sizeHint())
        self.file_list.addItem(list_item)
        self.file_list.setItemWidget(list_item, item_widget)

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Wybierz pliki", "", "Wszystkie pliki (*)")
        if paths:
            self.selected_files = paths
            self.output.append(f"Wybrano {len(paths)} plików do wysłania.")
            self.file_list.clear()
            self.file_list.addItem(f"Gotowe do wysłania: {len(paths)} plików. Naciśnij 'Wyślij pliki'.")

    def upload_files(self):
        key = self.api_key_input.text().strip()
        if not key or not self.selected_files:
            return QMessageBox.warning(self, "Błąd", "Podaj API key i wybierz pliki!")
        self.save_api_key()
        self.file_list.clear()
        
        for file_path in self.selected_files:
            widget = FileUploadWidget(file_path)
            list_item = QListWidgetItem()
            list_item.setSizeHint(widget.sizeHint())
            self.file_list.addItem(list_item)
            self.file_list.setItemWidget(list_item, widget)

            worker = UploadWorker(file_path, key)
            worker.signals.progress.connect(widget.progress.setValue)
            worker.signals.finished.connect(lambda res, w=widget: self.upload_finished(res, w))
            self.threadpool.start(worker)

    def upload_finished(self, result, widget):
        if result.get("status") == 200:
            widget.title_label.setText(f"✅ {os.path.basename(widget.file_path)}")
            widget.viewer_url = result.get("viewer_url", "")
            widget.direct_url = result.get("direct_url", "")
            widget.viewer_btn.setEnabled(True)
            widget.direct_btn.setEnabled(True)
            self.output.append(f"✅ Wysłano: {os.path.basename(widget.file_path)}\n➡️ {widget.viewer_url}")
        else:
            err = result.get("error", "Nieznany błąd")
            widget.title_label.setText(f"❌ {os.path.basename(widget.file_path)}")
            self.output.append(f"❌ Błąd przy wysyłaniu {os.path.basename(widget.file_path)}: {err}")
        widget.progress.setValue(100)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app)
    window = PixeldrainApp()
    window.show()
    sys.exit(app.exec())
