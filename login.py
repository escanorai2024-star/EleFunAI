import sys
import os
import json
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox,
    QFrame, QCheckBox, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QFont, QPalette, QColor, QMouseEvent

# Attempt to import main.py functionality
try:
    import main
except ImportError:
    main = None

class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("鬼叔AI - Login")
        self.setFixedSize(400, 420)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Set up the UI style (Unified White theme)
        self.setStyleSheet("""
            QFrame#MainFrame {
                background-color: #ffffff;
                border-radius: 16px;
                border: 1px solid #e0e0e0;
            }
            /* Unified Top Bar Style */
            QWidget#TopBar {
                background-color: #ffffff;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border-bottom: 1px solid #e0e0e0;
            }
            QLabel#TopTitle {
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 14px;
                font-weight: bold;
                color: #333333;
            }
            QPushButton#TopBtn {
                border: none;
                background: transparent;
                border-radius: 4px;
                font-size: 16px;
                color: #5f6368;
            }
            QPushButton#TopBtn:hover {
                background-color: #f0f0f0;
                color: #202124;
            }
            
            QLineEdit {
                background-color: #f5f5f5;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 10px 15px;
                font-size: 15px;
                color: #333;
                selection-background-color: #e6f4ea;
                min-height: 20px;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
                background-color: #ffffff;
            }
            QPushButton#LoginBtn {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#LoginBtn:hover {
                background-color: #43A047;
            }
            QPushButton#LoginBtn:pressed {
                background-color: #2E7D32;
                padding-top: 14px;
                padding-bottom: 10px;
            }
            QPushButton#CloseBtn {
                background-color: transparent;
                color: #bdbdbd;
                border: none;
                font-size: 16px;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton#CloseBtn:hover {
                background-color: #ffebee;
                color: #d93025;
            }
            QLabel#Title {
                color: #4CAF50;
                font-size: 24px;
                font-weight: bold;
                margin-top: 10px;
                margin-bottom: 20px;
            }
            QCheckBox {
                font-size: 13px;
                color: #666;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #bdbdbd;
                background-color: white;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border-color: #4CAF50;
            }
        """)
        
        # Main Layout (Transparent wrapper)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.setLayout(main_layout)
        
        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 40))
        
        # Main Frame
        self.frame = QFrame()
        self.frame.setObjectName("MainFrame")
        self.frame.setGraphicsEffect(shadow)
        main_layout.addWidget(self.frame)
        
        # Frame Layout
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        
        # --- Top Bar ---
        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 0, 10, 0)
        
        # Title in TopBar
        self.top_title = QLabel("鬼叔AI")
        self.top_title.setObjectName("TopTitle")
        top_layout.addWidget(self.top_title)
        
        top_layout.addStretch()
        
        # Close Button in Top Bar
        close_btn = QPushButton("✕")
        close_btn.setObjectName("TopBtn")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        top_layout.addWidget(close_btn)
        
        frame_layout.addWidget(top_bar)
        
        # Content Layout
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(40, 30, 40, 40)
        content_layout.setSpacing(20)
        frame_layout.addLayout(content_layout)

        # Welcome Title
        title_lbl = QLabel("Welcome")
        title_lbl.setObjectName("Title")
        title_lbl.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(title_lbl)
        
        # Username
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username / 账号")
        content_layout.addWidget(self.username)
        
        # Password
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password / 密码")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self.handle_login)
        content_layout.addWidget(self.password)
        
        # Remember Me
        self.remember_cb = QCheckBox("Remember me / 记住密码")
        content_layout.addWidget(self.remember_cb)
        
        content_layout.addSpacing(10)
        
        # Login Button
        self.btn_login = QPushButton("Login")
        self.btn_login.setObjectName("LoginBtn")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.clicked.connect(self.handle_login)
        content_layout.addWidget(self.btn_login)
        
        content_layout.addStretch()
        
        # Initialize
        self.load_credentials()
        
        # Auto-login check
        QTimer.singleShot(100, self.check_auto_login)
        
        # Enable dragging from Top Bar
        top_bar.mousePressEvent = self.mousePressEvent
        top_bar.mouseMoveEvent = self.mouseMoveEvent
        

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)
        
    def get_config_path(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_dir = os.path.join(base_dir, 'json')
        if not os.path.exists(json_dir):
            os.makedirs(json_dir, exist_ok=True)
        return os.path.join(json_dir, 'login_config.json')

    def load_credentials(self):
        try:
            config_path = self.get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('remember', False):
                        self.username.setText(data.get('username', ''))
                        self.password.setText(data.get('password', ''))
                        self.remember_cb.setChecked(True)
        except Exception as e:
            # print(f"Error loading credentials: {e}")
            pass

    def check_auto_login(self):
        """Check if auto-login is enabled and perform login if so."""
        if self.remember_cb.isChecked() and self.username.text() and self.password.text():
            # print("Auto-login triggered")
            self.handle_login()

    def save_credentials(self, username, password):
        try:
            config_path = self.get_config_path()
            data = {}
            if self.remember_cb.isChecked():
                data = {
                    'username': username,
                    'password': password,
                    'remember': True
                }
            else:
                # If unchecked, we might want to clear or just save username? 
                # User asked to record password to json, implying logic.
                # If unchecked, we clear the saved file or save empty.
                data = {
                    'username': '',
                    'password': '',
                    'remember': False
                }
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            # print(f"Error saving credentials: {e}")
            pass

    def handle_login(self):
        user = self.username.text().strip()
        pwd = self.password.text().strip()
        
        if not user or not pwd:
            QMessageBox.warning(self, "Tip / 提示", "Please enter username and password\n请输入账号和密码")
            return
            
        # Authentication Logic
        if user == "admin" and pwd == "admin":
            # Check user agreement before proceeding
            try:
                from Legalterms import ensure_terms_agreed
                if not ensure_terms_agreed(self):
                    return
            except ImportError:
                print("Legalterms module not found")

            # Save or clear credentials based on checkbox
            self.save_credentials(user, pwd)
            
            # print(f"Login successful for user: {user}")
            self.launch_main_app()
        else:
            QMessageBox.warning(self, "Error / 错误", "Invalid username or password\n账号或密码错误")

    def launch_main_app(self):
        if main and hasattr(main, 'start_main_window_from_login'):
            # Use LoadingWindow from loading.py
            try:
                import loading
                self.loading_win = loading.LoadingWindow()
                # We don't connect loading_finished signal anymore because we drive it manually
                # self.loading_win.loading_finished.connect(self.start_main_interface)
                self.loading_win.show()
                # Start in manual mode (or just start timer but we will interrupt it)
                self.loading_win.start_loading()
                
                # Close login window AFTER loading screen is shown
                self.close()
                
                # Start initialization immediately
                QTimer.singleShot(100, self.start_main_interface)
                
            except ImportError:
                # Fallback if loading.py is missing or has issues
                self.close()
                self.start_main_interface()
            except Exception as e:
                print(f"Error showing loading screen: {e}")
                self.close()
                self.start_main_interface()
        else:
            QMessageBox.critical(self, "Error", "Cannot load main application.\n(main.py not found or incompatible)")

    def start_main_interface(self):
        # Ensure UI is updated before heavy loading
        QApplication.processEvents()

        # Start main app FIRST to ensure it's ready before closing loading screen
        # This prevents any visual gap or delay
        try:
            loading_win = getattr(self, 'loading_win', None)
            self.main_window = main.start_main_window_from_login(loading_window=loading_win)
        except Exception as e:
            print(f"Error starting main window: {e}")
            self.main_window = None

        # Close loading window AFTER main window is initialized (and shown)
        if hasattr(self, 'loading_win'):
            self.loading_win.close()
            
        if not self.main_window:
            # Terms declined or other issue
            sys.exit(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    login_win = LoginWindow()
    login_win.show()
    
    sys.exit(app.exec())
