"""Left-panel folder tree widget."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Custom data roles
_KEY_ROLE = Qt.ItemDataRole.UserRole
_FAV_ROLE = Qt.ItemDataRole.UserRole + 1


class _TreeWidget(QTreeWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._crate_paths_by_id: dict[int, list[str]] = {}

    def set_crate_paths(self, crate_paths_by_id: dict[int, list[str]]) -> None:
        self._crate_paths_by_id = {
            int(crate_id): list(paths) for crate_id, paths in crate_paths_by_id.items()
        }

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        mime = QMimeData()
        urls = []
        for item in items:
            key = item.data(0, _KEY_ROLE)
            if not isinstance(key, str) or not key.startswith("crate:"):
                continue
            try:
                crate_id = int(key[6:])
            except ValueError:
                continue
            urls.extend(QUrl.fromLocalFile(path) for path in self._crate_paths_by_id.get(crate_id, []))
        if urls:
            mime.setUrls(urls)
        return mime


class TreePane(QWidget):
    """Renders a folder tree from tree_rows() output and emits selection events."""

    folder_selected = Signal(str, bool)  # (key, is_favorites_branch)
    scan_requested = Signal()
    analyze_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree = _TreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setColumnCount(1)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

        scan_btn = QPushButton("Scan")
        analyze_btn = QPushButton("Analyze")
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(4, 4, 4, 4)
        btn_bar.addWidget(scan_btn)
        btn_bar.addWidget(analyze_btn)
        btn_bar.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)
        layout.addLayout(btn_bar)

        self._tree.currentItemChanged.connect(self._on_item_changed)
        scan_btn.clicked.connect(self.scan_requested)
        analyze_btn.clicked.connect(self.analyze_requested)

    def set_rows(self, rows: list[tuple], expand: bool = True) -> None:
        """Rebuild the tree from tree_rows() output."""
        self._tree.blockSignals(True)
        self._tree.clear()
        item_map: dict[str, QTreeWidgetItem] = {}

        for parent_key, key, label, is_fav in rows:
            item = QTreeWidgetItem([label])
            item.setData(0, _KEY_ROLE, key)
            item.setData(0, _FAV_ROLE, bool(is_fav))

            if parent_key is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item = item_map.get(parent_key)
                if parent_item is not None:
                    parent_item.addChild(item)
                else:
                    self._tree.addTopLevelItem(item)

            item_map[key] = item

        if expand:
            self._tree.expandAll()
        self._tree.blockSignals(False)

    def select_key(self, key: str) -> bool:
        """Programmatically select the tree item with the given key; return True on match."""
        it = self._tree.invisibleRootItem()
        stack = [it.child(i) for i in range(it.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _KEY_ROLE) == key:
                self._tree.setCurrentItem(item)
                return True
            stack.extend(item.child(i) for i in range(item.childCount()))
        return False

    def set_crate_paths(self, crate_paths_by_id: dict[int, list[str]]) -> None:
        self._tree.set_crate_paths(crate_paths_by_id)

    def _on_item_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        key: str = current.data(0, _KEY_ROLE)
        is_fav: bool = current.data(0, _FAV_ROLE)
        if key:
            self.folder_selected.emit(key, bool(is_fav))
