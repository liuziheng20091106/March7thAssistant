import os
from module.config.config import Config



VERSION_PATH = "./assets/config/version.txt"
EXAMPLE_PATH = "./assets/config/config.example.yaml"
CONFIG_PATH = "./config.yaml"

cfg = Config(VERSION_PATH, EXAMPLE_PATH, CONFIG_PATH)
cfg.env = os.environ.copy()
#cfg.env['PATH'] = os.path.dirname(cfg.python_exe_path) + ';' + cfg.env['PATH']
cfg.useragent = {"User-Agent": f"March7thAssistant/{cfg.version}"}

