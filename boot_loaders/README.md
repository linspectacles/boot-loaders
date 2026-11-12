# Boot Loaders 0.1.6

LinSpectacles Boot Loaders 0.1.6 moves implementation files into the inner `boot_loaders/`
package without changing their behaviour. The initial System selection and Metadata Details
synchronization from 0.1.5, using the Kernel Modules 0.0.5 approach, remain preserved.
The last visible inventory column continues to stretch to the available width.

The alternate-row stylesheet, `Expose. Explore. Explain.` slogan, and
`Boot Loaders 0.1.6 — LinSpectacles Applet` standalone titlebar are preserved.

The existing boot-loader/EFI inventory, parser, optional privileged-helper contract,
comparison behavior, and read-only acquisition model are preserved. Existing capabilities include:

- `Raw Data...` for the selected record, using only the already-retained `bootctl status --no-pager` snapshot;
  the dialog shows the complete source section containing the selected record and the complete retained snapshot,
  with copy/export operations that never trigger a new acquisition.
- `F3` to hide/show Metadata Details, with a persisted setting shared by normal and privileged views.
- `Ctrl+L` to toggle Horizontal/Vertical record-details layout.
- `Shift+F5` to activate the existing Refresh path; in the privileged window this intentionally follows the
  existing paired ordinary/elevated refresh override rather than bypassing it.
- `Ctrl+/` to open Options.
- the canonical Systemd-style Sources presentation (`#151719` canvas, `#333333` border,
  `#9cdcfe` section headings, `#dcdcdc` source text).

The optional helper is packaged for installation at `/usr/libexec/linspectacles-boot-helper` and identifies as
version `0.0.8`; capabilities and protocol remain unchanged.

Boot Loaders remains read-only and boot/EFI-focused. Raw Data is a source-oriented view of the
current snapshot, not an additional scan path and not a maintenance interface.
