"""
Agemini30: Gemini 3.0 配置模块（专门用于 gemini-3-pro-image-preview）

- 读取 json/gemini30.json 配置文件
- 默认使用云雾 API (https://yunwu.ai/v1beta)
- 使用 Bearer Token 认证方式

提供:
- get_config(): 返回当前配置 dict
- test_connection(): 测试连接，返回 (ok, message)
- ConfigDialog: 配置对话框
"""

from __future__ import annotations
import os
import sys
import json
from typing import Tuple, Dict, Any

import urllib.request
import urllib.error
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt


DEFAULT_BASE_URL = "https://yunwu.ai/v1beta"
DEFAULT_MODEL = "gemini-3-pro-image-preview"


def _get_app_root() -> str:
    """获取软件所在根目录（兼容 EXE 打包后的情况）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def _json_path(*parts: str) -> str:
    return os.path.join(_get_app_root(), "json", *parts)


def get_config() -> Dict[str, Any]:
    """读取 Gemini 3.0 配置"""
    cfg: Dict[str, Any] = {
        "api_key": "",
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "size": "1:1",
        "resolution": "1K",     # 分辨率：1K/2K/4K
        "quality": "80",        # 清晰度：0-100 的整数（字符串形式存储）
    }

    # 读取 json/gemini30.json
    try:
        config_path = _json_path("gemini30.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            for k in ("api_key", "base_url", "model", "size", "resolution", "quality"):
                v = data.get(k)
                if v is not None:
                    if isinstance(v, str) and v.strip():
                        cfg[k] = v.strip()
                    elif isinstance(v, int):
                        cfg[k] = str(v)
    except Exception:
        pass

    return cfg


def test_connection(timeout: int = 8) -> Tuple[bool, str]:
    """
    测试能否访问指定模型信息。
    - 成功: 返回 (True, "OK <model>")
    - 失败: 返回 (False, 错误消息)
    """
    cfg = get_config()
    api_key = cfg.get("api_key", "").strip()
    base_url = (cfg.get("base_url") or DEFAULT_BASE_URL).strip()
    model = (cfg.get("model") or DEFAULT_MODEL).strip()

    if not api_key:
        return False, "缺少 API Key"

    # 云雾 API 使用 Bearer token 认证
    url = f"{base_url}/models/{model}"
    req = urllib.request.Request(url, method="GET")
    req.add_header('Authorization', f'Bearer {api_key}')
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            text = resp.read().decode("utf-8", errors="ignore")
            if 200 <= code < 300:
                return True, f"OK {model}"
            try:
                data = json.loads(text)
                msg = data.get("error", {}).get("message") or text[:200]
            except Exception:
                msg = text[:200]
            return False, f"HTTP {code}: {msg}"
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode("utf-8", errors="ignore")
            data = json.loads(text)
            msg = data.get("error", {}).get("message") or text[:200]
        except Exception:
            msg = str(e)[:200]
        return False, f"HTTP {e.code}: {msg}"
    except urllib.error.URLError as e:
        return False, f"URL错误: {str(e)[:200]}"


if __name__ == "__main__":
    ok, msg = test_connection()
    print("[Agemini30]", "Success:" if ok else "Failed:", msg)


class ConfigDialog(QDialog):
    """
    Gemini 3.0 配置窗口
    - 专门用于 gemini-3-pro-image-preview 模型
    - 使用云雾 API
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini 3.0 配置")
        self.setFixedSize(540, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("Gemini 3.0 Pro Image Preview")
        title.setAlignment(Qt.AlignLeft)
        layout.addWidget(title)

        # API Key
        layout.addWidget(QLabel("API 密钥 (Token):"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("请输入云雾 API Token (sk-...)")
        layout.addWidget(self.api_key_edit)

        # Base URL
        layout.addWidget(QLabel("Base URL:"))
        row_url = QHBoxLayout()
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText(DEFAULT_BASE_URL)
        btn_reset_url = QPushButton("恢复默认")
        btn_reset_url.clicked.connect(lambda: self.base_url_edit.setText(DEFAULT_BASE_URL))
        row_url.addWidget(self.base_url_edit)
        row_url.addWidget(btn_reset_url)
        layout.addLayout(row_url)

        # 模型显示（固定为 gemini-3-pro-image-preview）
        layout.addWidget(QLabel("模型:"))
        model_label = QLabel(DEFAULT_MODEL)
        model_label.setStyleSheet("color: #34d399; padding: 6px;")
        layout.addWidget(model_label)

        # 尺寸设置（输出比例）
        layout.addWidget(QLabel("输出比例:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems([
            "1:1",      # 正方形
            "16:9",     # 横向
            "9:16",     # 纵向
            "4:3",      # 横向
            "3:4",      # 纵向
        ])
        layout.addWidget(self.size_combo)

        # 分辨率选项
        layout.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "1K (1024x1024)",
            "2K (2048x2048)",
            "4K (4096x4096)",
        ])
        layout.addWidget(self.resolution_combo)

        # 清晰度选项（0-100 的质量值）
        layout.addWidget(QLabel("清晰度 (JPEG 质量):"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems([
            "60 (标准)",
            "80 (高清)",
            "95 (超高清)",
            "100 (无损)",
        ])
        layout.addWidget(self.quality_combo)

        # 操作区
        ops = QHBoxLayout()
        btn_test = QPushButton("测试连接")
        btn_save = QPushButton("保存")
        btn_close = QPushButton("关闭")
        btn_test.clicked.connect(self._test)
        btn_save.clicked.connect(self._save)
        btn_close.clicked.connect(self.close)
        ops.addWidget(btn_test)
        ops.addStretch(1)
        ops.addWidget(btn_save)
        ops.addWidget(btn_close)
        layout.addLayout(ops)

        # 样式（与设置窗口一致的深色风格）
        self.setStyleSheet(
            """
            QDialog { background: #1a1b1d; color: #dfe3ea; }
            QLabel { color: #dfe3ea; }
            QLineEdit, QComboBox { background: #0c0d0e; color: #ffffff; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px; }
            QPushButton { background: #0c0d0e; color: #cfd3da; border: 1px solid #2a2d31; border-radius: 6px; padding: 6px 12px; }
            QPushButton:hover { background: #181c22; }
            """
        )

        # 载入配置
        self._load()

    def _load(self):
        cfg = get_config()
        self.api_key_edit.setText(cfg.get("api_key", ""))
        self.base_url_edit.setText(cfg.get("base_url", DEFAULT_BASE_URL))
        
        # 输出比例
        size_ratio = str(cfg.get("size", "1:1"))
        idx_sz = self.size_combo.findText(size_ratio)
        if idx_sz >= 0:
            self.size_combo.setCurrentIndex(idx_sz)
        
        # 分辨率
        resolution = str(cfg.get("resolution", "1K"))
        for i in range(self.resolution_combo.count()):
            if resolution in self.resolution_combo.itemText(i):
                self.resolution_combo.setCurrentIndex(i)
                break
        
        # 清晰度
        quality = str(cfg.get("quality", "80"))
        for i in range(self.quality_combo.count()):
            if quality in self.quality_combo.itemText(i):
                self.quality_combo.setCurrentIndex(i)
                break

    def _test(self):
        # 暂存到内存后测试（不写文件）
        def temp_test() -> Tuple[bool, str]:
            api_key = self.api_key_edit.text().strip()
            base_url = (self.base_url_edit.text().strip() or DEFAULT_BASE_URL)
            base_url = base_url.strip(" ,`").rstrip('/')
            model = DEFAULT_MODEL
            
            if not api_key:
                return False, "缺少 API Key"
            
            url = f"{base_url}/models/{model}"
            
            try:
                req = urllib.request.Request(url, method="GET")
                req.add_header('Authorization', f'Bearer {api_key}')
                
                with urllib.request.urlopen(req, timeout=8) as resp:
                    code = getattr(resp, "status", 200)
                    if 200 <= code < 300:
                        return True, "连接成功"
                    return False, f"HTTP {code}"
            except urllib.error.HTTPError as e:
                try:
                    text = e.read().decode("utf-8", errors="ignore")
                    data = json.loads(text)
                    msg = data.get("error", {}).get("message", str(e))
                except Exception:
                    msg = str(e)
                return False, f"HTTP {e.code}: {msg[:120]}"
            except urllib.error.URLError as e:
                return False, f"URL错误: {str(e)[:120]}"

        ok, msg = temp_test()
        if ok:
            QMessageBox.information(self, "测试连接", msg)
        else:
            QMessageBox.critical(self, "测试连接", msg)

    def _save(self):
        # 规范化并保存配置
        api_key = self.api_key_edit.text().strip()
        base_url = (self.base_url_edit.text().strip() or DEFAULT_BASE_URL)
        base_url = base_url.strip(" ,`").rstrip('/')
        
        # 提取分辨率和清晰度的实际值
        resolution_text = self.resolution_combo.currentText()
        resolution = "1K"
        if "2K" in resolution_text:
            resolution = "2K"
        elif "4K" in resolution_text:
            resolution = "4K"
        
        quality_text = self.quality_combo.currentText()
        quality = "80"
        if "60" in quality_text:
            quality = "60"
        elif "80" in quality_text:
            quality = "80"
        elif "95" in quality_text:
            quality = "95"
        elif "100" in quality_text:
            quality = "100"
        
        cfg = {
            "api_key": api_key,
            "base_url": base_url,
            "model": DEFAULT_MODEL,
            "size": self.size_combo.currentText(),
            "resolution": resolution,
            "quality": quality,
        }
        
        # 写入 json/gemini30.json
        try:
            path = _json_path("gemini30.json")
            json_dir = os.path.dirname(path)
            os.makedirs(json_dir, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "保存", f"配置已保存至：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e)[:200])
