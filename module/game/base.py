from abc import abstractmethod
import os
import time
from typing import Literal, Tuple, Optional
from utils.logger.logger import Logger


# Set process as DPI-aware to get actual pixel dimensions instead of scaled values
# This needs to be called once before any window operations
# PROCESS_PER_MONITOR_DPI_AWARE = 1 (Windows 8.1+)
PROCESS_PER_MONITOR_DPI_AWARE = 1
try:
    # Try to set DPI awareness (Windows 8.1+)
    ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
except (OSError, AttributeError):
    try:
        # Fallback for older Windows versions
        ctypes.windll.user32.SetProcessDPIAware()
    except (OSError, AttributeError):
        # If both fail, continue without DPI awareness (likely not on Windows)
        pass


class GameControllerBase:
    def __init__(self, script_path: Optional[str] = None, logger: Optional[Logger] = None) -> None:
        self.script_path = os.path.normpath(script_path) if script_path and isinstance(script_path, (str, bytes, os.PathLike)) else None
        self.logger = logger

    def log_debug(self, message: str) -> None:
        """记录调试日志，如果logger不为None"""
        if self.logger is not None:
            self.logger.debug(message)

    def log_info(self, message: str) -> None:
        """记录信息日志，如果logger不为None"""
        if self.logger is not None:
            self.logger.info(message)

    def log_error(self, message: str) -> None:
        """记录错误日志，如果logger不为None"""
        if self.logger is not None:
            self.logger.error(message)

    def log_warning(self, message: str) -> None:
        """记录警告日志，如果logger不为None"""
        if self.logger is not None:
            self.logger.warning(message)

    @abstractmethod
    def start_game_process(self) -> bool:
        """启动游戏进程"""
        ...

    @abstractmethod
    def stop_game(self) -> bool:
        """终止游戏"""
        ...

    '''@abstractmethod
    def get_window_handle(self) -> int:
        """获取 window handle"""
        ...

    @abstractmethod
    def get_input_handler(self):  # -> InputBase
        """获取用于模拟鼠标和键盘操作的类"""
        ...
'''
    '''def switch_to_game(self) -> bool:
        """将游戏窗口切换到前台"""
        try:
            hwnd = self.get_window_handle()
            if hwnd == 0:
                self.log_debug("游戏窗口未找到")
                return False
            self.set_foreground_window_with_retry(hwnd)
            self.log_info("游戏窗口已切换到前台")
            return True
        except Exception as e:
            self.log_error(f"激活游戏窗口时发生错误：{e}")
            return False'''

    '''def get_resolution(self) -> Optional[Tuple[int, int]]:
        """检查游戏窗口的分辨率"""
        try:
            hwnd = self.get_window_handle()
            if hwnd == 0:
                self.log_debug("游戏窗口未找到")
                return None
            _, _, window_width, window_height = win32gui.GetClientRect(hwnd)
            return window_width, window_height
        except IndexError:
            self.log_debug("游戏窗口未找到")
            return None'''

    def shutdown(self, action: Literal['Exit', 'Loop', 'Shutdown', 'Sleep', 'Hibernate', 'Restart', 'Logoff', 'TurnOffDisplay', 'RunScript'], delay: int = 60) -> bool:
        """
        终止游戏并在指定的延迟后执行系统操作：关机、睡眠、休眠、重启、注销。

        参数:
            action: 要执行的系统操作。
            delay: 延迟时间，单位为秒，默认为60秒。

        返回:
            操作成功执行返回True，否则返回False。
        """
        self.stop_game()
        return True


    def run_script(self) -> bool:
        """运行指定的程序或脚本（支持.exe、.ps1和.bat）"""

        return True

    @staticmethod
    def set_foreground_window_with_retry(hwnd) -> None:
        """尝试将窗口设置为前台，失败时先最小化再恢复。"""
        pass