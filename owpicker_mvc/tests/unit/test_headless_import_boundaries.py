import builtins
import importlib
import sys
import unittest


class TestHeadlessImportBoundaries(unittest.TestCase):
    def test_controller_map_package_imports_without_pyside6(self):
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if str(name).startswith("PySide6"):
                raise ModuleNotFoundError("No module named 'PySide6'")
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            if "controller.map" in sys.modules:
                del sys.modules["controller.map"]
            importlib.import_module("controller.map")
        finally:
            builtins.__import__ = original_import

    def test_shutdown_manager_imports_without_pyside6(self):
        original_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if str(name).startswith("PySide6"):
                raise ModuleNotFoundError("No module named 'PySide6'")
            return original_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import
        try:
            if "controller.shutdown_manager" in sys.modules:
                del sys.modules["controller.shutdown_manager"]
            __import__("controller.shutdown_manager", fromlist=["*"])
        finally:
            builtins.__import__ = original_import


if __name__ == "__main__":
    unittest.main()
