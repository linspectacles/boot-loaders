#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles Boot Loaders - privileged inspection window
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

from __future__ import annotations

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from .applet import BootInspectorWidget, CATEGORIES, collect_bootctl
from .privilege import helper_contract, helper_status_details, install_or_update_helper, remove_helper

BG = "#171717"
PANEL = "#1e1e1e"
FG = "#dcdcdc"
BORDER = "#666"
AMBER_DARK = "#3a2d13"
AMBER_DEEP = "#6a4b0c"
AMBER = "#d6a23d"
AMBER_LIGHT = "#f2d18b"


def _state_word(details):
    if details.get("ready"):
        return "Installed and verified"
    if details.get("installed"):
        return "Installed — update/repair required"
    return "Not installed"


def _signature(records):
    rows = []
    for record in records or []:
        details = tuple((str(k), str(v)) for k, v in (record.get("_details") or []))
        rows.append((str(record.get("category") or ""), str(record.get("name") or ""), details))
    return tuple(sorted(rows))


def _by_category(records):
    result = {category: [] for category in CATEGORIES if category != "All Categories"}
    for record in records or []:
        result.setdefault(str(record.get("category") or "Other"), []).append(record)
    return result


def _comparison_rows(ordinary_result, elevated_result):
    ordinary = ordinary_result or {"ok": False, "records": [], "message": "Not scanned"}
    elevated = elevated_result or {"ok": False, "records": [], "message": "Not scanned"}
    o_records = list(ordinary.get("records") or [])
    e_records = list(elevated.get("records") or [])

    def describe(result, records):
        if not result.get("ok"):
            return str(result.get("message") or "Unavailable")
        return f"Available — {len(records)} record(s)"

    def compare(o, e, o_ok=True, e_ok=True):
        if not e_ok:
            return "Elevated unavailable"
        if not o_ok and e_ok:
            return "Access added"
        if _signature(o) == _signature(e):
            return "Same — no additional access observed"
        if len(e) > len(o):
            return f"Access expanded (+{len(e) - len(o)} record(s))"
        return "Different result — inspect Boot Loaders"

    rows = [(
        "Overall",
        describe(ordinary, o_records),
        describe(elevated, e_records),
        compare(o_records, e_records, bool(ordinary.get("ok")), bool(elevated.get("ok"))),
    )]
    o_by = _by_category(o_records)
    e_by = _by_category(e_records)
    for category in [c for c in CATEGORIES if c != "All Categories"]:
        o = o_by.get(category, [])
        e = e_by.get(category, [])
        rows.append((
            category,
            f"{len(o)} record(s)" if ordinary.get("ok") else "Unavailable",
            f"{len(e)} record(s)" if elevated.get("ok") else "Unavailable",
            compare(o, e, bool(ordinary.get("ok")), bool(elevated.get("ok"))),
        ))
    return rows


class ComparisonReportDialog(QDialog):
    """Observed ordinary-vs-elevated report; intentionally separate from the inspector surface."""

    def __init__(self, ordinary_result, elevated_result, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparison Report — Boot Loaders")
        self.resize(1120, 560)
        self.setMinimumSize(820, 420)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG}; color: {FG}; }}
            QLabel {{ color: {FG}; }}
            QTableWidget {{ background: {PANEL}; color: {FG}; border: 1px solid {BORDER}; }}
            QTableWidget::item:selected {{ background: {AMBER_DEEP}; color: #fff4d2; }}
            QHeaderView::section {{ background: #252526; color: {FG}; border: 0; border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; padding: 5px; font-weight: 600; }}
            QPushButton {{ background: {PANEL}; color: {FG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 10px; }}
            QPushButton:hover {{ border-color: {AMBER}; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        heading = QLabel("Comparison Report")
        font = heading.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize(), 11))
        heading.setFont(font)
        root.addWidget(heading)

        note = QLabel("Observed comparison of ordinary-user and helper-backed bootctl status results from the latest privileged inspection.")
        note.setWordWrap(True)
        root.addWidget(note)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(["Category", "Standard access", "With helper", "Comparison"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        for index in range(4):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 210)
        table.setColumnWidth(1, 260)
        table.setColumnWidth(2, 260)
        table.setColumnWidth(3, 330)

        rows = _comparison_rows(ordinary_result, elevated_result)
        table.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            for column_index, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setForeground(QColor(AMBER_LIGHT))
                table.setItem(row_index, column_index, item)
        root.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)


class PrivilegedInspectionDialog(QDialog):
    session_state_changed = pyqtSignal()
    closing = pyqtSignal(bool)

    def __init__(self, client, metadata_font="", parent=None):
        super().__init__(parent)
        self.setObjectName("PrivilegedInspectionDialog")
        self.setWindowTitle("Privileged Inspection — Boot Loaders")
        self.resize(1220, 820)
        self.setMinimumSize(900, 640)
        self.client = client
        self.metadata_font = metadata_font or ""
        self.contract = helper_contract()
        self.session_ever_active = False
        self._closing = False
        self._scan_after_authorize = False
        self._last_state = self.client.state
        self._ordinary_result = None
        self._elevated_result = None

        self._build_ui()

        # Like the SELinux privileged surface, the replicated inspector is usable
        # before authorization with ordinary-user visibility.
        self.inspector.load_from_result(collect_bootctl(elevated=False), elevated=False)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._refresh_helper_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            QDialog#PrivilegedInspectionDialog {{ background: {BG}; color: {FG}; }}
            QFrame#PrivilegeHeader {{ background: {AMBER_DARK}; border: 1px solid {AMBER}; border-radius: 5px; }}
            QLabel {{ color: {FG}; }}
            QLabel#PrivilegeTitle {{ color: {AMBER_LIGHT}; font-weight: 700; }}
            QLabel#PrivilegeState {{ color: {AMBER_LIGHT}; font-weight: 600; }}
            QPushButton {{ background: {PANEL}; color: {FG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 5px 10px; }}
            QPushButton:hover {{ border-color: {AMBER}; }}
            QPushButton#PrivilegePrimary {{ background: {AMBER_DEEP}; color: #fff4d2; border: 1px solid {AMBER}; font-weight: 600; }}
            QPushButton#PrivilegeActive {{ background: {AMBER}; color: #171717; border: 1px solid {AMBER_LIGHT}; font-weight: 700; }}
            QPushButton:disabled {{ color: #777; border-color: #444; background: #1b1b1b; }}
            QTableWidget, QTextEdit, QLineEdit, QComboBox {{ background: {PANEL}; color: {FG}; border: 1px solid {BORDER}; }}
            QTableWidget::item:selected {{ background: {AMBER_DEEP}; color: #fff4d2; }}
            QHeaderView::section {{ background: #252526; color: {FG}; border: 0; border-right: 1px solid {BORDER}; border-bottom: 1px solid {BORDER}; padding: 5px; font-weight: 600; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("PrivilegeHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(12, 9, 12, 9)
        title = QLabel("Privileged Inspection — Boot Loaders")
        title.setObjectName("PrivilegeTitle")
        font = title.font()
        font.setBold(True)
        font.setPointSize(max(font.pointSize(), 11))
        title.setFont(font)
        header_layout.addWidget(title)
        note = QLabel(
            "This window mirrors Boot Loaders in an elevated context. Inspect with Privileged Access starts the fixed read-only helper and immediately refreshes the boot-loader inventory. Closing this window ends the helper session."
        )
        note.setWordWrap(True)
        header_layout.addWidget(note)
        root.addWidget(header)

        status_row = QHBoxLayout()
        self.helper_status_label = QLabel()
        self.helper_status_label.setWordWrap(True)
        status_row.addWidget(self.helper_status_label, 1)
        self.session_label = QLabel("Session: Inactive")
        self.session_label.setObjectName("PrivilegeState")
        status_row.addWidget(self.session_label)
        root.addLayout(status_row)

        action_row = QHBoxLayout()
        self.install_button = QPushButton("Install Helper...")
        self.install_button.clicked.connect(self._install_helper)
        action_row.addWidget(self.install_button)
        self.remove_button = QPushButton("Remove Helper...")
        self.remove_button.clicked.connect(self._remove_helper)
        action_row.addWidget(self.remove_button)
        action_row.addStretch(1)
        self.inspect_button = QPushButton("Inspect with Privileged Access...")
        self.inspect_button.setObjectName("PrivilegePrimary")
        self.inspect_button.clicked.connect(self._inspect)
        action_row.addWidget(self.inspect_button)
        self.comparison_button = QPushButton("Comparison Report...")
        self.comparison_button.clicked.connect(self._show_comparison_report)
        self.comparison_button.setEnabled(False)
        action_row.addWidget(self.comparison_button)
        root.addLayout(action_row)

        self.inspector = BootInspectorWidget(
            parent=self, autoload=False, privilege_client=self.client, privileged_surface=True
        )
        self.inspector.apply_host_settings({"metadata_font": self.metadata_font, "hidden_columns": []})
        # Match the authoritative SELinux privileged metadata/status treatment.
        self.inspector.set_theme_colors(
            "#1e1e1e",
            "#dcdcdc",
            "#f2d18b",
            "#e5bd70",
            "#3a2d13",
            "#f2d18b",
        )
        # In the elevated surface Refresh List performs a paired ordinary/elevated
        # refresh so the Comparison Report remains tied to the displayed result.
        try:
            self.inspector.refresh_btn.clicked.disconnect()
        except TypeError:
            pass
        self.inspector.refresh_btn.clicked.connect(self._refresh_inventory)
        root.addWidget(self.inspector, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        root.addWidget(buttons)

    def _refresh_helper_ui(self):
        details = helper_status_details()
        self.helper_status_label.setText(
            f"Helper: {_state_word(details)}"
            + (f" · {details.get('installed_version')}" if details.get("installed_version") else "")
        )
        active = bool(self.client.enabled)
        self.install_button.setEnabled(not active)
        self.remove_button.setVisible(bool(details.get("installed")))
        self.remove_button.setEnabled(not active)
        if active:
            self.inspect_button.setText("Privileged Access: Active")
            self.inspect_button.setObjectName("PrivilegeActive")
            self.inspect_button.setEnabled(False)
        elif self.client.state == "connecting":
            self.inspect_button.setText("Authorizing...")
            self.inspect_button.setObjectName("PrivilegePrimary")
            self.inspect_button.setEnabled(False)
        else:
            self.inspect_button.setText("Inspect with Privileged Access...")
            self.inspect_button.setObjectName("PrivilegePrimary")
            self.inspect_button.setEnabled(bool(details.get("ready")))
        self.inspect_button.style().unpolish(self.inspect_button)
        self.inspect_button.style().polish(self.inspect_button)
        self.comparison_button.setEnabled(
            self._ordinary_result is not None and self._elevated_result is not None
        )

    def _inspect(self):
        if self.client.enabled or self.client.state == "connecting":
            return
        ok, why = self.client.availability()
        if not ok:
            QMessageBox.information(self, "Privileged Inspection", why)
            self._refresh_helper_ui()
            return
        answer = QMessageBox.question(
            self,
            "Privileged Boot Inspection",
            "Start an ephemeral read-only privileged inspection session?\n\n"
            "PolicyKit will request authorization. Only fixed boot-loader / EFI status "
            "queries are available to the helper. Boot-loader inspection is refreshed "
            "automatically after authorization. Closing this window ends the helper session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._scan_after_authorize = True
        self.client.start_async()
        self.session_label.setText("Session: Authorizing…")
        self._refresh_helper_ui()
        self.session_state_changed.emit()

    def _refresh_inventory(self):
        if self.client.enabled:
            self._run_observed_inspection()
        else:
            self.inspector.load_from_result(collect_bootctl(elevated=False), elevated=False)

    def _run_observed_inspection(self):
        self._ordinary_result = collect_bootctl(elevated=False)
        self._elevated_result = collect_bootctl(self.client, elevated=True, timeout=20)
        self.inspector.load_from_result(self._elevated_result, elevated=True)
        self._refresh_helper_ui()

    def _show_comparison_report(self):
        if self._ordinary_result is None or self._elevated_result is None:
            QMessageBox.information(self, "Comparison Report", "Run privileged inspection first so there are paired ordinary and elevated results to compare.")
            return
        dialog = ComparisonReportDialog(self._ordinary_result, self._elevated_result, self)
        dialog.exec()

    def _poll(self):
        if self._closing:
            return
        state = self.client.state
        if state == "on" and self.client.enabled:
            newly_active = self._last_state != "on"
            self.session_ever_active = True
            self.session_label.setText("Session: Active")
            if newly_active and self._scan_after_authorize:
                self._scan_after_authorize = False
                QTimer.singleShot(0, self._run_observed_inspection)
        elif state == "connecting":
            self.session_label.setText("Session: Authorizing…")
        elif state == "error":
            self.session_label.setText("Session: Inactive — " + self.client.message)
            self._scan_after_authorize = False
        else:
            self.session_label.setText("Session: Inactive")
        self._last_state = state
        self._refresh_helper_ui()
        self.session_state_changed.emit()

    def _install_helper(self):
        details = helper_status_details()
        verb = "update or repair" if details.get("installed") else "install"
        answer = QMessageBox.question(
            self,
            "Boot Loaders Privileged Helper",
            f"{verb.capitalize()} the optional root-owned Boot Loaders helper?\n\n"
            "PolicyKit will request administrator authorization. The helper exposes only "
            "the fixed read-only boot-loader / EFI status query; the GUI itself is not elevated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.install_button.setEnabled(False)
        QApplication.processEvents()
        ok, message = install_or_update_helper()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Boot Loaders Privileged Helper", message
        )
        self._refresh_helper_ui()
        self.session_state_changed.emit()

    def _remove_helper(self):
        answer = QMessageBox.question(
            self,
            "Remove Boot Loaders Privileged Helper",
            "Remove the optional root-owned Boot Loaders helper?\n\n"
            "The normal read-only Boot Loaders will continue to work. PolicyKit will "
            "request administrator authorization for removal.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        ok, message = remove_helper()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Boot Loaders Privileged Helper", message
        )
        self._refresh_helper_ui()
        self.session_state_changed.emit()

    def closeEvent(self, event):
        # Match SELinux Inspector's proven ephemeral-window teardown ordering.
        if self._closing:
            event.accept()
            return

        self._closing = True
        self._timer.stop()
        try:
            self._timer.timeout.disconnect(self._poll)
        except (TypeError, RuntimeError):
            pass

        had_session = bool(self.session_ever_active or self.client.enabled)
        self._scan_after_authorize = False

        # End privilege synchronously before accepting the close.
        self.client.stop()
        self._ordinary_result = None
        self._elevated_result = None
        self.session_state_changed.emit()
        self.closing.emit(had_session)

        event.accept()
        super().closeEvent(event)

