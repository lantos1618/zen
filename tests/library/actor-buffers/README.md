# Concurrent byte-buffer admission

Run through `python3 tests/quality/actor_buffers.py --zen ./zen`.
The gate links this native probe into the actual generated Zen program under
UBSan. It resolves the emitted message, turn and preparation callback names;
the probe does not implement another actor runtime.

Eight producer threads must rendezvous inside preparation at the same time,
then deliver 512 byte buffers. The worker grows each buffer and checks its
contents and per-producer order; stopped checks every producer's delivery count. The gate tracks
private preparation allocations and verifies all are released after shutdown.
The gate separately proves refusal cleanup, reentrant callbacks, and stop during
preparation with deliberate deadlock, early-stopped and leak controls.
