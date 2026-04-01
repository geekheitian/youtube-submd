import os
import sys
import unittest
from pathlib import Path

from config import ConfigError, load_runtime_config


class ApiFoundationTests(unittest.TestCase):
    def test_api_and_worker_modules_are_importable(self):
        import importlib.util

        project_root = Path(__file__).resolve().parent.parent.parent
        api_spec = importlib.util.spec_from_file_location(
            "api.app", project_root / "api" / "app.py"
        )
        api_module = importlib.util.module_from_spec(api_spec)
        worker_spec = importlib.util.spec_from_file_location(
            "workers.celery_app", project_root / "workers" / "celery_app.py"
        )
        worker_module = importlib.util.module_from_spec(worker_spec)
        api_spec.loader.exec_module(api_module)
        worker_spec.loader.exec_module(worker_module)
        self.assertTrue(callable(api_module.create_app))
        self.assertTrue(callable(worker_module.create_celery_app))

    def test_runtime_config_requires_backend_env_when_requested(self):
        previous_database = os.environ.pop("DATABASE_URL", None)
        previous_redis = os.environ.pop("REDIS_URL", None)
        try:
            with self.assertRaises(ConfigError):
                load_runtime_config(require_backends=True)
        finally:
            if previous_database is not None:
                os.environ["DATABASE_URL"] = previous_database
            if previous_redis is not None:
                os.environ["REDIS_URL"] = previous_redis

    def test_runtime_config_uses_defaults_without_required_backends(self):
        config = load_runtime_config(require_backends=False)
        self.assertEqual(config.api_host, "127.0.0.1")
        self.assertEqual(config.api_port, 8000)
        self.assertEqual(config.api_key_header, "X-API-Key")


if __name__ == "__main__":
    unittest.main()
