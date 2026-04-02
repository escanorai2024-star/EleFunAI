import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, 
    QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QFont, QIcon

class RegisterWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Register")
        self.setFixedSize(360, 450)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # State for window dragging
        self.old_pos = None

        self.setup_ui()

    def setup_ui(self):
        # Main container with rounded corners and white background
        self.container = QFrame(self)
        self.container.setGeometry(5, 5, 350, 440)
        self.container.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
            }
        """)
        
        # Add shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 0)
        self.container.setGraphicsEffect(shadow)

        # Main Layout
        main_layout = QVBoxLayout(self.container)
        main_layout.setContentsMargins(20, 10, 20, 30)
        main_layout.setSpacing(10)

        # --- Top Bar ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch()
        
        # Close Button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 20)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                color: #f44336;
            }
        """)
        btn_close.clicked.connect(self.close)
        top_bar.addWidget(btn_close)
        
        main_layout.addLayout(top_bar)
        
        # Spacer
        main_layout.addSpacing(10)

        # --- Title ---
        title = QLabel("Register")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #4CAF50;
            font-size: 32px;
            font-weight: bold;
            font-family: 'Segoe UI', Arial;
        """)
        main_layout.addWidget(title)
        
        main_layout.addSpacing(20)

        # --- Inputs ---
        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Username")
        self.input_user.setFixedHeight(45)
        self.input_user.setStyleSheet(self._input_style())
        main_layout.addWidget(self.input_user)
        
        self.input_pwd = QLineEdit()
        self.input_pwd.setPlaceholderText("Password")
        self.input_pwd.setEchoMode(QLineEdit.Password)
        self.input_pwd.setFixedHeight(45)
        self.input_pwd.setStyleSheet(self._input_style())
        main_layout.addWidget(self.input_pwd)
        
        self.input_confirm = QLineEdit()
        self.input_confirm.setPlaceholderText("Confirm Password")
        self.input_confirm.setEchoMode(QLineEdit.Password)
        self.input_confirm.setFixedHeight(45)
        self.input_confirm.setStyleSheet(self._input_style())
        main_layout.addWidget(self.input_confirm)

        main_layout.addSpacing(20)

        # --- Register Button ---
        self.btn_register = QPushButton("REGISTER")
        self.btn_register.setFixedHeight(45)
        self.btn_register.setCursor(Qt.PointingHandCursor)
        self.btn_register.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 22px;
                border: none;
            }
            QPushButton:hover {
                background-color: #43A047;
            }
            QPushButton:pressed {
                background-color: #388E3C;
            }
        """)
        self.btn_register.clicked.connect(self.handle_register)
        main_layout.addWidget(self.btn_register)
        
        main_layout.addStretch()

    def _input_style(self):
        return """
            QLineEdit {
                background-color: #f5f5f5;
                border: none;
                border-radius: 22px;
                padding: 0 20px;
                font-size: 14px;
                color: #333;
            }
            QLineEdit:focus {
                background-color: #e0e0e0;
            }
        """

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def handle_register(self):
        # Mock registration logic
        username = self.input_user.text()
        password = self.input_pwd.text()
        confirm = self.input_confirm.text()
        
        if username and password and password == confirm:
            print(f"Registering user: {username}")
            self.close()
        else:
            print("Registration failed: Invalid input or passwords do not match")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    window = RegisterWindow()
    window.show()
    sys.exit(app.exec())
