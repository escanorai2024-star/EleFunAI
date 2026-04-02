from __future__ import annotations
import os
import json
import sys
from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
)


TERMS_TEXT_ZH = (
    "使用本软件即代表您已阅读并同意以下用户协议：\n\n"
    "[✓] 您不得实施包括但不限于以下行为，也不得为任何违反法律法规的行为提供便利：\n"
    "    反对宪法所规定的基本原则的。\n"
    "    危害国家安全，泄露国家秘密，颠覆国家政权，破坏国家统一的。\n"
    "    损害国家荣誉和利益的。\n"
    "    煽动民族仇恨、民族歧视，破坏民族团结的。\n"
    "    破坏国家宗教政策，宣扬邪教和封建迷信的。\n"
    "    散布谣言，扰乱社会秩序，破坏社会稳定的。\n"
    "    散布淫秽、色情、赌博、暴力、凶杀、恐怖或教唆犯罪的。\n"
    "    侮辱或诽谤他人，侵害他人合法权益的。\n"
    "    实施任何违背\"七条底线\"的行为。\n"
    "    含有法律、行政法规禁止的其他内容的。\n\n"
    "[✓] 不得使用他人的素材进行二次产生图片。\n"
    "[✓] 不得违反相关互联网规定。\n"
    "[✓] 不得使用软件用于违法用途。\n"
    "[✓] 不得参考借鉴他人风格，否则会被封号，永不解封，相关产生的记录会记录在API服务商。后果由您自行承担。\n"
    "[✓] 因您的数据的产生、收集、处理、使用等任何相关事项存在违反法律法规等情况而造成的全部结果及责任均由您自行承担。\n\n"
    "本软件完全免费，仅用作 AIGC 学习使用，为游戏创作者、视频制作者 增效节能。"
)

TERMS_TEXT_EN = (
    "By using this software, you agree to the following user agreement:\n\n"
    "[✓] You shall not engage in any of the following behaviors, including but not limited to, nor shall you facilitate any behavior that violates laws and regulations:\n"
    "Opposing the basic principles stipulated in the Constitution.\n"
    "Endangering national security, leaking state secrets, subverting state power, or undermining national unity.\n"
    "Damaging national honor and interests.\n"
    "Inciting ethnic hatred or discrimination, or undermining ethnic unity.\n"
    "Undermining national religious policies, or promoting cults and feudal superstitions.\n"
    "Spreading rumors, disrupting social order, or undermining social stability.\n"
    "Spreading obscenity, pornography, gambling, violence, murder, terrorism, or instigating crime.\n"
    "Insulting or defaming others, or infringing upon the legitimate rights and interests of others.\n"
    "Any behavior that violates the 'Seven Bottom Lines'.\n"
    "Containing other content prohibited by laws and administrative regulations.\n\n"
    "[✓] You may not use other people's materials to create derivative images.\n"
    "[✓] You may not violate relevant internet regulations.\n"
    "[✓] You may not use software for illegal purposes.\n"
    "[✓] You may not reference or imitate other people's styles; otherwise, your account will be banned permanently, and related records will be kept by the API service provider. You will be solely responsible for the consequences.\n"
    "[✓] You will be solely responsible for all consequences and liabilities arising from any violation of laws and regulations related to the generation, collection, processing, or use of your data.\n\n"
    "This software is completely free, intended solely for AIGC learning, improving efficiency for game creators and video producers."
)


def _agreement_path() -> str:
    import sys
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    json_dir = os.path.join(base_dir, 'json')
    os.makedirs(json_dir, exist_ok=True)
    # 改为通过文本文件 agree.txt 作为同意标记
    return os.path.join(json_dir, 'agree.txt')


def has_agreed() -> bool:
    # 仅根据 json/agree.txt 的存在性判断是否已同意
    try:
        path = _agreement_path()
        return os.path.exists(path)
    except Exception:
        return False


class LegalTermsDialog(QDialog):
    def __init__(self, parent=None, countdown_seconds: int = 0):
        super().__init__(parent)
        self._lang = 'zh'  # 'zh' or 'en'
        self.setWindowTitle('用户协议')
        self.setModal(True)
        self.resize(700, 500)

        lay = QVBoxLayout(self)
        # 顶部标题行：左侧标题，右侧语言切换
        header = QHBoxLayout()
        self.lbl_title = QLabel('请阅读并同意以下用户协议')
        header.addWidget(self.lbl_title)
        header.addStretch(1)
        # 醒目的语言切换按钮
        self.btn_lang = QPushButton('Switch TO ENGLISH')
        self.btn_lang.setObjectName('LangToggle')
        self.btn_lang.setCursor(Qt.PointingHandCursor)
        self.btn_lang.setToolTip('Switch to English')
        header.addWidget(self.btn_lang)
        lay.addLayout(header)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(TERMS_TEXT_ZH)
        lay.addWidget(self.text, stretch=1)

        self.lbl_hint = QLabel('请仔细阅读用户协议。')
        lay.addWidget(self.lbl_hint)

        row = QHBoxLayout()
        self.btn_agree = QPushButton('同意')
        self.btn_decline = QPushButton('不同意并退出')
        self.btn_agree.setEnabled(True)
        row.addWidget(self.btn_decline)
        row.addStretch(1)
        row.addWidget(self.btn_agree)
        lay.addLayout(row)

        self._remain = int(countdown_seconds)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        if countdown_seconds > 0:
            self._timer.start()

        self.btn_decline.clicked.connect(self._on_decline)
        self.btn_agree.clicked.connect(self._on_agree)
        self.btn_lang.clicked.connect(self._toggle_language)

        # 简易深色样式与文本可读性
        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; }
            QLabel { color: #dfe3ea; }
            QTextEdit { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            #LangToggle { background: #1e60ff; color: #ffffff; border: none; font-weight: 700; padding: 6px 14px; border-radius: 8px; }
            #LangToggle:hover { background: #3a79ff; }
            #LangToggle:pressed { background: #1551e6; }
            """
        )

    def _tick(self):
        self._remain -= 1
        if self._remain <= 0:
            self._timer.stop()
            self.btn_agree.setEnabled(True)
            self.btn_agree.setText('同意' if self._lang == 'zh' else 'Agree')
            self.lbl_hint.setText('您现在可以点击"同意"继续使用。' if self._lang == 'zh' else 'You can now click "Agree" to continue.')
        else:
            if self._lang == 'zh':
                self.btn_agree.setText(f'同意 ({self._remain})')
                self.lbl_hint.setText('请仔细阅读用户协议。')
            else:
                self.btn_agree.setText(f'Agree ({self._remain})')
                self.lbl_hint.setText('Please read the user agreement carefully.')

    def _on_decline(self):
        # 拒绝：直接退出应用
        self.reject()
        try:
            sys.exit(0)
        except SystemExit:
            pass

    def _on_agree(self):
        # 同意：创建 json/agree.txt 文件标记已同意
        try:
            path = _agreement_path()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"agreed=true\n")
                f.write(f"timestamp={datetime.now().isoformat(timespec='seconds')}\n")
        except Exception:
            # 即使写入失败也继续接受，避免卡住用户
            pass
        self.accept()

    def _apply_language(self):
        if self._lang == 'zh':
            self.setWindowTitle('用户协议')
            self.lbl_title.setText('请阅读并同意以下用户协议')
            self.text.setPlainText(TERMS_TEXT_ZH)
            # 按当前倒计时状态更新按钮
            if self._remain > 0:
                self.btn_agree.setText(f'同意 ({self._remain})')
                self.lbl_hint.setText('请仔细阅读用户协议。')
            else:
                self.btn_agree.setText('同意')
                self.lbl_hint.setText('请仔细阅读用户协议。')
            self.btn_decline.setText('不同意并退出')
            self.btn_lang.setText('Switch TO ENGLISH')
            self.btn_lang.setToolTip('Switch to English')
        else:
            self.setWindowTitle('User Agreement')
            self.lbl_title.setText('Please read and agree to the following user agreement')
            self.text.setPlainText(TERMS_TEXT_EN)
            if self._remain > 0:
                self.btn_agree.setText(f'Agree ({self._remain})')
                self.lbl_hint.setText('Please read the user agreement carefully.')
            else:
                self.btn_agree.setText('Agree')
                self.lbl_hint.setText('Please read the user agreement carefully.')
            self.btn_decline.setText('Disagree and Exit')
            self.btn_lang.setText('中文')
            self.btn_lang.setToolTip('切换到中文')

    def _toggle_language(self):
        # 单击切换中英文
        self._lang = 'en' if self._lang == 'zh' else 'zh'
        self._apply_language()


def ensure_terms_agreed(parent=None) -> bool:
    """检查是否存在 json/agree.txt；不存在则弹出协议对话框。

    返回 True 代表可继续运行，False 代表应退出。"""
    # 已同意则直接通过（存在 agree.txt）
    if has_agreed():
        return True
    # 弹出协议对话框
    dlg = LegalTermsDialog(parent=parent, countdown_seconds=0)
    res = dlg.exec()
    return bool(res)