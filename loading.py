import sys
import importlib.util
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar, 
    QGraphicsDropShadowEffect, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont

class LoadingWindow(QWidget):
    loading_finished = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("鬼叔AI - Loading")
        self.setFixedSize(450, 350)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Drop Shadow (Android-style subtle shadow)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 80))

        # Frame (Card)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-radius: 20px;
            }
        """)
        self.frame.setGraphicsEffect(shadow)
        main_layout.addWidget(self.frame)

        # Frame Layout
        layout = QVBoxLayout(self.frame)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(25)
        layout.setContentsMargins(40, 40, 40, 40)

        # Logo/Icon Area (Circular logo)
        logo_label = QLabel("G")
        logo_label.setFixedSize(80, 80)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                font-size: 48px;
                font-weight: bold;
                border-radius: 40px;
            }
        """)
        layout.addWidget(logo_label)

        # Title
        self.title_label = QLabel("鬼叔AI")
        self.title_label.setStyleSheet("""
            color: #333333; 
            font-size: 24px; 
            font-weight: bold; 
            font-family: 'Segoe UI', 'Roboto', sans-serif;
        """)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        # Status & Progress Container
        status_container = QWidget()
        status_layout = QVBoxLayout(status_container)
        status_layout.setSpacing(15)
        status_layout.setContentsMargins(0, 0, 0, 0)
        
        # Subtitle
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("""
            color: #888888; 
            font-size: 14px;
            font-family: 'Segoe UI', 'Roboto', sans-serif;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)

        # Progress Bar (Android-style thin line)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #e0e0e0;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)
        status_layout.addWidget(self.progress_bar)
        
        layout.addWidget(status_container)

        # Timer for simulation
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_progress)
        self.progress_value = 0
        
        # Loading steps
        self.steps = [
            (15, "Loading system core..."),
            (35, "Initializing UI components..."),
            (55, "Connecting to cloud services..."),
            (75, "Loading AI models..."),
            (90, "Preparing workspace..."),
            (98, "Starting..."),
            (100, "Ready")
        ]
        self.current_step_index = 0

    def start_loading(self):
        self.progress_value = 0
        self.current_step_index = 0
        self.progress_bar.setValue(0)
        # 50ms interval, roughly 2.5 seconds total if linear, but we'll jump a bit
        self.timer.start(30) 

    def update_progress_manual(self, value, text):
        """Manually update progress from external process"""
        if self.timer.isActive():
            self.timer.stop()
        
        self.progress_value = value
        self.progress_bar.setValue(value)
        self.status_label.setText(text)
        QApplication.processEvents()

    def update_progress(self):
        # Accelerate a bit at the beginning, slow down at the end
        if self.progress_value < 60:
            self.progress_value += 2
        else:
            self.progress_value += 1
            
        self.progress_bar.setValue(self.progress_value)

        # Update text based on progress
        for threshold, text in self.steps:
            if self.progress_value < threshold:
                if self.status_label.text() != text:
                    self.status_label.setText(text)
                break
        
        if self.progress_value >= 100:
            self.timer.stop()
            self.loading_finished.emit()

def main():
    print("[Loading] 正在初始化应用程序...")
    app = QApplication(sys.argv)
    
    # Just for testing the loading window independently
    win = LoadingWindow()
    win.show()
    win.start_loading()
    
    # In a real run, we would launch the main app after loading
    # For independent test, we just exit after loading or keep it open
    # Let's keep it open for a moment then close
    win.loading_finished.connect(lambda: print("Loading finished!"))
    # win.loading_finished.connect(app.quit) # Uncomment to auto-close on finish test
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
