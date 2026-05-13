from helpers.config_loader import load_runtime_config, get_default_config


_initialized = False


def apply_runtime_config(values):
    for key, value in values.items():
        globals()[key] = value


def initialize_runtime(config_path=None):
    values = load_runtime_config(config_path)
    apply_runtime_config(values)
    global _initialized
    _initialized = True
    return values["config_path"]


def is_initialized():
    return _initialized


apply_runtime_config(get_default_config())
config_path = None
