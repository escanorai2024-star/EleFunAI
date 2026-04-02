from PySide6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtWidgets import QApplication
import sys
import subprocess
import os

def detect_gpu_info():
    try:
        out = subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'], timeout=2)
        text = out.decode('utf-8', errors='ignore').strip()
        if text:
            parts = text.split(',')
            name = parts[0].strip()
            driver = parts[1].strip() if len(parts) > 1 else ''
            return True, name, driver
    except Exception:
        pass
    return False, '', ''

def recommend_pytorch_index(gpu_name: str) -> str:
    n = (gpu_name or '').lower()
    if any(k in n for k in ['4090','4080','4070','4060','rtx 40','ada']):
        return 'https://download.pytorch.org/whl/cu121'
    if any(k in n for k in ['3090','3080','3070','3060','a100','a30','a40','a10','rtx 30','ampere']):
        return 'https://download.pytorch.org/whl/cu118'
    if any(k in n for k in ['2080','2070','2060','t4','quadro rtx','rtx 20','turing']):
        return 'https://download.pytorch.org/whl/cu118'
    return 'https://download.pytorch.org/whl/cu121'

def install_pytorch(parent):
    has_gpu, name, driver = detect_gpu_info()
    if has_gpu:
        idx = recommend_pytorch_index(name)
        msg = f"检测到显卡: {name} {('驱动 ' + driver) if driver else ''}\n建议安装: {idx}\n\n示例命令:\npython -m pip install torch torchvision --index-url {idx}"
    else:
        msg = "未检测到GPU，建议安装CPU版本:\n\n示例命令:\npython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
    QMessageBox.information(parent, 'PyTorch 安装指引', msg)

class _AutoWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(bool, str)
    def __init__(self, base_dir: str, index_urls: list[str]):
        super().__init__()
        self.base_dir = base_dir
        self.index_urls = index_urls
    def work(self):
        try:
            target = os.path.join(self.base_dir, 'PyTorch')
            os.makedirs(target, exist_ok=True)
            steps = 2 + len(self.index_urls)
            s = 0
            self.progress.emit(int(s/steps*100), 'pip install --upgrade pip')
            r = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], capture_output=True, text=True)
            s += 1
            if r.returncode != 0:
                self.finished.emit(False, r.stderr or r.stdout)
                return
            last_err = ''
            for url in self.index_urls:
                pct = int(s/steps*100)
                self.progress.emit(pct, f'pip install torch torchvision --index-url {url}')
                cmd = [sys.executable, '-m', 'pip', 'install', '--index-url', url, '--target', target, 'torch', 'torchvision']
                r2 = subprocess.run(cmd, capture_output=True, text=True)
                s += 1
                if r2.returncode == 0:
                    self.progress.emit(100, 'done')
                    self.finished.emit(True, target)
                    return
                last_err = r2.stderr or r2.stdout
            self.finished.emit(False, last_err or '安装失败')
        except Exception as e:
            self.finished.emit(False, str(e))

def install_pytorch_auto(parent):
    has, name, driver = detect_gpu_info()
    if has:
        rec = recommend_pytorch_index(name)
        alts = ['https://download.pytorch.org/whl/cu118'] if rec.endswith('cu121') else ['https://download.pytorch.org/whl/cu121']
        idxs = [rec] + alts + ['https://download.pytorch.org/whl/cpu']
    else:
        idxs = ['https://download.pytorch.org/whl/cpu']
    base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    win = QDialog(parent)
    win.setWindowTitle('Download PyTorch')
    lay = QVBoxLayout(win)
    lbl = QLabel(f"步骤 1 > 判断显卡: {'已检测到GPU: ' + name + (' | 驱动 ' + driver if driver else '') if has else '未检测到GPU'}\n步骤 2 > 需要的 PyTorch 版本: {'CUDA ' + idxs[0].split('/')[-1] if has else 'CPU'}\n步骤 3 > 开始下载…")
    bar = QProgressBar()
    bar.setRange(0, 100)
    lay.addWidget(lbl)
    lay.addWidget(bar)
    win.resize(640, 220)
    win.show()
    thread = QThread(parent)
    worker = _AutoWorker(base, idxs)
    
    # Register to global registry to prevent GC
    app = QApplication.instance()
    if app:
        if not hasattr(app, '_active_install_workers'):
            app._active_install_workers = []
        app._active_install_workers.append(worker)
        
    worker.moveToThread(thread)
    def _on_prog(v, txt):
        try:
            bar.setValue(v)
            lbl.setText(lbl.text().split('\n步骤 3')[0] + f"\n步骤 3 > 开始下载\n{txt}  ({v}%)")
            QApplication.processEvents()
            print(f'[DEBUG] [PyTorch] {txt} ({v}%)', flush=True)
        except Exception:
            pass
    def _done(ok, msg):
        try:
            win.close()
        except Exception:
            pass
        if ok:
            QMessageBox.information(parent, '安装完成', f'已安装到：{msg}\n重启应用后将自动加载该环境。')
            print(f'[DEBUG] [PyTorch] 安装完成 -> {msg}', flush=True)
        else:
            QMessageBox.warning(parent, '安装失败', msg)
            print(f'[DEBUG] [PyTorch] 安装失败: {msg}', flush=True)
        try:
            thread.quit(); thread.wait()
        except Exception:
            pass
        
        # Cleanup worker
        app = QApplication.instance()
        if app and hasattr(app, '_active_install_workers'):
            if worker in app._active_install_workers:
                app._active_install_workers.remove(worker)

    worker.progress.connect(_on_prog)
    worker.finished.connect(_done)
    thread.started.connect(worker.work)
    thread.start()

def open_pytorch_download(parent):
    try:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        url = 'https://pytorch.org/get-started/locally/'
        QMessageBox.information(parent, '打开下载地址', '已为你打开 PyTorch 官方安装指南网页，按页面提示选择命令进行安装。')
        QDesktopServices.openUrl(QUrl(url))
    except Exception:
        try:
            import webbrowser
            webbrowser.open('https://pytorch.org/get-started/locally/')
        except Exception:
            pass