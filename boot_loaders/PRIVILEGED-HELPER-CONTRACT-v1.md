# Boot Loaders — Privileged Helper Contract v1

Boot Loaders' normal GUI always runs as the ordinary user. The optional helper is installed at:

`/usr/libexec/linspectacles-boot-helper`

The helper is read-only, root-owned, fixed-operation, and used only while the dedicated Privileged Inspection window has an authorised session open.

## Fixed operation

`bootctl_status`

Runs only the equivalent of:

`bootctl status --no-pager`

There is no arbitrary command operation, no arbitrary file-read operation, and no operation that writes firmware variables, boot entries, ESP files, Secure Boot configuration, or boot-loader state.

Closing the Privileged Inspection window stops the helper session. An installed helper does not mean privilege is active.
