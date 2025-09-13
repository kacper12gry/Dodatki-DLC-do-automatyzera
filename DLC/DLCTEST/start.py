import sys
from PyQt6.QtWidgets import QApplication, QMessageBox

# Prosty przykład: aplikacja, która tylko wyświetla okno komunikatu
app = QApplication(sys.argv)
QMessageBox.information(None, "Mój Dodatek", "Witaj! Dodatek został pomyślnie uruchomiony.")
sys.exit()
