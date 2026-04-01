from importlib import import_module

__all__ = ["ConfigError", "RuntimeConfig", "load_runtime_config"]


def __getattr__(name: str):
    if name in __all__:
        module = import_module("config.runtime")
        return getattr(module, name)
    raise AttributeError(f"module 'config' has no attribute {name!r}")
