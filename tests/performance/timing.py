"""The ratio every concurrency timing test in this directory compares against."""

# Timing rules for the timing tests in this directory. A timing assertion compares
# two measurements taken in the same run, never a number of seconds: a load average
# far above the core count slows both sides alike, so a ratio survives it and a
# wall-clock limit does not (2026-11-01: three absolute limits went red at load ~30).
# Each test also asserts the work actually happened, because a swallowed error is fast.

CONCURRENCY_RATIO = 0.5  # concurrent must take less than half the sequential time
