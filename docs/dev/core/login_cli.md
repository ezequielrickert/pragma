# core/login_cli.py

## module

`pragma login` command wiring - argument parsing and the capture/report
loop - kept out of `cli.py` itself, the same way `core/static_cli.py`
and `core/cluster_cli.py` are.

## parse_login_args

Its own small parser rather than a case in the main run parser, since
it takes none of a crawl run's flags (budgets, output dir, agent/
graph-store wiring) and adding it there would make every one of those
look like it applies here too. No `--headless` flag - there is no such
thing as a headless interactive sign-in, so the capture browser is
always visible; this flag was removed after testing against a real
site exposed that a headless capture browser silently hangs on
`input()` nobody can ever answer.

## run_login_command

`pragma login <url>` always captures a fresh session via
`spiders/browser/login.py::force_login_session`, since running this
command by hand is itself the explicit request to sign in - it never
reuses a cached session or checks for a login form first, unlike the
auto-invoked `ensure_login_session` other stages call.
