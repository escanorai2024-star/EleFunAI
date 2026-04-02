from PySide6.QtCore import QSettings

class TestModeManager:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def __init__(self):
        # 使用 QSettings 存储设置，保持跨会话持久化
        # Organization: GhostOS, Application: DirectorTestMode
        self.settings = QSettings("GhostOS", "DirectorTestMode")
        
    def is_enabled(self):
        # 默认值为 False (不开启)
        return self.settings.value("test_mode_enabled", False, type=bool)
        
    def set_enabled(self, enabled):
        self.settings.setValue("test_mode_enabled", enabled)

# 辅助函数，方便外部调用
def is_test_mode_enabled():
    return TestModeManager.get_instance().is_enabled()

def set_test_mode_enabled(enabled):
    TestModeManager.get_instance().set_enabled(enabled)
