from io import BytesIO
from PIL import Image
from module.config import cfg

class Screenshot:
    @staticmethod
    def is_application_fullscreen(window):
        # 云游戏默认情况：始终视为全屏
        return True

    @staticmethod
    def get_window_real_resolution(window):
        # 云游戏默认分辨率
        return 1920, 1080

    @staticmethod
    def get_window_region(window):
        # 云游戏默认区域
        return (0, 0, 1920, 1080)

    @staticmethod
    def get_window(title):
        # 云游戏下无需本地窗口句柄
        return False

    @staticmethod
    def get_main_screen_location():
        # 云游戏下无需多屏位置
        return None, None
    
    @staticmethod
    def take_screenshot(title, crop=(0, 0, 1, 1)):
        # 仅保留云游戏截屏逻辑
        from module.game import cloud_game
        screenshot = Image.open(BytesIO(cloud_game.take_screenshot()))
        width, height = screenshot.size

        left = int(width * crop[0])
        top = int(height * crop[1])
        crop_width = int(width * crop[2])
        crop_height = int(height * crop[3])

        screenshot = screenshot.crop((left, top, left + crop_width, top + crop_height))

        # Selenium 截图分辨率一般就是浏览器窗口实际像素，所以 scale_factor 默认为 1
        screenshot_scale_factor = 1

        screenshot_pos = (left, top, crop_width, crop_height)

        return screenshot, screenshot_pos, screenshot_scale_factor
