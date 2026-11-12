# Optional privileged inspection

Boot Loaders is useful without privilege and structures the boot-loader/EFI state visible through the current user's `bootctl status` query.

The optional privileged helper can run the same fixed read-only query with elevated visibility. The Privileged Inspection window uses the same Boot Loaders inventory in an amber/gold elevated visual language. `Inspect with Privileged Access...` authorizes and immediately performs paired ordinary and helper-backed inspection.

`Comparison Report...` is a separate dialog that reports what elevated access actually added in the latest paired inspection. It is not another inspector tab.

Helper installation and active privilege are separate states. Privilege is active only while the dedicated window has an authorised helper session. Closing the window ends that session.
