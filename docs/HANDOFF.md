# Current development handoff

This is a work-in-progress snapshot, not a verified release. Preserve existing
changes. Native application work lives in sibling zen-rooms, zen-ui, zen-macos
and zen-ios repositories. Rooms is the current chat/voice application; zen-tui
contains older experiments.

## UI continuation

Use Rooms for native macOS and iOS design work. Recent changes remove redundant
idle voice labels, add measured microphone peak history, and remove the tight
inner composer border. Mac build and focus/selection inspection passed for the
composer change. iOS build passed before that macOS-only styling change.
Improve layout, navigation and input accessibility using shared zen-ui primitives;
keep platform implementation in the native adapters. Preserve actual errors and
use measured data for audio visualizations.

## Memory and compiler continuation

Allocation overflow/alignment, failed actor-spawn cleanup and numeric comparison
lowering received focused regression and mutation tests. Further ownership
changes are present in this snapshot and must be independently revalidated;
do not rely on earlier results as validation of all current files. In particular,
review owning container lookup, descriptor aliases, extraction, insertion refusal,
recursive ownership and pointer storage together. See ISSUES.md, the current
stagebook, ownership fixtures and quality gates.

The earlier isolated aggregate run stopped at the warning ratchet. Investigation
found Apple's gcc executable is Clang, and a separate macOS spawn deprecation.
Newer gate/source edits in this snapshot need verification. ThreadSanitizer failed
even on a trivial local program; successful UBSan and actor stress runs are not
race-detector coverage or a whole-language soundness proof. Main source also
contains the previously paused opaque-type draft. Do not promote a compiler or
seed solely because this snapshot is committed.

Read AGENTS.md and docs/STYLE.md. Run focused ownership gates first, then the
repository aggregate verification. Record exact failures and preserve failing
controls; do not raise warning baselines or weaken tests just to obtain green.
