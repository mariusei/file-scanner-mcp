# Task queue notes

Liten, stabil fixture for golden-test av scan_directory-formatet.

## Design

The queue keeps tasks sorted by priority.

## Open questions

- Should `drain` preserve insertion order for equal priorities?
