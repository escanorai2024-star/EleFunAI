import sys
import os
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, 
    QCheckBox, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath

# Attempt to import main.py functionality
try:
    import main
except ImportError:
    main = None

# Attempt to import loading.py functionality
try:
    from loading import LoadingWindow
except ImportError:
    LoadingWindow = None

try:
    from register import RegisterWindow
except ImportError:
    RegisterWindow = None

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setFixedSize(360, 400)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # State for window dragging
        self.old_pos = None
        
        # User credentials file path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.user_file = os.path.join(base_dir, "json", "user.txt")

        self.setup_ui()
        
        # Timer for top bar clock
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()
        
        # Try auto login
        self.logged_in = False
        self.check_auto_login()

    def check_auto_login(self):
        if os.path.exists(self.user_file):
            try:
                with open(self.user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    username = data.get('username', '')
                    password = data.get('password', '')
                    remember = data.get('remember', False)
                    
                    if username:
                        self.input_user.setText(username)
                    if password:
                        self.input_pwd.setText(password)
                    self.cb_remember.setChecked(remember)
                    
                    # If remember is checked and we have credentials, auto login
                    if remember and username and password:
                        self.handle_login(auto=True)
            except Exception as e:
                print(f"Error reading user file: {e}")

    def setup_ui(self):
        # Main container with rounded corners and white background
        self.container = QFrame(self)
        self.container.setGeometry(5, 5, 350, 390)
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
        top_bar.setSpacing(2)
        
        # Time Label
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: #333; font-weight: bold; font-size: 12px; font-family: Arial;")
        top_bar.addWidget(self.time_label)
        
        top_bar.addStretch()
        
        # Battery Icon
        lbl_battery = QLabel("🔋 100%")
        lbl_battery.setStyleSheet("color: #333; font-size: 12px; font-weight: bold;")
        top_bar.addWidget(lbl_battery)
        
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
        main_layout.addSpacing(20)

        # --- Title ---
        title = QLabel("鬼叔AI")
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
        self.input_user.setPlaceholderText("admin")
        self.input_user.setText("admin") # Default value as per request context implication
        self.input_user.setFixedHeight(45)
        self.input_user.setStyleSheet("""
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
        """)
        main_layout.addWidget(self.input_user)
        
        self.input_pwd = QLineEdit()
        self.input_pwd.setPlaceholderText("••••••")
        self.input_pwd.setEchoMode(QLineEdit.Password)
        self.input_pwd.setText("123456") # Default password for convenience
        self.input_pwd.setFixedHeight(45)
        self.input_pwd.setStyleSheet(self.input_user.styleSheet())
        main_layout.addWidget(self.input_pwd)

        # --- Checkbox and Register Button ---
        cb_layout = QHBoxLayout()
        self.cb_remember = QCheckBox("Remember me")
        self.cb_remember.setChecked(True)
        self.cb_remember.setStyleSheet("""
            QCheckBox {
                color: #666;
                font-size: 13px;
                spacing: 8px;
            }
        """)
        cb_layout.addWidget(self.cb_remember)
        
        cb_layout.addStretch()
        
        self.btn_register = QPushButton("Register")
        self.btn_register.setCursor(Qt.PointingHandCursor)
        self.btn_register.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666;
                font-size: 13px;
                border: none;
            }
            QPushButton:hover {
                color: #4CAF50;
                text-decoration: underline;
            }
        """)
        self.btn_register.clicked.connect(self.open_register)
        cb_layout.addWidget(self.btn_register)
        
        main_layout.addLayout(cb_layout)

        main_layout.addSpacing(10)

        # --- Login Button ---
        self.btn_login = QPushButton("LOGIN")
        self.btn_login.setFixedHeight(45)
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setStyleSheet("""
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
        self.btn_login.clicked.connect(self.handle_login)
        main_layout.addWidget(self.btn_login)
        
        main_layout.addStretch()

    def update_time(self):
        current_time = datetime.now().strftime("%H:%M")
        self.time_label.setText(current_time)

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

    def handle_login(self, auto=False):
        # Here you can add real authentication logic
        username = self.input_user.text()
        password = self.input_pwd.text()
        
        # Simple mock validation
        if username and password:
            # Save credentials if remember is checked
            if self.cb_remember.isChecked():
                try:
                    json_dir = os.path.dirname(self.user_file)
                    os.makedirs(json_dir, exist_ok=True)
                    with open(self.user_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            'username': username,
                            'password': password,
                            'remember': True
                        }, f, ensure_ascii=False, indent=2)
                    print(f"Credentials saved to {self.user_file}")
                except Exception as e:
                    print(f"Error saving user file: {e}")
            else:
                # If unchecked, maybe clear the file or just the remember flag?
                # User asked to save if checked. If unchecked, we usually don't save or clear.
                # Let's clear it to be safe if they explicitly uncheck it.
                if os.path.exists(self.user_file):
                    try:
                        os.remove(self.user_file)
                    except Exception:
                        pass
            
            self.launch_main_app()
        else:
            # Shake animation or error message could go here
            if not auto:
                pass

    def open_register(self):
        if RegisterWindow:
            self.register_window = RegisterWindow()
            self.register_window.show()
        else:
            print("Error: register.py not found or failed to import.")

    def launch_main_app(self):
        if main:
            self.logged_in = True
            # Hide login window
            self.hide()
            
            # Show loading window if available
            loading_win = None
            if LoadingWindow:
                loading_win = LoadingWindow()
                loading_win.show()
                # Force UI update
                QApplication.processEvents()
            
            # Start main application
            # Pass loading_window to receive progress updates
            self.main_window = main.start_main_window_from_login(loading_win)
            
            # Close loading window
            if loading_win:
                loading_win.close()
            
            # Close login window after main window is shown
            self.close()
        else:
            print("Error: main.py not found or failed to import.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Optional: Set global font
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    window = LoginWindow()
    if not window.logged_in:
        window.show()
    
    sys.exit(app.exec())
