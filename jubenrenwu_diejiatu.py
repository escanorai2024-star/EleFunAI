import os
import time
import base64
import requests
from PySide6.QtCore import QThread, Signal, QSettings

try:
    import Agemini
except:
    Agemini = None
try:
    import Agemini30
except:
    Agemini30 = None

class CharacterOverlayGenerator(QThread):
    progress = Signal(str)
    image_generated = Signal(str, str)
    finished_all = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, tasks, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.stopped = False
        self.config = {}
        self.provider = "BANANA"

        # Register to global registry to prevent GC
        app = QApplication.instance()
        if app:
            if not hasattr(app, '_active_overlay_workers'):
                app._active_overlay_workers = []
            app._active_overlay_workers.append(self)
        self.finished.connect(self._cleanup_worker)

    def _cleanup_worker(self):
        app = QApplication.instance()
        if app and hasattr(app, '_active_overlay_workers'):
            if self in app._active_overlay_workers:
                app._active_overlay_workers.remove(self)
        self.deleteLater()

    def run(self):
        output_dir = os.path.join(os.getcwd(), "frame", "character_overlay")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        settings = QSettings("GhostOS", "App")
        provider_raw = settings.value("api/image_provider", "BANANA")
        p = str(provider_raw).lower()
        provider = "BANANA"
        if "midjourney" in p:
            provider = "Midjourney"
        elif "banana2" in p or "gemini 3" in p or "gemini3" in p:
            provider = "BANANA2"
        elif "banana" in p or "gemini" in p:
            provider = "BANANA"

        self.config = {}
        if provider == "BANANA":
            if Agemini:
                self.config = Agemini.get_config()
            else:
                self.error_occurred.emit("Agemini module not found")
                return
        elif provider == "BANANA2":
            if Agemini30:
                self.config = Agemini30.get_config()
            else:
                self.error_occurred.emit("Agemini30 module not found")
                return
        else:
            self.error_occurred.emit("人物叠加仅支持 Gemini/Banana")
            return

        self.provider = provider
        try:
            masked_key = ""
            k = self.config.get("api_key", "")
            if isinstance(k, str) and len(k) >= 8:
                masked_key = k[:4] + "..." + k[-4:]
            print("[人物叠加] DEBUG 配置:", {
                "provider": provider,
                "model": self.config.get("model"),
                "base_url": self.config.get("base_url"),
                "resolution": self.config.get("resolution"),
                "size": self.config.get("size"),
                "api_key": masked_key
            })
        except Exception:
            pass

        count = 0
        for task in self.tasks:
            if self.stopped:
                break
            row_id = task.get("id")
            prompt = task.get("prompt")
            ref_image = task.get("ref_image")
            if not prompt or not ref_image:
                self.error_occurred.emit(f"{row_id}: 缺少提示词或参考图")
                continue
            self.progress.emit(f"正在生成: {row_id}...")
            try:
                with open(ref_image, "rb") as f:
                    b = base64.b64encode(f.read()).decode("utf-8")
                try:
                    print("[人物叠加] DEBUG 请求载荷:", {
                        "id": row_id,
                        "prompt_preview": (prompt or "")[:200],
                        "ref_image": ref_image,
                        "b64_size": len(b)
                    })
                except Exception:
                    pass
                result = self.generate_gemini(prompt, b)
                if result:
                    filename = f"char_overlay_{row_id}_{int(time.time())}.png"
                    path = os.path.join(output_dir, filename)
                    with open(path, "wb") as w:
                        w.write(result)
                    try:
                        print("[人物叠加] DEBUG 已保存:", {
                            "id": row_id,
                            "filepath": path,
                            "filesize": os.path.getsize(path)
                        })
                    except Exception:
                        pass
                    self.image_generated.emit(str(row_id), path)
                    count += 1
                else:
                    self.error_occurred.emit(f"{row_id} 生成失败: 无数据")
            except Exception as e:
                self.error_occurred.emit(f"{row_id} 生成失败: {str(e)}")

        self.finished_all.emit(count)

    def generate_gemini(self, prompt, b64_image):
        api_key = self.config.get("api_key")
        base_url = self.config.get("base_url")
        model = self.config.get("model", "gemini-2.0-flash-exp")
        if not api_key:
            raise Exception("Gemini API Key 未配置")
        url = f"{base_url}/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "image/png", "data": b64_image}}
                ]
            }]
        }
        if "gemini-3" in model or "pro-image" in model or "flash-image" in model:
            payload["generationConfig"] = {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"imageSize": self.config.get("resolution", "1K"), "numberOfImages": 1, "aspectRatio": self.config.get("size", "1:1")}
            }
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp.raise_for_status()
        try:
            masked = (api_key[:4] + "..." + api_key[-4:]) if isinstance(api_key, str) and len(api_key) >= 8 else "masked"
            print("[人物叠加] DEBUG 请求信息:", {
                "url": url,
                "headers": {"Authorization": f"Bearer {masked}", "Content-Type": "application/json"},
                "payload_keys": list(payload.keys())
            })
        except Exception:
            pass
        if "image/" in resp.headers.get("Content-Type", ""):
            try:
                print("[人物叠加] DEBUG 原始图片响应:", {
                    "status": resp.status_code,
                    "content_type": resp.headers.get("Content-Type"),
                    "length": len(resp.content)
                })
            except Exception:
                pass
            return resp.content
        data = resp.json()
        try:
            print("[人物叠加] DEBUG 响应JSON:", {
                "status": resp.status_code,
                "keys": list(data.keys()) if isinstance(data, dict) else [],
                "preview": str(data)[:400]
            })
        except Exception:
            pass
        if "candidates" in data and data["candidates"]:
            for c in data["candidates"]:
                if "content" in c and "parts" in c["content"]:
                    for part in c["content"]["parts"]:
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"]["data"])
        raise Exception("未找到图片数据")

    def stop(self):
        self.stopped = True
