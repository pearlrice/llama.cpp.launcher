# coding:utf-8
import sys
import os
import re
import json
import codecs
import subprocess
import time


def _launcher_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _runtime_dir(base_dir):
    core_dir = os.path.join(base_dir, 'core')
    if os.path.isdir(core_dir):
        return core_dir
    return base_dir


def _candidate_core_dirs(base_dir):
    dirs = [
        os.path.join(base_dir, 'core'),
    ]
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        dirs.append(os.path.join(meipass, 'core'))
    return dirs


def _run_embedded_autodeploy():
    base_dir = _launcher_base_dir()
    os.environ.setdefault('AUTODEPLOY_BASE_DIR', _runtime_dir(base_dir))
    for core_dir in _candidate_core_dirs(base_dir):
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        core_file = os.path.join(core_dir, 'deploy_core.py')
        if os.path.exists(core_file):
            sys.argv[0] = core_file
            import runpy
            runpy.run_path(core_file, run_name='__main__')
            return
    try:
        import deploy_core
        deploy_core.main()
    except Exception as e:
        raise SystemExit(f'deploy_core.py not found in launcher core directory: {e}')


if '--run-autodeploy' in sys.argv:
    sys.argv.remove('--run-autodeploy')
    _run_embedded_autodeploy()
    raise SystemExit(0)

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QColor, QFont, QTextCursor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit, QLabel, QFrame,
                               QFileDialog, QLineEdit, QGraphicsOpacityEffect, QMessageBox)

if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('llama.cpp.launcher')
    except Exception:
        pass

# qfluentwidgets 在导入时会创建 QWidget，必须先创建 QApplication
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
_appFont = QFont('Microsoft YaHei UI', 10)
_appFont.setHintingPreference(QFont.PreferFullHinting)
app.setFont(_appFont)

from qfluentwidgets import (MSFluentWindow, FluentIcon as FIF, setTheme, Theme, isDarkTheme,
                            ScrollArea, ExpandLayout, SettingCardGroup, SettingCard,
                            LineEdit, ComboBox, SpinBox, DoubleSpinBox,
                            PrimaryPushButton, PushButton,
                            InfoBar, InfoBarPosition, NavigationItemPosition)
from qfluentwidgets.components.widgets.combo_box import ComboBoxMenu


class FixedComboBox(ComboBox):
    """修复弹出菜单外层边框的 ComboBox"""

    def _createComboMenu(self):
        menu = ComboBoxMenu(self)
        menu.setShadowEffect(blurRadius=0, offset=(0, 0), color=QColor(0, 0, 0, 0))
        menu.layout().setContentsMargins(0, 0, 0, 0)
        return menu


class DoubleClickPushButton(PushButton):
    """只响应双击动作的解锁按钮。"""

    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


CTRL_WIDTH = 200
DISTRO = 'Ubuntu-24.04'
DEFAULT_MODEL_SEARCH_PATHS = [
    '/home/{user}/model',
    '/home/{user}/models',
    '/home/{user}/gguf_models',
    '/home/{user}/llama-cpp-turboquant',
]
TERMINAL_MAX_BLOCKS = 2000
TERMINAL_FLUSH_INTERVAL_MS = 100
TERMINAL_BUFFER_CHAR_LIMIT = 262144
WORKER_EMIT_INTERVAL_SEC = 0.05
WORKER_EMIT_CHAR_LIMIT = 65536
LOG_VERBOSITY_LEVELS = {
    'warn': '2',
    'info': '3',
    'debug': '4',
}
LEGACY_LOG_VERBOSITY_ALIASES = {
    '关闭': 'warn',
    '禁用': 'warn',
    '启用': 'debug',
    '2': 'warn',
    '3': 'info',
    '4': 'debug',
}
DEFAULT_LAUNCHER_CONFIG = {
    'language': 'CH',
    'theme': '深色',
    'font_scale': 100,
}
LAUNCHER_THEMES = {
    '深色': Theme.DARK,
    '浅色': Theme.LIGHT,
    '跟随系统': Theme.AUTO,
}
THEME_ALIASES = {
    'Dark': '深色',
    'Light': '浅色',
    'Auto': '跟随系统',
    'dark': '深色',
    'light': '浅色',
    'auto': '跟随系统',
}
LANG_TEXT = {
    'CH': {
        'nav.basic': '基础设置',
        'nav.deploy': '一键部署',
        'nav.model': '模型设置',
        'nav.server': '服务器设置',
        'nav.log': '运行日志',
        'nav.settings': '设置',
        'window.title': 'llama.cpp 启动器',
        'settings.title': '启动器设置',
        'settings.launcher_group': '偏好',
        'settings.language_title': '语言',
        'settings.language_content': '切换启动器导航和设置页语言',
        'settings.theme_title': 'UI 颜色',
        'settings.theme_content': '切换深色、浅色或跟随系统主题',
        'settings.font_title': '字体大小',
        'settings.font_content': '按比例调整标题、分组标题、说明文字和日志字号（80%-130%）',
        'settings.reset_group': '还原设置',
        'settings.reset_params_title': '还原所有参数设置为默认',
        'settings.reset_params_content': '重置模型、服务器和路径参数，不影响启动器语言/主题/字体',
        'settings.reset_params_button': '还原参数默认值',
        'settings.reset_launcher_title': '还原启动器设置',
        'settings.reset_launcher_content': '重置语言、UI 颜色和字体大小',
        'settings.reset_launcher_button': '还原启动器设置',
        'basic.preview': '命令预览',
        'basic.path_group': '路径配置',
        'basic.model_group': '模型选择',
        'basic.exec_title': '程序路径',
        'basic.exec_content': '设置 llama-server 在 WSL 中的可执行文件路径；支持 {user} 占位符',
        'basic.search_title': '模型搜索路径',
        'basic.search_content': '用分号分隔多个 WSL 目录；支持 {user} 占位符',
        'basic.refresh_title': '刷新本地模型',
        'basic.refresh_content': '扫描搜索路径中的 .gguf 文件并更新模型下拉列表',
        'basic.refresh_button': '刷新本地模型列表',
        'basic.llm_title': '大语言模型',
        'basic.llm_content': '选择要加载的 GGUF 模型文件',
        'basic.mm_title': '多模态模型',
        'basic.mm_content': '选择同目录或搜索路径里的 mmproj 文件（可选）',
        'basic.run': '运行',
        'deploy.info': '优先使用程序目录中的 .wsl 镜像；没有镜像时下载 Ubuntu 官方 .wsl 后本地导入，部署完成后自动写入启动配置',
        'deploy.config_group': '部署配置',
        'deploy.progress': '部署进度',
        'deploy.lock': '锁定',
        'deploy.unlock': '双击解锁',
        'deploy.start': '开始部署',
        'deploy.stop': '停止',
        'deploy.clear': '清空',
        'deploy.username_title': 'WSL 用户名',
        'deploy.username_content': '不存在时会自动创建；已存在时会复用该用户',
        'deploy.password_title': 'WSL 密码',
        'deploy.password_content': '用于新用户创建和 sudo 提权，只在本次部署进程中传递，默认为1234',
        'deploy.install_title': '安装目录',
        'deploy.install_content': 'WSL Ubuntu-24.04 的安装位置（需有足够磁盘空间，建议30G+）',
        'deploy.model_preset_title': '下载预设模型',
        'deploy.model_preset_content': '选择一键部署要下载的默认模型；下载源按 HuggingFace、ModelScope 顺序自动回退',
        'model.param_group': '基本参数',
        'model.kv_group': 'KV 缓存',
        'model.mm_group': '多模态参数',
        'model.advanced_group': '高级设置(谨慎调整)',
        'model.ctx_title': '上下文长度',
        'model.ctx_content': '提示词上下文窗口大小，值越大能处理越长的对话（默认256k）',
        'model.predict_title': '最大生成长度',
        'model.predict_content': '单次最多生成的 token 数，-1 为无限制（默认 12800）',
        'model.temp_title': '温度',
        'model.temp_content': '控制输出随机性，越高越随机/有创意，越低越确定/保守（默认 1.0）',
        'model.top_p_title': 'Top-P',
        'model.top_p_content': '核采样，只从累计概率达到 P 的最小 token 集合中采样（默认 0.95）',
        'model.top_k_title': 'Top-K',
        'model.top_k_content': '只从概率最高的 K 个 token 中采样（默认 64）',
        'model.cache_k_title': 'K 缓存精度',
        'model.cache_k_content': '低精度省显存但可能影响质量（默认 turbo3，即启用 turboQuant 低损失压缩）',
        'model.cache_v_title': 'V 缓存精度',
        'model.cache_v_content': '低精度省显存但可能影响质量（默认 turbo3，即启用 turboQuant 低损失压缩）',
        'model.cache_ram_title': 'KV 缓存大小',
        'model.cache_ram_content': 'KV 缓存的内存上限，留空为自动（单位 MB）',
        'model.flash_title': 'Flash Attention 2',
        'model.flash_content': '加速推理并降低显存占用（默认 Auto）',
        'model.image_min_title': '图像最小 Token 数',
        'model.image_min_content': '动态分辨率模型中每张图像的最小 Token 数（默认 1024）',
        'model.repeat_penalty_title': '重复惩罚',
        'model.repeat_penalty_content': '对已出现的 token 施加惩罚以减少重复，1.0 为不惩罚（默认 1.1）',
        'model.repeat_last_n_title': '惩罚回溯窗口',
        'model.repeat_last_n_content': '重复惩罚回溯的 token 数量（默认 64）',
        'model.ngl_title': 'GPU 层数',
        'model.ngl_content': '将模型的前 N 层卸载到 GPU，设为 999 可将整个模型放入 GPU（默认 999）',
        'model.main_gpu_title': '主 GPU',
        'model.main_gpu_content': '多 GPU 时指定主 GPU 的设备 ID（默认 0）',
        'model.tensor_split_title': '张量分割比例',
        'model.tensor_split_content': '多 GPU 时各 GPU 负载比例，如 3,7 表示 30%/70%（留空为均分）',
        'model.nommap_title': '禁用内存映射',
        'model.nommap_content': '不使用 mmap 加载模型，改为直接读入内存（默认禁用 mmap）',
        'model.numa_title': 'NUMA 优化',
        'model.numa_content': '多路 CPU 服务器性能优化策略（默认关闭）',
        'server.net_group': '网络配置',
        'server.perf_group': '性能配置',
        'server.toggle_group': '功能开关',
        'server.host_title': '监听地址',
        'server.host_content': '服务器绑定的 IP 地址，0.0.0.0 可从局域网访问',
        'server.port_title': '端口',
        'server.port_content': '服务器监听的端口号（默认 8080）',
        'server.api_key_title': 'API 密钥',
        'server.api_key_content': '设置后客户端需携带此密钥进行身份验证（留空为无）',
        'server.threads_title': '线程数',
        'server.threads_content': 'CPU 推理使用的线程数，-1 为自动检测（默认 4）',
        'server.batch_title': '批处理大小',
        'server.batch_content': '提示词处理阶段的逻辑批大小，影响首次响应速度（默认 2048）',
        'server.ubatch_title': '微批处理大小',
        'server.ubatch_content': '更细粒度的批处理控制（默认 512）',
        'server.parallel_title': '并行序列数',
        'server.parallel_content': '服务器最大并发 slot 数量，-1 为自动（默认 -1）',
        'server.timeout_title': '超时时间',
        'server.timeout_content': '服务器超时，单位秒（默认 600）',
        'server.verbose_title': '详细输出',
        'server.verbose_content': '设置 llama-server 日志等级，默认 warn(2)，避免 --verbose 的性能问题',
        'server.metrics_title': '监控指标',
        'server.metrics_content': '启用 Prometheus 格式的性能监控端点',
        'server.webui_title': 'Web 界面',
        'server.webui_content': '内置的 Web 聊天界面',
        'log.launch': '启动',
        'log.stop': '停止',
        'log.clear': '清空',
    },
    'EN': {
        'nav.basic': 'Basics',
        'nav.deploy': 'Deploy',
        'nav.model': 'Model',
        'nav.server': 'Server',
        'nav.log': 'Logs',
        'nav.settings': 'Settings',
        'window.title': 'llama.cpp Launcher',
        'settings.title': 'Launcher Settings',
        'settings.launcher_group': 'Launcher Preferences',
        'settings.language_title': 'Language',
        'settings.language_content': 'Switch launcher navigation and settings language',
        'settings.theme_title': 'UI Theme',
        'settings.theme_content': 'Use dark, light, or system theme',
        'settings.font_title': 'Font Size',
        'settings.font_content': 'Scale titles, section titles, descriptions, and logs (80%-130%)',
        'settings.reset_group': 'Reset',
        'settings.reset_params_title': 'Reset Runtime Parameters',
        'settings.reset_params_content': 'Reset model, server, and path parameters without changing launcher preferences',
        'settings.reset_params_button': 'Reset Parameters',
        'settings.reset_launcher_title': 'Reset Launcher Settings',
        'settings.reset_launcher_content': 'Reset language, theme, and font size',
        'settings.reset_launcher_button': 'Reset Launcher',
        'basic.preview': 'Command Preview',
        'basic.path_group': 'Paths',
        'basic.model_group': 'Models',
        'basic.exec_title': 'Executable Path',
        'basic.exec_content': 'Path to the llama-server executable inside WSL. Supports the {user} placeholder.',
        'basic.search_title': 'Model Search Paths',
        'basic.search_content': 'Separate multiple WSL directories with semicolons. Supports the {user} placeholder.',
        'basic.refresh_title': 'Refresh Local Models',
        'basic.refresh_content': 'Scan search paths for .gguf files and update model dropdowns.',
        'basic.refresh_button': 'Refresh Models',
        'basic.llm_title': 'Language Model',
        'basic.llm_content': 'Select the GGUF model file to load.',
        'basic.mm_title': 'Multimodal Model',
        'basic.mm_content': 'Optional mmproj file from the same directory or search paths.',
        'basic.run': 'Run',
        'deploy.info': 'Uses a .wsl image from the program folder first. If none exists, downloads the official Ubuntu .wsl image and imports it locally. Startup settings are updated after deployment.',
        'deploy.config_group': 'Deploy Configuration',
        'deploy.progress': 'Deploy Progress',
        'deploy.lock': 'Lock',
        'deploy.unlock': 'Double-click Unlock',
        'deploy.start': 'Start Deploy',
        'deploy.stop': 'Stop',
        'deploy.clear': 'Clear',
        'deploy.username_title': 'WSL User',
        'deploy.username_content': 'Creates this user if missing; reuses it if it already exists.',
        'deploy.password_title': 'WSL Password',
        'deploy.password_content': 'Used for user creation and sudo. Passed only to this deployment process. Default: 1234.',
        'deploy.install_title': 'Install Directory',
        'deploy.install_content': 'Install location for WSL Ubuntu-24.04. Requires enough disk space; 30GB+ recommended.',
        'deploy.model_preset_title': 'Model Preset',
        'deploy.model_preset_content': 'Default model downloaded by one-click deploy. Sources fall back from HuggingFace to ModelScope.',
        'model.param_group': 'Model Basics',
        'model.kv_group': 'KV Cache',
        'model.mm_group': 'Multimodal',
        'model.advanced_group': 'Advanced Settings',
        'model.ctx_title': 'Context Window',
        'model.ctx_content': 'Prompt context window. Larger values allow longer conversations (default 256k).',
        'model.predict_title': 'max_output_tokens',
        'model.predict_content': 'Maximum tokens generated per response. Use -1 for no limit (default 12800).',
        'model.temp_title': 'Temperature',
        'model.temp_content': 'Controls randomness. Higher is more creative, lower is more deterministic (default 1.0).',
        'model.top_p_title': 'Top-P',
        'model.top_p_content': 'Nucleus sampling. Samples from the smallest token set whose cumulative probability reaches P (default 0.95).',
        'model.top_k_title': 'Top-K',
        'model.top_k_content': 'Samples only from the K most likely tokens (default 64).',
        'model.cache_k_title': 'K Cache Precision',
        'model.cache_k_content': 'Lower precision saves VRAM but can affect quality (default turbo3, turboQuant compression).',
        'model.cache_v_title': 'V Cache Precision',
        'model.cache_v_content': 'Lower precision saves VRAM but can affect quality (default turbo3, turboQuant compression).',
        'model.cache_ram_title': 'KV Cache Size',
        'model.cache_ram_content': 'RAM limit for KV cache. Leave empty for auto (MB).',
        'model.flash_title': 'Flash Attention 2',
        'model.flash_content': 'Speeds up inference and reduces VRAM usage (default Auto).',
        'model.image_min_title': 'Image Min Tokens',
        'model.image_min_content': 'Minimum tokens per image for dynamic-resolution models (default 1024).',
        'model.repeat_penalty_title': 'Repeat Penalty',
        'model.repeat_penalty_content': 'Penalizes repeated tokens. 1.0 disables the penalty (default 1.1).',
        'model.repeat_last_n_title': 'Penalty Lookback',
        'model.repeat_last_n_content': 'Number of previous tokens used for repeat penalty lookback (default 64).',
        'model.ngl_title': 'GPU Layers',
        'model.ngl_content': 'Offload the first N model layers to GPU. Use 999 to offload the whole model (default 999).',
        'model.main_gpu_title': 'Main GPU',
        'model.main_gpu_content': 'Main GPU device ID for multi-GPU systems (default 0).',
        'model.tensor_split_title': 'Tensor Split',
        'model.tensor_split_content': 'Per-GPU load ratio, e.g. 3,7 means 30%/70%. Leave empty for even split.',
        'model.nommap_title': 'Disable mmap',
        'model.nommap_content': 'Load the model into memory instead of using mmap (mmap disabled by default).',
        'model.numa_title': 'NUMA',
        'model.numa_content': 'CPU NUMA optimization strategy for multi-socket systems (default off).',
        'server.net_group': 'Network',
        'server.perf_group': 'Performance',
        'server.toggle_group': 'Feature Toggles',
        'server.host_title': 'Host',
        'server.host_content': 'IP address to bind. 0.0.0.0 allows LAN access.',
        'server.port_title': 'Port',
        'server.port_content': 'Server listening port (default 8080).',
        'server.api_key_title': 'API Key',
        'server.api_key_content': 'Require clients to provide this key. Leave empty to disable.',
        'server.threads_title': 'Threads',
        'server.threads_content': 'CPU inference threads. -1 auto-detects (default 4).',
        'server.batch_title': 'Batch Size',
        'server.batch_content': 'Logical batch size for prompt processing. Affects time to first token (default 2048).',
        'server.ubatch_title': 'Microbatch Size',
        'server.ubatch_content': 'Fine-grained batch control (default 512).',
        'server.parallel_title': 'Parallel Slots',
        'server.parallel_content': 'Maximum concurrent server slots. -1 means auto (default -1).',
        'server.timeout_title': 'Timeout',
        'server.timeout_content': 'Server timeout in seconds (default 600).',
        'server.verbose_title': 'Log Level',
        'server.verbose_content': 'Set llama-server log level. Default: warn(2), avoiding --verbose overhead.',
        'server.metrics_title': 'Metrics',
        'server.metrics_content': 'Enable Prometheus-style performance metrics.',
        'server.webui_title': 'Web UI',
        'server.webui_content': 'Built-in web chat interface.',
        'log.launch': 'Launch',
        'log.stop': 'Stop',
        'log.clear': 'Clear',
    },
}

# PyInstaller 打包后 __file__ 指向临时目录，需要用 sys.executable 定位 exe 所在目录
BASE_DIR = _launcher_base_dir()
CORE_DIR = os.path.join(BASE_DIR, 'core')
CONFIG_DIR = _runtime_dir(BASE_DIR)
for _core_dir in _candidate_core_dirs(BASE_DIR):
    if _core_dir not in sys.path:
        sys.path.insert(0, _core_dir)

try:
    from model_presets import DEFAULT_MODEL_PRESET_KEY, MODEL_PRESETS
except Exception:
    DEFAULT_MODEL_PRESET_KEY = 'qwen3.5-27b'
    MODEL_PRESETS = {
        DEFAULT_MODEL_PRESET_KEY: {'display_name': 'Qwen3.5-27B UD-Q4_K_XL'},
    }


def getAppIcon():
    candidates = []
    if getattr(sys, 'frozen', False) and os.path.exists(sys.executable):
        candidates.append(sys.executable)
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        candidates.append(os.path.join(meipass, 'icon.ico'))
    candidates.append(os.path.join(BASE_DIR, 'icon.ico'))
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        icon = QIcon(candidate)
        if not icon.isNull():
            return icon
    fallback = QIcon(':/qfluentwidgets/images/logo.png')
    if not fallback.isNull():
        return fallback
    return QIcon()


def setWindowsAppId():
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('llama.cpp.launcher')
    except Exception:
        pass


def loadModels():
    """从 config.json 加载模型映射；为空时由“刷新本地模型列表”扫描 WSL 实际文件。"""
    config_path = os.path.join(CONFIG_DIR, 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            models = cfg.get('models', {})
            llm_models = models.get('llm', {})
            mm_models = models.get('mm', {})
            if isinstance(llm_models, dict) and isinstance(mm_models, dict) and 'models' in cfg:
                return llm_models, mm_models
        except Exception:
            pass

    return {}, {}


def isAdmin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def decodeProcessOutput(raw):
    if not raw:
        return ''
    for enc in ('utf-8', 'utf-16-le', 'gb18030', 'cp936'):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode('utf-8', errors='replace')


class BaseSettingInterface(ScrollArea):
    """设置页面基类，统一处理滚动区域 + 标题 + ExpandLayout"""

    def __init__(self, title: str, object_name: str, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        self.titleLabel = QLabel(title, self)
        self.titleLabel.setObjectName('settingLabel')

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 80, 0, 0)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName(object_name)
        self.setStyleSheet('background: transparent; border: none;')
        self.viewport().setStyleSheet('background: transparent;')

        self.scrollWidget.setObjectName('scrollWidget')
        self.scrollWidget.setStyleSheet('background: transparent;')
        self.titleLabel.move(36, 30)
        self.titleLabel.setStyleSheet('font: 33px "Segoe UI", "Microsoft YaHei"; color: white; background: transparent;')

        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)


class BasicInterface(QFrame):
    """基础设置：程序路径 + 命令预览（自适应高度）"""

    def __init__(self, llm_models=None, mm_models=None, parent=None):
        super().__init__(parent=parent)
        self.llmPaths = llm_models or {}
        self.mmPaths = mm_models or {}
        self.setObjectName('basic-interface')
        self.setStyleSheet('background: transparent; border: none;')

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(36, 30, 36, 20)
        mainLayout.setSpacing(0)

        self.titleLabel = QLabel('基础设置', self)
        self.titleLabel.setStyleSheet('font: 33px "Segoe UI", "Microsoft YaHei"; color: white; background: transparent;')
        mainLayout.addWidget(self.titleLabel)
        mainLayout.addSpacing(30)

        # ─────────── 路径配置 ───────────
        self.pathGroup = SettingCardGroup('路径配置', self)
        self.execPathCard = SettingCard(FIF.COMMAND_PROMPT, '程序路径', '设置 llama-server 在 WSL 中的可执行文件路径；支持 {user} 占位符', self.pathGroup)
        self.execPathEdit = LineEdit(self.execPathCard)
        self.execPathEdit.setPlaceholderText('~/llama-cpp-turboquant/build/bin/llama-server')
        self.execPathEdit.setText('~/llama-cpp-turboquant/build/bin/llama-server')
        self.execPathEdit.setFixedWidth(300)
        self.execPathCard.hBoxLayout.addWidget(self.execPathEdit, 0, Qt.AlignRight)
        self.execPathCard.hBoxLayout.addSpacing(16)
        self.pathGroup.addSettingCard(self.execPathCard)

        self.modelSearchPathCard = SettingCard(
            FIF.FOLDER,
            '模型搜索路径',
            '用分号分隔多个 WSL 目录；支持 {user} 占位符',
            self.pathGroup
        )
        self.modelSearchPathEdit = LineEdit(self.modelSearchPathCard)
        self.modelSearchPathEdit.setText('; '.join(DEFAULT_MODEL_SEARCH_PATHS))
        self.modelSearchPathEdit.setFixedWidth(520)
        self.modelSearchPathCard.hBoxLayout.addWidget(self.modelSearchPathEdit, 0, Qt.AlignRight)
        self.modelSearchPathCard.hBoxLayout.addSpacing(16)
        self.pathGroup.addSettingCard(self.modelSearchPathCard)

        self.refreshModelsCard = SettingCard(
            FIF.SYNC,
            '刷新本地模型',
            '扫描搜索路径中的 .gguf 文件并更新模型下拉列表',
            self.pathGroup
        )
        self.refreshModelsBtn = PushButton(FIF.SYNC, '刷新本地模型列表', self.refreshModelsCard)
        self.refreshModelsBtn.setFixedWidth(180)
        self.refreshModelsCard.hBoxLayout.addWidget(self.refreshModelsBtn, 0, Qt.AlignRight)
        self.refreshModelsCard.hBoxLayout.addSpacing(16)
        self.pathGroup.addSettingCard(self.refreshModelsCard)

        self.modelGroup = SettingCardGroup('模型选择', self)

        self.llmCard = SettingCard(FIF.IOT, '大语言模型', '选择要加载的 GGUF 模型文件', self.modelGroup)
        self.llmCombo = FixedComboBox(self.llmCard)
        self.llmCombo.addItems(list(self.llmPaths.keys()))
        self.llmCombo.setFixedWidth(300)
        self.llmCard.hBoxLayout.addWidget(self.llmCombo, 0, Qt.AlignRight)
        self.llmCard.hBoxLayout.addSpacing(16)

        self.mmCard = SettingCard(FIF.PHOTO, '多模态模型', '选择同目录或搜索路径里的 mmproj 文件（可选）', self.modelGroup)
        self.mmCombo = FixedComboBox(self.mmCard)
        self.mmCombo.addItems(['无'] + list(self.mmPaths.keys()))
        self.mmCombo.setFixedWidth(300)
        self.mmCard.hBoxLayout.addWidget(self.mmCombo, 0, Qt.AlignRight)
        self.mmCard.hBoxLayout.addSpacing(16)

        self.modelGroup.addSettingCard(self.llmCard)
        self.modelGroup.addSettingCard(self.mmCard)

        mainLayout.addWidget(self.pathGroup)
        mainLayout.addSpacing(16)
        mainLayout.addWidget(self.modelGroup)
        mainLayout.addSpacing(28)

        # ─────────── 命令预览 ───────────
        self.previewLabel = QLabel('命令预览', self)
        self.previewLabel.setStyleSheet('font: 20px "Segoe UI", "Microsoft YaHei"; color: white; background: transparent;')
        mainLayout.addWidget(self.previewLabel)
        mainLayout.addSpacing(12)

        self.cmdPreview = QTextEdit(self)
        self.cmdPreview.setReadOnly(True)
        self.cmdPreview.setStyleSheet('background: rgba(255,255,255,0.04); border: none; border-radius: 8px; color: rgba(255,255,255,0.8); font: 13px "Consolas", "Microsoft YaHei"; padding: 12px 16px;')
        mainLayout.addWidget(self.cmdPreview, 1)
        mainLayout.addSpacing(12)

        # ─────────── 底部运行按钮 ───────────
        self.runBtn = PrimaryPushButton(FIF.PLAY, '运行', self)
        self.runBtn.setFixedHeight(40)
        mainLayout.addWidget(self.runBtn)


class ModelInterface(BaseSettingInterface):
    """模型设置"""

    def __init__(self, parent=None):
        super().__init__('模型设置', 'model-interface', parent)

        # ─────────── 模型参数 ───────────
        self.paramGroup = SettingCardGroup('基本参数', self.scrollWidget)

        # 上下文长度 (-c)
        self.ctxCard = SettingCard(FIF.SCROLL, '上下文长度', '提示词上下文窗口大小，值越大能处理越长的对话（默认256k）', self.paramGroup)
        self.ctxEdit = LineEdit(self.ctxCard)
        self.ctxEdit.setText('256')
        self.ctxEdit.setFixedWidth(100)
        from PySide6.QtGui import QIntValidator
        self.ctxEdit.setValidator(QIntValidator(1, 999999, self.ctxEdit))
        self.ctxSuffix = QLabel('K', self.ctxCard)
        self.ctxSuffix.setStyleSheet('font: 14px; background: transparent;')
        self.ctxCard.hBoxLayout.addWidget(self.ctxEdit, 0, Qt.AlignRight)
        self.ctxCard.hBoxLayout.addSpacing(8)
        self.ctxCard.hBoxLayout.addWidget(self.ctxSuffix)
        self.ctxCard.hBoxLayout.addSpacing(16)

        # 最大生成长度 (-n)
        self.predictCard = SettingCard(FIF.EDIT, '最大生成长度', '单次最多生成的 token 数，-1 为无限制（默认 12800）', self.paramGroup)
        self.predictEdit = LineEdit(self.predictCard)
        self.predictEdit.setText('12800')
        self.predictEdit.setFixedWidth(CTRL_WIDTH)
        from PySide6.QtGui import QIntValidator
        self.predictEdit.setValidator(QIntValidator(-1, 999999, self.predictEdit))
        self.predictCard.hBoxLayout.addWidget(self.predictEdit, 0, Qt.AlignRight)
        self.predictCard.hBoxLayout.addSpacing(16)

        # 温度 (--temp)
        self.tempCard = SettingCard(FIF.CALORIES, '温度', '控制输出随机性，越高越随机/有创意，越低越确定/保守（默认 1.0）', self.paramGroup)
        self.tempSpin = DoubleSpinBox(self.tempCard)
        self.tempSpin.setRange(0.0, 2.0)
        self.tempSpin.setValue(0.7)
        self.tempSpin.setSingleStep(0.1)
        self.tempSpin.setDecimals(2)
        self.tempSpin.setFixedWidth(CTRL_WIDTH)
        self.tempCard.hBoxLayout.addWidget(self.tempSpin, 0, Qt.AlignRight)
        self.tempCard.hBoxLayout.addSpacing(16)

        # Top-P (--top-p)
        self.topPCard = SettingCard(FIF.MARKET, 'Top-P', '核采样，只从累计概率达到 P 的最小 token 集合中采样（默认 0.95）', self.paramGroup)
        self.topPSpin = DoubleSpinBox(self.topPCard)
        self.topPSpin.setRange(0.0, 1.0)
        self.topPSpin.setValue(0.9)
        self.topPSpin.setSingleStep(0.05)
        self.topPSpin.setDecimals(2)
        self.topPSpin.setFixedWidth(CTRL_WIDTH)
        self.topPCard.hBoxLayout.addWidget(self.topPSpin, 0, Qt.AlignRight)
        self.topPCard.hBoxLayout.addSpacing(16)

        # Top-K (--top-k)
        self.topKCard = SettingCard(FIF.FILTER, 'Top-K', '只从概率最高的 K 个 token 中采样（默认 64）', self.paramGroup)
        self.topKSpin = SpinBox(self.topKCard)
        self.topKSpin.setRange(0, 200)
        self.topKSpin.setValue(40)
        self.topKSpin.setFixedWidth(CTRL_WIDTH)
        self.topKCard.hBoxLayout.addWidget(self.topKSpin, 0, Qt.AlignRight)
        self.topKCard.hBoxLayout.addSpacing(16)

        self.paramGroup.addSettingCard(self.ctxCard)
        self.paramGroup.addSettingCard(self.predictCard)
        self.paramGroup.addSettingCard(self.tempCard)
        self.paramGroup.addSettingCard(self.topPCard)
        self.paramGroup.addSettingCard(self.topKCard)
        self.expandLayout.addWidget(self.paramGroup)

        # ─────────── KV 缓存 ───────────
        self.kvGroup = SettingCardGroup('KV 缓存', self.scrollWidget)

        # K 缓存精度 (--cache-type-k)
        self.cacheKCard = SettingCard(FIF.SPEED_OFF, 'K 缓存精度', '低精度省显存但可能影响质量（默认 turbo3,即启用turboQuant低损失压缩)', self.kvGroup)
        self.cacheKCombo = FixedComboBox(self.cacheKCard)
        self.cacheKCombo.addItems(['fp16', 'bf16', 'q8_0', 'q4_0',  'q5_0', 'turbo2', 'turbo3', 'turbo4'])
        self.cacheKCombo.setCurrentText('turbo3')
        self.cacheKCombo.setFixedWidth(CTRL_WIDTH)
        self.cacheKCard.hBoxLayout.addWidget(self.cacheKCombo, 0, Qt.AlignRight)
        self.cacheKCard.hBoxLayout.addSpacing(16)

        # V 缓存精度 (--cache-type-v)
        self.cacheVCard = SettingCard(FIF.SPEED_HIGH, 'V 缓存精度', '低精度省显存但可能影响质量（默认 turbo3）即启用turboQuant低损失压缩)', self.kvGroup)
        self.cacheVCombo = FixedComboBox(self.cacheVCard)
        self.cacheVCombo.addItems(['fp16', 'bf16', 'q8_0', 'q4_0',  'q5_0', 'turbo2', 'turbo3', 'turbo4'])
        self.cacheVCombo.setCurrentText('turbo3')
        self.cacheVCombo.setFixedWidth(CTRL_WIDTH)
        self.cacheVCard.hBoxLayout.addWidget(self.cacheVCombo, 0, Qt.AlignRight)
        self.cacheVCard.hBoxLayout.addSpacing(16)

        # KV 缓存大小 (--cache-ram)
        self.cacheRamCard = SettingCard(FIF.SAVE, 'KV 缓存大小', 'KV 缓存的内存上限，留空为自动（单位 MB）', self.kvGroup)
        self.cacheRamEdit = LineEdit(self.cacheRamCard)
        self.cacheRamEdit.setPlaceholderText('auto')
        self.cacheRamEdit.setFixedWidth(100)
        self.cacheRamSuffix = QLabel('MB', self.cacheRamCard)
        self.cacheRamSuffix.setStyleSheet('font: 14px; background: transparent;')
        self.cacheRamCard.hBoxLayout.addWidget(self.cacheRamEdit, 0, Qt.AlignRight)
        self.cacheRamCard.hBoxLayout.addSpacing(8)
        self.cacheRamCard.hBoxLayout.addWidget(self.cacheRamSuffix)
        self.cacheRamCard.hBoxLayout.addSpacing(16)

        # Flash Attention (--flash-attn)
        self.faCard = SettingCard(FIF.SPEED_MEDIUM, 'Flash Attention 2', '加速推理并降低显存占用（默认 Auto）', self.kvGroup)
        self.faCombo = FixedComboBox(self.faCard)
        self.faCombo.addItems(['auto', 'on', 'off'])
        self.faCombo.setCurrentText('auto')
        self.faCombo.setFixedWidth(CTRL_WIDTH)
        self.faCard.hBoxLayout.addWidget(self.faCombo, 0, Qt.AlignRight)
        self.faCard.hBoxLayout.addSpacing(16)

        self.kvGroup.addSettingCard(self.cacheKCard)
        self.kvGroup.addSettingCard(self.cacheVCard)
        self.kvGroup.addSettingCard(self.cacheRamCard)
        self.kvGroup.addSettingCard(self.faCard)
        self.expandLayout.addWidget(self.kvGroup)

        # ─────────── 多模态参数 ───────────
        self.mmParamGroup = SettingCardGroup('多模态参数', self.scrollWidget)

        # 图像最小 Token 数 (--image-min-tokens)
        self.imgMinCard = SettingCard(FIF.PHOTO, '图像最小 Token 数', '动态分辨率模型中每张图像的最小 Token 数（默认 1024）', self.mmParamGroup)
        self.imgMinEdit = LineEdit(self.imgMinCard)
        self.imgMinEdit.setPlaceholderText('1024')
        self.imgMinEdit.setText('1024')
        self.imgMinEdit.setFixedWidth(CTRL_WIDTH)
        self.imgMinCard.hBoxLayout.addWidget(self.imgMinEdit, 0, Qt.AlignRight)
        self.imgMinCard.hBoxLayout.addSpacing(16)

        self.mmParamGroup.addSettingCard(self.imgMinCard)
        self.expandLayout.addWidget(self.mmParamGroup)

        # ─────────── GPU 加速 高级设置───────────
        self.gpuGroup = SettingCardGroup('高级设置(谨慎调整)', self.scrollWidget)
        # 重复惩罚 (--repeat-penalty)
        self.repeatPenaltyCard = SettingCard(FIF.REMOVE, '重复惩罚', '对已出现的 token 施加惩罚以减少重复，1.0 为不惩罚（默认 1.1）', self.gpuGroup)
        self.repeatPenaltySpin = DoubleSpinBox(self.repeatPenaltyCard)
        self.repeatPenaltySpin.setRange(0.0, 2.0)
        self.repeatPenaltySpin.setValue(1.1)
        self.repeatPenaltySpin.setSingleStep(0.1)
        self.repeatPenaltySpin.setDecimals(2)
        self.repeatPenaltySpin.setFixedWidth(CTRL_WIDTH)
        self.repeatPenaltyCard.hBoxLayout.addWidget(self.repeatPenaltySpin, 0, Qt.AlignRight)
        self.repeatPenaltyCard.hBoxLayout.addSpacing(16)

        # 惩罚回溯窗口 (--repeat-last-n)
        self.repeatLastNCard = SettingCard(FIF.HISTORY, '惩罚回溯窗口', '重复惩罚回溯的 token 数量（默认 64）', self.gpuGroup)
        self.repeatLastNSpin = SpinBox(self.repeatLastNCard)
        self.repeatLastNSpin.setRange(0, 4096)
        self.repeatLastNSpin.setValue(64)
        self.repeatLastNSpin.setFixedWidth(CTRL_WIDTH)
        self.repeatLastNCard.hBoxLayout.addWidget(self.repeatLastNSpin, 0, Qt.AlignRight)
        self.repeatLastNCard.hBoxLayout.addSpacing(16)

        # GPU 层数 (-ngl)
        self.nglCard = SettingCard(FIF.SPEED_HIGH, 'GPU 层数', '将模型的前 N 层卸载到 GPU，设为 999 可将整个模型放入 GPU（默认 999）', self.gpuGroup)
        self.nglSpin = SpinBox(self.nglCard)
        self.nglSpin.setRange(0, 999)
        self.nglSpin.setValue(999)
        self.nglSpin.setFixedWidth(CTRL_WIDTH)
        self.nglCard.hBoxLayout.addWidget(self.nglSpin, 0, Qt.AlignRight)
        self.nglCard.hBoxLayout.addSpacing(16)

        # 主 GPU (-mg)
        self.mainGpuCard = SettingCard(FIF.DEVELOPER_TOOLS, '主 GPU', '多 GPU 时指定主 GPU 的设备 ID（默认 0）', self.gpuGroup)
        self.mainGpuSpin = SpinBox(self.mainGpuCard)
        self.mainGpuSpin.setRange(0, 15)
        self.mainGpuSpin.setValue(0)
        self.mainGpuSpin.setFixedWidth(CTRL_WIDTH)
        self.mainGpuCard.hBoxLayout.addWidget(self.mainGpuSpin, 0, Qt.AlignRight)
        self.mainGpuCard.hBoxLayout.addSpacing(16)

        # 张量分割比例 (-ts)
        self.tsSplitCard = SettingCard(FIF.SYNC, '张量分割比例', '多 GPU 时各 GPU 负载比例，如 3,7 表示 30%/70%（留空为均分）', self.gpuGroup)
        self.tsSplitEdit = LineEdit(self.tsSplitCard)
        self.tsSplitEdit.setPlaceholderText('均分')
        self.tsSplitEdit.setFixedWidth(CTRL_WIDTH)
        self.tsSplitCard.hBoxLayout.addWidget(self.tsSplitEdit, 0, Qt.AlignRight)
        self.tsSplitCard.hBoxLayout.addSpacing(16)

        # 禁用内存映射 (--no-mmap)
        self.nommapCard = SettingCard(FIF.REMOVE, '禁用内存映射', '不使用 mmap 加载模型，改为直接读入内存（默认禁用 mmap）', self.gpuGroup)
        self.nommapCombo = FixedComboBox(self.nommapCard)
        self.nommapCombo.addItems(['no-mmap', 'enable-mmap'])
        self.nommapCombo.setCurrentText('no-mmap')
        self.nommapCombo.setFixedWidth(CTRL_WIDTH)
        self.nommapCard.hBoxLayout.addWidget(self.nommapCombo, 0, Qt.AlignRight)
        self.nommapCard.hBoxLayout.addSpacing(16)

        # NUMA 优化 (--numa)
        self.numaCard = SettingCard(FIF.CONNECT, 'NUMA 优化', '多路 CPU 服务器性能优化策略（默认关闭）', self.gpuGroup)
        self.numaCombo = FixedComboBox(self.numaCard)
        self.numaCombo.addItems(['关闭', 'distribute', 'isolate', 'numactl'])
        self.numaCombo.setFixedWidth(CTRL_WIDTH)
        self.numaCard.hBoxLayout.addWidget(self.numaCombo, 0, Qt.AlignRight)
        self.numaCard.hBoxLayout.addSpacing(16)

        self.gpuGroup.addSettingCard(self.nglCard)
        self.gpuGroup.addSettingCard(self.mainGpuCard)
        self.gpuGroup.addSettingCard(self.tsSplitCard)
        self.gpuGroup.addSettingCard(self.nommapCard)
        self.gpuGroup.addSettingCard(self.numaCard)
        self.gpuGroup.addSettingCard(self.repeatPenaltyCard)
        self.gpuGroup.addSettingCard(self.repeatLastNCard)
        self.expandLayout.addWidget(self.gpuGroup)


class ServerInterface(BaseSettingInterface):
    """服务器设置"""

    def __init__(self, parent=None):
        super().__init__('服务器设置', 'server-interface', parent)

        # ─────────── 网络配置 ───────────
        self.netGroup = SettingCardGroup('网络配置', self.scrollWidget)

        # 监听地址 (--host)
        self.hostCard = SettingCard(FIF.GLOBE, '监听地址', '服务器绑定的 IP 地址，0.0.0.0 可从局域网访问', self.netGroup)
        self.hostEdit = LineEdit(self.hostCard)
        self.hostEdit.setText('0.0.0.0')
        self.hostEdit.setFixedWidth(CTRL_WIDTH)
        self.hostCard.hBoxLayout.addWidget(self.hostEdit, 0, Qt.AlignRight)
        self.hostCard.hBoxLayout.addSpacing(16)

        # 端口 (--port)
        self.portCard = SettingCard(FIF.CONNECT, '端口', '服务器监听的端口号（默认 8080）', self.netGroup)
        self.portSpin = SpinBox(self.portCard)
        self.portSpin.setRange(1, 65535)
        self.portSpin.setValue(8080)
        self.portSpin.setFixedWidth(CTRL_WIDTH)
        self.portCard.hBoxLayout.addWidget(self.portSpin, 0, Qt.AlignRight)
        self.portCard.hBoxLayout.addSpacing(16)

        # API 密钥 (--api-key)
        self.apiKeyCard = SettingCard(FIF.VPN, 'API 密钥', '设置后客户端需携带此密钥进行身份验证（留空为无）', self.netGroup)
        self.apiKeyEdit = LineEdit(self.apiKeyCard)
        self.apiKeyEdit.setPlaceholderText('留空则不启用')
        self.apiKeyEdit.setFixedWidth(CTRL_WIDTH)
        self.apiKeyCard.hBoxLayout.addWidget(self.apiKeyEdit, 0, Qt.AlignRight)
        self.apiKeyCard.hBoxLayout.addSpacing(16)

        self.netGroup.addSettingCard(self.hostCard)
        self.netGroup.addSettingCard(self.portCard)
        self.netGroup.addSettingCard(self.apiKeyCard)
        self.expandLayout.addWidget(self.netGroup)

        # ─────────── 性能配置 ───────────
        self.perfGroup = SettingCardGroup('性能配置', self.scrollWidget)

        # 线程数 (--threads)
        self.threadsCard = SettingCard(FIF.SPEED_HIGH, '线程数', 'CPU 推理使用的线程数，-1 为自动检测（默认 4）', self.perfGroup)
        self.threadsSpin = SpinBox(self.threadsCard)
        self.threadsSpin.setRange(-1, 256)
        self.threadsSpin.setValue(4)
        self.threadsSpin.setFixedWidth(CTRL_WIDTH)
        self.threadsCard.hBoxLayout.addWidget(self.threadsSpin, 0, Qt.AlignRight)
        self.threadsCard.hBoxLayout.addSpacing(16)

        # 批处理大小 (--batch-size)
        self.batchCard = SettingCard(FIF.SPEED_MEDIUM, '批处理大小', '提示词处理阶段的逻辑批大小，影响首次响应速度（默认 2048）', self.perfGroup)
        self.batchSpin = SpinBox(self.batchCard)
        self.batchSpin.setRange(1, 8192)
        self.batchSpin.setValue(2048)
        self.batchSpin.setFixedWidth(CTRL_WIDTH)
        self.batchCard.hBoxLayout.addWidget(self.batchSpin, 0, Qt.AlignRight)
        self.batchCard.hBoxLayout.addSpacing(16)

        # 微批处理大小 (--ubatch-size)
        self.ubatchCard = SettingCard(FIF.SPEED_OFF, '微批处理大小', '更细粒度的批处理控制（默认 512）', self.perfGroup)
        self.ubatchSpin = SpinBox(self.ubatchCard)
        self.ubatchSpin.setRange(1, 8192)
        self.ubatchSpin.setValue(512)
        self.ubatchSpin.setFixedWidth(CTRL_WIDTH)
        self.ubatchCard.hBoxLayout.addWidget(self.ubatchSpin, 0, Qt.AlignRight)
        self.ubatchCard.hBoxLayout.addSpacing(16)

        # 并行序列数 (--parallel)
        self.parallelCard = SettingCard(FIF.SYNC, '并行序列数', '服务器最大并发 slot 数量，-1 为自动（默认 -1）', self.perfGroup)
        self.parallelSpin = SpinBox(self.parallelCard)
        self.parallelSpin.setRange(-1, 128)
        self.parallelSpin.setValue(-1)
        self.parallelSpin.setFixedWidth(CTRL_WIDTH)
        self.parallelCard.hBoxLayout.addWidget(self.parallelSpin, 0, Qt.AlignRight)
        self.parallelCard.hBoxLayout.addSpacing(16)

        # 超时时间 (--timeout)
        self.timeoutCard = SettingCard(FIF.HISTORY, '超时时间', '服务器超时，单位秒（默认 600）', self.perfGroup)
        self.timeoutSpin = SpinBox(self.timeoutCard)
        self.timeoutSpin.setRange(0, 99999)
        self.timeoutSpin.setValue(600)
        self.timeoutSpin.setFixedWidth(CTRL_WIDTH)
        self.timeoutCard.hBoxLayout.addWidget(self.timeoutSpin, 0, Qt.AlignRight)
        self.timeoutCard.hBoxLayout.addSpacing(16)

        self.perfGroup.addSettingCard(self.threadsCard)
        self.perfGroup.addSettingCard(self.batchCard)
        self.perfGroup.addSettingCard(self.ubatchCard)
        self.perfGroup.addSettingCard(self.parallelCard)
        self.perfGroup.addSettingCard(self.timeoutCard)
        self.expandLayout.addWidget(self.perfGroup)

        # ─────────── 功能开关 ───────────
        self.toggleGroup = SettingCardGroup('功能开关', self.scrollWidget)

        # 详细输出 (--log-verbosity)
        self.verboseCard = SettingCard(FIF.VIEW, '详细输出', '设置 llama-server 日志等级，默认 warn(2)，避免 --verbose 的性能问题', self.toggleGroup)
        self.verboseCombo = FixedComboBox(self.verboseCard)
        self.verboseCombo.addItems(['warn', 'info', 'debug'])
        self.verboseCombo.setCurrentText('warn')
        self.verboseCombo.setFixedWidth(CTRL_WIDTH)
        self.verboseCard.hBoxLayout.addWidget(self.verboseCombo, 0, Qt.AlignRight)
        self.verboseCard.hBoxLayout.addSpacing(16)

        # 监控指标 (--metrics)
        self.metricsCard = SettingCard(FIF.DEVELOPER_TOOLS, '监控指标', '启用 Prometheus 格式的性能监控端点', self.toggleGroup)
        self.metricsCombo = FixedComboBox(self.metricsCard)
        self.metricsCombo.addItems(['关闭', '启用'])
        self.metricsCombo.setFixedWidth(CTRL_WIDTH)
        self.metricsCard.hBoxLayout.addWidget(self.metricsCombo, 0, Qt.AlignRight)
        self.metricsCard.hBoxLayout.addSpacing(16)

        # 禁用 Web 界面 (--no-webui)
        self.webuiCard = SettingCard(FIF.GLOBE, 'Web 界面', '内置的 Web 聊天界面', self.toggleGroup)
        self.webuiCombo = FixedComboBox(self.webuiCard)
        self.webuiCombo.addItems(['启用', '禁用'])
        self.webuiCombo.setFixedWidth(CTRL_WIDTH)
        self.webuiCard.hBoxLayout.addWidget(self.webuiCombo, 0, Qt.AlignRight)
        self.webuiCard.hBoxLayout.addSpacing(16)

        self.toggleGroup.addSettingCard(self.verboseCard)
        self.toggleGroup.addSettingCard(self.metricsCard)
        self.toggleGroup.addSettingCard(self.webuiCard)
        self.expandLayout.addWidget(self.toggleGroup)


_ANSI_RE = re.compile(r'\x1b\[[\?>=]*[0-9;]*[a-zA-Z~@`]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\([A-Z]|\x1b[=>]')


class TerminalWorker(QThread):
    """后台线程：通过 subprocess 读取进程输出"""
    dataReady = Signal(str)
    processFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._command = ''
        self._env = None
        self._process = None
        self._cwd = None
        self._decoder = None
        self._decoder_name = None

    def start_process(self, command, env=None, cwd=None):
        self._command = command
        self._env = env
        self._cwd = cwd
        self._decoder = None
        self._decoder_name = None
        self.start()

    def _decodeOutput(self, raw):
        if not raw:
            return ''
        if self._decoder is None:
            if raw.startswith(b'\xff\xfe') or raw.count(b'\x00') > max(2, len(raw) // 8):
                self._decoder_name = 'utf-16-le'
            else:
                self._decoder_name = 'utf-8'
            self._decoder = codecs.getincrementaldecoder(self._decoder_name)(errors='strict')
        try:
            return self._decoder.decode(raw)
        except UnicodeDecodeError:
            self._decoder_name = 'gb18030'
            self._decoder = codecs.getincrementaldecoder(self._decoder_name)(errors='replace')
            return self._decoder.decode(raw)

    def run(self):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            env = None
            if self._env:
                env = os.environ.copy()
                env.update(self._env)
            self._process = subprocess.Popen(self._command, env=env, cwd=self._cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, startupinfo=si, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            pending = []
            pending_chars = 0
            last_emit = time.monotonic()

            def flush_pending():
                nonlocal pending, pending_chars, last_emit
                if pending:
                    self.dataReady.emit(''.join(pending))
                    pending = []
                    pending_chars = 0
                last_emit = time.monotonic()

            while True:
                raw = self._process.stdout.read1(16384)
                if not raw:
                    break
                text = self._decodeOutput(raw)
                if text:
                    pending.append(text)
                    pending_chars += len(text)
                    if pending_chars >= WORKER_EMIT_CHAR_LIMIT or time.monotonic() - last_emit >= WORKER_EMIT_INTERVAL_SEC:
                        flush_pending()
            if self._decoder is not None:
                tail = self._decoder.decode(b'', final=True)
                if tail:
                    pending.append(tail)
                    pending_chars += len(tail)
            flush_pending()
            self._process.wait()
            self.processFinished.emit(self._process.returncode)
        except Exception as e:
            self.dataReady.emit(f'\n--- 启动失败: {e} ---\n')
            self.processFinished.emit(-1)

    def write(self, data):
        if self._process and self._process.poll() is None and self._process.stdin:
            try:
                self._process.stdin.write(data.encode('utf-8'))
                self._process.stdin.flush()
            except Exception:
                pass

    def stop(self):
        if self._process and self._process.poll() is None:
            if sys.platform == 'win32':
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = subprocess.SW_HIDE
                    subprocess.run(
                        ['taskkill', '/PID', str(self._process.pid), '/T', '/F'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=si,
                        timeout=5,
                    )
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
            else:
                try:
                    self._process.terminate()
                except Exception:
                    pass
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    self._process.kill()
                except Exception:
                    pass


class TerminalTextEdit(QPlainTextEdit):
    """终端文本控件，拦截键盘输入并转发到 pty"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        font = QFont('Consolas', 11)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setMaximumBlockCount(TERMINAL_MAX_BLOCKS)
        self.setStyleSheet('QPlainTextEdit { background-color: #1e1e1e; color: #cccccc; border: 1px solid #333333; border-radius: 4px; padding: 8px; selection-background-color: #264f78; }')

    def keyPressEvent(self, event):
        if not self.worker:
            super().keyPressEvent(event)
            return
        key = event.key()
        modifiers = event.modifiers()
        if modifiers & Qt.ControlModifier:
            if key == Qt.Key_C and self.textCursor().hasSelection():
                self.copy()
                return
            if key == Qt.Key_A:
                self.selectAll()
                return
            code = key - Qt.Key_A + 1
            if 1 <= code <= 26:
                self.worker.write(chr(code))
            return
        key_map = {
            Qt.Key_Return: '\r', Qt.Key_Enter: '\r',
            Qt.Key_Backspace: '\x7f', Qt.Key_Tab: '\t', Qt.Key_Escape: '\x1b',
            Qt.Key_Up: '\x1b[A', Qt.Key_Down: '\x1b[B',
            Qt.Key_Right: '\x1b[C', Qt.Key_Left: '\x1b[D',
            Qt.Key_Home: '\x1b[H', Qt.Key_End: '\x1b[F',
            Qt.Key_Delete: '\x1b[3~', Qt.Key_Insert: '\x1b[2~',
            Qt.Key_PageUp: '\x1b[5~', Qt.Key_PageDown: '\x1b[6~',
        }
        if key in key_map:
            self.worker.write(key_map[key])
        elif event.text():
            self.worker.write(event.text())


class LogInterface(QWidget):
    """运行日志界面（嵌入终端模拟器）"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('log-interface')
        self.worker = None
        self._logBuffer = []
        self._logBufferChars = 0
        self._logTimer = QTimer(self)
        self._logTimer.setInterval(TERMINAL_FLUSH_INTERVAL_MS)
        self._logTimer.timeout.connect(self._flushLogBuffer)

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(36, 20, 36, 20)
        mainLayout.setSpacing(12)

        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(0, 0, 0, 0)
        self.titleLabel = QLabel('终端', self)
        self.titleLabel.setStyleSheet('font: 33px "Segoe UI", "Microsoft YaHei"; color: white; background: transparent;')
        titleLayout.addWidget(self.titleLabel)
        titleLayout.addStretch(1)
        self.gpuMemLabel = QLabel('Llama: --G | Total: --/--G', self)
        self.gpuMemLabel.setStyleSheet('font: 20px "Consolas", "Microsoft YaHei"; color: rgba(255,255,255,0.85); background: transparent;')
        titleLayout.addWidget(self.gpuMemLabel, 0, Qt.AlignVCenter | Qt.AlignRight)
        mainLayout.addLayout(titleLayout)

        self.logText = TerminalTextEdit(self)
        mainLayout.addWidget(self.logText, 1)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(12)
        self.launchBtn = PrimaryPushButton(FIF.PLAY, '启动', self)
        self.launchBtn.setFixedHeight(40)
        btnLayout.addWidget(self.launchBtn)
        self.stopBtn = PushButton(FIF.CLOSE, '停止', self)
        self.stopBtn.setFixedHeight(40)
        self.stopBtn.setEnabled(False)
        self.stopBtn.clicked.connect(self.stopProcess)
        btnLayout.addWidget(self.stopBtn)
        self.clearBtn = PushButton(FIF.DELETE, '清空', self)
        self.clearBtn.setFixedHeight(40)
        self.clearBtn.clicked.connect(lambda: self.logText.clear())
        btnLayout.addWidget(self.clearBtn)
        mainLayout.addLayout(btnLayout)
        self._gpuLaunchBaselineUsedG = None
        self.gpuMemTimer = QTimer(self)
        self.gpuMemTimer.setInterval(1000)
        self.gpuMemTimer.timeout.connect(self._updateGpuMemLabel)
        self.gpuMemTimer.start()
        self._updateGpuMemLabel()

    def _formatGpuValue(self, value):
        return f'{value:.1f}'.rstrip('0').rstrip('.')

    def _queryGpuMemory(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,
            startupinfo=startupinfo,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode != 0:
            return None
        total_used_mb = 0.0
        total_mem_mb = 0.0
        for line in result.stdout.splitlines():
            if ',' not in line:
                continue
            used_text, total_text = line.split(',', 1)
            try:
                total_used_mb += float(used_text.strip())
                total_mem_mb += float(total_text.strip())
            except ValueError:
                continue
        if total_mem_mb <= 0:
            return None
        used_g = total_used_mb / 1024.0
        total_g = total_mem_mb / 1024.0
        return used_g, total_g

    def _updateGpuMemLabel(self):
        try:
            gpu_mem = self._queryGpuMemory()
            if not gpu_mem:
                self.gpuMemLabel.setText('Llama: --G | Total: --/--G')
                return
            used_g, total_g = gpu_mem
            total_text = f'{self._formatGpuValue(used_g)}/{self._formatGpuValue(total_g)}G'
            llama_text = '--G'
            if self.worker and self.worker.isRunning() and self._gpuLaunchBaselineUsedG is not None:
                llama_used_g = max(0.0, used_g - self._gpuLaunchBaselineUsedG)
                llama_text = f'{self._formatGpuValue(llama_used_g)}G'
            self.gpuMemLabel.setText(f'Llama: {llama_text} | Total: {total_text}')
        except Exception:
            self.gpuMemLabel.setText('Llama: --G | Total: --/--G')

    def launchCommand(self, command):
        """通过 pywinpty 启动命令"""
        if self.worker and self.worker.isRunning():
            InfoBar.warning(title='进程正在运行', content='请先停止当前进程', orient=Qt.Horizontal, isClosable=False, position=InfoBarPosition.TOP, duration=2000, parent=self.window())
            return
        self.logText.clear()
        self._logBuffer.clear()
        self._logBufferChars = 0
        self.worker = TerminalWorker(self)
        self.worker.dataReady.connect(self._appendOutput)
        self.worker.processFinished.connect(self._onProcessFinished)
        self.logText.worker = self.worker
        gpu_mem = self._queryGpuMemory()
        self._gpuLaunchBaselineUsedG = gpu_mem[0] if gpu_mem else None
        self.worker.start_process(command)
        self._logTimer.start()
        self.launchBtn.setEnabled(False)
        self.stopBtn.setEnabled(True)
        self.logText.setFocus()

    def _appendOutput(self, text):
        text = _ANSI_RE.sub('', text)
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        text = re.sub(r'\n{2,}', '\n', text)
        if not text:
            return
        self._logBuffer.append(text)
        self._logBufferChars += len(text)
        if self._logBufferChars > TERMINAL_BUFFER_CHAR_LIMIT:
            combined = ''.join(self._logBuffer)
            kept = combined[-TERMINAL_BUFFER_CHAR_LIMIT:]
            self._logBuffer = ['\n--- 日志输出过快，已丢弃部分未显示内容 ---\n', kept]
            self._logBufferChars = sum(len(part) for part in self._logBuffer)
        if self._logBufferChars >= WORKER_EMIT_CHAR_LIMIT:
            self._flushLogBuffer()

    def _flushLogBuffer(self):
        if not self._logBuffer:
            return
        combined = ''.join(self._logBuffer)
        self._logBuffer.clear()
        self._logBufferChars = 0
        if not combined:
            return
        cursor = self.logText.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(combined)
        self.logText.setTextCursor(cursor)
        self.logText.ensureCursorVisible()

    def _onProcessFinished(self, exit_code):
        self._logTimer.stop()
        self._flushLogBuffer()
        cursor = self.logText.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(f'\n--- 进程已退出 (exit code: {exit_code}) ---\n')
        self.logText.setTextCursor(cursor)
        self.logText.ensureCursorVisible()
        self.launchBtn.setEnabled(True)
        self.stopBtn.setEnabled(False)
        self.logText.worker = None
        self._gpuLaunchBaselineUsedG = None

    def stopProcess(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.launchBtn.setEnabled(True)
            self.stopBtn.setEnabled(False)


class DeployInterface(QFrame):
    """一键部署：WSL2 + llama.cpp 自动化部署"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('deploy-interface')
        self.setStyleSheet('background: transparent; border: none;')
        self.worker = None
        self._deployLocked = False
        self._lockEffects = {}

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(36, 30, 36, 20)
        mainLayout.setSpacing(0)

        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(0, 0, 0, 0)
        titleLayout.setSpacing(10)
        self.titleLabel = QLabel('一键部署', self)
        self.titleLabel.setStyleSheet('font: 33px "Segoe UI", "Microsoft YaHei"; color: white; background: transparent;')
        titleLayout.addWidget(self.titleLabel)
        self.lockBtn = PushButton(self)
        self.lockBtn.setText('锁定')
        self.lockBtn.setFixedHeight(32)
        self.lockBtn.clicked.connect(lambda: self._setDeployLocked(True))
        titleLayout.addWidget(self.lockBtn)
        self.unlockBtn = DoubleClickPushButton(self)
        self.unlockBtn.setText('双击解锁')
        self.unlockBtn.setFixedHeight(32)
        self.unlockBtn.setToolTip('双击解除一键部署锁定状态')
        self.unlockBtn.doubleClicked.connect(self._unlockDeploy)
        titleLayout.addWidget(self.unlockBtn)
        titleLayout.addStretch(1)
        mainLayout.addLayout(titleLayout)
        mainLayout.addSpacing(20)

        self.infoLabel = QLabel(
            '优先使用程序目录中的 .wsl 镜像；没有镜像时下载 Ubuntu 官方 .wsl 后本地导入，部署完成后自动写入启动配置',
            self
        )
        self.infoLabel.setStyleSheet(
            'font: 14px "Segoe UI", "Microsoft YaHei"; '
            'color: rgba(96, 205, 255, 1); '
            'background: rgba(96, 205, 255, 0.08); '
            'border-radius: 6px; padding: 10px 16px;'
        )
        mainLayout.addWidget(self.infoLabel)
        mainLayout.addSpacing(20)

        self.configGroup = SettingCardGroup('部署配置', self)

        self.usernameCard = SettingCard(
            FIF.EDIT, 'WSL 用户名',
            '不存在时会自动创建；已存在时会复用该用户',
            self.configGroup
        )
        self.usernameEdit = LineEdit(self.usernameCard)
        self.usernameEdit.setPlaceholderText('llama')
        self.usernameEdit.setText('llama')
        self.usernameEdit.setFixedWidth(300)
        self.usernameCard.hBoxLayout.addWidget(self.usernameEdit, 0, Qt.AlignRight)
        self.usernameCard.hBoxLayout.addSpacing(16)
        self.configGroup.addSettingCard(self.usernameCard)

        self.passwordCard = SettingCard(
            FIF.COMMAND_PROMPT, 'WSL 密码',
            '用于新用户创建和 sudo 提权，只在本次部署进程中传递，默认为1234',
            self.configGroup
        )
        self.passwordEdit = LineEdit(self.passwordCard)
        self.passwordEdit.setPlaceholderText('请输入 WSL 密码')
        self.passwordEdit.setText('1234')
        self.passwordEdit.setEchoMode(QLineEdit.Password)
        self.passwordEdit.setFixedWidth(300)
        self.passwordCard.hBoxLayout.addWidget(self.passwordEdit, 0, Qt.AlignRight)
        self.passwordCard.hBoxLayout.addSpacing(16)
        self.configGroup.addSettingCard(self.passwordCard)

        self.installDirCard = SettingCard(
            FIF.FOLDER, '安装目录',
            'WSL Ubuntu-24.04 的安装位置（需有足够磁盘空间，建议30G+）',
            self.configGroup
        )
        self.installDirBtn = PushButton(FIF.FOLDER, '选择文件夹', self.installDirCard)
        self.installDirBtn.setFixedWidth(300)
        default_dir = os.path.join(
            os.environ.get('USERPROFILE', '~'), 'WSL', 'Ubuntu-24.04'
        )
        self._installDir = default_dir
        self.installDirBtn.setText(default_dir)
        self.installDirBtn.clicked.connect(self._browseInstallDir)
        self.installDirCard.hBoxLayout.addWidget(self.installDirBtn, 0, Qt.AlignRight)
        self.installDirCard.hBoxLayout.addSpacing(16)
        self.configGroup.addSettingCard(self.installDirCard)

        # 选择下载的模型预设
        self.modelPresetKeys = list(MODEL_PRESETS.keys())
        if DEFAULT_MODEL_PRESET_KEY in self.modelPresetKeys:
            self.modelPresetKeys.remove(DEFAULT_MODEL_PRESET_KEY)
            self.modelPresetKeys.insert(0, DEFAULT_MODEL_PRESET_KEY)
        self.modelPresetCard = SettingCard(
            FIF.IOT,
            '下载预设模型',
            '选择一键部署要下载的默认模型；下载源按 HuggingFace、ModelScope 顺序自动回退',
            self.configGroup
        )
        self.modelPresetCombo = FixedComboBox(self.modelPresetCard)
        self.modelPresetCombo.addItems([
            MODEL_PRESETS[key].get('display_name', key) for key in self.modelPresetKeys
        ])
        self.modelPresetCombo.setFixedWidth(300)
        self.modelPresetCard.hBoxLayout.addWidget(self.modelPresetCombo, 0, Qt.AlignRight)
        self.modelPresetCard.hBoxLayout.addSpacing(16)
        self.configGroup.addSettingCard(self.modelPresetCard)

        mainLayout.addWidget(self.configGroup)
        mainLayout.addSpacing(16)

        self.progressLabel = QLabel('部署进度', self)
        self.progressLabel.setStyleSheet('font: 20px "Segoe UI", "Microsoft YaHei";color: white; background: transparent;')
        mainLayout.addWidget(self.progressLabel)
        mainLayout.addSpacing(8)

        self.statusLabel = QLabel('等待开始', self)
        self.statusLabel.setStyleSheet(
            'font: 14px "Segoe UI", "Microsoft YaHei"; '
            'color: rgba(255,255,255,0.78); background: transparent;'
        )
        mainLayout.addWidget(self.statusLabel)
        mainLayout.addSpacing(8)

        self.logText = TerminalTextEdit(self)
        mainLayout.addWidget(self.logText, 1)
        mainLayout.addSpacing(12)

        self._logBuffer = []
        self._lineBuffer = ''
        self._resultFile = os.path.join(CONFIG_DIR, 'deploy_result.json')
        self._logTimer = QTimer(self)
        self._logTimer.setInterval(100)
        self._logTimer.timeout.connect(self._flushLogBuffer)

        btnLayout = QHBoxLayout()
        btnLayout.setSpacing(12)
        self.deployBtn = PrimaryPushButton(FIF.SYNC, '开始部署', self)
        self.deployBtn.setFixedHeight(40)
        btnLayout.addWidget(self.deployBtn)
        self.stopBtn = PushButton(FIF.CLOSE, '停止', self)
        self.stopBtn.setFixedHeight(40)
        self.stopBtn.setEnabled(False)
        self.stopBtn.clicked.connect(self.stopDeploy)
        btnLayout.addWidget(self.stopBtn)
        self.clearBtn = PushButton(FIF.DELETE, '清空', self)
        self.clearBtn.setFixedHeight(40)
        self.clearBtn.clicked.connect(lambda: self.logText.clear())
        btnLayout.addWidget(self.clearBtn)
        mainLayout.addLayout(btnLayout)

        self._lockableWidgets = [
            self.infoLabel,
            self.configGroup,
            self.progressLabel,
            self.statusLabel,
            self.logText,
            self.deployBtn,
            self.stopBtn,
            self.clearBtn,
        ]
        for widget in self._lockableWidgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(1.0)
            widget.setGraphicsEffect(effect)
            self._lockEffects[widget] = effect
        self._refreshDeployControls()

    def _isDeployRunning(self):
        return bool(self.worker and self.worker.isRunning())

    def _refreshDeployControls(self):
        locked = self._deployLocked
        running = self._isDeployRunning()
        opacity = 0.42 if locked else 1.0
        for widget in getattr(self, '_lockableWidgets', []):
            widget.setEnabled(True if widget is self.logText else not locked)
            effect = self._lockEffects.get(widget)
            if effect:
                effect.setOpacity(opacity)
        self.lockBtn.setEnabled(not locked)
        self.unlockBtn.setEnabled(locked)
        if locked:
            return
        self.deployBtn.setEnabled(not running)
        self.stopBtn.setEnabled(running)
        self.clearBtn.setEnabled(True)

    def _setDeployLocked(self, locked, message=None):
        self._deployLocked = locked
        if locked and not message:
            message = '一键部署已锁定，双击“解锁”后才能操作'
        elif not locked and not message:
            message = '一键部署已解锁'
        self.statusLabel.setText(message)
        self._refreshDeployControls()

    def _unlockDeploy(self):
        self._setDeployLocked(False)

    def _confirmStartDeploy(self):
        window = self.window()
        if hasattr(window, '_confirmAction'):
            return window._confirmAction(
                '确认开始部署',
                '是否现在开始部署，预估需要等待20-50分钟（取决于网络和cpu编译速度）'
            )
        box = QMessageBox(window)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle('确认开始部署')
        box.setText('是否现在开始部署，预估需要等待20-50分钟（取决于网络和cpu编译速度）')
        startButton = box.addButton('确定', QMessageBox.AcceptRole)
        cancelButton = box.addButton('取消', QMessageBox.RejectRole)
        box.setDefaultButton(cancelButton)
        box.exec()
        return box.clickedButton() == startButton

    def _browseInstallDir(self):
        folder = QFileDialog.getExistingDirectory(
            self, '选择 WSL 安装目录',
            self._installDir,
        )
        if folder:
            self._installDir = folder
            self.installDirBtn.setText(folder)

    def _findAutodeployPath(self):
        for core_dir in _candidate_core_dirs(BASE_DIR):
            candidate = os.path.join(core_dir, 'autodeploy.py')
            if os.path.exists(candidate):
                return candidate
        return os.path.join(BASE_DIR, 'autodeploy.py')

    def startDeploy(self):
        if self._deployLocked:
            InfoBar.warning(
                title='一键部署已锁定',
                content='请先双击“解锁”后再开始部署',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=2500,
                parent=self.window()
            )
            return
        if self.worker and self.worker.isRunning():
            InfoBar.warning(
                title='部署正在进行',
                content='请先停止当前部署',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=2000,
                parent=self.window()
            )
            return
        if not isAdmin():
            InfoBar.error(
                title='需要管理员权限',
                content='请右键以管理员身份运行启动器后再开始部署',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=5000,
                parent=self.window()
            )
            self.statusLabel.setText('需要管理员权限，请重新以管理员身份运行')
            return

        install_dir = self._installDir
        username = self.usernameEdit.text().strip() or 'llama'
        password = self.passwordEdit.text()
        model_index = max(0, self.modelPresetCombo.currentIndex())
        model_preset = self.modelPresetKeys[model_index] if self.modelPresetKeys else DEFAULT_MODEL_PRESET_KEY
        if not install_dir:
            InfoBar.error(
                title='未设置安装目录',
                content='请选择或输入 WSL 安装目录',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=3000,
                parent=self.window()
            )
            return
        if not password:
            InfoBar.error(
                title='未设置 WSL 密码',
                content='请输入用于创建用户和 sudo 提权的密码',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=3000,
                parent=self.window()
            )
            return

        autodeploy_path = self._findAutodeployPath()
        if not os.path.exists(autodeploy_path):
            InfoBar.error(
                title='找不到部署脚本',
                content='autodeploy.py 不在程序目录下',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=3000,
                parent=self.window()
            )
            return

        if not self._confirmStartDeploy():
            return

        self.logText.clear()
        self.statusLabel.setText('准备启动部署')
        self._lineBuffer = ''
        if os.path.exists(self._resultFile):
            try:
                os.remove(self._resultFile)
            except Exception:
                pass

        env = {
            'AUTODEPLOY_USERNAME': username,
            'AUTODEPLOY_PASSWORD': password,
            'AUTODEPLOY_INSTALL_DIR': install_dir,
            'AUTODEPLOY_BASE_DIR': CONFIG_DIR,
            'AUTODEPLOY_NON_INTERACTIVE': '1',
            'AUTODEPLOY_NO_START_SERVER': '1',
            'AUTODEPLOY_JSON_EVENTS': '1',
            'AUTODEPLOY_RESULT_FILE': self._resultFile,
            'AUTODEPLOY_MODEL_PRESET': model_preset,
            'PYTHONUNBUFFERED': '1',
            'PYTHONUTF8': '1',
            'PYTHONIOENCODING': 'utf-8',
        }
        for scan_dir in [BASE_DIR, CONFIG_DIR]:
            if not os.path.isdir(scan_dir):
                continue
            for f in os.listdir(scan_dir):
                full = os.path.join(scan_dir, f)
                if f.endswith('.wsl') and os.path.getsize(full) > 100 * 1024 * 1024:
                    env['AUTODEPLOY_WSL_MIRROR'] = full
                    break
            if env.get('AUTODEPLOY_WSL_MIRROR'):
                break

        deploy_args = [
            '--non-interactive',
            '--username', username,
            '--install-dir', install_dir,
            '--no-start-server',
            '--model-preset', model_preset,
            '--json-events',
            '--result-file', self._resultFile,
        ]
        if getattr(sys, 'frozen', False):
            command = subprocess.list2cmdline([sys.executable, '--run-autodeploy', *deploy_args])
            deploy_cwd = BASE_DIR
        else:
            command = subprocess.list2cmdline([sys.executable, '-u', autodeploy_path, *deploy_args])
            deploy_cwd = os.path.dirname(autodeploy_path)

        self.worker = TerminalWorker(self)
        self.worker.dataReady.connect(self._appendOutput)
        self.worker.processFinished.connect(self._onDeployFinished)
        self.logText.worker = self.worker
        self._logBuffer.clear()
        self._logTimer.start()
        self.worker.start_process(command, env=env, cwd=deploy_cwd)
        self._refreshDeployControls()
        self.logText.setFocus()

    def _appendOutput(self, text):
        text = _ANSI_RE.sub('', text)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        if not text:
            return

        text = self._lineBuffer + text
        lines = text.splitlines(keepends=True)
        self._lineBuffer = ''
        if lines and not lines[-1].endswith('\n'):
            self._lineBuffer = lines.pop()

        visible = []
        for line in lines:
            clean = line.rstrip('\n')
            if clean.startswith('::autodeploy-json::'):
                self._handleDeployEvent(clean[len('::autodeploy-json::'):])
                continue
            visible.append(line)
        if visible:
            self._logBuffer.append(''.join(visible))

    def _handleDeployEvent(self, raw):
        try:
            event = json.loads(raw)
        except Exception:
            return
        message = event.get('message') or ''
        phase = event.get('phase') or ''
        status = event.get('status') or ''
        if message:
            self.statusLabel.setText(f'{phase} / {status}: {message}')

    def _flushLogBuffer(self):
        if not self._logBuffer:
            return
        combined = ''.join(self._logBuffer)
        self._logBuffer.clear()
        combined = re.sub(r'\n{2,}', '\n', combined)
        if not combined:
            return
        cursor = self.logText.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(combined)
        self.logText.setTextCursor(cursor)
        self.logText.ensureCursorVisible()

    def _onDeployFinished(self, exit_code):
        self._logTimer.stop()
        if self._lineBuffer:
            if self._lineBuffer.startswith('::autodeploy-json::'):
                self._handleDeployEvent(self._lineBuffer[len('::autodeploy-json::'):])
            else:
                self._logBuffer.append(self._lineBuffer + '\n')
            self._lineBuffer = ''
        self._flushLogBuffer()
        cursor = self.logText.textCursor()
        cursor.movePosition(QTextCursor.End)
        if exit_code == 0:
            cursor.insertText('\n--- 部署完成! ---\n')
            self.statusLabel.setText('部署完成，正在写入启动配置')
            if self._applyDeployResult():
                self._setDeployLocked(True, '部署完成，启动配置已更新；一键部署已自动锁定')
        else:
            cursor.insertText(f'\n--- 部署结束 (exit code: {exit_code}) ---\n')
            self.statusLabel.setText(f'部署结束，exit code: {exit_code}')
        self.logText.setTextCursor(cursor)
        self.logText.ensureCursorVisible()
        self._refreshDeployControls()
        self.logText.worker = None

    def _applyDeployResult(self):
        if not os.path.exists(self._resultFile):
            self.statusLabel.setText('部署完成，但没有找到部署结果文件')
            return False
        try:
            with open(self._resultFile, 'r', encoding='utf-8') as f:
                result = json.load(f)
        except Exception as e:
            self.statusLabel.setText(f'部署结果读取失败: {e}')
            return False
        window = self.window()
        if hasattr(window, 'applyDeployResult'):
            window.applyDeployResult(result)
            self.statusLabel.setText('部署完成，启动配置已更新')
            return True
        return False

    def stopDeploy(self):
        if self.worker and self.worker.isRunning():
            self.statusLabel.setText('正在停止部署进程...')
            self.worker.stop()
            self._refreshDeployControls()


class LauncherSettingsInterface(BaseSettingInterface):
    """启动器自身设置：语言、主题、字体和重置入口"""

    def __init__(self, parent=None):
        super().__init__('启动器设置', 'launcher-settings-interface', parent)

        self.launcherGroup = SettingCardGroup('偏好', self.scrollWidget)

        self.languageCard = SettingCard(
            FIF.LANGUAGE, '语言',
            '切换启动器导航和设置页语言',
            self.launcherGroup
        )
        self.languageCombo = FixedComboBox(self.languageCard)
        self.languageCombo.addItems(['CN', 'EN'])
        self.languageCombo.setFixedWidth(CTRL_WIDTH)
        self.languageCard.hBoxLayout.addWidget(self.languageCombo, 0, Qt.AlignRight)
        self.languageCard.hBoxLayout.addSpacing(16)
        self.launcherGroup.addSettingCard(self.languageCard)

        self.themeCard = SettingCard(
            FIF.BRUSH, 'UI 颜色',
            '切换深色、浅色或跟随系统主题',
            self.launcherGroup
        )
        self.themeCombo = FixedComboBox(self.themeCard)
        self.themeCombo.addItems(list(LAUNCHER_THEMES.keys()))
        self.themeCombo.setFixedWidth(CTRL_WIDTH)
        self.themeCard.hBoxLayout.addWidget(self.themeCombo, 0, Qt.AlignRight)
        self.themeCard.hBoxLayout.addSpacing(16)
        self.launcherGroup.addSettingCard(self.themeCard)

        self.fontScaleCard = SettingCard(
            FIF.FONT, '字体大小',
            '按比例调整标题、分组标题、说明文字和日志字号（80%-130%）',
            self.launcherGroup
        )
        self.fontScaleSpin = SpinBox(self.fontScaleCard)
        self.fontScaleSpin.setRange(80, 130)
        self.fontScaleSpin.setValue(100)
        self.fontScaleSpin.setSingleStep(5)
        self.fontScaleSpin.setFixedWidth(140)
        self.fontScaleSuffix = QLabel('%', self.fontScaleCard)
        self.fontScaleSuffix.setStyleSheet('font: 14px; background: transparent;')
        self.fontScaleCard.hBoxLayout.addWidget(self.fontScaleSpin, 0, Qt.AlignRight)
        self.fontScaleCard.hBoxLayout.addSpacing(8)
        self.fontScaleCard.hBoxLayout.addWidget(self.fontScaleSuffix)
        self.fontScaleCard.hBoxLayout.addSpacing(16)
        self.launcherGroup.addSettingCard(self.fontScaleCard)

        self.expandLayout.addWidget(self.launcherGroup)

        self.resetGroup = SettingCardGroup('还原设置', self.scrollWidget)

        self.resetParamsCard = SettingCard(
            FIF.RETURN, '还原所有参数设置为默认',
            '重置模型、服务器和路径参数，不影响启动器语言/主题/字体',
            self.resetGroup
        )
        self.resetParamsBtn = PushButton(FIF.RETURN, '还原参数默认值', self.resetParamsCard)
        self.resetParamsBtn.setFixedWidth(180)
        self.resetParamsCard.hBoxLayout.addWidget(self.resetParamsBtn, 0, Qt.AlignRight)
        self.resetParamsCard.hBoxLayout.addSpacing(16)
        self.resetGroup.addSettingCard(self.resetParamsCard)

        self.resetLauncherCard = SettingCard(
            FIF.SYNC, '还原启动器设置',
            '重置语言、UI 颜色和字体大小',
            self.resetGroup
        )
        self.resetLauncherBtn = PushButton(FIF.SYNC, '还原启动器设置', self.resetLauncherCard)
        self.resetLauncherBtn.setFixedWidth(180)
        self.resetLauncherCard.hBoxLayout.addWidget(self.resetLauncherBtn, 0, Qt.AlignRight)
        self.resetLauncherCard.hBoxLayout.addSpacing(16)
        self.resetGroup.addSettingCard(self.resetLauncherCard)

        self.expandLayout.addWidget(self.resetGroup)

    def setLauncherValues(self, cfg):
        self.languageCombo.blockSignals(True)
        self.themeCombo.blockSignals(True)
        self.fontScaleSpin.blockSignals(True)
        self.languageCombo.setCurrentText(cfg.get('language', DEFAULT_LAUNCHER_CONFIG['language']))
        self.themeCombo.setCurrentText(cfg.get('theme', DEFAULT_LAUNCHER_CONFIG['theme']))
        self.fontScaleSpin.setValue(int(cfg.get('font_scale', DEFAULT_LAUNCHER_CONFIG['font_scale'])))
        self.languageCombo.blockSignals(False)
        self.themeCombo.blockSignals(False)
        self.fontScaleSpin.blockSignals(False)

    def launcherValues(self):
        return {
            'language': self.languageCombo.currentText() or DEFAULT_LAUNCHER_CONFIG['language'],
            'theme': THEME_ALIASES.get(self.themeCombo.currentText(), self.themeCombo.currentText() or DEFAULT_LAUNCHER_CONFIG['theme']),
            'font_scale': self.fontScaleSpin.value(),
        }

    def applyLanguage(self, lang):
        text = LANG_TEXT.get(lang, LANG_TEXT['CH'])
        self.titleLabel.setText(text['settings.title'])
        self.launcherGroup.titleLabel.setText(text['settings.launcher_group'])
        self.languageCard.setTitle(text['settings.language_title'])
        self.languageCard.setContent(text['settings.language_content'])
        self.themeCard.setTitle(text['settings.theme_title'])
        self.themeCard.setContent(text['settings.theme_content'])
        self.fontScaleCard.setTitle(text['settings.font_title'])
        self.fontScaleCard.setContent(text['settings.font_content'])
        self.resetGroup.titleLabel.setText(text['settings.reset_group'])
        self.resetParamsCard.setTitle(text['settings.reset_params_title'])
        self.resetParamsCard.setContent(text['settings.reset_params_content'])
        self.resetParamsBtn.setText(text['settings.reset_params_button'])
        self.resetLauncherCard.setTitle(text['settings.reset_launcher_title'])
        self.resetLauncherCard.setContent(text['settings.reset_launcher_content'])
        self.resetLauncherBtn.setText(text['settings.reset_launcher_button'])


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()

        self._launcherConfig = self._readLauncherConfig()
        setTheme(LAUNCHER_THEMES.get(self._launcherConfig.get('theme'), Theme.DARK))

        llm_models, mm_models = loadModels()
        self.basicInterface = BasicInterface(llm_models, mm_models, self)
        self.modelInterface = ModelInterface(self)
        self.serverInterface = ServerInterface(self)
        self.deployInterface = DeployInterface(self)
        self.logInterface = LogInterface(self)
        self.settingsInterface = LauncherSettingsInterface(self)

        self.initNavigation()
        self.initWindow()
        self._connectAllSignals()
        self._loadConfig()
        self.settingsInterface.setLauncherValues(self._launcherConfig)
        self._applyLauncherSettings(save=False)
        self._updateCommandPreview()
        self.logInterface.launchBtn.clicked.connect(self._onLaunch)
        self.basicInterface.runBtn.clicked.connect(self._onRunBtnClicked)
        self.deployInterface.deployBtn.clicked.connect(self.deployInterface.startDeploy)

    def initNavigation(self):
        self.navButtons = {
            'basic': self.addSubInterface(self.basicInterface, FIF.HOME, '基础设置'),
            'deploy': self.addSubInterface(self.deployInterface, FIF.SYNC, '一键部署'),
            'model': self.addSubInterface(self.modelInterface, FIF.IOT, '模型设置'),
            'server': self.addSubInterface(self.serverInterface, FIF.WIFI, '服务器设置'),
            'log': self.addSubInterface(self.logInterface, FIF.COMMAND_PROMPT, '运行日志'),
            'settings': self.addSubInterface(
                self.settingsInterface,
                FIF.SETTING,
                '设置',
                position=NavigationItemPosition.BOTTOM
            ),
        }

    def initWindow(self):
        self.resize(900, 700)
        self.setWindowTitle('llama.cpp 启动器')
        self.setWindowIcon(getAppIcon())
        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def buildCommand(self):
        """汇总所有页面的参数，构建 WSL 启动命令"""
        bi = self.basicInterface
        mi = self.modelInterface
        si = self.serverInterface
        parts = ['wsl', self._expandedExecPath()]

        # 模型选择（用实际路径替换显示名）
        llm = bi.llmCombo.currentText()
        if llm and llm in bi.llmPaths:
            parts.extend(['-m', bi.llmPaths[llm]])

        mm = bi.mmCombo.currentText()
        if mm and mm != '无' and mm in bi.mmPaths:
            parts.extend(['-mm', bi.mmPaths[mm]])

        # 模型参数
        ctx_text = mi.ctxEdit.text().strip()
        if ctx_text:
            parts.extend(['-c', str(int(ctx_text) * 1000)])

        predict = mi.predictEdit.text().strip()
        if predict:
            parts.extend(['-n', predict])

        parts.extend(['--temp', f'{mi.tempSpin.value():.2f}'])
        parts.extend(['--top-p', f'{mi.topPSpin.value():.2f}'])
        parts.extend(['--top-k', str(mi.topKSpin.value())])
        parts.extend(['--repeat-penalty', f'{mi.repeatPenaltySpin.value():.2f}'])
        parts.extend(['--repeat-last-n', str(mi.repeatLastNSpin.value())])

        # KV 缓存
        parts.extend(['--cache-type-k', mi.cacheKCombo.currentText()])
        parts.extend(['--cache-type-v', mi.cacheVCombo.currentText()])

        cache_ram = mi.cacheRamEdit.text().strip()
        if cache_ram:
            parts.extend(['--cache-ram', cache_ram])

        parts.extend(['--flash-attn', mi.faCombo.currentText()])

        # 多模态参数
        if mm and mm != '无':
            img_min = mi.imgMinEdit.text().strip()
            if img_min:
                parts.extend(['--image-min-tokens', img_min])

        # GPU 加速
        parts.extend(['-ngl', str(mi.nglSpin.value())])
        if mi.mainGpuSpin.value() != 0:
            parts.extend(['-mg', str(mi.mainGpuSpin.value())])
        ts = mi.tsSplitEdit.text().strip()
        if ts:
            parts.extend(['-ts', ts])
        if mi.nommapCombo.currentText() in ('no-mmap', '启用'):
            parts.append('--no-mmap')
        numa = mi.numaCombo.currentText()
        if numa != '关闭':
            parts.extend(['--numa', numa])

        # 服务器 - 网络
        parts.extend(['--host', si.hostEdit.text().strip()])
        parts.extend(['--port', str(si.portSpin.value())])

        api_key = si.apiKeyEdit.text().strip()
        if api_key:
            parts.extend(['--api-key', api_key])

        # 服务器 - 性能
        parts.extend(['--threads', str(si.threadsSpin.value())])
        parts.extend(['--batch-size', str(si.batchSpin.value())])
        parts.extend(['--ubatch-size', str(si.ubatchSpin.value())])
        parts.extend(['--parallel', str(si.parallelSpin.value())])
        parts.extend(['--timeout', str(si.timeoutSpin.value())])

        # 服务器 - 功能开关
        parts.extend(['--log-verbosity', LOG_VERBOSITY_LEVELS.get(self._normalizedLogVerbosity(), '2')])
        if si.metricsCombo.currentText() == '启用':
            parts.append('--metrics')
        if si.webuiCombo.currentText() == '禁用':
            parts.append('--no-webui')

        return ' '.join(parts)

    def _updateCommandPreview(self):
        self.basicInterface.cmdPreview.setText(self.buildCommand())

    def _connectAllSignals(self):
        """连接所有控件的信号，实时更新命令预览"""
        bi = self.basicInterface
        mi = self.modelInterface
        si = self.serverInterface

        bi.execPathEdit.textChanged.connect(self._updateCommandPreview)

        bi.llmCombo.currentIndexChanged.connect(self._updateCommandPreview)
        bi.mmCombo.currentIndexChanged.connect(self._updateCommandPreview)
        bi.modelSearchPathEdit.textChanged.connect(self._updateCommandPreview)
        bi.refreshModelsBtn.clicked.connect(self.refreshLocalModels)
        mi.ctxEdit.textChanged.connect(self._updateCommandPreview)
        mi.predictEdit.textChanged.connect(self._updateCommandPreview)
        mi.tempSpin.valueChanged.connect(self._updateCommandPreview)
        mi.topPSpin.valueChanged.connect(self._updateCommandPreview)
        mi.topKSpin.valueChanged.connect(self._updateCommandPreview)
        mi.repeatPenaltySpin.valueChanged.connect(self._updateCommandPreview)
        mi.repeatLastNSpin.valueChanged.connect(self._updateCommandPreview)
        mi.cacheKCombo.currentIndexChanged.connect(self._updateCommandPreview)
        mi.cacheVCombo.currentIndexChanged.connect(self._updateCommandPreview)
        mi.cacheRamEdit.textChanged.connect(self._updateCommandPreview)
        mi.faCombo.currentIndexChanged.connect(self._updateCommandPreview)
        mi.imgMinEdit.textChanged.connect(self._updateCommandPreview)
        mi.nglSpin.valueChanged.connect(self._updateCommandPreview)
        mi.mainGpuSpin.valueChanged.connect(self._updateCommandPreview)
        mi.tsSplitEdit.textChanged.connect(self._updateCommandPreview)
        mi.nommapCombo.currentIndexChanged.connect(self._updateCommandPreview)
        mi.numaCombo.currentIndexChanged.connect(self._updateCommandPreview)

        si.hostEdit.textChanged.connect(self._updateCommandPreview)
        si.portSpin.valueChanged.connect(self._updateCommandPreview)
        si.apiKeyEdit.textChanged.connect(self._updateCommandPreview)
        si.threadsSpin.valueChanged.connect(self._updateCommandPreview)
        si.batchSpin.valueChanged.connect(self._updateCommandPreview)
        si.ubatchSpin.valueChanged.connect(self._updateCommandPreview)
        si.parallelSpin.valueChanged.connect(self._updateCommandPreview)
        si.timeoutSpin.valueChanged.connect(self._updateCommandPreview)
        si.verboseCombo.currentIndexChanged.connect(self._updateCommandPreview)
        si.metricsCombo.currentIndexChanged.connect(self._updateCommandPreview)
        si.webuiCombo.currentIndexChanged.connect(self._updateCommandPreview)
        self.settingsInterface.languageCombo.currentIndexChanged.connect(self._onLauncherSettingsChanged)
        self.settingsInterface.themeCombo.currentIndexChanged.connect(self._onLauncherSettingsChanged)
        self.settingsInterface.fontScaleSpin.valueChanged.connect(self._onLauncherSettingsChanged)
        self.settingsInterface.resetParamsBtn.clicked.connect(self.resetRuntimeConfig)
        self.settingsInterface.resetLauncherBtn.clicked.connect(self.resetLauncherConfig)

    def _onLaunch(self):
        self._updateCommandPreview()
        cmd = self.buildCommand()
        self.logInterface.launchCommand(cmd)

    def _onRunBtnClicked(self):
        self.switchTo(self.logInterface)
        self._onLaunch()

    def _normalizedLogVerbosity(self, value=None):
        raw = self.serverInterface.verboseCombo.currentText() if value is None else value
        key = str(raw or '').strip()
        key = LEGACY_LOG_VERBOSITY_ALIASES.get(key, key.lower())
        return key if key in LOG_VERBOSITY_LEVELS else 'warn'

    # ─────────── 启动器设置 ───────────

    def _defaultConfigPath(self):
        primary = os.path.join(CONFIG_DIR, 'default_config.json')
        if os.path.exists(primary):
            return primary
        meipass = getattr(sys, '_MEIPASS', '')
        bundled = os.path.join(meipass, 'core', 'default_config.json') if meipass else ''
        if bundled and os.path.exists(bundled):
            return bundled
        return os.path.join(BASE_DIR, 'default_config.json')

    def _readJsonFile(self, path, default=None):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {} if default is None else default

    def _readLauncherConfig(self):
        cfg = dict(DEFAULT_LAUNCHER_CONFIG)
        saved = self._readJsonFile(self._configPath(), {})
        if isinstance(saved, dict) and isinstance(saved.get('launcher'), dict):
            cfg.update(saved['launcher'])
        legacy = self._readJsonFile(os.path.join(BASE_DIR, 'launcher.json'), {})
        if isinstance(legacy, dict):
            cfg.update(legacy)
        cfg['language'] = 'EN' if str(cfg.get('language')).upper() == 'EN' else 'CH'
        cfg['theme'] = THEME_ALIASES.get(cfg.get('theme'), cfg.get('theme'))
        if cfg.get('theme') not in LAUNCHER_THEMES:
            cfg['theme'] = DEFAULT_LAUNCHER_CONFIG['theme']
        try:
            cfg['font_scale'] = max(80, min(130, int(cfg.get('font_scale', 100))))
        except Exception:
            cfg['font_scale'] = DEFAULT_LAUNCHER_CONFIG['font_scale']
        return cfg

    def _saveLauncherConfig(self):
        self._saveConfig()

    def _onLauncherSettingsChanged(self):
        self._launcherConfig = self.settingsInterface.launcherValues()
        self._applyLauncherSettings(save=True)

    def _applyLauncherSettings(self, save=False):
        cfg = dict(DEFAULT_LAUNCHER_CONFIG)
        cfg.update(self._launcherConfig)
        cfg['theme'] = THEME_ALIASES.get(cfg.get('theme'), cfg.get('theme'))
        cfg['font_scale'] = max(80, min(130, int(cfg.get('font_scale', 100))))
        self._launcherConfig = cfg
        setTheme(LAUNCHER_THEMES.get(cfg['theme'], Theme.DARK))
        self._applyLanguage(cfg['language'])
        self._applyFontScale(cfg['font_scale'])
        if save:
            self._saveLauncherConfig()

    def _applyLanguage(self, lang):
        text = LANG_TEXT.get(lang, LANG_TEXT['CH'])
        self.setWindowTitle(text['window.title'])
        self.basicInterface.titleLabel.setText(text['nav.basic'])
        self.deployInterface.titleLabel.setText(text['nav.deploy'])
        self.modelInterface.titleLabel.setText(text['nav.model'])
        self.serverInterface.titleLabel.setText(text['nav.server'])
        self.logInterface.titleLabel.setText(text['nav.log'])
        self.settingsInterface.applyLanguage(lang)

        bi = self.basicInterface
        bi.previewLabel.setText(text['basic.preview'])
        bi.pathGroup.titleLabel.setText(text['basic.path_group'])
        bi.modelGroup.titleLabel.setText(text['basic.model_group'])
        self._setCardText(bi.execPathCard, text['basic.exec_title'], text['basic.exec_content'])
        self._setCardText(bi.modelSearchPathCard, text['basic.search_title'], text['basic.search_content'])
        self._setCardText(bi.refreshModelsCard, text['basic.refresh_title'], text['basic.refresh_content'])
        bi.refreshModelsBtn.setText(text['basic.refresh_button'])
        self._setCardText(bi.llmCard, text['basic.llm_title'], text['basic.llm_content'])
        self._setCardText(bi.mmCard, text['basic.mm_title'], text['basic.mm_content'])
        bi.runBtn.setText(text['basic.run'])

        di = self.deployInterface
        di.infoLabel.setText(text['deploy.info'])
        di.configGroup.titleLabel.setText(text['deploy.config_group'])
        di.progressLabel.setText(text['deploy.progress'])
        di.lockBtn.setText(text['deploy.lock'])
        di.unlockBtn.setText(text['deploy.unlock'])
        di.deployBtn.setText(text['deploy.start'])
        di.stopBtn.setText(text['deploy.stop'])
        di.clearBtn.setText(text['deploy.clear'])
        self._setCardText(di.usernameCard, text['deploy.username_title'], text['deploy.username_content'])
        self._setCardText(di.passwordCard, text['deploy.password_title'], text['deploy.password_content'])
        self._setCardText(di.installDirCard, text['deploy.install_title'], text['deploy.install_content'])
        self._setCardText(di.modelPresetCard, text['deploy.model_preset_title'], text['deploy.model_preset_content'])

        mi = self.modelInterface
        mi.paramGroup.titleLabel.setText(text['model.param_group'])
        mi.kvGroup.titleLabel.setText(text['model.kv_group'])
        mi.mmParamGroup.titleLabel.setText(text['model.mm_group'])
        mi.gpuGroup.titleLabel.setText(text['model.advanced_group'])
        self._setCardText(mi.ctxCard, text['model.ctx_title'], text['model.ctx_content'])
        self._setCardText(mi.predictCard, text['model.predict_title'], text['model.predict_content'])
        self._setCardText(mi.tempCard, text['model.temp_title'], text['model.temp_content'])
        self._setCardText(mi.topPCard, text['model.top_p_title'], text['model.top_p_content'])
        self._setCardText(mi.topKCard, text['model.top_k_title'], text['model.top_k_content'])
        self._setCardText(mi.cacheKCard, text['model.cache_k_title'], text['model.cache_k_content'])
        self._setCardText(mi.cacheVCard, text['model.cache_v_title'], text['model.cache_v_content'])
        self._setCardText(mi.cacheRamCard, text['model.cache_ram_title'], text['model.cache_ram_content'])
        self._setCardText(mi.faCard, text['model.flash_title'], text['model.flash_content'])
        self._setCardText(mi.imgMinCard, text['model.image_min_title'], text['model.image_min_content'])
        self._setCardText(mi.repeatPenaltyCard, text['model.repeat_penalty_title'], text['model.repeat_penalty_content'])
        self._setCardText(mi.repeatLastNCard, text['model.repeat_last_n_title'], text['model.repeat_last_n_content'])
        self._setCardText(mi.nglCard, text['model.ngl_title'], text['model.ngl_content'])
        self._setCardText(mi.mainGpuCard, text['model.main_gpu_title'], text['model.main_gpu_content'])
        self._setCardText(mi.tsSplitCard, text['model.tensor_split_title'], text['model.tensor_split_content'])
        self._setCardText(mi.nommapCard, text['model.nommap_title'], text['model.nommap_content'])
        self._setCardText(mi.numaCard, text['model.numa_title'], text['model.numa_content'])

        si = self.serverInterface
        si.netGroup.titleLabel.setText(text['server.net_group'])
        si.perfGroup.titleLabel.setText(text['server.perf_group'])
        si.toggleGroup.titleLabel.setText(text['server.toggle_group'])
        self._setCardText(si.hostCard, text['server.host_title'], text['server.host_content'])
        self._setCardText(si.portCard, text['server.port_title'], text['server.port_content'])
        self._setCardText(si.apiKeyCard, text['server.api_key_title'], text['server.api_key_content'])
        self._setCardText(si.threadsCard, text['server.threads_title'], text['server.threads_content'])
        self._setCardText(si.batchCard, text['server.batch_title'], text['server.batch_content'])
        self._setCardText(si.ubatchCard, text['server.ubatch_title'], text['server.ubatch_content'])
        self._setCardText(si.parallelCard, text['server.parallel_title'], text['server.parallel_content'])
        self._setCardText(si.timeoutCard, text['server.timeout_title'], text['server.timeout_content'])
        self._setCardText(si.verboseCard, text['server.verbose_title'], text['server.verbose_content'])
        self._setCardText(si.metricsCard, text['server.metrics_title'], text['server.metrics_content'])
        self._setCardText(si.webuiCard, text['server.webui_title'], text['server.webui_content'])

        li = self.logInterface
        li.launchBtn.setText(text['log.launch'])
        li.stopBtn.setText(text['log.stop'])
        li.clearBtn.setText(text['log.clear'])

        for key, button in getattr(self, 'navButtons', {}).items():
            label = text.get(f'nav.{key}')
            if label and hasattr(button, 'setText'):
                button.setText(label)

    def _setCardText(self, card, title, content):
        card.setTitle(title)
        card.setContent(content)

    def _scaleSize(self, base, scale):
        return max(8, round(base * scale / 100))

    def _fontForUi(self, point_size, family='Microsoft YaHei UI'):
        font = QFont(family, point_size)
        font.setHintingPreference(QFont.PreferFullHinting)
        return font

    def _applyFontScale(self, scale):
        dark = isDarkTheme()
        title_color = 'white' if dark else 'black'
        body_color = 'rgba(255,255,255,0.78)' if dark else 'rgba(0,0,0,0.72)'
        preview_bg = 'rgba(255,255,255,0.04)' if dark else '#eef2f6'
        preview_border = 'none' if dark else '1px solid #d8dee6'
        log_bg = '#1e1e1e' if dark else '#f6f8fb'
        log_fg = '#cccccc' if dark else '#1f2933'
        log_border = '#333333' if dark else '#cfd8e3'
        log_selection = '#264f78' if dark else '#b8ddff'
        info_fg = 'rgba(96, 205, 255, 1)' if dark else '#008c8c'
        info_bg = 'rgba(96, 205, 255, 0.08)' if dark else 'rgba(0, 188, 188, 0.14)'
        title_size = self._scaleSize(33, scale)
        section_size = self._scaleSize(20, scale)
        card_title_size = self._scaleSize(15, scale)
        card_content_size = self._scaleSize(13, scale)
        self._applySurfaceTheme(dark)
        ui_font = QFont('Microsoft YaHei UI', self._scaleSize(10, scale))
        ui_font.setHintingPreference(QFont.PreferFullHinting)
        app.setFont(ui_font)
        for label in [
            self.basicInterface.titleLabel,
            self.modelInterface.titleLabel,
            self.serverInterface.titleLabel,
            self.deployInterface.titleLabel,
            self.logInterface.titleLabel,
            self.settingsInterface.titleLabel,
        ]:
            label.setStyleSheet(
                f'font: {title_size}px "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"; '
                f'color: {title_color}; background: transparent;'
            )

        for label in [
            self.basicInterface.previewLabel,
            self.deployInterface.progressLabel,
            self.logInterface.gpuMemLabel,
        ]:
            label.setStyleSheet(
                f'font: {section_size}px "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"; '
                f'color: {title_color}; background: transparent;'
            )

        for group in self.findChildren(SettingCardGroup):
            group.titleLabel.setStyleSheet(
                f'font: {section_size}px "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"; '
                f'color: {title_color}; background: transparent;'
            )
        for card in self.findChildren(SettingCard):
            card.titleLabel.setStyleSheet(
                f'font: {card_title_size}px "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"; '
                f'font-weight: 400; color: {title_color}; background: transparent;'
            )
            card.contentLabel.setStyleSheet(
                f'font: {card_content_size}px "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei"; '
                f'color: {body_color}; background: transparent;'
            )

        self.basicInterface.cmdPreview.setStyleSheet(
            f'background: {preview_bg}; border: {preview_border}; border-radius: 8px; '
            f'color: {body_color}; padding: 12px 16px;'
        )
        for logEdit in [self.logInterface.logText, self.deployInterface.logText]:
            logEdit.setStyleSheet(
                f'QPlainTextEdit {{ background-color: {log_bg}; color: {log_fg}; border: 1px solid {log_border}; '
                f'border-radius: 4px; padding: 8px; '
                f'selection-background-color: {log_selection}; }}'
            )
        self.deployInterface.infoLabel.setStyleSheet(
            f'color: {info_fg}; '
            f'background: {info_bg}; '
            'border-radius: 6px; padding: 10px 16px; font-weight: 400;'
        )
        self.deployInterface.statusLabel.setStyleSheet(
            f'color: {body_color}; background: transparent;'
        )
        self.modelInterface.ctxSuffix.setStyleSheet('background: transparent;')
        self.modelInterface.cacheRamSuffix.setStyleSheet('background: transparent;')
        self.settingsInterface.fontScaleSuffix.setStyleSheet('background: transparent;')
        self._applyNativeFontsForAllPages(scale, title_color, body_color)

    def _applyNativeFontsForAllPages(self, scale, title_color, body_color):
        title_pt = max(18, round(25 * scale / 100))
        section_pt = max(11, round(15 * scale / 100))
        card_title_pt = max(9, round(11 * scale / 100))
        card_content_pt = max(8, round(10 * scale / 100))
        mono_pt = max(8, round(10 * scale / 100))

        for label in [
            self.basicInterface.titleLabel,
            self.modelInterface.titleLabel,
            self.serverInterface.titleLabel,
            self.deployInterface.titleLabel,
            self.logInterface.titleLabel,
            self.settingsInterface.titleLabel,
        ]:
            label.setStyleSheet(f'color: {title_color}; background: transparent;')
            label.setFont(self._fontForUi(title_pt))

        for label in [
            self.basicInterface.previewLabel,
            self.deployInterface.progressLabel,
            self.logInterface.gpuMemLabel,
        ]:
            label.setStyleSheet(f'color: {title_color}; background: transparent;')
            label.setFont(self._fontForUi(section_pt))

        for group in self.findChildren(SettingCardGroup):
            group.titleLabel.setStyleSheet(f'color: {title_color}; background: transparent;')
            group.titleLabel.setFont(self._fontForUi(section_pt))

        for card in self.findChildren(SettingCard):
            card.titleLabel.setStyleSheet(f'font-weight: 400; color: {title_color}; background: transparent;')
            card.titleLabel.setFont(self._fontForUi(card_title_pt))
            card.contentLabel.setStyleSheet(f'color: {body_color}; background: transparent;')
            card.contentLabel.setFont(self._fontForUi(card_content_pt))

        for label in [
            self.modelInterface.ctxSuffix,
            self.modelInterface.cacheRamSuffix,
            self.settingsInterface.fontScaleSuffix,
            self.deployInterface.infoLabel,
            self.deployInterface.statusLabel,
        ]:
            label.setFont(self._fontForUi(card_title_pt))

        self.basicInterface.cmdPreview.setFont(self._fontForUi(mono_pt, 'Cascadia Mono'))
        self.logInterface.logText.setFont(self._fontForUi(mono_pt, 'Cascadia Mono'))
        self.deployInterface.logText.setFont(self._fontForUi(mono_pt, 'Cascadia Mono'))

    def _applySurfaceTheme(self, dark):
        page_bg = 'transparent' if dark else '#f3f5f7'
        for widget in [self.basicInterface, self.deployInterface, self.logInterface]:
            widget.setStyleSheet(f'#{widget.objectName()} {{ background: {page_bg}; border: none; }}')
        for widget in [self.modelInterface, self.serverInterface, self.settingsInterface]:
            widget.setStyleSheet(f'#{widget.objectName()} {{ background: {page_bg}; border: none; }}')
            widget.viewport().setStyleSheet(f'background: {page_bg};')
            widget.scrollWidget.setStyleSheet(f'background: {page_bg};')

    def _confirmAction(self, title, message):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(message)
        okButton = box.addButton('确定', QMessageBox.AcceptRole)
        cancelButton = box.addButton('取消', QMessageBox.RejectRole)
        box.setDefaultButton(cancelButton)
        box.exec()
        return box.clickedButton() == okButton

    def resetRuntimeConfig(self):
        if not self._confirmAction('还原参数默认值', '确定要还原所有模型、服务器和路径参数吗？启动器语言、主题和字体不会改变。'):
            return
        cfg = self._readJsonFile(self._defaultConfigPath(), {})
        if not cfg:
            InfoBar.error(
                title='还原失败',
                content='default_config.json 不存在或无法读取',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=3500,
                parent=self
            )
            return
        self._applyRuntimeConfig(cfg)
        self._updateCommandPreview()
        self._saveConfig()
        InfoBar.success(
            title='参数已还原',
            content='模型、服务器和路径参数已恢复为默认值',
            orient=Qt.Horizontal, isClosable=False,
            position=InfoBarPosition.TOP, duration=3000,
            parent=self
        )

    def resetLauncherConfig(self):
        if not self._confirmAction('还原启动器设置', '确定要还原语言、UI 颜色和字体大小吗？'):
            return
        self._launcherConfig = dict(DEFAULT_LAUNCHER_CONFIG)
        self.settingsInterface.setLauncherValues(self._launcherConfig)
        self._applyLauncherSettings(save=True)
        InfoBar.success(
            title='启动器设置已还原',
            content='语言、UI 颜色和字体大小已恢复为默认值',
            orient=Qt.Horizontal, isClosable=False,
            position=InfoBarPosition.TOP, duration=3000,
            parent=self
        )

    # ─────────── 配置持久化 ───────────

    def _modelSearchPaths(self):
        text = self.basicInterface.modelSearchPathEdit.text()
        parts = [p.strip() for p in re.split(r'[;\n,，]+', text) if p.strip()]
        return parts or list(DEFAULT_MODEL_SEARCH_PATHS)

    def _detectWslUser(self):
        cached = getattr(self, '_cachedWslUser', None)
        if cached:
            return cached
        try:
            result = subprocess.run(
                ['wsl', '-d', DISTRO, '--', 'sh', '-lc', 'id -un 2>/dev/null || printf llama'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            user = decodeProcessOutput(result.stdout).replace('\x00', '').strip()
            self._cachedWslUser = user or 'llama'
            return self._cachedWslUser
        except Exception:
            self._cachedWslUser = 'llama'
            return 'llama'

    def _expandWslPath(self, path, user=None):
        user = user or self._detectWslUser()
        p = (path or '').replace('<用户>', user).replace('{user}', user).replace('$USER', user).strip()
        if p == '~' or p.startswith('~/'):
            p = f"/home/{user}{p[1:]}"
        return p

    def _expandedExecPath(self):
        return self._expandWslPath(self.basicInterface.execPathEdit.text())

    def _expandedModelSearchPaths(self):
        user = self._detectWslUser()
        paths = []
        for path in self._modelSearchPaths():
            p = self._expandWslPath(path, user)
            if p and p not in paths:
                paths.append(p)
        return paths

    def _modelDisplayName(self, path):
        filename = path.rstrip('/').split('/')[-1]
        return filename[:-5] if filename.lower().endswith('.gguf') else filename

    def _isModelCandidate(self, path):
        name = path.rstrip('/').split('/')[-1].lower()
        if not name.endswith('.gguf'):
            return False
        ignored_prefixes = ('ggml-vocab-',)
        ignored_parts = ('/tests/', '/test-models/')
        if name.startswith(ignored_prefixes):
            return False
        return not any(part in path.lower() for part in ignored_parts)

    def _addUniqueModel(self, models, name, path):
        candidate = name
        idx = 2
        while candidate in models and models[candidate] != path:
            candidate = f"{name} ({idx})"
            idx += 1
        models[candidate] = path

    def _scanWslModels(self, paths):
        script = r"""
for p in "$@"; do
    [ -d "$p" ] || continue
    find "$p" -maxdepth 4 -type f -iname '*.gguf' -print 2>/dev/null
done
"""
        result = subprocess.run(
            ['wsl', '-d', DISTRO, '--', 'bash', '-s', '--', *paths],
            input=script.encode('utf-8'),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        output = decodeProcessOutput(result.stdout).replace('\x00', '')
        files = []
        seen = set()
        for line in output.splitlines():
            path = line.strip()
            if path.lower().endswith('.gguf') and path not in seen:
                files.append(path)
                seen.add(path)
        return files, result.returncode, output

    def _setModelMaps(self, llm_models, mm_models, current_llm=None, current_mm=None):
        bi = self.basicInterface
        bi.llmPaths = llm_models
        bi.mmPaths = mm_models
        self._resetComboItems(bi.llmCombo, list(bi.llmPaths.keys()), current_llm)
        self._resetComboItems(bi.mmCombo, ['无'] + list(bi.mmPaths.keys()), current_mm or '无')

    def refreshLocalModels(self):
        bi = self.basicInterface
        current_llm = bi.llmCombo.currentText()
        current_mm = bi.mmCombo.currentText()
        paths = self._expandedModelSearchPaths()
        if not paths:
            InfoBar.warning(
                title='没有搜索路径',
                content='请先填写模型搜索路径',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=2500,
                parent=self
            )
            return
        try:
            files, rc, output = self._scanWslModels(paths)
        except Exception as e:
            InfoBar.error(
                title='刷新失败',
                content=f'扫描 WSL 模型失败: {e}',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=4000,
                parent=self
            )
            return

        llm_models = {}
        mm_models = {}
        for path in files:
            if not self._isModelCandidate(path):
                continue
            name = self._modelDisplayName(path)
            if 'mmproj' in name.lower():
                self._addUniqueModel(mm_models, name, path)
            else:
                self._addUniqueModel(llm_models, name, path)

        if not llm_models and not mm_models:
            InfoBar.warning(
                title='未找到模型',
                content='搜索路径里没有发现 .gguf 文件',
                orient=Qt.Horizontal, isClosable=False,
                position=InfoBarPosition.TOP, duration=3500,
                parent=self
            )
            return

        self._setModelMaps(
            llm_models,
            mm_models,
            current_llm if current_llm in llm_models else next(iter(llm_models), None),
            current_mm if current_mm in mm_models else ('无' if not mm_models else next(iter(mm_models))),
        )
        self._updateCommandPreview()
        self._saveConfig()
        InfoBar.success(
            title='模型列表已刷新',
            content=f'发现 {len(llm_models)} 个大语言模型，{len(mm_models)} 个多模态模型',
            orient=Qt.Horizontal, isClosable=False,
            position=InfoBarPosition.TOP, duration=3000,
            parent=self
        )

    def _configPath(self):
        return os.path.join(CONFIG_DIR, 'config.json')

    def _saveConfig(self):
        bi = self.basicInterface
        mi = self.modelInterface
        si = self.serverInterface
        cfg = {
            'exec_path': bi.execPathEdit.text(),
            'model_search_path': self._modelSearchPaths(),
            'llm_model': bi.llmCombo.currentText(),
            'mm_model': bi.mmCombo.currentText(),
            'ctx_length': mi.ctxEdit.text(),
            'predict_length': mi.predictEdit.text(),
            'temperature': mi.tempSpin.value(),
            'top_p': mi.topPSpin.value(),
            'top_k': mi.topKSpin.value(),
            'repeat_penalty': mi.repeatPenaltySpin.value(),
            'repeat_last_n': mi.repeatLastNSpin.value(),
            'cache_type_k': mi.cacheKCombo.currentText(),
            'cache_type_v': mi.cacheVCombo.currentText(),
            'cache_ram': mi.cacheRamEdit.text(),
            'flash_attention': mi.faCombo.currentText(),
            'image_min_tokens': mi.imgMinEdit.text(),
            'ngl': mi.nglSpin.value(),
            'main_gpu': mi.mainGpuSpin.value(),
            'tensor_split': mi.tsSplitEdit.text(),
            'nommap': mi.nommapCombo.currentText(),
            'numa': mi.numaCombo.currentText(),
            'host': si.hostEdit.text(),
            'port': si.portSpin.value(),
            'api_key': si.apiKeyEdit.text(),
            'threads': si.threadsSpin.value(),
            'batch_size': si.batchSpin.value(),
            'ubatch_size': si.ubatchSpin.value(),
            'parallel': si.parallelSpin.value(),
            'timeout': si.timeoutSpin.value(),
            'log_verbosity': self._normalizedLogVerbosity(),
            'metrics': si.metricsCombo.currentText(),
            'webui': si.webuiCombo.currentText(),
            'models': {
                'llm': bi.llmPaths,
                'mm': bi.mmPaths,
            },
            'launcher': dict(self._launcherConfig),
        }
        try:
            os.makedirs(os.path.dirname(self._configPath()), exist_ok=True)
            with open(self._configPath(), 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _loadConfig(self):
        path = self._configPath() if os.path.exists(self._configPath()) else self._defaultConfigPath()
        cfg = self._readJsonFile(path, {})
        if not cfg:
            return
        self._applyRuntimeConfig(cfg)

    def _applyRuntimeConfig(self, cfg):
        bi = self.basicInterface
        mi = self.modelInterface
        si = self.serverInterface
        models = cfg.get('models', {})
        if isinstance(models, dict):
            llm_models = models.get('llm', {})
            mm_models = models.get('mm', {})
            if isinstance(llm_models, dict) or isinstance(mm_models, dict):
                self._setModelMaps(
                    llm_models if isinstance(llm_models, dict) else bi.llmPaths,
                    mm_models if isinstance(mm_models, dict) else bi.mmPaths,
                    cfg.get('llm_model'),
                    cfg.get('mm_model'),
                )
        bi.execPathEdit.setText(cfg.get('exec_path', bi.execPathEdit.text()))
        search_path = cfg.get('model_search_path') or cfg.get('search_path')
        if isinstance(search_path, list):
            bi.modelSearchPathEdit.setText('; '.join(search_path))
        elif isinstance(search_path, str):
            bi.modelSearchPathEdit.setText(search_path)
        bi.llmCombo.setCurrentText(cfg.get('llm_model', bi.llmCombo.currentText()))
        bi.mmCombo.setCurrentText(cfg.get('mm_model', bi.mmCombo.currentText()))
        mi.ctxEdit.setText(cfg.get('ctx_length', mi.ctxEdit.text()))
        mi.predictEdit.setText(cfg.get('predict_length', mi.predictEdit.text()))
        mi.tempSpin.setValue(cfg.get('temperature', mi.tempSpin.value()))
        mi.topPSpin.setValue(cfg.get('top_p', mi.topPSpin.value()))
        mi.topKSpin.setValue(cfg.get('top_k', mi.topKSpin.value()))
        mi.repeatPenaltySpin.setValue(cfg.get('repeat_penalty', mi.repeatPenaltySpin.value()))
        mi.repeatLastNSpin.setValue(cfg.get('repeat_last_n', mi.repeatLastNSpin.value()))
        mi.cacheKCombo.setCurrentText(cfg.get('cache_type_k', mi.cacheKCombo.currentText()))
        mi.cacheVCombo.setCurrentText(cfg.get('cache_type_v', mi.cacheVCombo.currentText()))
        mi.cacheRamEdit.setText(cfg.get('cache_ram', mi.cacheRamEdit.text()))
        mi.faCombo.setCurrentText(cfg.get('flash_attention', mi.faCombo.currentText()))
        mi.imgMinEdit.setText(cfg.get('image_min_tokens') or mi.imgMinEdit.text())
        mi.nglSpin.setValue(cfg.get('ngl', mi.nglSpin.value()))
        mi.mainGpuSpin.setValue(cfg.get('main_gpu', mi.mainGpuSpin.value()))
        mi.tsSplitEdit.setText(cfg.get('tensor_split', mi.tsSplitEdit.text()))
        nommap = cfg.get('nommap', mi.nommapCombo.currentText())
        if nommap in ('启用', '关闭', 'no-mmap'):
            nommap = 'no-mmap'
        elif nommap == 'enable-mmap':
            nommap = 'enable-mmap'
        mi.nommapCombo.setCurrentText(nommap)
        mi.numaCombo.setCurrentText(cfg.get('numa', mi.numaCombo.currentText()))
        si.hostEdit.setText(cfg.get('host', si.hostEdit.text()))
        si.portSpin.setValue(cfg.get('port', si.portSpin.value()))
        si.apiKeyEdit.setText(cfg.get('api_key', si.apiKeyEdit.text()))
        si.threadsSpin.setValue(cfg.get('threads', si.threadsSpin.value()))
        si.batchSpin.setValue(cfg.get('batch_size', si.batchSpin.value()))
        si.ubatchSpin.setValue(cfg.get('ubatch_size', si.ubatchSpin.value()))
        si.parallelSpin.setValue(cfg.get('parallel', si.parallelSpin.value()))
        si.timeoutSpin.setValue(cfg.get('timeout', si.timeoutSpin.value()))
        si.verboseCombo.setCurrentText(self._normalizedLogVerbosity(cfg.get('log_verbosity', cfg.get('verbose', si.verboseCombo.currentText()))))
        si.metricsCombo.setCurrentText(cfg.get('metrics', si.metricsCombo.currentText()))
        si.webuiCombo.setCurrentText(cfg.get('webui', si.webuiCombo.currentText()))

    def _resetComboItems(self, combo, items, current=None):
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        if current is not None:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    def applyDeployResult(self, result):
        bi = self.basicInterface
        mi = self.modelInterface
        si = self.serverInterface

        llm_name = result.get('llm_model_name') or 'Qwen3.5-27B-UD-Q4_K_XL'
        llm_path = result.get('llm_model_path') or ''
        mm_name = result.get('mm_model_name') or 'Qwen3.5-mmproj-F16'
        mm_path = result.get('mm_model_path') or ''

        if llm_path:
            bi.llmPaths[llm_name] = llm_path
        if mm_path:
            bi.mmPaths[mm_name] = mm_path

        self._resetComboItems(bi.llmCombo, list(bi.llmPaths.keys()), llm_name)
        self._resetComboItems(bi.mmCombo, ['无'] + list(bi.mmPaths.keys()), mm_name if mm_path else '无')

        search_paths = self._modelSearchPaths()
        result_search_paths = result.get('model_search_path')
        if isinstance(result_search_paths, str):
            result_search_paths = [result_search_paths]
        elif not isinstance(result_search_paths, list):
            result_search_paths = []
        for path in [
            *result_search_paths,
            result.get('model_dir'),
            os.path.dirname(llm_path) if llm_path else '',
            os.path.dirname(mm_path) if mm_path else '',
        ]:
            if path and path not in search_paths:
                search_paths.append(path)
        bi.modelSearchPathEdit.setText('; '.join(search_paths))

        exec_path = result.get('exec_path')
        if exec_path:
            bi.execPathEdit.setText(exec_path)

        if result.get('ctx_length_k'):
            mi.ctxEdit.setText(str(result.get('ctx_length_k')))
        if result.get('cache_type_k'):
            mi.cacheKCombo.setCurrentText(result.get('cache_type_k'))
        if result.get('cache_type_v'):
            mi.cacheVCombo.setCurrentText(result.get('cache_type_v'))
        if result.get('batch_size'):
            si.batchSpin.setValue(int(result.get('batch_size')))
        if result.get('parallel'):
            si.parallelSpin.setValue(int(result.get('parallel')))
        if result.get('host'):
            si.hostEdit.setText(result.get('host'))
        if result.get('port'):
            si.portSpin.setValue(int(result.get('port')))
        if result.get('api_key'):
            si.apiKeyEdit.setText(result.get('api_key'))
        si.metricsCombo.setCurrentText('启用')
        si.verboseCombo.setCurrentText('warn')

        self._updateCommandPreview()
        self._saveConfig()
        InfoBar.success(
            title='配置已更新',
            content='部署得到的模型路径和启动参数已写入 config.json',
            orient=Qt.Horizontal, isClosable=False,
            position=InfoBarPosition.TOP, duration=3000,
            parent=self
        )

    def closeEvent(self, event):
        self._saveConfig()
        super().closeEvent(event)


if __name__ == '__main__':
    setWindowsAppId()
    app.setWindowIcon(getAppIcon())
    setTheme(Theme.DARK)
    w = MainWindow()
    w.show()
    app.exec()
