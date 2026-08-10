# `src/cli.py`

## main

Bare `python3 src/cli.py` from a real terminal launches the interactive
menu app (navigate between analyzing a URL and configuring the
pipeline, no flags needed). `python3 src/cli.py config` jumps straight
to the setup wizard. Any other invocation (flags/positional URL) runs a
single analysis directly, for scripting/automation.
