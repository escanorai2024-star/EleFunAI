"""
Agemini: 从 X 目录读取 Gemini/Banana 配置并进行连接测试。

- 优先读取 `X/gemini.json` 的 `api_key`、`base_url`、`model`
- 回退读取 `X/banana_settings.json`（若含相同字段）
- 再回退读取 `X/api.txt` 仅作为 API Key

提供:
- get_config(): 返回当前配置 dict
- test_connection(): 测试是否能访问指定模型信息，返回 (ok, message)

说明: 直接使用 requests 调用 Google Generative Language API，避免导入 X 目录中的模块路径问题。
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


DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash-image"


def _get_app_root() -> str:
    """获取软件所在根目录（兼容 EXE 打包后的情况）"""
    if getattr(sys, 'frozen', False):
        # 打包成 EXE 后，使用可执行文件所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，使用当前脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))

def _x_path(*parts: str) -> str:
    return os.path.join(_get_app_root(), "X", *parts)

def _json_path(*parts: str) -> str:
    return os.path.join(_get_app_root(), "json", *parts)


def get_config() -> Dict[str, Any]:
    """读取 Gemini 配置，按优先级合并返回。"""
    cfg: Dict[str, Any] = {
        "api_key": "",
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
    }

    # 1) 优先读取 json/gemini.json（新的保存位置）
    try:
        gj_new = _json_path("gemini.json")
        if os.path.exists(gj_new):
            with open(gj_new, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            for k in ("api_key", "base_url", "model"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    cfg[k] = v.strip()
            if "size" in data:
                cfg["size"] = data.get("size")
            if "resolution" in data:
                cfg["resolution"] = data.get("resolution")
            if "provider" in data:
                cfg["provider"] = data.get("provider")
    except Exception:
        pass

    # 2) 读取 X/gemini.json（兼容旧位置）
    try:
        gj = _x_path("gemini.json")
        if os.path.exists(gj):
            with open(gj, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            for k in ("api_key", "base_url", "model"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    cfg[k] = v.strip()
            if "size" in data:
                cfg["size"] = data.get("size")
            if "resolution" in data:
                cfg["resolution"] = data.get("resolution")
            # 兼容旧字段
            if "draw_count" in data:
                cfg["draw_count"] = data.get("draw_count")
    except Exception:
        pass

    # 3) 读取 X/banana_settings.json（旧版可能包含字段）
    try:
        bs = _x_path("banana_settings.json")
        if os.path.exists(bs):
            with open(bs, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            for k in ("api_key", "base_url", "model"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    cfg[k] = v.strip()
            # provider 不影响连接，但保留供外部参考
            if "provider" in data:
                cfg["provider"] = data.get("provider")
    except Exception:
        pass

    # 4) 读取 X/api.txt 作为 api_key 回退
    try:
        at = _x_path("api.txt")
        if os.path.exists(at) and not cfg.get("api_key"):
            with open(at, "r", encoding="utf-8") as f:
                k = (f.read() or "").strip()
            if k:
                cfg["api_key"] = k
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

    # 根据 base_url 决定认证方式
    use_bearer_auth = 'yunwu.ai' in base_url.lower()
    
    # 访问模型元数据接口
    url = f"{base_url}/models/{model}"
    
    if use_bearer_auth:
        # 使用 Bearer token 认证
        req = urllib.request.Request(url, method="GET")
        req.add_header('Authorization', f'Bearer {api_key}')
    else:
        # 使用 URL 参数认证
        full_url = f"{url}?key={api_key}"
        req = urllib.request.Request(full_url, method="GET")
    
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
    print("[Agemini]", "Success:" if ok else "Failed:", msg)


class ConfigDialog(QDialog):
    """
    Gemini Banana 配置窗口（参考 web 目录的交互风格，简洁直观）。
    - 字段：API Key、Base URL、模型选择（下拉）、抽卡次数（1/2/3）
    - 功能：测试连接、保存到 X/gemini.json
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gemini 配置")
        # 调大配置窗口尺寸
        self.setFixedSize(540, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("Gemini Banana 配置")
        title.setAlignment(Qt.AlignLeft)
        layout.addWidget(title)

        # API Key
        layout.addWidget(QLabel("API 密钥:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("请输入 Google Gemini API 密钥")
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

        # 模型选择
        layout.addWidget(QLabel("模型:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "gemini-2.5-flash-image",
            "gemini-2.0-flash-exp",
            "gemini-2.5-flash",
            "gemini-3-pro-image-preview",
        ])
        layout.addWidget(self.model_combo)

        # 尺寸设置（参考 web/image.html 的输出比例）
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
        # 模型
        model = cfg.get("model", DEFAULT_MODEL)
        idx = self.model_combo.findText(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        # 抽卡次数字段（可选）
        # 输出比例
        size_ratio = str(cfg.get("size", "1:1"))
        idx_sz = self.size_combo.findText(size_ratio)
        if idx_sz >= 0:
            self.size_combo.setCurrentIndex(idx_sz)

    def _test(self):
        # 暂存到内存后测试（不写文件）
        # 用用户填写的值覆盖当前配置进行测试
        def temp_test() -> Tuple[bool, str]:
            api_key = self.api_key_edit.text().strip()
            base_url = (self.base_url_edit.text().strip() or DEFAULT_BASE_URL)
            base_url = base_url.strip(" ,`").rstrip('/')
            model = self.model_combo.currentText()
            if not api_key:
                return False, "缺少 API Key"
            
            # 根据 base_url 决定认证方式
            use_bearer_auth = 'yunwu.ai' in base_url.lower()
            url = f"{base_url}/models/{model}"
            
            try:
                if use_bearer_auth:
                    # 使用 Bearer token 认证
                    req = urllib.request.Request(url, method="GET")
                    req.add_header('Authorization', f'Bearer {api_key}')
                else:
                    # 使用 URL 参数认证
                    req = urllib.request.Request(f"{url}?key={api_key}", method="GET")
                
                with urllib.request.urlopen(req, timeout=8) as resp:
                    code = getattr(resp, "status", 200)
                    if 200 <= code < 300:
                        return True, "连接成功"
                    return False, f"HTTP {code}"
            except urllib.error.HTTPError as e:
                return False, f"HTTP {e.code}"
            except urllib.error.URLError as e:
                return False, f"URL错误: {str(e)[:120]}"

        ok, msg = temp_test()
        if ok:
            QMessageBox.information(self, "测试连接", msg)
        else:
            QMessageBox.critical(self, "测试连接", msg)

    def _save(self):
        # 规范化并保存配置（去除意外的逗号/反引号、末尾斜杠）
        api_key = self.api_key_edit.text().strip()
        base_url = (self.base_url_edit.text().strip() or DEFAULT_BASE_URL)
        base_url = base_url.strip(" ,`").rstrip('/')
        model = self.model_combo.currentText()
        cfg = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            # 新增：输出比例
            "size": self.size_combo.currentText(),
        }
        # 写入 json/gemini.json（按用户要求保存到 JSON 目录）
        try:
            path = _json_path("gemini.json")
            # 确保 json 目录存在
            json_dir = os.path.dirname(path)
            os.makedirs(json_dir, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "保存", f"配置已保存至：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e)[:200])