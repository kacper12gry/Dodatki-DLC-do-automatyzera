# account_manager_dialog.py
import json
import copy
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, 
    QDialogButtonBox, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QHBoxLayout, QSplitter, QWidget, QPushButton, QLabel
)
from PyQt6.QtCore import Qt

class AccountManagerDialog(QDialog):
    def __init__(self, dane, filepath, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zarządzaj Kontami")
        self.setMinimumSize(800, 500)

        self.filepath = filepath
        self.dane = copy.deepcopy(dane) # Pracuj na głębokiej kopii
        self.current_item = None # Przechowuje aktualnie edytowany element drzewa
        self.data_changed = False

        # --- UI Setup ---
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Lewy panel (drzewo)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Sezony i Serie"])
        self.tree.currentItemChanged.connect(self.on_item_selected)
        left_layout.addWidget(self.tree)
        
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Dodaj nowe")
        self.delete_button = QPushButton("Usuń zaznaczone")
        self.add_button.clicked.connect(self.prepare_for_add)
        self.delete_button.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.delete_button)
        left_layout.addLayout(button_layout)
        
        splitter.addWidget(left_panel)

        # Prawy panel (formularz)
        right_panel = QWidget()
        self.form_layout = QFormLayout(right_panel)
        
        self.sezon_combo = QComboBox()
        self.sezon_combo.setEditable(True)
        self.seria_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.haslo_edit = QLineEdit()
        self.haslo_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.form_layout.addRow(QLabel("<h3>Dane konta</h3>"))
        self.form_layout.addRow("Nazwa sezonu:", self.sezon_combo)
        self.form_layout.addRow("Nazwa serii:", self.seria_edit)
        self.form_layout.addRow("E-mail konta:", self.email_edit)
        self.form_layout.addRow("Hasło konta:", self.haslo_edit)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.form_layout.addRow(self.button_box)
        
        right_panel.setEnabled(False) # Domyślnie wyłączony
        self.form_widget = right_panel
        splitter.addWidget(right_panel)

        splitter.setSizes([300, 500])

        self.populate_tree()

    def populate_tree(self):
        """Wypełnia drzewo danymi z `self.dane`."""
        self.tree.clear()
        for sezon, serie in self.dane.items():
            sezon_item = QTreeWidgetItem(self.tree, [sezon])
            for seria_data in serie:
                seria_item = QTreeWidgetItem(sezon_item, [seria_data["Seria"]])
                seria_item.setData(0, Qt.ItemDataRole.UserRole, seria_data) # Przechowaj cały słownik
        self.tree.expandAll()

    def mark_as_changed(self):
        """Oznacza dane jako zmienione i aktualizuje tytuł okna."""
        if not self.data_changed:
            self.data_changed = True
            self.setWindowTitle(self.windowTitle() + " *")

    def on_item_selected(self, current, previous):
        """Wywoływane po wybraniu elementu w drzewie."""
        self.current_item = current
        if not current or not current.parent(): # Jeśli to sezon, a nie seria
            self.form_widget.setEnabled(False)
            return

        self.form_widget.setEnabled(True)
        seria_data = current.data(0, Qt.ItemDataRole.UserRole)
        
        self.sezon_combo.blockSignals(True)
        self.sezon_combo.clear()
        self.sezon_combo.addItems(self.dane.keys())
        self.sezon_combo.setCurrentText(current.parent().text(0))
        self.sezon_combo.blockSignals(False)

        self.seria_edit.setText(seria_data["Seria"])
        self.email_edit.setText(seria_data["Mail"])
        self.haslo_edit.setText(seria_data["Haslo"])

    def prepare_for_add(self):
        """Czyści formularz, aby umożliwić dodanie nowego wpisu."""
        self.tree.clearSelection()
        self.current_item = None
        self.form_widget.setEnabled(True)
        
        self.sezon_combo.blockSignals(True)
        self.sezon_combo.clear()
        self.sezon_combo.addItems(self.dane.keys())
        self.sezon_combo.setCurrentText("")
        self.sezon_combo.blockSignals(False)

        self.seria_edit.clear()
        self.email_edit.clear()
        self.haslo_edit.clear()
        self.sezon_combo.setFocus()

    def delete_selected(self):
        """Usuwa zaznaczoną serię lub cały sezon."""
        if not self.current_item:
            QMessageBox.warning(self, "Błąd", "Wybierz element, który chcesz usunąć.")
            return

        item_is_season = not self.current_item.parent()

        if item_is_season:
            sezon_name = self.current_item.text(0)
            title = "Potwierdzenie usunięcia sezonu"
            text = f"Czy na pewno chcesz usunąć cały sezon '{sezon_name}' i wszystkie jego serie?"
        else:  # item is a series
            seria_data = self.current_item.data(0, Qt.ItemDataRole.UserRole)
            sezon_name = self.current_item.parent().text(0)
            title = "Potwierdzenie usunięcia serii"
            text = f"Czy na pewno chcesz usunąć serię '{seria_data['Seria']}' z sezonu '{sezon_name}'?"

        reply = QMessageBox.question(self, title, text,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            return

        if item_is_season:
            if sezon_name in self.dane:
                del self.dane[sezon_name]
                self.mark_as_changed()
        else:
            if sezon_name in self.dane and seria_data in self.dane[sezon_name]:
                self.dane[sezon_name].remove(seria_data)
                if not self.dane[sezon_name]:  # Jeśli sezon jest pusty, usuń go
                    del self.dane[sezon_name]
                self.mark_as_changed()

        self.populate_tree()
        self.form_widget.setEnabled(False)

    def accept(self):
        """Waliduje formularz i zapisuje wszystkie zmiany (dodanie, edycja, usunięcie)."""
        # Jeśli formularz jest aktywny, przetwarzamy jego dane
        if self.form_widget.isEnabled():
            sezon = self.sezon_combo.currentText().strip()
            seria = self.seria_edit.text().strip()
            email = self.email_edit.text().strip()
            haslo = self.haslo_edit.text().strip()

            if not all([sezon, seria, email, haslo]):
                QMessageBox.warning(self, "Brak danych", "Wszystkie pola muszą być wypełnione.")
                return  # Nie zamykaj, pozwól na korektę

            new_data = {"Seria": seria, "Mail": email, "Haslo": haslo}

            if self.current_item and self.current_item.parent():  # Tryb edycji serii
                old_data = self.current_item.data(0, Qt.ItemDataRole.UserRole)
                old_sezon = self.current_item.parent().text(0)

                if old_sezon == sezon:
                    old_data.update(new_data)
                else:
                    self.dane[old_sezon].remove(old_data)
                    if not self.dane[old_sezon]:
                        del self.dane[old_sezon]
                    if sezon not in self.dane:
                        self.dane[sezon] = []
                    self.dane[sezon].append(new_data)
            else:  # Tryb dodawania nowej serii
                if sezon not in self.dane:
                    self.dane[sezon] = []

                for s in self.dane[sezon]:
                    if s['Seria'].lower() == seria.lower():
                        QMessageBox.warning(self, "Duplikat", f"Seria '{seria}' już istnieje w tym sezonie.")
                        return
                self.dane[sezon].append(new_data)

            self.mark_as_changed()
            self.populate_tree()  # Odśwież drzewo, aby pokazać zmiany
            self.form_widget.setEnabled(False)

        # Zapisz zmiany, jeśli jakiekolwiek nastąpiły
        if self.data_changed:
            if self._save_data():
                QMessageBox.information(self, "Sukces", "Zmiany zostały pomyślnie zapisane.")
                super().accept()
            else:
                # Błąd zapisu, nie zamykaj dialogu
                return
        else:
            super().accept()

    def _save_data(self):
        """Zapisuje dane do pliku JSON."""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.dane, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Błąd zapisu", f"Nie udało się zapisać pliku `dane.json`:\n{e}")
            return False

    def reject(self):
        """Obsługuje zamknięcie okna (przycisk Anuluj, ESC, przycisk 'X')."""
        if self.data_changed:
            reply = QMessageBox.question(self, 'Niezapisane zmiany',
                                         'Masz niezapisane zmiany. Czy chcesz je zapisać?',
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Save:
                self.accept()  # Wywołaj logikę zapisu; zamknie okno jeśli się powiedzie
            elif reply == QMessageBox.StandardButton.Discard:
                super().reject()  # Odrzuć zmiany i zamknij
            else:  # Cancel
                return  # Nie rób nic, nie zamykaj okna
        else:
            super().reject()  # Brak zmian, po prostu zamknij

    def reject(self):
        """Obsługuje zamknięcie okna (przycisk Anuluj, ESC, przycisk 'X')."""
        if self.data_changed:
            reply = QMessageBox.question(self, 'Niezapisane zmiany',
                                         'Masz niezapisane zmiany. Czy chcesz je zapisać?',
                                         QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                         QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Save:
                self.accept()  # Wywołaj logikę zapisu; zamknie okno jeśli się powiedzie
            elif reply == QMessageBox.StandardButton.Discard:
                super().reject()  # Odrzuć zmiany i zamknij
            else:  # Cancel
                return  # Nie rób nic, nie zamykaj okna
        else:
            super().reject()  # Brak zmian, po prostu zamknij