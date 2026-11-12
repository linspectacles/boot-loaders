<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/boot-loaders.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/boot-loaders.png"
      alt="Boot Loaders screenshot"
      width="900"
    >
  </a>
</p>

# Boot Loaders

**Expose. Explore. Explain.**

Boot Loaders is a read-only structured inspector for boot-loader and EFI state reported by `bootctl`, with optional ephemeral privileged visibility through a fixed helper.

Current release: **0.1.8**

Repository: <https://github.com/linspectacles/boot-loaders>

## What Boot Loaders is

Boot Loaders answers a focused question: **what boot-loader, ESP and firmware boot information does the system report right now?**

It keeps acquisition and interpretation close to the Linux interfaces actually used by the applet. When a source is unavailable, restricted, or does not report a field, the README does not imply that the applet can manufacture the missing information.

## Highlights

- Structured parsing of `bootctl status --no-pager`.
- Records for **System**, **Current Boot Loader**, **Random Seed**, ESP boot-loader entries, EFI boot entries, and additional labelled sections reported by `bootctl`.
- **Raw Data...** shows the complete retained source section for a selected record and the full retained snapshot without rerunning acquisition.
- Optional privileged inspection uses the same fixed read-only `bootctl status --no-pager` query.
- **Comparison Report...** compares actual ordinary and helper-visible results when both have been acquired.
- Metadata Details visibility and horizontal/vertical layout are persistent presentation settings.

## Data sources and acquisition

- `bootctl status --no-pager`.
- Optional fixed helper at `/usr/libexec/linspectacles-boot-helper` for the same read-only query with elevated visibility.

The applet uses those sources according to the acquisition paths implemented in this release. Optional tools or privileged helpers only affect the views/actions that explicitly use them; they are not treated as silent substitutes for unrelated sources.

## Interface

Boot Loaders follows the LinSpectacles inventory + **Metadata Details** pattern where applicable: an acquired inventory remains separate from the details for the selected record, and search/filter controls operate on the data the applet has actually collected.

The applet's **Options** surface provides the presentation/source/about controls implemented by this release, together with export controls where present in the source. Applet-specific actions remain explicit rather than being folded into background collection.

## Read-only and scope boundaries

Boot Loaders does not change firmware variables, EFI boot entries, the ESP, Secure Boot state or boot-loader configuration. Raw Data is a view of the retained snapshot, not a second scan path. The helper exposes no arbitrary command or arbitrary file-read API.

## Useful keyboard shortcuts

| Command | Shortcut |
| --- | --- |
| Show / hide Metadata Details | `F3` |
| Toggle Horizontal / Vertical details | `Ctrl+L` |
| Refresh | `Shift+F5` |
| Options | `Ctrl+/` |

## Running from source

The supplied source is directly runnable on Linux. The Python-side requirements are:

- Python 3.
- PyQt6 for the graphical interface.

Create a local virtual environment if you do not already have the required Python packages in the environment you want to use:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6
python3 linspectacles_boot_loaders/standalone.py
```

Linux commands, procfs/sysfs interfaces, system services, or optional helpers mentioned in **Data sources and acquisition** are applet-specific runtime inputs. A missing optional source is handled by the applet's existing availability/error path; it is not replaced here with an invented dependency or capability.

No RPM installation instructions are included in this README.

## Source layout and LinSpectacles integration

The applet source is contained in:

```text
linspectacles_boot_loaders/
├── __init__.py
├── applet.json
├── standalone.py
├── LICENSE
├── README.md
└── boot_loaders/
    ├── __init__.py
    ├── applet.py
    ├── _support.py
    ├── privilege.py
    ├── privileged_window.py
    ├── icon.png
    ├── README.md
    ├── PRIVILEGED.md
    ├── PRIVILEGED-HELPER-CONTRACT-v1.md
    └── privileged/
        ├── linspectacles-boot-helper
        └── install-helper.sh
```

`applet.json` supplies the LinSpectacles applet identity and entrypoint metadata. `standalone.py` launches the applet directly, while the package's applet factory provides the host-loadable LinSpectacles integration used by the source.

## Configuration

Presentation and inspection preferences are persisted only through the settings mechanisms already implemented by the applet. Persisted UI state does not grant the applet permission to modify the inspected Linux subsystem.

## Scope

Boot Loaders is intentionally specialist. Related Linux information that belongs to another LinSpectacles subsystem remains outside this applet rather than being inferred or duplicated here.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- Repository: <https://github.com/linspectacles/boot-loaders>
- Issues: <https://github.com/linspectacles/boot-loaders/issues>

<p align="center">
  <a href="https://github.com/linspectacles/boot-loaders">
    <img
      src="boot_loaders/icon.png"
      alt="Boot Loaders"
      width="256"
    >
  </a>
</p>
