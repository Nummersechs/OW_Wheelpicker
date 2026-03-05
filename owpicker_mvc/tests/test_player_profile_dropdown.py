import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from controller.main_window import MainWindow
from services.state_store import ModeStateStore
from utils import qt_runtime
from view.profile_dropdown import PlayerProfileDropdown


class _DummyStateSync:
    def __init__(self):
        self.calls = []

    def save_state(self, **kwargs):
        self.calls.append(dict(kwargs))


class TestPlayerProfileDropdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        qt_runtime.apply_preferred_app_font(cls._app)

    def test_widget_sets_profiles_and_order(self):
        widget = PlayerProfileDropdown()
        widget.set_profiles(["Main", "PUG", "Scrim"], 1)
        self.assertEqual(widget.current_profile_index(), 1)
        self.assertEqual(widget.current_profile_name(), "PUG")
        self.assertEqual(widget.current_order(), [0, 1, 2])

    def test_widget_emits_activate_and_rename(self):
        widget = PlayerProfileDropdown()
        widget.set_profiles(["Main", "PUG", "Scrim"], 0)
        activated = []
        renamed = []
        widget.profileActivated.connect(lambda idx: activated.append(idx))
        widget.profileRenamed.connect(lambda idx, name: renamed.append((idx, name)))
        widget.list_widget.setCurrentRow(2)
        widget.name_edit.setText("Tryout")
        widget.name_edit.editingFinished.emit()
        self.assertIn(2, activated)
        self.assertEqual(renamed[-1], (2, "Tryout"))

    def test_outside_click_clears_focus_and_closes_popup(self):
        widget = PlayerProfileDropdown()
        widget.set_profiles(["Main", "PUG", "Scrim"], 0)
        widget.resize(260, 34)
        widget.move(120, 120)
        widget._expanded = True

        press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(2.0, 2.0),
            QtCore.QPointF(2.0, 2.0),
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        widget.eventFilter(self._app, press)
        self._app.processEvents()

        self.assertFalse(widget._expanded)
        self.assertFalse(widget.popup.isVisible())
        widget.close()

    def _make_window_stub(self):
        mw = MainWindow.__new__(MainWindow)
        mw._player_profile_combo_syncing = False
        mw._restoring_state = False
        mw.current_mode = "players"
        mw.hero_ban_active = False
        mw._capture_calls = []
        mw._load_calls = []
        mw._capture_players_state_for_profiles = lambda: mw._capture_calls.append(True)
        mw._load_mode_into_wheels = lambda mode, hero_ban=False: mw._load_calls.append((mode, hero_ban))
        mw.state_sync = _DummyStateSync()
        mw._state_store = ModeStateStore.from_saved({})
        mw.player_profile_dropdown = PlayerProfileDropdown()
        mw._refresh_player_profile_combo()
        return mw

    def test_reorder_from_widget_order_persists_immediately(self):
        mw = self._make_window_stub()
        names = ["Main", "PUG", "Scrim", "Tryout", "Flex", "Test"]
        for idx, name in enumerate(names):
            mw._state_store.rename_player_profile(idx, name)
        mw._refresh_player_profile_combo()

        dropdown = mw.player_profile_dropdown
        lw = dropdown.list_widget
        item = lw.takeItem(1)
        lw.insertItem(0, item)
        dropdown._emit_order_changed()

        with patch.object(mw.state_sync, "save_state", wraps=mw.state_sync.save_state) as save_state:
            mw._on_player_profile_reordered(dropdown.current_order())
            save_state.assert_called_with(sync=False, immediate=True)

        self.assertEqual(mw._state_store.get_player_profile_names()[0], "PUG")
        self.assertEqual(mw._state_store.get_player_profile_names()[1], "Main")

    def test_profile_changed_and_renamed_through_mainwindow_handlers(self):
        mw = self._make_window_stub()
        self.assertTrue(mw._state_store.set_active_player_profile(1))
        mw._refresh_player_profile_combo()
        mw._on_player_profile_changed(0)
        self.assertTrue(mw._capture_calls)
        self.assertTrue(mw._load_calls)

        mw._on_player_profile_name_edited(0, "Main Team")
        self.assertEqual(mw._state_store.get_player_profile_names()[0], "Main Team")
        self.assertTrue(any(call.get("sync") is False for call in mw.state_sync.calls))


if __name__ == "__main__":
    unittest.main()
