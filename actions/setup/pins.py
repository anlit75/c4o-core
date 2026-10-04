"""
The c4o-core image is named in the Makefile and in devcontainer.json, and
nothing reads one from the other: the Makefile drives the commands, and
devcontainer.json is read by a tool that never touches the Makefile. A tag
bumped in one and missed in the other does not fail loudly -- whoever opens the
Codespace just gets a different c4o-core than whoever runs make.
"""
import json
import os
import re
import sys


def read(path):
    # A file that is not here is a file somebody removed on purpose --
    # dropping .devcontainer/ is a reasonable thing to do with a template.
    # Only the pins that are still here have to agree.
    return open(path).read() if os.path.exists(path) else None


def pins():
    values = {}
    makefile = read("Makefile")
    if makefile is not None:
        m = re.search(r"^C4O_IMAGE\s*:=\s*(\S+)", makefile, re.M)
        values["Makefile"] = m.group(1) if m else None

    devcontainer = read(".devcontainer/devcontainer.json")
    if devcontainer is not None:
        # devcontainer.json is JSONC; strip the line comments first.
        stripped = re.sub(r"^\s*//.*$", "", devcontainer, flags=re.M)
        values[".devcontainer/devcontainer.json"] = json.loads(stripped).get("image")
    return values


def main():
    values = pins()
    if "Makefile" not in values:
        print("::error::No Makefile here. The c4o-core actions read the image name from C4O_IMAGE in it.")
        return 1

    # Present but unreadable means this check went stale, not that the pins
    # disagree. Name the file rather than leaving a traceback.
    for path, value in values.items():
        if value is None:
            print(f"::error::{path}: found no c4o-core image reference.")
            return 1

    if len(set(values.values())) > 1:
        print("::error::The c4o-core image reference is inconsistent:")
        for path, value in values.items():
            print(f"  {path}: {value}")
        return 1
    print("c4o-core image reference is consistent: " + next(iter(values.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
