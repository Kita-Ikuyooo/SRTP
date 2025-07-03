import sys
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QProgressBar, QTextBrowser, QMessageBox,
    QDoubleSpinBox, QGroupBox, QFrame
)
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont


# ==================================================================
# 模拟给药泵硬件 (在后台线程中运行) - 保持不变
# ==================================================================
class DrugPumpSimulator(QThread):
    # 定义信号
    progress_updated = pyqtSignal(float, float, float)  # 信号：发射 (当前已注射量, 总目标量, 剩余药量)
    infusion_finished = pyqtSignal()  # 信号：注射完成
    infusion_stopped = pyqtSignal(float)  # 信号：注射停止 (参数：已注射量)
    infusion_paused = pyqtSignal(float)  # 信号：注射暂停 (参数：已注射量)
    status_changed = pyqtSignal(str)  # 信号：状态改变 (参数：状态字符串)
    log_message = pyqtSignal(str)  # 信号：记录日志 (参数：日志消息)
    remaining_low_warning = pyqtSignal()  # 信号：剩余药量不足警告

    def __init__(self):
        super().__init__()
        self.target_volume = 0.0  # 目标给药量 (uL)
        self.current_volume = 0.0  # 当前已注射量 (uL)
        self.infusion_speed = 0.0  # 注射速度 (uL/s)
        self.is_running = False  # 是否正在注射
        self.should_stop = False  # 是否收到停止指令
        self.should_pause = False  # 是否收到暂停指令
        self.status = "就绪"  # 当前状态
        self.remaining_medicine = 5000  # 设备剩余药剂量 (uL), 初始5.0mL = 5000uL
        self.paused_volume = 0.0  # 暂停时的已注射量
        self.low_warning_emitted = False  # 标记是否已经发出低药量警告
        self.volume = self.remaining_medicine  # 设备容量

    def set_speed(self, speed):
        """设置注射速度"""
        self.infusion_speed = speed

    def start_infusion(self, volume, speed, is_resume=False):
        """启动模拟注射过程"""
        if self.is_running:
            self.log_message.emit("警告：注射已在进行中！")
            return False

        # 检查剩余药量
        if self.remaining_medicine <= 0:
            self.log_message.emit("错误：设备中药量已耗尽！")
            QMessageBox.critical(None, "药量不足", "设备中药量已耗尽，无法开始注射！")
            return False

        # 检查剩余药量是否足够
        if not is_resume:  # 新任务需要检查整个目标量
            if volume > self.remaining_medicine:
                self.log_message.emit(f"错误：剩余药量不足（剩余:{self.remaining_medicine}uL, 需要:{volume}uL）")
                QMessageBox.critical(None, "药量不足",
                                     f"剩余药量不足！\n剩余药量: {self.remaining_medicine:.1f}uL\n需要药量: {volume:.1f}uL")
                return False
            # 新任务开始时重置警告标记
            self.low_warning_emitted = False

        self.target_volume = volume
        self.infusion_speed = speed
        self.is_running = True
        self.should_stop = False
        self.should_pause = False
        self.status = "注射中"
        self.status_changed.emit(self.status)

        if is_resume:
            self.log_message.emit(
                f"[恢复] 继续注射: 目标剂量: {self.target_volume} uL, 速度: {self.infusion_speed} uL/s")
        else:
            self.current_volume = 0.0  # 新任务重置已注射量
            self.log_message.emit(f"[开始] 目标剂量: {self.target_volume} uL, 速度: {self.infusion_speed} uL/s")

        self.start()  # 启动后台线程 (会调用 run() 方法)
        return True

    def pause_infusion(self):
        """暂停模拟注射过程"""
        if self.is_running and not self.should_pause:
            self.should_pause = True
            self.status = "暂停中"
            self.status_changed.emit(self.status)
            self.log_message.emit("[用户操作] 暂停注射")

    def stop_infusion(self):
        """停止模拟注射过程"""
        if self.is_running:
            self.should_stop = True
            self.status = "正在停止..."
            self.status_changed.emit(self.status)
            self.log_message.emit("[用户操作] 停止注射")

    def run(self):
        """后台线程执行的核心模拟逻辑 (不要直接操作UI！)"""
        increment = 0.1  # 每次模拟增加的剂量 (uL) - 模拟精度

        # 计算每次增加的延迟时间 (基于注射速度)
        if self.infusion_speed > 0:
            delay = increment / self.infusion_speed
        else:
            delay = 0.1  # 默认延迟

        while self.current_volume < self.target_volume and not self.should_stop:
            if self.should_pause:
                self.paused_volume = self.current_volume
                self.infusion_paused.emit(self.current_volume)
                self.is_running = False
                return

            # 模拟一小步注射
            self.current_volume += increment
            if self.current_volume > self.target_volume:
                self.current_volume = self.target_volume

            # 更新剩余药量
            self.remaining_medicine -= increment
            if self.remaining_medicine < 0:
                self.remaining_medicine = 0

            # 检查剩余药量是否低于5% 且 尚未发出警告
            if self.remaining_medicine <= 0.05 * self.volume and not self.low_warning_emitted:  # 5% of volume
                self.remaining_low_warning.emit()
                self.low_warning_emitted = True  # 标记已发出警告

            # 通过信号更新进度 (UI线程会接收并更新界面)
            self.progress_updated.emit(self.current_volume, self.target_volume, self.remaining_medicine)
            time.sleep(delay)  # 模拟注射需要时间

        # 注射结束处理
        self.is_running = False
        if self.should_stop:
            self.status = "已停止"
            self.status_changed.emit(self.status)
            self.infusion_stopped.emit(self.current_volume)
            self.log_message.emit(f"[停止] 已注射: {self.current_volume:.1f} uL")
        else:
            self.status = "完成"
            self.status_changed.emit(self.status)
            self.infusion_finished.emit()
            self.log_message.emit(f"[完成] 已注射: {self.current_volume:.1f} uL")


# ==================================================================
# 主应用程序窗口 - 美化界面
# ==================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("帕金森给药装置控制软件 (模拟模式)")
        self.setMinimumSize(800, 600)

        # 设置应用样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #c0c0c0;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
                color: #2c3e50;
            }
            QPushButton {
                background-color: #5c9ccc;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4a8bc2;
            }
            QPushButton:pressed {
                background-color: #3a7ab2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
            QPushButton#stopButton {
                background-color: #e74c3c;
            }
            QPushButton#stopButton:hover {
                background-color: #c0392b;
            }
            QPushButton#stopButton:pressed {
                background-color: #a93226;
            }
            QLabel {
                color: #2c3e50;
            }
            QProgressBar {
                border: 1px solid #c0c0c0;
                border-radius: 5px;
                text-align: center;
                background-color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #5c9ccc;
                width: 10px;
            }
            QTextBrowser {
                background-color: white;
                border: 1px solid #c0c0c0;
                border-radius: 4px;
            }
            QDoubleSpinBox, QLineEdit {
                border: 1px solid #c0c0c0;
                border-radius: 4px;
                padding: 4px;
                background-color: white;
            }
        """)

        # 创建模拟泵对象
        self.pump_simulator = DrugPumpSimulator()

        # ----------------------------
        # 创建 UI 控件
        # ----------------------------
        # 状态显示
        self.status_indicator = QLabel()
        self.status_indicator.setFixedSize(20, 20)
        self.status_indicator.setStyleSheet("background-color: gray; border-radius: 10px;")

        self.status_label = QLabel("状态: 就绪")
        self.status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        # 状态布局
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.status_indicator)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        # 设备信息面板
        device_info_group = QGroupBox("设备信息")
        device_info_layout = QGridLayout()

        self.device_name_label = QLabel("设备名称:")
        self.device_name_value = QLabel("帕金森给药装置模拟器")
        self.device_id_label = QLabel("设备ID:")
        self.device_id_value = QLabel("PD-2024-SIM001")
        self.software_ver_label = QLabel("软件版本:")
        self.software_ver_value = QLabel("v1.2.0")

        device_info_layout.addWidget(self.device_name_label, 0, 0)
        device_info_layout.addWidget(self.device_name_value, 0, 1)
        device_info_layout.addWidget(self.device_id_label, 1, 0)
        device_info_layout.addWidget(self.device_id_value, 1, 1)
        device_info_layout.addWidget(self.software_ver_label, 2, 0)
        device_info_layout.addWidget(self.software_ver_value, 2, 1)

        device_info_group.setLayout(device_info_layout)

        # 参数设置区域
        params_group = QGroupBox("参数设置")
        params_layout = QGridLayout()

        # 注射速度控制
        self.speed_label = QLabel("注射速度 (μL/s):")
        self.speed_input = QDoubleSpinBox()
        self.speed_input.setDecimals(3)
        self.speed_input.setRange(0.001, 1.0)
        self.speed_input.setSingleStep(0.001)
        self.speed_input.setValue(0.0)
        self.speed_input.setFixedWidth(120)

        # 给药量设置
        self.volume_label = QLabel("目标注射量 (μL):")
        self.volume_input = QLineEdit()
        self.volume_input.setPlaceholderText("输入数字...")
        self.volume_input.setFixedWidth(120)

        params_layout.addWidget(self.speed_label, 0, 0)
        params_layout.addWidget(self.speed_input, 0, 1)
        params_layout.addWidget(self.volume_label, 1, 0)
        params_layout.addWidget(self.volume_input, 1, 1)
        params_group.setLayout(params_layout)

        # 剂量信息区域
        dose_group = QGroupBox("剂量信息")
        self.dose_layout = QGridLayout()

        self.current_vol_label = QLabel("0.0")
        self.current_vol_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.target_vol_label = QLabel("0.0")
        self.target_vol_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.remaining_vol_label = QLabel("5000.0")
        self.remaining_vol_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))

        self.dose_layout.addWidget(QLabel("已注射量 (μL):"), 0, 0)
        self.dose_layout.addWidget(self.current_vol_label, 0, 1)
        self.dose_layout.addWidget(QLabel("目标注射量 (μL):"), 1, 0)
        self.dose_layout.addWidget(self.target_vol_label, 1, 1)
        self.dose_layout.addWidget(QLabel("设备剩余药量 (μL):"), 2, 0)
        self.dose_layout.addWidget(self.remaining_vol_label, 2, 1)
        self.dose_layout.addWidget(QLabel("药量状态:"), 3, 0)

        # 药量状态指示器
        self.medicine_status_indicator = QLabel()
        self.medicine_status_indicator.setFixedSize(20, 20)
        self.medicine_status_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
        self.dose_layout.addWidget(self.medicine_status_indicator, 3, 1)

        dose_group.setLayout(self.dose_layout)

        # 控制按钮
        self.start_button = QPushButton("开始注射")
        self.pause_button = QPushButton("暂停注射")
        self.pause_button.setEnabled(False)
        self.stop_button = QPushButton("停止注射")
        self.stop_button.setObjectName("stopButton")  # 用于特殊样式
        self.stop_button.setEnabled(False)

        # 按钮布局
        self.button_layout = QHBoxLayout()
        self.button_layout.addWidget(self.start_button)
        self.button_layout.addWidget(self.pause_button)
        self.button_layout.addWidget(self.stop_button)
        self.button_layout.addStretch()

        # 控制按钮组
        control_group = QGroupBox("控制")
        control_group.setLayout(self.button_layout)

        # 进度条区域
        progress_group = QGroupBox("注射进度")
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(25)
        progress_layout.addWidget(self.progress_bar)
        progress_group.setLayout(progress_layout)

        # 日志区域
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout()
        self.log_display = QTextBrowser()
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #c0c0c0;")

        # ----------------------------
        # 布局管理 (使用嵌套布局)
        # ----------------------------
        # 创建主Widget和主垂直布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 顶部状态区域
        top_layout = QHBoxLayout()
        top_layout.addLayout(status_layout)
        top_layout.addStretch()
        top_layout.addWidget(device_info_group)
        main_layout.addLayout(top_layout)

        # 参数和剂量区域
        params_dose_layout = QHBoxLayout()
        params_dose_layout.addWidget(params_group, 1)
        params_dose_layout.addWidget(dose_group, 1)
        main_layout.addLayout(params_dose_layout)

        # 控制区域
        main_layout.addWidget(control_group)

        # 进度条区域
        main_layout.addWidget(progress_group)

        # 日志区域
        main_layout.addWidget(log_group, 1)  # 参数1表示这个控件可以拉伸

        # ----------------------------
        # 连接信号与槽 (事件处理) - 保持不变
        # ----------------------------
        # 按钮点击事件
        self.start_button.clicked.connect(self.on_start_clicked)
        self.pause_button.clicked.connect(self.on_pause_clicked)
        self.stop_button.clicked.connect(self.on_stop_clicked)
        self.speed_input.valueChanged.connect(self.on_speed_changed)

        # 连接模拟泵的信号到UI的槽
        self.pump_simulator.progress_updated.connect(self.update_progress)
        self.pump_simulator.infusion_finished.connect(self.on_infusion_finished)
        self.pump_simulator.infusion_stopped.connect(self.on_infusion_stopped)
        self.pump_simulator.infusion_paused.connect(self.on_infusion_paused)
        self.pump_simulator.status_changed.connect(self.update_status)
        self.pump_simulator.log_message.connect(self.log_message)
        self.pump_simulator.remaining_low_warning.connect(self.on_remaining_low)

        # 初始日志消息
        self.log_message("系统启动 - 模拟模式")
        self.log_message("设备已就绪，等待指令")

    # ==================================================================
    # 槽函数 (处理事件和更新UI) - 保持不变
    # ==================================================================
    def on_speed_changed(self, value):
        """注射速度改变"""
        self.pump_simulator.set_speed(value)

    def on_start_clicked(self):
        """处理 '开始注射' 按钮点击"""
        # 根据当前状态决定是开始新任务还是恢复暂停的任务
        if self.pump_simulator.status == "暂停中":
            # 恢复暂停的任务
            self.log_message("恢复暂停的注射任务")
            self.pump_simulator.start_infusion(
                self.pump_simulator.target_volume,
                self.pump_simulator.infusion_speed,
                is_resume=True
            )
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            return

        # 否则是开始新的注射任务
        # 1. 获取并验证输入
        volume_text = self.volume_input.text().strip()
        speed = self.speed_input.value()

        if not volume_text:
            QMessageBox.warning(self, "输入错误", "请输入目标给药量！")
            return

        try:
            target_volume = float(volume_text)
            if target_volume <= 0:
                raise ValueError("剂量必须为正数")
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", f"无效的剂量: {e}")
            return

        # 2. 检查注射速度
        if speed <= 0:
            QMessageBox.warning(self, "输入错误", "注射速度必须大于0！")
            return

        # 3. 检查注射量警告
        if target_volume > 200:
            reply = QMessageBox.warning(
                self,
                "注射量过大警告",
                f"目标注射量({target_volume}μL)超过200μL！\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # 4. 检查注射速度警告
        if speed > 0.1:
            reply = QMessageBox.warning(
                self,
                "注射速率过快警告",
                f"注射速度({speed}μL/s)超过0.1μL/s！\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # 5. 确认操作 (安全措施!)
        reply = QMessageBox.question(
            self,
            "确认注射",
            f"确认开始注射 {target_volume} uL 药物?\n注射速度: {speed} uL/s",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.No:
            return

        # 6. 调用模拟泵开始注射
        if self.pump_simulator.start_infusion(target_volume, speed):
            # 7. 更新UI状态 (禁用开始按钮，启用停止按钮)
            self.start_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
            self.log_message(f"[用户操作] 开始注射指令发出: {target_volume} uL, 速度: {speed} uL/s")

    def on_pause_clicked(self):
        """处理 '暂停注射' 按钮点击"""
        if self.pump_simulator.status == "注射中":
            self.pump_simulator.pause_infusion()
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(True)  # 确保暂停状态下可以停止

    def on_stop_clicked(self):
        """处理 '停止注射' 按钮点击"""
        # 在"注射中"或"暂停中"状态下都可以停止
        if self.pump_simulator.status in ["注射中", "暂停中"]:
            self.pump_simulator.stop_infusion()
            # 注意：UI状态的改变将在收到模拟泵的`infusion_stopped`信号后处理
        else:
            self.log_message("警告：当前状态无法停止注射")

    def update_progress(self, current_vol, target_vol, remaining_med):
        """更新进度条和剂量显示 (由模拟泵的progress_updated信号触发)"""
        # 计算百分比
        percent = (current_vol / target_vol) * 100 if target_vol > 0 else 0
        self.progress_bar.setValue(int(percent))

        # 更新剂量标签
        self.current_vol_label.setText(f"{current_vol:.1f}")
        self.target_vol_label.setText(f"{target_vol:.1f}")
        self.remaining_vol_label.setText(f"{remaining_med:.1f}")

        # 更新药量状态指示器
        med_percent = (remaining_med / 5000) * 100
        if med_percent < 5:
            self.medicine_status_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
        elif med_percent < 20:
            self.medicine_status_indicator.setStyleSheet("background-color: orange; border-radius: 10px;")
        else:
            self.medicine_status_indicator.setStyleSheet("background-color: green; border-radius: 10px;")

    def on_infusion_finished(self):
        """注射完成处理 (由模拟泵的infusion_finished信号触发)"""
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        QMessageBox.information(self, "完成", "药物注射已完成！")

    def on_infusion_stopped(self, volume_injected):
        """注射停止处理 (由模拟泵的infusion_stopped信号触发)"""
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        QMessageBox.information(self, "已停止", f"注射已停止。已注射量: {volume_injected:.1f} uL")

    def on_infusion_paused(self, volume_injected):
        """注射暂停处理 (由模拟泵的infusion_paused信号触发)"""
        self.log_message(f"注射已暂停。已注射量: {volume_injected:.1f} uL")
        # 不需要弹出消息框，因为暂停是用户主动操作
        # 更新UI状态已在按钮点击事件中处理

    def update_status(self, new_status):
        """更新状态标签 (由模拟泵的status_changed信号触发)"""
        self.status_label.setText(f"状态: {new_status}")

        # 更新状态指示灯
        if "注射中" in new_status:
            self.status_indicator.setStyleSheet("background-color: orange; border-radius: 10px;")
            # 禁用速度设置
            self.speed_input.setEnabled(False)
        elif "暂停中" in new_status:
            self.status_indicator.setStyleSheet("background-color: blue; border-radius: 10px;")
            # 启用速度设置（允许在暂停时修改速度）
            self.speed_input.setEnabled(True)
        elif "停止" in new_status or "错误" in new_status:
            self.status_indicator.setStyleSheet("background-color: red; border-radius: 10px;")
            # 启用速度设置
            self.speed_input.setEnabled(True)
        else:  # 就绪/完成
            self.status_indicator.setStyleSheet("background-color: green; border-radius: 10px;")
            # 启用速度设置
            self.speed_input.setEnabled(True)

    def log_message(self, message):
        """向日志区域添加消息 (可由自身或模拟泵的log_message信号触发)"""
        timestamp = time.strftime("%H:%M:%S")  # 添加时间戳
        self.log_display.append(f"[{timestamp}] {message}")

    def on_remaining_low(self):
        """剩余药量不足5%警告"""
        remaining = self.pump_simulator.remaining_medicine
        self.log_message(f"警告：设备剩余药量不足5% ({remaining:.1f}μL)！")
        QMessageBox.warning(
            self,
            "药量不足警告",
            f"设备剩余药量不足5%！\n当前剩余药量: {remaining:.1f}μL\n请及时补充药物。"
        )


# ==================================================================
# 主程序入口
# ==================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())