#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# LinSpectacles - Linux Inspector Suite
# Copyright (C) 2026 brunonlinespace
# GPL-3.0-or-later

from __future__ import annotations

APPLET_ID = "linspectacles-boot-loaders"
APPLET_NAME = "Boot Loaders"
APPLET_VERSION = "0.1.10"
APPLET_AUTHOR = "brunonlinespace"
APPLET_EDITOR = "brunonlinespace"
APPLET_ORGANIZATION_ID = "linspectacles"
APPLET_ORGANIZATION_URL = "https://github.com/linspectacles/"
APPLET_REPOSITORY = "https://github.com/linspectacles/boot-loaders"

import os
import re
import subprocess
from pathlib import Path

from PyQt6.QtCore import QSettings, QTimer, Qt, QUrl
from PyQt6.QtGui import QColor, QFontDatabase, QKeySequence, QPixmap, QShortcut, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from ._support import (
    BaseInspectorTab, apply_metadata_font, export_records_dialog, metadata_font_qss,
)
from .privilege import PrivilegeClient

SECTION_SYSTEM = "System"
SECTION_CURRENT = "Current Boot Loader"
SECTION_RANDOM = "Random Seed"
SECTION_ESP = "Available Boot Loaders on ESP"
SECTION_EFI = "Boot Loaders Listed in EFI Variables"

CATEGORIES = [
    "All Categories",
    "System",
    "Current Boot Loader",
    "Random Seed",
    "ESP Boot Loader",
    "EFI Boot Entry",
    "Other",
]


SOURCES_TEXT = """Boot Loaders is read-only. Its displayed facts come from these interfaces.

Boot-loader / firmware boot status
  bootctl status --no-pager

Structured presentation
  LinSpectacles parses the explicitly labelled sections and properties reported by
  bootctl into records for System, Current Boot Loader, Random Seed, boot
  loaders available on the ESP, boot loaders listed in EFI variables, and any
  additional labelled sections reported by bootctl.

Privileged inspection
  Optional fixed helper: /usr/libexec/linspectacles-boot-helper
  The helper can run only the same fixed read-only bootctl status --no-pager
  query with elevated visibility. It has no arbitrary command API and no
  arbitrary file-read API.

Raw Data
  Raw Data shows the complete text retained from the current bootctl acquisition.
  Opening, copying, or exporting Raw Data does not rerun bootctl.

Important distinctions
  System, Current Boot Loader and Random Seed are singleton status sections.
  ESP Boot Loader and EFI Boot Entry are collections parsed from the matching
  bootctl sections. Boot Loaders does not change firmware variables, boot
  entries, the ESP, Secure Boot state, or boot-loader configuration.
"""

_KEY_VALUE_RE = re.compile(r"^\s*([^:]+?):\s*(.*)$")
_TREE_PREFIX_RE = re.compile(r"^[\s│├└─┬┼]+")


def _clean_value(value: str) -> str:
    text = str(value or "").strip()
    text = _TREE_PREFIX_RE.sub("", text).strip()
    return text


def _details_dict(details):
    result = {}
    for key, value in details:
        if key not in result:
            result[key] = value
    return result


def _basename_from_reported_path(value: str) -> str:
    text = _clean_value(value)
    # Product/version text is often appended in parentheses. Keep it in details,
    # but use the path-like portion for the compact record name.
    path_part = text.split(" (", 1)[0].strip()
    if path_part:
        name = Path(path_part).name
        if name:
            return name
    return text or "ESP Boot Loader"


def _summary_for(category: str, details) -> str:
    values = _details_dict(details)
    if category == "System":
        firmware = values.get("Firmware") or values.get("Firmware Arch") or ""
        secure = values.get("Secure Boot") or ""
        parts = []
        if firmware:
            parts.append(firmware)
        if secure:
            parts.append(f"Secure Boot: {secure}")
        return " · ".join(parts) or "Reported system boot environment"
    if category == "Current Boot Loader":
        return values.get("Product") or values.get("File") or "Reported current boot loader"
    if category == "Random Seed":
        exists = values.get("Exists") or values.get("System Token") or ""
        return f"Exists: {exists}" if exists else "Reported random-seed state"
    if category == "ESP Boot Loader":
        return values.get("File") or values.get("ESP") or "Reported ESP boot loader"
    if category == "EFI Boot Entry":
        status = values.get("Status") or ""
        entry_id = values.get("ID") or ""
        return " · ".join(part for part in (entry_id, status) if part) or "Reported EFI boot entry"
    return details[0][1] if details else "Reported boot-loader section"


def parse_bootctl_status(text: str):
    """Convert bootctl's human-readable sections into LinSpectacles records.

    The parser is intentionally conservative: it structures only what bootctl
    explicitly labels and keeps the matching raw lines in each record.
    """
    sections = []
    current = None
    for raw in (text or "").splitlines():
        line = raw.rstrip("\n")
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            current = {"name": line.strip()[:-1], "lines": [], "raw_lines": [line]}
            sections.append(current)
        elif current is not None:
            current["raw_lines"].append(line)
            if line.strip():
                current["lines"].append(line)

    records = []
    for section in sections:
        section_name = section["name"]
        lines = section["lines"]
        raw_section = "\n".join(section.get("raw_lines") or [f"{section_name}:"]).rstrip("\n")
        parsed = []
        for line in lines:
            match = _KEY_VALUE_RE.match(line)
            if match:
                parsed.append((match.group(1).strip(), _clean_value(match.group(2))))
            elif parsed and line.strip():
                key, previous = parsed[-1]
                continuation = _clean_value(line)
                if continuation:
                    parsed[-1] = (key, previous + "\n" + continuation)

        if section_name in (SECTION_SYSTEM, SECTION_CURRENT, SECTION_RANDOM):
            category = {
                SECTION_SYSTEM: "System",
                SECTION_CURRENT: "Current Boot Loader",
                SECTION_RANDOM: "Random Seed",
            }[section_name]
            details = parsed or [("Section", section_name), ("Status", "No labelled properties were parsed.")]
            records.append({
                "name": section_name,
                "category": category,
                "summary": _summary_for(category, details),
                "_section": section_name,
                "_details": details,
                "_raw_section": raw_section,
            })
            continue

        if section_name == SECTION_ESP:
            esp_value = ""
            pending = []
            for key, value in parsed:
                if key == "ESP":
                    esp_value = value
                    pending = [("ESP", value)]
                elif key == "File":
                    details = list(pending)
                    details.append(("File", value))
                    name = _basename_from_reported_path(value)
                    records.append({
                        "name": name,
                        "category": "ESP Boot Loader",
                        "summary": value or esp_value,
                        "_section": section_name,
                        "_details": details,
                        "_raw_section": raw_section,
                    })
                else:
                    pending.append((key, value))
            # If bootctl reported the section but no File key, retain it as one record.
            if not any(r.get("_section") == section_name for r in records):
                details = parsed or [("Section", section_name), ("Status", "No labelled properties were parsed.")]
                records.append({
                    "name": SECTION_ESP,
                    "category": "ESP Boot Loader",
                    "summary": _summary_for("ESP Boot Loader", details),
                    "_section": section_name,
                    "_details": details,
                    "_raw_section": raw_section,
                })
            continue

        if section_name == SECTION_EFI:
            groups = []
            current_group = []
            for key, value in parsed:
                if key == "Title" and current_group:
                    groups.append(current_group)
                    current_group = []
                current_group.append((key, value))
            if current_group:
                groups.append(current_group)
            if not groups:
                groups = [[("Section", section_name), ("Status", "No labelled properties were parsed.")]]
            for details in groups:
                values = _details_dict(details)
                name = values.get("Title") or values.get("ID") or "EFI Boot Entry"
                records.append({
                    "name": name,
                    "category": "EFI Boot Entry",
                    "summary": _summary_for("EFI Boot Entry", details),
                    "_section": section_name,
                    "_details": details,
                    "_raw_section": raw_section,
                })
            continue

        # Preserve unexpected bootctl sections without pretending to understand them.
        details = parsed or [("Section", section_name), ("Status", "No labelled properties were parsed.")]
        records.append({
            "name": section_name,
            "category": "Other",
            "summary": _summary_for("Other", details),
            "_section": section_name,
            "_details": details,
            "_raw_section": raw_section,
        })
    return records


def collect_bootctl(privilege_client=None, elevated=False, timeout=15):
    if elevated:
        if privilege_client is None or not privilege_client.enabled:
            return {"ok": False, "state": "restricted", "message": "Privileged helper session is not active.", "text": "", "records": []}
        response = privilege_client.request("bootctl_status", timeout=max(3.0, float(timeout) + 2.0))
        if not response:
            return {"ok": False, "state": "error", "message": privilege_client.message, "text": "", "records": []}
        if response.get("ok") is False:
            return {"ok": False, "state": "error", "message": str(response.get("error") or "Privileged bootctl query failed."), "text": "", "records": []}
        text = (response.get("stdout") or response.get("stderr") or "").strip()
        rc = int(response.get("returncode", 0))
        records = parse_bootctl_status(text)
        if text:
            return {"ok": True, "state": "observed", "message": f"Elevated bootctl returned {len(records)} structured record(s).", "text": text, "records": records, "returncode": rc}
        return {"ok": False, "state": "unavailable", "message": "Elevated bootctl returned no status output.", "text": "", "records": [], "returncode": rc}

    env = dict(os.environ)
    env.update({"SYSTEMD_COLORS": "0", "SYSTEMD_PAGER": "cat", "PAGER": "cat"})
    try:
        result = subprocess.run(
            ["bootctl", "status", "--no-pager"], capture_output=True, text=True,
            check=False, timeout=timeout, env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "state": "unavailable", "message": "bootctl is not installed or not available in PATH.", "text": "", "records": []}
    except subprocess.TimeoutExpired:
        return {"ok": False, "state": "error", "message": "bootctl status timed out.", "text": "", "records": []}
    except OSError as exc:
        return {"ok": False, "state": "error", "message": f"Could not run bootctl: {exc}", "text": "", "records": []}

    text = (result.stdout or result.stderr or "").strip()
    records = parse_bootctl_status(text)
    if text:
        state = "observed" if result.returncode == 0 else "observed"
        message = f"Loaded {len(records)} boot-loader record(s) from bootctl status."
        if result.returncode != 0:
            message += f" bootctl exited with status {result.returncode}; displayed output is retained as reported."
        return {"ok": True, "state": state, "message": message, "text": text, "records": records, "returncode": result.returncode}
    return {"ok": False, "state": "unavailable", "message": f"bootctl status returned no output (exit status {result.returncode}).", "text": "", "records": [], "returncode": result.returncode}


def _source_formats():
    key_format = QTextCharFormat()
    key_format.setForeground(QColor("#9cdcfe"))
    key_format.setFontWeight(600)
    value_format = QTextCharFormat()
    value_format.setForeground(QColor("#dcdcdc"))
    return key_format, value_format


def _sources_canvas(owner):
    """Canonical LinSpectacles Sources canvas, aligned with Systemd Inspector."""
    widget = QTextEdit()
    widget.setReadOnly(True)
    widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    chosen_font = apply_metadata_font(widget, owner._metadata_font_serialized)
    widget.setStyleSheet(
        "QTextEdit { "
        f"{metadata_font_qss(chosen_font)} "
        "background-color: #151719; color: #dcdcdc; "
        "border: 1px solid #333333; "
        "}"
    )
    return widget


def _populate_sources_canvas(canvas):
    """Render the existing provenance text using the canonical Sources colours."""
    headings = {
        "Boot-loader / firmware boot status",
        "Structured presentation",
        "Privileged inspection",
        "Raw Data",
        "Important distinctions",
    }
    key_format, value_format = _source_formats()
    canvas.clear()
    cursor = canvas.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    for line in SOURCES_TEXT.splitlines():
        fmt = key_format if line in headings else value_format
        cursor.insertText(line + "\n", fmt)
    canvas.setTextCursor(cursor)
    canvas.moveCursor(QTextCursor.MoveOperation.Start)


class RawDataDialog(QDialog):
    """Snapshot-only view of the exact bootctl text already acquired."""

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self.owner = owner
        self.setWindowTitle("Raw Data — Boot Loaders")
        self.resize(980, 720)

        result = owner._last_collect or {}
        self._full_snapshot = str(result.get("text") or "")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        heading = QLabel("Raw Data")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(max(heading_font.pointSize(), 11))
        heading.setFont(heading_font)
        root.addWidget(heading)

        context = "Privileged helper snapshot" if owner._last_collect_elevated else "Standard-access snapshot"
        note = QLabel(
            f"{context} · Full retained output from the current inspection. "
            "This dialog never reruns bootctl."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        command = QLabel("Source query: bootctl status --no-pager")
        command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(command)

        self.snapshot_text = self._raw_text_widget(
            self._full_snapshot or "No retained bootctl output is available for this inspection."
        )
        root.addWidget(self.snapshot_text, 1)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        copy_button = QPushButton("Copy All")
        copy_button.clicked.connect(self._copy_current)
        action_row.addWidget(copy_button)
        export_button = QPushButton("Export...")
        export_button.clicked.connect(self._export_current)
        action_row.addWidget(export_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        action_row.addWidget(close_button)
        root.addLayout(action_row)

    def _raw_text_widget(self, text):
        widget = QTextEdit()
        widget.setReadOnly(True)
        widget.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        widget.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        widget.setPlainText(text)
        widget.setStyleSheet(
            "QTextEdit { background-color: #151719; color: #dcdcdc; "
            "border: 1px solid #333333; }"
        )

        # Use the exact Sources palette without changing any retained raw text.
        key_format, _value_format = _source_formats()
        block = widget.document().begin()
        while block.isValid():
            line = block.text()
            if line and not line[0].isspace() and line.rstrip().endswith(":"):
                start, end = 0, len(line)
            else:
                match = _KEY_VALUE_RE.match(line)
                if match is None:
                    block = block.next()
                    continue
                start, end = match.start(1), match.end(1) + 1

            cursor = widget.textCursor()
            cursor.setPosition(block.position() + start)
            cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(key_format)
            block = block.next()

        widget.moveCursor(QTextCursor.MoveOperation.Start)
        return widget

    def _current_text(self):
        return self._full_snapshot

    def _copy_current(self):
        QApplication.clipboard().setText(self._current_text())

    def _export_current(self):
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Raw Data",
            "boot-loaders-raw-snapshot.txt",
            "Plain Text (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self._current_text(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Export Raw Data", f"Could not write the export:\n{exc}")
            return
        self.owner.set_status(f"Exported Raw Data to {path}")

class BootOptionsDialog(QDialog):
    """Tabbed Boot Loaders options using established LinSpectacles dialog patterns."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Options — Boot Loaders")
        self.resize(980, 720)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # Appearance — mirrors the Suite Configuration Appearance-page structure.
        appearance_page = QWidget()
        appearance_layout = QVBoxLayout(appearance_page)
        appearance_layout.setContentsMargins(12, 12, 12, 12)
        appearance_layout.setSpacing(10)

        appearance_heading = QLabel("Metadata display")
        appearance_heading_font = appearance_heading.font()
        appearance_heading_font.setBold(True)
        appearance_heading.setFont(appearance_heading_font)
        appearance_layout.addWidget(appearance_heading)

        appearance_note = QLabel(
            "Choose how the inventory and Metadata Details panes are arranged. "
            "This Boot Loaders setting is remembered and is shared by normal and privileged views."
        )
        appearance_note.setWordWrap(True)
        appearance_layout.addWidget(appearance_note)

        layout_row = QHBoxLayout()
        layout_row.addWidget(QLabel("Record details layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Horizontal", "Vertical"])
        self.layout_combo.setCurrentText(
            "Vertical" if owner.details_orientation == "vertical" else "Horizontal"
        )
        self.layout_combo.currentTextChanged.connect(self._layout_changed)
        layout_row.addWidget(self.layout_combo)
        layout_row.addStretch(1)
        appearance_layout.addLayout(layout_row)

        self.show_metadata_panel = QCheckBox("Show Metadata Details panel (F3)")
        self.show_metadata_panel.setChecked(owner.metadata_panel_visible)
        self.show_metadata_panel.toggled.connect(self._metadata_panel_changed)
        appearance_layout.addWidget(self.show_metadata_panel)

        shortcut_note = QLabel(
            "Shortcuts: F3 hides/restores Metadata Details; Shift+F5 refreshes the current "
            "boot-loader inspection; Ctrl+L toggles Horizontal/Vertical; Ctrl+/ opens Options."
        )
        shortcut_note.setWordWrap(True)
        appearance_layout.addWidget(shortcut_note)
        appearance_layout.addStretch(1)
        tabs.addTab(appearance_page, "Appearance")

        # Sources — same content and metadata presentation as the former Sources dialog.
        sources_page = QWidget()
        sources_layout = QVBoxLayout(sources_page)
        sources_layout.setContentsMargins(12, 12, 12, 12)
        sources_layout.setSpacing(10)

        sources_heading = QLabel("Data Sources")
        sources_heading_font = sources_heading.font()
        sources_heading_font.setBold(True)
        sources_heading_font.setPointSize(max(sources_heading_font.pointSize(), 11))
        sources_heading.setFont(sources_heading_font)
        sources_layout.addWidget(sources_heading)

        sources_note = QLabel(
            "Commands and system interfaces used by this read-only Boot Loaders view."
        )
        sources_note.setWordWrap(True)
        sources_layout.addWidget(sources_note)

        sources_text = _sources_canvas(owner)
        _populate_sources_canvas(sources_text)
        sources_layout.addWidget(sources_text, 1)
        tabs.addTab(sources_page, "Sources")

        # Export — choose exactly which existing Boot Loaders record fields are exported.
        export_page = QWidget()
        export_layout = QVBoxLayout(export_page)
        export_layout.setContentsMargins(12, 12, 12, 12)
        export_layout.setSpacing(10)

        export_heading = QLabel("Export details")
        export_heading_font = export_heading.font()
        export_heading_font.setBold(True)
        export_heading.setFont(export_heading_font)
        export_layout.addWidget(export_heading)

        export_note = QLabel(
            "Select the Boot Loaders details to include in the export."
        )
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)

        self.export_name = QCheckBox("Name / Record")
        self.export_category = QCheckBox("Category")
        self.export_summary = QCheckBox("Summary")
        self.export_details = QCheckBox("Record Details")
        for checkbox in (
            self.export_name,
            self.export_category,
            self.export_summary,
            self.export_details,
        ):
            checkbox.setChecked(True)
            export_layout.addWidget(checkbox)

        export_layout.addStretch(1)
        export_row = QHBoxLayout()
        export_row.addStretch(1)
        export_button = QPushButton("Export...")
        export_button.clicked.connect(self._export_selected)
        export_row.addWidget(export_button)
        export_layout.addLayout(export_row)
        tabs.addTab(export_page, "Export")

        # About — adapted directly from the Suite About-dialog composition.
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(24, 20, 24, 18)
        about_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(112, 112)
        icon_path = Path(__file__).resolve().parent / "icon.png"
        if icon_path.is_file():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        112,
                        112,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        about_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        name = QLabel("<h2 style='margin:0'>Boot Loaders</h2>")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(name)

        version = QLabel(f"Version {APPLET_VERSION}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(version)

        slogan = QLabel("<b>Expose. Explore. Explain.</b>")
        slogan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(slogan)

        description = QLabel(
            "A read-only LinSpectacles applet for structured inspection of boot-loader, "
            "ESP and EFI boot state, with optional ephemeral privileged visibility."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(description)

        details = QLabel(
            "<b>Build:</b> Standalone LinSpectacles applet<br>"
            "<b>Organisation ID:</b> "
            f"<a href='{APPLET_ORGANIZATION_URL}'>{APPLET_ORGANIZATION_ID}</a><br>"
            f"<b>Applet ID:</b> {APPLET_ID}"
        )
        details.setWordWrap(True)
        details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        details.setOpenExternalLinks(True)
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(details)

        copyright_label = QLabel(
            "Copyright © 2026 "
            "<a href='https://github.com/brunonlinespace'>brunonlinespace</a>"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(copyright_label)

        license_label = QLabel("Licensed under GNU GPLv3 or later.")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(license_label)

        readme_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "README.md")
        ).toString()
        license_url = QUrl.fromLocalFile(
            str(Path(__file__).resolve().parent.parent / "LICENSE")
        ).toString()
        links = QLabel(
            f"<a href='{readme_url}'>README</a> &nbsp;·&nbsp; "
            f"<a href='{license_url}'>License</a> &nbsp;·&nbsp; "
            f"<a href='{APPLET_REPOSITORY}'>Repository</a>"
        )
        links.setOpenExternalLinks(True)
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(links)
        about_layout.addStretch(1)
        tabs.addTab(about_page, "About")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _layout_changed(self, text):
        self.owner.set_details_orientation(str(text).strip().lower(), persist=True)

    def _metadata_panel_changed(self, checked):
        self.owner.set_metadata_panel_visible(bool(checked), persist=True)

    def _export_selected(self):
        selected = []
        if self.export_name.isChecked():
            selected.append(("name", "Name / Record", 230, "left"))
        if self.export_category.isChecked():
            selected.append(("category", "Category", 180, "left"))
        if self.export_summary.isChecked():
            selected.append(("summary", "Summary", 360, "left"))
        if self.export_details.isChecked():
            selected.append(("record_details", "Record Details", 520, "left"))

        if not selected:
            QMessageBox.information(
                self, "Export", "Select at least one detail to export."
            )
            return

        records = []
        for record in self.owner.get_export_records():
            item = {}
            if self.export_name.isChecked():
                item["name"] = record.get("name", "")
            if self.export_category.isChecked():
                item["category"] = record.get("category", "")
            if self.export_summary.isChecked():
                item["summary"] = record.get("summary", "")
            if self.export_details.isChecked():
                lines = []
                section = record.get("_section")
                if section:
                    lines.append(f"Source Section: {section}")
                for key, value in record.get("_details") or []:
                    lines.append(f"{key}: {value if value != '' else '(empty)'}")
                item["record_details"] = "\n".join(lines)
            records.append(item)

        if not records:
            QMessageBox.information(
                self, "Export", "There is no collected data to export yet."
            )
            return

        path = export_records_dialog(
            self, APPLET_NAME, records, columns=selected
        )
        if path is not None:
            self.owner.set_status(f"Exported data to {path}")


class BootInspectorWidget(BaseInspectorTab):
    PRIVILEGE_ACTIVE_QSS = (
        "QPushButton { background: #6a4b0c; color: #fff4d2; "
        "border: 1px solid #d6a23d; border-radius: 4px; padding: 5px 10px; font-weight: 600; } "
        "QPushButton:hover { border-color: #f2c96d; }"
    )

    def __init__(self, parent=None, *, autoload=True, privilege_client=None, privileged_surface=False):
        columns = [
            ("name", "Name / Record", 230, "left"),
            ("category", "Category", 180, "left"),
            ("summary", "Summary", 360, "left"),
        ]
        super().__init__("Boot Loader Records", columns, CATEGORIES, parent)
        self.export_title = APPLET_NAME
        self.search_entry.setPlaceholderText("Search boot-loader records...")
        self._metadata_font_serialized = ""
        self._privileged_surface = bool(privileged_surface)
        self.privilege_client = privilege_client or PrivilegeClient()
        self._privileged_dialog = None
        self._shutting_down = False
        self._last_collect = None
        self._last_collect_elevated = False
        self._options_dialog = None

        self.metadata_panel_visible = True
        self._load_metadata_panel_visibility()

        # The separate Sources and Export controls are consolidated into Options.
        self.export_btn.hide()
        export_index = self.dash_layout.indexOf(self.export_btn)
        if export_index < 0:
            export_index = self.dash_layout.count()

        if not self._privileged_surface:
            self.privilege_btn = QPushButton("Privileged Inspection...")
            self.privilege_btn.clicked.connect(self.open_privileged_inspection)
            self.dash_layout.insertWidget(export_index, self.privilege_btn)
            export_index += 1
        else:
            self.privilege_btn = None

        # Raw Data is an explicit full view of the current retained snapshot.
        self.raw_data_btn = QPushButton("Raw Data...")
        self.raw_data_btn.setEnabled(False)
        self.raw_data_btn.clicked.connect(self.show_raw_data)
        self.dash_layout.insertWidget(export_index, self.raw_data_btn)
        export_index += 1

        self.options_btn = QPushButton("Options...")
        self.options_btn.clicked.connect(self.show_options)
        self.dash_layout.insertWidget(export_index, self.options_btn)

        self.details_orientation = "horizontal"
        self._load_details_orientation()
        self._install_shortcuts()

        self._privilege_timer = QTimer(self)
        self._privilege_timer.setInterval(250)
        self._privilege_timer.timeout.connect(self._refresh_privilege_button)
        if not self._privileged_surface:
            self._privilege_timer.start()

        if autoload:
            self.load_modules()

    def apply_host_settings(self, settings=None, column_visibility_callback=None):
        settings = settings or {}
        self._metadata_font_serialized = str(settings.get("metadata_font", "") or "")
        super().apply_host_settings(settings, column_visibility_callback)

    def style_table_item(self, item, column_id, record):
        # Category remains a record field/filter, but carries no category colour coding.
        return

    def _load_metadata_panel_visibility(self):
        settings = QSettings("brunonlinespace", "Boot Loaders")
        value = settings.value("metadata_panel_visible", True)
        if isinstance(value, str):
            visible = value.strip().lower() not in {"0", "false", "no", "off"}
        else:
            visible = bool(value)
        self.set_metadata_panel_visible(visible, persist=False)

    def set_metadata_panel_visible(self, visible, *, persist=True):
        self.metadata_panel_visible = bool(visible)
        self.details_panel.setVisible(self.metadata_panel_visible)
        if persist:
            settings = QSettings("brunonlinespace", "Boot Loaders")
            settings.setValue("metadata_panel_visible", self.metadata_panel_visible)
            settings.sync()
            self._propagate_metadata_panel_visibility(self.metadata_panel_visible)

    def _propagate_metadata_panel_visibility(self, visible):
        if self._privileged_surface:
            privileged_window = self.parentWidget()
            ordinary = privileged_window.parentWidget() if privileged_window is not None else None
            if isinstance(ordinary, BootInspectorWidget):
                ordinary.set_metadata_panel_visible(visible, persist=False)
        elif self._privileged_dialog is not None:
            elevated = getattr(self._privileged_dialog, "inspector", None)
            if isinstance(elevated, BootInspectorWidget):
                elevated.set_metadata_panel_visible(visible, persist=False)

    def toggle_metadata_panel(self):
        self.set_metadata_panel_visible(not self.metadata_panel_visible, persist=True)

    def toggle_details_orientation(self):
        target = "vertical" if self.details_orientation == "horizontal" else "horizontal"
        self.set_details_orientation(target, persist=True)

    def _install_shortcuts(self):
        self._metadata_shortcut = QShortcut(QKeySequence("F3"), self)
        self._metadata_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._metadata_shortcut.activated.connect(self.toggle_metadata_panel)

        self._layout_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._layout_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._layout_shortcut.activated.connect(self.toggle_details_orientation)

        self._refresh_shortcut = QShortcut(QKeySequence("Shift+F5"), self)
        self._refresh_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._refresh_shortcut.activated.connect(self._shortcut_refresh)

        self._options_shortcut = QShortcut(QKeySequence("Ctrl+/"), self)
        self._options_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._options_shortcut.activated.connect(self.show_options)

    def _shortcut_refresh(self):
        # Click the existing button so the privileged surface keeps its paired-refresh override.
        self.refresh_btn.click()

    def _load_details_orientation(self):
        settings = QSettings("brunonlinespace", "Boot Loaders")
        orientation = str(settings.value("details_orientation", "horizontal") or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.set_details_orientation(orientation, persist=False)

    def set_details_orientation(self, orientation, *, persist=True):
        orientation = str(orientation or "horizontal").lower()
        if orientation not in {"horizontal", "vertical"}:
            orientation = "horizontal"
        self.details_orientation = orientation

        if orientation == "vertical":
            self.splitter.setOrientation(Qt.Orientation.Vertical)
            if hasattr(self, "details_layout"):
                self.details_layout.setContentsMargins(0, 8, 0, 0)
            self.splitter.setSizes([430, 330])
        else:
            self.splitter.setOrientation(Qt.Orientation.Horizontal)
            if hasattr(self, "details_layout"):
                self.details_layout.setContentsMargins(8, 0, 0, 0)
            self.splitter.setSizes([480, 700])

        if persist:
            settings = QSettings("brunonlinespace", "Boot Loaders")
            settings.setValue("details_orientation", orientation)
            settings.sync()
            self._propagate_details_orientation(orientation)

    def _propagate_details_orientation(self, orientation):
        if self._privileged_surface:
            privileged_window = self.parentWidget()
            ordinary = privileged_window.parentWidget() if privileged_window is not None else None
            if isinstance(ordinary, BootInspectorWidget):
                ordinary.set_details_orientation(orientation, persist=False)
        elif self._privileged_dialog is not None:
            elevated = getattr(self._privileged_dialog, "inspector", None)
            if isinstance(elevated, BootInspectorWidget):
                elevated.set_details_orientation(orientation, persist=False)

    def load_from_result(self, result, elevated=False):
        self._last_collect = result
        self._last_collect_elevated = bool(elevated)
        self.modules_data = list(result.get("records") or [])
        self.stats_label.setText(f"{self.total_label_text}: {len(self.modules_data)}")
        self.filter_modules()
        prefix = "Elevated: " if elevated else ""
        self.set_status(prefix + str(result.get("message") or "Boot-loader inspection complete."))
        self.export_btn.setEnabled(bool(self.modules_data))

    def load_modules(self):
        elevated = self._privileged_surface and self.privilege_client.enabled
        result = collect_bootctl(self.privilege_client, elevated=elevated)
        self.load_from_result(result, elevated=elevated)

    def filter_modules(self, *_):
        # The shared inventory filter selects the first visible row and
        # synchronizes Metadata Details before this applet updates its controls.
        super().filter_modules(*_)
        if self.table.rowCount() == 0:
            self.set_status("No boot-loader records match the current filter.")
        self._sync_raw_data_button()

    def on_module_select(self):
        record = self.current_record()
        if not record:
            self._sync_raw_data_button()
            return
        self.clear_info()
        self.append_info(f"--- {record.get('name', 'Boot Loader Record')} ---\n")
        self.append_key_value("Category", record.get("category") or "Not reported")
        self.append_key_value("Source Section", record.get("_section") or "Not reported")
        for key, value in record.get("_details") or []:
            self.append_key_value(key, value if value != "" else "(empty)")
        self.set_status(f"Inspecting reported boot-loader record [{record.get('name', '')}].")
        self._sync_raw_data_button()

    def _sync_raw_data_button(self):
        if not hasattr(self, "raw_data_btn"):
            return
        result = self._last_collect or {}
        self.raw_data_btn.setEnabled(bool(result.get("text")))

    def show_raw_data(self):
        if not (self._last_collect or {}).get("text"):
            QMessageBox.information(
                self,
                "Raw Data",
                "Complete a boot-loader inspection first.",
            )
            return
        dialog = RawDataDialog(self)
        dialog.exec()

    def show_options(self):
        dialog = BootOptionsDialog(self)
        dialog.exec()

    def _refresh_privilege_button(self):
        if self.privilege_btn is None:
            return
        active = bool(
            self._privileged_dialog is not None
            and self._privileged_dialog.isVisible()
            and self.privilege_client.enabled
        )
        if active:
            self.privilege_btn.setText("Privileged Inspection: Active...")
            self.privilege_btn.setStyleSheet(self.PRIVILEGE_ACTIVE_QSS)
            self.privilege_btn.setToolTip(
                "An authorised read-only helper session is active only for the separate "
                "Privileged Inspection window. Closing that window ends the session."
            )
        elif self.privilege_client.state == "connecting" and self._privileged_dialog is not None:
            self.privilege_btn.setText("Privileged Inspection: Authorizing...")
            self.privilege_btn.setStyleSheet("")
            self.privilege_btn.setToolTip(
                "Waiting for PolicyKit authorization in the privileged inspection window."
            )
        else:
            self.privilege_btn.setText("Privileged Inspection...")
            self.privilege_btn.setStyleSheet("")
            self.privilege_btn.setToolTip(
                "Open the separate optional read-only privileged inspection window. "
                "The normal applet remains ordinary-user only."
            )


    def _privileged_dialog_finished(self, _result):
        QTimer.singleShot(0, self._finalize_privileged_dialog_close)

    def _finalize_privileged_dialog_close(self):
        dialog = self._privileged_dialog
        if dialog is not None and not dialog.isVisible():
            self._privileged_dialog = None
        self._refresh_privilege_button()

    def _privileged_window_closed(self, had_session):
        self._refresh_privilege_button()
        if self._shutting_down or not had_session:
            return
        settings = QSettings("brunonlinespace", "Boot Loaders")
        show_message = settings.value(
            "privileged/show_end_confirmation", True, type=bool
        )
        if show_message:
            QTimer.singleShot(0, self._show_privilege_end_message)

    def _show_privilege_end_message(self):
        if self._shutting_down:
            return
        settings = QSettings("brunonlinespace", "Boot Loaders")
        box = QMessageBox(self)
        box.setWindowTitle("Privileged Inspection Ended")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("Privileged inspection ended")
        box.setInformativeText(
            "The Boot Loaders privileged helper session has been closed. LinSpectacles will not "
            "perform elevated boot inspection again until you explicitly open "
            "Privileged Inspection and authorize a new session."
        )
        checkbox = QCheckBox("Don't show this message again")
        box.setCheckBox(checkbox)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()
        if checkbox.isChecked():
            settings.setValue("privileged/show_end_confirmation", False)

    def set_applet_active(self, active):
        """Suite lifecycle hook: privilege must never survive leaving this applet."""
        if self._privileged_surface:
            return
        active = bool(active)
        if active:
            if not self._privilege_timer.isActive():
                self._privilege_timer.start()
            self._refresh_privilege_button()
            return

        if self._privilege_timer.isActive():
            self._privilege_timer.stop()

        # Route Suite deactivation through the same proven dialog close path used
        # by SELinux. Suppress only the user-facing "ended" reassurance because
        # the applet switch itself is the reason for teardown.
        previous = self._shutting_down
        self._shutting_down = True
        try:
            if self._privileged_dialog is not None:
                try:
                    self._privileged_dialog.close()
                except Exception:
                    pass
            self.privilege_client.stop()
        finally:
            self._shutting_down = previous
        self._refresh_privilege_button()

    def shutdown(self):
        self._shutting_down = True
        if hasattr(self, "_privilege_timer"):
            self._privilege_timer.stop()
        if self._privileged_dialog is not None:
            try:
                self._privileged_dialog.close()
            except Exception:
                pass
            self._privileged_dialog = None
        self.privilege_client.stop()
        self._refresh_privilege_button()

    def open_privileged_inspection(self):
        from .privileged_window import PrivilegedInspectionDialog

        if self._privileged_dialog is not None and self._privileged_dialog.isVisible():
            self._privileged_dialog.raise_()
            self._privileged_dialog.activateWindow()
            return

        dialog = PrivilegedInspectionDialog(
            self.privilege_client,
            metadata_font=self._metadata_font_serialized,
            parent=self,
        )
        self._privileged_dialog = dialog
        dialog.session_state_changed.connect(self._refresh_privilege_button)
        dialog.closing.connect(self._privileged_window_closed)
        dialog.finished.connect(self._privileged_dialog_finished)
        dialog.show()
        self._refresh_privilege_button()


def create_applet(parent=None):
    return BootInspectorWidget(parent=parent)


def run_standalone():
    import sys
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication, QMainWindow
    from ._support import STANDALONE_STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName(APPLET_NAME)
    app.setOrganizationName(APPLET_AUTHOR)
    icon_path = Path(__file__).resolve().parent / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(STANDALONE_STYLESHEET)
    window = QMainWindow()
    if icon_path.is_file():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.setWindowTitle(f"{APPLET_NAME} {APPLET_VERSION} — LinSpectacles Applet")
    window.resize(1200, 780)
    widget = create_applet()
    window.setCentralWidget(widget)
    app.aboutToQuit.connect(widget.shutdown)
    window.show()
    return app.exec()
