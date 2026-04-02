from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lang_code = 'zh'
        self._i18n = self._get_i18n(self._lang_code)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(10)

        self.title = QLabel(self._i18n['title'])
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title.setObjectName('AboutTitle')

        self.desc = QLabel(self._i18n['desc'])
        self.desc.setWordWrap(True)

        lay.addWidget(self.title)
        lay.addWidget(self.desc)

        # 链接（超链接样式：蓝色、下划线）
        self.link_bilibili = QLabel()
        self.link_github = QLabel()
        self.link_discord = QLabel()
        self.link_support = QLabel()
        self.link_youtube = QLabel()
        for lab in [self.link_bilibili, self.link_github, self.link_discord, self.link_support, self.link_youtube]:
            lab.setOpenExternalLinks(True)
            lab.setTextInteractionFlags(Qt.TextBrowserInteraction)
            lay.addWidget(lab)

        # 初始化链接文本
        self._refresh_links()
        lay.addStretch(1)

        # 简易样式与现有主窗口风格保持一致
        self.setStyleSheet(
            """
            QLabel#AboutTitle { color:#202124; font-size:24px; font-weight:600; font-family: 'Segoe UI', sans-serif; }
            QLabel { color:#5f6368; font-size: 14px; font-family: 'Segoe UI', sans-serif; }
            """
        )

    def set_language(self, code: str):
        if code not in ('zh', 'en'):
            code = 'zh'
        self._lang_code = code
        self._i18n = self._get_i18n(code)
        self.title.setText(self._i18n['title'])
        self.desc.setText(self._i18n['desc'])
        # 更新超链接文本
        self._refresh_links()

    def _get_i18n(self, code: str) -> dict:
        zh = {
            'title': '关于我们',
            'desc': '鬼叔AI 是一个简洁的创意工作平台，支持图像与视频生成、画板编辑与在应用内发送。',
            'bilibili': 'bilibili',
            'github': 'GitHub',
            'discord': 'Discord',
            'support_us': '赞助我们',
            'youtube': 'YouTube',
        }
        en = {
            'title': 'About Us',
            'desc': 'Ghost Uncle AI is a streamlined creative workspace for image/video generation, canvas editing, and in-app sending.',
            'bilibili': 'Bilibili',
            'github': 'GitHub',
            'discord': 'Discord',
            'support_us': 'Support Us',
            'youtube': 'YouTube',
        }
        return zh if code == 'zh' else en

    def _refresh_links(self):
        blue = '#1e66ff'
        # 仅中文界面显示 bilibili
        if self._lang_code == 'zh':
            self.link_bilibili.setVisible(True)
            self.link_bilibili.setText(
                f'<a href="https://space.bilibili.com/517480334" style="color:{blue}; text-decoration: underline;">{self._i18n["bilibili"]}</a>'
            )
        else:
            self.link_bilibili.setVisible(False)
        self.link_github.setText(
            f'<a href="https://github.com/guijiaosir/AItools" style="color:{blue}; text-decoration: underline;">{self._i18n["github"]}</a>'
        )
        self.link_discord.setText(
            f'<a href="https://www.discord.gg/32KQ29FrSB" style="color:{blue}; text-decoration: underline;">{self._i18n["discord"]}</a>'
        )
        self.link_support.setText(
            f'<a href="https://afdian.com/p/be429062a61e11f09da25254001e7c00" style="color:{blue}; text-decoration: underline;">{self._i18n["support_us"]}</a>'
        )
        # 仅在英文界面显示 YouTube 链接
        if self._lang_code == 'en':
            self.link_youtube.setVisible(True)
            self.link_youtube.setText(
                f'<a href="https://www.youtube.com/@KisameAI" style="color:{blue}; text-decoration: underline;">{self._i18n["youtube"]}</a>'
            )
        else:
            self.link_youtube.setVisible(False)