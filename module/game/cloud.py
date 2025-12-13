import os
import json
import psutil
from time import sleep
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, SessionNotCreatedException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.command import Command
from selenium.common.exceptions import WebDriverException
from multiprocessing.managers import BaseManager
import time
import threading
from threading import Event

from module.config import Config
from module.game.base import GameControllerBase
from module.logger import Logger
#from utils.encryption import wdp_encrypt, wdp_decrypt

# 模块级子进程函数：通过 BaseManager 连接到父进程暴露的 controller 代理，
# 周期性检查 is_in_game，从 True->False 时调用 _save_local_storage 并退出。

class CloudGameController(GameControllerBase):
    COOKIE_PATH = "settings/cookies.enc"          # Cookies 保存地址
    localStorage_PATH = "settings/local_storage.enc"  # localStorage 保存地址
    GAME_URL = "https://sr.mihoyo.com/cloud"            # 游戏地址
    # BROWSER_TAG 已移除：不再标记浏览器进程用于复用/清理
    MAX_RETRIES = 3  # 网页加载重试次数，0=不重试
    PERFERENCES = {
        "profile": {
            "content_settings": {
                "exceptions": {
                    "keyboard_lock": { # 允许 keyboard_lock 权限
                        "https://sr.mihoyo.com:443,*": {"setting": 1}
                    },
                    "clipboard": {   # 允许剪贴板读取权限
                        "https://sr.mihoyo.com:443,*": {"setting": 1}
                    }
                }
            }
        }
    }

    def __init__(self, cfg: Config, logger: Logger):
        super().__init__(script_path=cfg.script_path, logger=logger)
        self.driver = None
        self.cfg = cfg
        self.logger = logger
        # 已移除：退出时自动清理浏览器（不再复用/批量关闭由小助手启动的浏览器）
        # atexit.register(self._clean_at_exit)

    def _wait_game_page_loaded(self, timeout=5) -> None:
        """等待云崩铁网页加载出来，这里以背景图是否加载出来为准"""
        if not self.driver:
            return
        for retry in range(self.MAX_RETRIES + 1):
            if retry > 0:
                self.log_warning(f"页面加载超时，正在刷新重试... ({retry}/{self.MAX_RETRIES})")
                self.driver.refresh()
            try:
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.execute_script(
                        """
                        const img = document.querySelector('#app > div.home-wrapper > picture > img');
                        if (!img) return false;
                        return img && img.complete && img.naturalWidth > 0;
                        """
                    )
                )
                return
            except TimeoutException:
                pass

        raise Exception("页面加载失败，多次刷新无效。")

    def _confirm_viewport_resolution(self) -> None:
        """
        设置网页分辨率大小
        """
        self.driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 1080,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    
    
    def _get_browser_arguments(self, headless) -> list[str]:
        args = [
            # 已移除浏览器标记参数（不再尝试查找/复用/关闭其他进程）
            "--disable-infobars",   # 去掉提示 "Chrome测试版仅适用于自动测试。" 和 "浏览器正由自动测试软件控制。"
            "--lang=zh-CN",     # 浏览器语言中文
            "--log-level=3",    # 浏览器日志等级为error
            "--headless",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--start-maximized",
            "-–single-process",
            #"--user-data-dir=/chromedata/",  # 使用指定用户数据目录
            f"--force-device-scale-factor={float(self.cfg.browser_scale_factor)}",  # 设置缩放
            f"--app={self.GAME_URL}",   # 以应用模式启动
            "--disable-blink-features=AutomationControlled",  # 去除自动化痕迹，防止被人机验证
        ]
        
        return args
    '''chrome_options.add_argument('--headless') # 浏览器不提供可视化页面. linux下如果系统不支持可视化不加这条会启动失败
        chrome_options.add_argument('--no-sandbox')  # 解决DevToolsActivePort文件不存在的报错
        chrome_options.add_argument('--disable-dev-shm-usage') # 大量渲染时候写入/tmp而非/dev/shm
        chrome_options.add_argument('--disable-gpu') # 谷歌文档提到需要加上这个属性来规避bug
        chrome_options.add_argument('-–single-process')  #以单进程模式运行 Chromium。（启动时浏览器会给出不安全警告）
        chrome_options.add_argument('window-size=1920x1080')  # 指定浏览器分辨率
        chrome_options.add_argument('--start-maximized')  # 最大化运行（全屏窗口）,不设置，取元素会报错
        chrome_options.add_argument('--user-data-dir=/home/jenkins/data')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
'''
    def check_first_run(driver, target_cookie_name=None):
        """
        检查是否为首次运行
        :param driver: WebDriver实例
        :param target_cookie_name: 可选的特定Cookie名称
        :return: True表示首次运行，False表示非首次
        """
        cookies = driver.get_cookies()
        
        if target_cookie_name:
            # 检查特定Cookie是否存在
            for cookie in cookies:
                if cookie['name'] == target_cookie_name:
                    return False
            return True
        else:
            # 检查所有Cookie
            return len(cookies) == 0
    def _connect_or_create_browser(self, headless=False) -> None:
        """尝试连接到现有的（由小助手启动的）浏览器，如果没有，那就创建一个"""
        browser_type = "chrome"
        integrated = self.cfg.browser_type=="integrated"
        browser_path, driver_path = self._prepare_browser_and_driver(browser_type, integrated)
        
        if browser_type == "chrome":
            options = ChromeOptions()
            service = None
            webdriver_type = webdriver.Remote
            executor_url = "http://chrome:4444/wd/hub"
        
        # 记录（为了兼容旧逻辑），但远程模式下一般无本地 driver_path/service
        
        self.log_info(f"正在通过远程 Selenium Hub 启动 {browser_type} 浏览器（{executor_url}）")

        options.add_experimental_option("prefs", self.PERFERENCES)  # 允许云游戏权限
        # 添加参数
        for arg in self._get_browser_arguments(headless=headless):
            options.add_argument(arg)
        
        try:
            # 使用 Remote 连接到 Selenium Hub
            self.driver = webdriver_type(command_executor=executor_url, options=options)
        except SessionNotCreatedException as e:
            self.log_error(f"浏览器启动失败: {e}")
            self.log_error("如果设置了浏览器启动参数，请去掉所有浏览器启动参数后重试")
            self.log_error("如果仍然存在问题，请更换浏览器重试")
            raise Exception("浏览器启动失败")
        
        if not self.cfg.cloud_game_fullscreen_enable:
            self.driver.set_window_size(1920, 1120)
        '''if not self.cfg.browser_persistent_enable:
            self._load_initial_local_storage()'''
        if self.cfg.auto_battle_detect_enable:
            self.change_auto_battle(True) 
        if self.cfg.browser_userdata_enable:
            self._load_cookies()
            self._load_local_storage()
            
        self._refresh_page()

    def _restart_browser(self, headless=False) -> None:
        """重启浏览器"""
        self.stop_game()
        self._connect_or_create_browser(headless=headless)
    def _show_warning_tips(self) -> None:
        # 增强版：带有10秒倒计时
        warnscript = """
        // 移除已存在的提示
        var oldAlert = document.getElementById('countdown-alert');
        if (oldAlert) oldAlert.remove();

        // 创建提示框
        var alertDiv = document.createElement('div');
        alertDiv.id = 'countdown-alert';
        alertDiv.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            background: linear-gradient(135deg, #ffcc00, #ff9900);
            color: #333;
            text-align: center;
            padding: 20px 0;
            font-size: 20px;
            font-weight: bold;
            z-index: 999999;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            font-family: Arial, sans-serif;
        `;

        // 添加倒计时功能
        var countdown = 10;
        alertDiv.innerHTML = '手动运行请通过悬浮球退出游戏，且等待至少 <span id="countdown">10</span> 秒再关闭浏览器';

        // 添加到页面
        document.body.appendChild(alertDiv);

        // 开始倒计时
        var countdownElement = document.getElementById('countdown');
        var countdownInterval = setInterval(function() {
            countdown--;
            if (countdown <= 0) {
                clearInterval(countdownInterval);
                alertDiv.innerHTML = '您已经了解本消息内容';
                alertDiv.style.background = '#4CAF50';
                alertDiv.style.color = 'white';
                
                // 3秒后自动隐藏
                setTimeout(function() {
                    alertDiv.style.opacity = '0';
                    alertDiv.style.transition = 'opacity 1s';
                    setTimeout(function() {
                        alertDiv.remove();
                        document.body.style.marginTop = '0';
                    }, 1000);
                }, 3000);
            }
        }, 1000);

        // 调整页面内容避免被遮挡
        setTimeout(function() {
            document.body.style.marginTop = alertDiv.offsetHeight + 'px';
        }, 100);
        """

        self.driver.execute_script(warnscript)
    def _save_local_storage(self) -> bool:
        """保存 localStorage"""
        if not self.driver:
            return
        try:
            ls_json = self.driver.execute_script("return JSON.stringify(window.localStorage);")
            with open(self.localStorage_PATH, "wb") as f:
                # f.write(wdp_encrypt(ls_json.encode()))
                f.write(ls_json.encode())
            self.log_info("本地存储信息保存成功。")
        except Exception as e:
            self.log_error(f"保存 localStorage 失败: {e}")
    def _load_local_storage(self) -> bool:
        """加载 localStorage"""
        if not self.driver:
            return False

        try:
            with open(self.localStorage_PATH, "rb") as f:
                # ls = json.loads(wdp_decrypt(f.read()).decode())
                ls = json.loads(f.read().decode())

            for key, value in ls.items():
                try:
                    self.driver.execute_script(
                        "window.localStorage.setItem(arguments[0], arguments[1]);",
                        key,
                        value,
                    )
                except Exception:
                    pass  # 忽略无效项

            self.driver.refresh()
            self.log_info("本地存储信息加载成功。")
            return True
        except FileNotFoundError:
            self.log_info("localStorage 文件不存在。正在加载默认配置...")
            self._load_initial_local_storage()
            return False
        except Exception as e:
            self.log_error(f"加载 localStorage 失败: {e}")
            return False
    def _load_initial_local_storage(self) -> bool:
        """加载初始配置，去除初始引导，免责协议等弹窗"""

        try:
            with open("assets/config/initial_local_storage.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            # settings = json.loads(data["clgm_web_app_settings_hkrpg_cn"])
            # settings["videoMode"] = self.cfg.cloud_game_smooth_first_enable if 1 else 0
            # data["clgm_web_app_settings_hkrpg_cn"] = json.dumps(settings)

            # client_config = json.loads(data["clgm_web_app_client_store_config_hkrpg_cn"])
            # client_config["speedLimitGearId"] = self.cfg.cloud_game_video_quality
            # client_config["fabPosition"]["x"] = self.cfg.cloud_game_fab_pos_x
            # client_config["fabPosition"]["y"] = self.cfg.cloud_game_fab_pos_y
            # client_config["showGameStatBar"] = self.cfg.cloud_game_status_bar_enable
            # client_config["gameStatBarType"] = self.cfg.cloud_game_status_bar_type
            # client_config["volume"] = self.cfg.browser_headless_enable if 0 else 1
            # data["clgm_web_app_client_store_config_hkrpg_cn"] = json.dumps(client_config)

            # 注入浏览器
            for key, value in data.items():
                self.driver.execute_script(
                    "window.localStorage.setItem(arguments[0], arguments[1]);",
                    key,
                    value,
                )
            self.log_info("加载初始配置成功")
            return True
        except Exception as e:
            self.log_error(f"加载初始配置失败 {e}")
            return False

    def _save_cookies(self) -> bool:
        """保存 Cookies""" 
        if not self.driver:
            return
        try:
            cookies_json = json.dumps(self.driver.get_cookies(), ensure_ascii=False, indent=4)
            with open(self.COOKIE_PATH, "wb") as f:
                # f.write(wdp_encrypt(cookies_json.encode()))
                f.write(cookies_json.encode())
            self.log_info("登录信息保存成功。")
        except Exception as e:
            self.log_error(f"保存 cookies 失败: {e}")

    def _load_cookies(self) -> bool:
        """加载 Cookies"""
        if not self.driver:
            return False
        try:
            with open(self.COOKIE_PATH, "rb") as f:
                # cookies = json.loads(wdp_decrypt(f.read()).decode())
                cookies = json.loads(f.read().decode())

            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception:
                    pass  # 忽略无效 cookie

            self.driver.refresh()
            self.log_info("登录信息加载成功。")
            return True
        except FileNotFoundError:
            self.log_info("cookies 文件不存在。")
            return False
        except Exception as e:
            self.log_error(f"加载 cookies 失败: {e}")
            return False
    
    def _refresh_page(self) -> None:
        if self.driver:
            self.driver.refresh()
            self._wait_game_page_loaded()

    def _check_login(self, timeout=5) -> bool:
        """检查是否已经登录"""
        if not self.driver:
            return None
        
        logged_in_selector = "div.user-aid.wel-card__aid, .game-player, [class*='waiting-in-queue']"
        not_logged_in_id = "mihoyo-login-platform-iframe"

        try:
            state = WebDriverWait(self.driver, timeout).until(
                lambda d: (
                    "logged_in"
                    if d.find_elements(By.CSS_SELECTOR, logged_in_selector)
                    else (
                        "not_logged_in"
                        if d.find_elements(By.ID, not_logged_in_id)
                        else None
                    )
                )
            )

            return state == "logged_in"
        except TimeoutException:
            self.log_warning("检测登录状态超时：未出现登录或未登录标志元素")
            return None
            
    def _click_enter_game(self, timeout=5) -> None:
        """
        点击‘进入游戏’按钮。
        """
        if not self.driver:
            return
        
        game_selector = ".game-player"
        enter_button_selector = "div.wel-card__content--start"
        try:
            if self.driver.find_elements(By.CSS_SELECTOR, game_selector):
                self.log_info("已在游戏中")
                return 
            enter_button = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, enter_button_selector))
            )
            self.driver.execute_script("arguments[0].click();", enter_button)
        except Exception as e:
            self.log_error(f"点击进入游戏按钮游戏异常: {e}")
            raise e
        
    def _wait_in_queue(self, timeout=600) -> bool:
        """排队等待进入"""
        in_queue_selector = "[class*='waiting-in-queue']"
        cloud_game_selector = ".game-player"
        
        try:
            # 检查是否需要排队
            status = WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("""
                    if (document.querySelector(arguments[0])) return "game_running";
                    else if (document.querySelector(arguments[1])) return "in_queue";
                    else return null;
                """, cloud_game_selector, in_queue_selector)
            )

            if status == "game_running":
                self.log_info("游戏已启动，无需排队")
                return True
            elif status == "in_queue":
                self.log_info("正在排队...")
                try:
                    WebDriverWait(self.driver, timeout).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, in_queue_selector))
                    )
                    self.log_info("排队成功，正在进入游戏")
                    return True
                except TimeoutException:
                    self.log_error("排队超时")
                    return False
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log_error(f"等待排队异常: {e}")
            return False
    
    def is_integrated_browser_downloaded(self) -> bool:
        """当前是否已经下载内置浏览器"""
        return True
    
    def stop_game(self) -> bool:
        """退出游戏，关闭浏览器"""
        if self.driver:
            try:
                self.driver.execute(Command.CLOSE)
                self.log_info("关闭浏览器成功")
            except Exception:
                pass
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            
        # 已移除：不再在 stop_game 中额外尝试关闭由小助手启动的其它浏览器进程
        return True

    def start_game_process(self) -> bool:
        """启动浏览器进程"""
        try:
            self._connect_or_create_browser(headless=self.cfg.browser_headless_enable)
            self._confirm_viewport_resolution()
            #self._show_warning_tips()
            # 启动独立进程监视 is_in_game 的变化（True -> False 时会保存 localStorage）
            '''try:
                self.start_in_game_watcher()
            except Exception:
                # 监视器启动失败不影响主流程
                self.log_warning("启动 in-game 监视子进程失败")
            return True'''
        except Exception as e:
            self.log_error(f"启动或连接浏览器失败 {e}")
            return False
    
    def is_in_game(self) -> bool:
        if self.driver:
            return True if self.driver.find_elements(By.CSS_SELECTOR, ".game-player") else False
        
    # 启动线程监视 is_in_game（True -> False 时会调用 _save_local_storage）
    def start_in_game_watcher(self, poll_interval: float = 1.0) -> None:
        # 如果已有线程在运行则不重复启动
        if getattr(self, '_in_game_watcher_thread', None) and getattr(self._in_game_watcher_thread, 'is_alive', lambda: False)():
            self.log_warning("in-game 监视线程已在运行,正在退出")
            self.stop_in_game_watcher()
            

        # 停止事件和线程引用
        self._in_game_watcher_stop_event = Event()
        def _target():
            try:
                self._in_game_watcher_loop(poll_interval, self._in_game_watcher_stop_event)
            except Exception as e:
                # 线程内异常记录后退出，不影响主流程
                try:
                    self.log_error(f"in-game 监视线程异常: {e}")
                except Exception:
                    pass

        t = threading.Thread(target=_target, daemon=True, name="m7a_in_game_watcher")
        t.start()
        self._in_game_watcher_thread = t
        self.log_info("已启动 in-game 监视线程")

    def _in_game_watcher_loop(self, poll_interval: float, stop_event: Event) -> None:
        """在同一进程内循环轮询 is_in_game，并在 True->False 时保存 localStorage 后退出线程。"""
        # 先尝试获取初始状态（若为 None 则循环直到布尔值）
        prev = None
        try:
            prev = self.is_in_game()
        except Exception:
            prev = None

        while prev is None and not stop_event.is_set():
            stop_event.wait(poll_interval)
            try:
                prev = self.is_in_game()
            except Exception:
                prev = None

        # 主循环
        while not stop_event.is_set():
            stop_event.wait(poll_interval)
            try:
                cur = self.is_in_game()
            except Exception:
                cur = None
            # 检测到从 True 变为 False
            if prev and (cur is False):
                self.log_info("检测到游戏已退出，正在保存 localStorage 信息...")

                try:
                    # 尝试获取当前URL，如果浏览器关闭会抛出异常
                    current_url = self.driver.current_url
                    
                except Exception:
                    break
                try:
                    self._save_local_storage()
                    self._save_cookies()
                except Exception as e:
                    try:
                        self.log_error(f"保存 localStorage 失败: {e}")
                    except Exception:
                        pass
                break
            prev = cur
        self.log_info("in-game 监视线程已退出")

    # 停止监视线程
    def stop_in_game_watcher(self) -> None:
        try:
            stop_event = getattr(self, '_in_game_watcher_stop_event', None)
            if stop_event:
                stop_event.set()
        except Exception:
            pass
        try:
            t = getattr(self, '_in_game_watcher_thread', None)
            if t and t.is_alive():
                t.join(timeout=1)
        except Exception:
            pass
        self._in_game_watcher_thread = None
        self._in_game_watcher_stop_event = None

    def enter_cloud_game(self) -> bool:
        """进入云游戏"""
        try:            
            # 检测登录状态
            if not self._check_login():
                self.log_info("未登录")
                raise Exception("未登录，请先登录米哈游通行证账号")
                
                
                # 循环检测用户是否登录
                while not self._check_login():
                    sleep(2)
                    
                self.log_info("检测到登录成功")
                
                # 如果为 headless 模式，则重启浏览器回到 headless 模式
                if self.cfg.browser_headless_enable:
                    if self.cfg.browser_userdata_enable:
                        self._save_cookies()
                        self._save_local_storage()
                    self._restart_browser(headless=True)
            
            if self.cfg.browser_userdata_enable:
                self._save_cookies()
                self._save_local_storage()
            self._click_enter_game()
            if not self._wait_in_queue(int(self.cfg.cloud_game_max_queue_time) * 60):
                return False
            self._confirm_viewport_resolution() # 将浏览器内部分辨率设置为 1920x1080
            
            self.log_info("进入云游戏成功")
            return True 
        except Exception as e:
            self.try_dump_page()
            self.log_error(f"进入云游戏失败: {e}")
            return False
    
    def take_screenshot(self) -> bytes:
        """浏览器内截图"""
        if not self.driver:
            return None
        png = self.driver.get_screenshot_as_png()
        return png
    
    def execute_cdp_cmd(self, cmd: str, cmd_args: dict):
        return self.driver.execute_cdp_cmd(cmd, cmd_args)
    
    def get_window_handle(self) -> int:
        return self.driver.current_window_handle
    
    def switch_to_game(self) -> bool:
        if self.cfg.browser_headless_enable:
            self.log_warning("游戏切换至前台失败：当前为无窗口模式")
            return False
        else:
            return super().switch_to_game()
    
    def get_input_handler(self):
        from module.automation.cdp_input import CdpInput
        return CdpInput(cloud_game=self, logger=self.logger)

    def change_auto_battle(self, status: bool) -> None:
        """从 local storage 中读取并修改 auto battle"""
        ls = json.loads(self.driver.execute_script("return JSON.stringify(localStorage)"))
        cloud = json.loads(ls.get("cg_hkrpg_cn_cloudData", "{}"))
        cloud.setdefault("value", {})
        save = json.loads(cloud["value"].get("RPGCloudSave", "{}") or "{}")
        int_dicts = save.get("IntDicts", {})

        int_dicts["OtherSettings_AutoBattleOpen"] = int(status)
        int_dicts["OtherSettings_IsSaveBattleSpeed"] = int(status)

        save["IntDicts"] = int_dicts
        cloud["value"]["RPGCloudSave"] = json.dumps(save)
        ls["cg_hkrpg_cn_cloudData"] = json.dumps(cloud)

        for k, v in ls.items():
            self.driver.execute_script(f"localStorage.setItem('{k}', arguments[0]);", v)

    def stop_game(self) -> bool:
        """退出游戏，关闭浏览器"""
        if self.driver:
            try:
                if self.cfg.browser_userdata_enable:
                    self._save_cookies()
                    self._save_local_storage()
            except Exception:
                self.log_warning("保存登录信息失败")
            try:
                self.driver.execute(Command.CLOSE)
                self.log_info("关闭浏览器成功")
            except Exception:
                pass
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            
        # 已移除：不再在 stop_game 中额外尝试关闭由小助手启动的其它浏览器进程
        return True

