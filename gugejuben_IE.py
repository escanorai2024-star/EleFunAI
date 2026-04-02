
import csv
import sys
import os
from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, QLabel, QTextBrowser,
    QPushButton, QFileDialog, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt

class TableViewerWindow(QMainWindow):
    """内置浏览器窗口 - 用于显示剧本表格预览 (使用QTextBrowser)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("剧本预览 - 内置浏览器")
        self.resize(1000, 700)
        
        # 主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 顶部工具栏
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 5)
        
        # 弹簧将按钮推到右侧
        spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_layout.addItem(spacer)

        # 下载按钮
        self.btn_download = QPushButton("下载 CSV")
        self.btn_download.setCursor(Qt.PointingHandCursor)
        self.btn_download.clicked.connect(self.export_csv)
        self.btn_download.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-family: "Microsoft YaHei";
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1557b0;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """)
        top_layout.addWidget(self.btn_download)
        
        layout.addWidget(top_bar)
        
        # 使用 QTextBrowser 替代 IE 控件，避免安全限制和崩溃问题
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        layout.addWidget(self.browser)
        
        # 数据存储
        self.current_headers = []
        self.current_rows = []

    def set_table_data(self, headers, rows):
        """接收表格数据并转换为HTML显示"""
        self.current_headers = headers
        self.current_rows = rows
        html = self._generate_html(headers, rows)
        self.browser.setHtml(html)

    def export_csv(self):
        """导出当前表格为CSV文件"""
        if not self.current_headers and not self.current_rows:
            QMessageBox.warning(self, "提示", "没有可导出的数据")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存 CSV 文件", "剧本内容.csv", "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            try:
                # 使用 utf-8-sig 以便 Excel 正确识别中文
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    if self.current_headers:
                        writer.writerow(self.current_headers)
                    writer.writerows(self.current_rows)
                QMessageBox.information(self, "成功", f"文件已保存至:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")


    def _generate_html(self, headers, rows):
        """生成HTML表格 (适配QTextBrowser的CSS子集)"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body { 
                font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; 
                padding: 10px; 
                background-color: #f8f9fa;
                color: #202124;
            }
            h2 { color: #202124; margin-bottom: 20px; }
            table { 
                border-collapse: collapse; 
                width: 100%; 
                background-color: white;
                border: 1px solid #e0e0e0;
            }
            th { 
                background-color: #f1f3f4; 
                font-weight: bold;
                padding: 8px;
                border: 1px solid #e0e0e0;
                color: #202124;
                text-align: left;
            }
            td { 
                border: 1px solid #e0e0e0; 
                padding: 8px; 
                color: #3c4043;
            }
            tr { background-color: #ffffff; }
        </style>
        </head>
        <body>
            <h2>剧本内容预览</h2>
            <table cellspacing="0" cellpadding="5">
                <thead>
                    <tr>
        """
        
        # 添加表头
        for header in headers:
            html += f"<th>{header}</th>"
        
        html += """
                    </tr>
                </thead>
                <tbody>
        """
        
        # 添加数据行
        for i, row in enumerate(rows):
            # 简单的交替行颜色模拟 (QTextBrowser CSS支持有限)
            bg_color = "#ffffff" if i % 2 == 0 else "#f8f9fa"
            html += f'<tr style="background-color: {bg_color};">'
            
            for cell in row:
                cell_text = str(cell) if cell is not None else ""
                # 简单的HTML转义
                cell_text = cell_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html += f"<td>{cell_text}</td>"
            html += "</tr>"
            
        html += """
                </tbody>
            </table>
        </body>
        </html>
        """
        return html
