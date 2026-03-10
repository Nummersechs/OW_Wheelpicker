from __future__ import annotations

import i18n
from utils import theme as theme_util


class MapUIPresentationController:
    def __init__(self, owner) -> None:
        self._owner = owner

    def set_language(self, lang: str) -> None:
        owner = self._owner
        owner.language = lang
        i18n.set_language(lang)
        owner.lbl_map_types.setText(i18n.t("map.types"))
        owner.btn_edit_map_types.setText(i18n.t("map.edit_types"))
        owner.btn_edit_map_types.setToolTip(i18n.t("map.edit_types_tooltip"))
        owner._styling.apply_map_control_widths()
        for wheel in owner.map_lists.values():
            wheel.set_language(lang)
            wheel.set_spin_button_text(i18n.t("wheel.spin_single_map"))
        owner.map_main.set_language(lang)
        owner.map_main.set_spin_button_text(i18n.t("wheel.spin_map"))
        owner._editor.update_language()

    def apply_theme(self, theme: theme_util.Theme) -> None:
        self._owner._styling.apply_theme(theme)

