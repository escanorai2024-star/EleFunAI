from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QTextEdit, QPushButton


class GenerationDialog(QDialog):
    """生成进度对话框：负责展示状态、进度条与日志。

    从 photo.py 迁移而来，保持接口一致：
    - set_status(text)
    - append_log(html_or_text)
    - set_error(text)
    - finish(success)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)
        self.setWindowTitle(self._i18n['title'])
        self.setFixedSize(520, 340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.lbl_status = QLabel(self._i18n['ready'])
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.btn_close = QPushButton(self._i18n['close'])
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)

        lay.addWidget(self.lbl_status)
        lay.addWidget(self.bar)
        lay.addWidget(self.log, 1)
        lay.addWidget(self.btn_close)

        self.setStyleSheet(
            """
            QDialog { background:#ffffff; color:#333333; }
            QLabel { color:#333333; }
            QTextEdit { background:#ffffff; color:#333333; border:1px solid #d1d1d6; border-radius:6px; }
            QProgressBar { background:#f2f2f7; border:1px solid #d1d1d6; border-radius:6px; text-align: center; color: #333333; }
            QProgressBar::chunk { background:#34c759; border-radius: 5px; }
            QPushButton { background:#ffffff; color:#333333; border:1px solid #d1d1d6; border-radius:6px; padding:6px 12px; }
            QPushButton:hover { background:#f2f2f7; border-color:#34c759; color:#34c759; }
            """
        )

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def append_log(self, text: str):
        self.log.append(text)

    def set_error(self, text: str):
        self.append_log(f"<span style='color:#ef4444;'>{self._i18n['error_prefix']}{text}</span>")
        self.set_status(self._i18n['failed'])

    def finish(self, success: bool):
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.btn_close.setEnabled(True)
        self.set_status(self._i18n['done'] if success else self._i18n['failed'])
        # 自动关闭：短暂停留以便用户看到状态后自动关闭
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(600, self.accept)
        except Exception:
            pass

    def set_language(self, code: str):
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        self.setWindowTitle(self._i18n['title'])
        # 仅更新固定文本
        if not self.lbl_status.text():
            self.lbl_status.setText(self._i18n['ready'])
        self.btn_close.setText(self._i18n['close'])

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'title': '生成进度',
            'ready': '就绪',
            'close': '关闭',
            'error_prefix': '错误：',
            'failed': '生成失败',
            'done': '生成完成',
        }
        en = {
            'title': 'Generation Progress',
            'ready': 'Ready',
            'close': 'Close',
            'error_prefix': 'Error: ',
            'failed': 'Generation Failed',
            'done': 'Generation Completed',
        }
        return zh if code == 'zh' else en