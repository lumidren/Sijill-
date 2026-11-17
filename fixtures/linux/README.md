# Recorded Linux hosts

Each directory replays one host for `collectors/linux/pdpl_linux_collector.py --fixture <dir>`:

- `host.json` - hostname and whether the collector ran as root
- `commands.json` - exit code and output of each read-only command the collector runs
- `stat.json` - mode and owner of sensitive files
- `fs/` - configuration files the collector reads

These are fictional hosts for the demo clinic and the test suite, written in the shape real
hosts produce. They are not captures from a real machine.

| Host | Story |
|------|-------|
| `clinic-db-01` | Hardened database server: every check passes |
| `clinic-db-01-week3` | Same server after a vendor support visit: SSH password login was switched back on (the demo regression) |
| `clinic-web-01` | Unhardened web server: most checks fail |
| `minimal-host` | Container-like host with no tools: checks report MANUAL instead of guessing |
