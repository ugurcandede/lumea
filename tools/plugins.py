"""Keeps plugins/version.json honest. Standard library only (runs in CI without deps).

    python tools/plugins.py index    rewrite each plugin's "files" (sha256) and "requires"
    python tools/plugins.py check    fail if version.json is stale or a plugin can't run
                                     (bad shape, unbundled imports, wrong hashes)

You edit name / description / version / api in version.json by hand; `index` fills
in the rest. `check` (CI, on every change under plugins/) also enforces the rule
that's easy to forget: a packaged Lumea only contains the modules its own code
imports, so every module a plugin imports -- standard library included -- must be
imported by Lumea itself or listed in plugin_runtime.py. An import under an
`if sys.platform ...` test or a try/except ImportError is still checked that way,
but left out of "requires": the plugin needs it only where it exists. See
plugins/README.md.
"""

import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
INDEX = PLUGINS / "version.json"
RUNTIME = ROOT / "plugin_runtime.py"
HAND_FIELDS = ("name", "description", "version", "api")


def imports_of(path, conditional=False):
    """Absolute module names a .py file imports (relative imports skipped): the
    unconditional ones, or with ``conditional`` only those under an `if
    sys.platform ...` test or a try/except ImportError."""
    found = set()
    _collect(ast.parse(path.read_text(encoding="utf-8"), str(path)), False, conditional, found)
    return found


def _collect(node, guarded, want, found):
    for child in ast.iter_child_nodes(node):
        inner = guarded or _guards(child)
        if inner == want:
            if isinstance(child, ast.Import):
                found.update(alias.name for alias in child.names)
            elif isinstance(child, ast.ImportFrom) and child.level == 0 and child.module:
                found.add(child.module)
                if child.module == "PySide6":       # from PySide6 import QtX -> PySide6.QtX
                    found.update(f"PySide6.{a.name}" for a in child.names)
        _collect(child, inner, want, found)


def _guards(node):
    """True for `if sys.platform ...` (its elif / else too) and try/except ImportError."""
    if isinstance(node, ast.If):
        return "sys.platform" in ast.unparse(node.test)
    return isinstance(node, ast.Try) and any(
        h.type is not None and "ImportError" in ast.unparse(h.type) for h in node.handlers)


def all_imports_of(path):
    return imports_of(path) | imports_of(path, conditional=True)


def lumea_modules():
    """(modules Lumea's own code imports, modules only plugin_runtime.py adds)."""
    core = set()
    for path in ROOT.glob("*.py"):
        if path != RUNTIME:
            core |= all_imports_of(path)
            core.add(path.stem)                     # Lumea's own modules (plugin_api, effects, ...)
    return core, all_imports_of(RUNTIME) - core


def plugin_dirs():
    return sorted(p for p in PLUGINS.iterdir()
                  if p.is_dir() and not p.name.startswith((".", "_")) and (p / "__init__.py").is_file())


def plugin_files(folder):
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def shape_problems(folder):
    """The contract plugin_host relies on: class Plugin with __init__(self, api) and stop(self)."""
    tree = ast.parse((folder / "__init__.py").read_text(encoding="utf-8"))
    cls = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin"), None)
    if cls is None:
        return [f"{folder.name}/__init__.py doesn't define class Plugin"]
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    problems = []
    init = methods.get("__init__")
    if init is None or len(init.args.args) != 2:
        problems.append(f"{folder.name}: Plugin must define __init__(self, api)")
    if "stop" not in methods:
        problems.append(f"{folder.name}: Plugin must define stop(self) (undo everything __init__ did)")
    return problems


def computed(folder, core, runtime):
    """("files", "requires") for a plugin folder, plus problems found on the way."""
    files = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in plugin_files(folder)}
    needs, problems = set(), []
    for path in folder.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        always = imports_of(path)
        for module in all_imports_of(path):
            if covered(module, core):
                continue
            if not covered(module, runtime):
                problems.append(f"{folder.name}/{path.relative_to(folder).as_posix()} imports {module!r}, "
                                "which Lumea doesn't bundle: add it to plugin_runtime.py (needs an app release)")
            elif module in always:                  # a platform-conditional one isn't required everywhere
                needs.add(module)
    return files, sorted(needs), problems


def covered(module, modules):
    # A module is in the build if it or one of its parents is imported there
    # (PySide6 is the exception: each Qt module is bundled only if named).
    parts = module.split(".")
    if parts[0] == "PySide6":
        return module in modules or (len(parts) > 2 and ".".join(parts[:2]) in modules)
    return any(".".join(parts[:i]) in modules for i in range(1, len(parts) + 1))


def main(command):
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    entries = index["plugins"]
    core, runtime = lumea_modules()
    problems = []
    folders = {p.name: p for p in plugin_dirs()}
    for pid in sorted(set(entries) - set(folders)):
        problems.append(f"version.json lists {pid!r} but plugins/{pid}/__init__.py doesn't exist")
    for pid, folder in folders.items():
        entry = entries.get(pid)
        if entry is None:
            problems.append(f"plugins/{pid}/ isn't in version.json: add {{{', '.join(HAND_FIELDS)}}} for it")
            continue
        problems += [f"{pid}: missing {f!r} in version.json" for f in HAND_FIELDS if f not in entry]
        problems += shape_problems(folder)
        files, requires, found = computed(folder, core, runtime)
        problems += found
        if command == "index":
            entry["files"], entry["requires"] = files, requires
        elif entry.get("files") != files or entry.get("requires") != requires:
            problems.append(f"{pid}: version.json is out of date: run `python tools/plugins.py index`")
    if command == "index":
        INDEX.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    for p in problems:
        print(f"error: {p}")
    if not problems:
        print(f"ok: {len(folders)} plugin(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("index", "check"):
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
