# ray.py
# Ray - The Luz Package Manager
#
# Installs Luz packages from GitHub into luz_modules/<name>/
# Tracks dependencies in luz.json

import sys
import os
import json
import urllib.request
import zipfile
import shutil
import tempfile

VERSION = "0.1.0"
MODULES_DIR = "luz_modules"
MANIFEST = "luz.json"


def load_manifest():
    if os.path.exists(MANIFEST):
        with open(MANIFEST, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"name": os.path.basename(os.getcwd()), "version": "1.0.0", "dependencies": {}}


def save_manifest(data):
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def install_package(user, repo):
    url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.zip"
    print(f"Downloading {user}/{repo}...")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "pkg.zip")
        try:
            urllib.request.urlretrieve(url, zip_path)
        except Exception as e:
            # Try master branch as fallback
            try:
                url = f"https://github.com/{user}/{repo}/archive/refs/heads/master.zip"
                urllib.request.urlretrieve(url, zip_path)
            except Exception:
                print(f"ray: could not download {user}/{repo} — check the repo name")
                return

        with zipfile.ZipFile(zip_path, 'r') as z:
            tmp_real = os.path.realpath(tmp)
            for member in z.namelist():
                member_real = os.path.realpath(os.path.join(tmp, member))
                if not member_real.startswith(tmp_real + os.sep):
                    print(f"ray: unsafe path in archive: {member}")
                    return
            z.extractall(tmp)

        # GitHub extracts to repo-main/ or repo-master/
        extracted = [
            d for d in os.listdir(tmp)
            if os.path.isdir(os.path.join(tmp, d)) and d != "__MACOSX" and d != "pkg.zip"
        ]
        if not extracted:
            print("ray: could not find package contents after extraction")
            return

        pkg_dir = os.path.join(tmp, extracted[0])

        # Read the package's own luz.json for its name and version
        pkg_manifest_path = os.path.join(pkg_dir, "luz.json")
        if os.path.exists(pkg_manifest_path):
            with open(pkg_manifest_path, encoding='utf-8') as f:
                pkg_manifest = json.load(f)
            pkg_name = pkg_manifest.get("name", repo)
            pkg_version = pkg_manifest.get("version", "0.0.0")
        else:
            pkg_name = repo
            pkg_version = "0.0.0"

        # Install to luz_modules/<name>/
        os.makedirs(MODULES_DIR, exist_ok=True)
        dest = os.path.join(MODULES_DIR, pkg_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(pkg_dir, dest)

        # Update project luz.json
        manifest = load_manifest()
        manifest.setdefault("dependencies", {})[pkg_name] = pkg_version
        save_manifest(manifest)

        print(f"Installed {pkg_name} {pkg_version}  →  {MODULES_DIR}/{pkg_name}/")


def cmd_install(args):
    if not args:
        # Install all dependencies from luz.json
        if not os.path.exists(MANIFEST):
            print("ray: no luz.json found. Run 'ray init' first.")
            return
        manifest = load_manifest()
        deps = manifest.get("dependencies", {})
        if not deps:
            print("ray: no dependencies listed in luz.json")
            return
        print(f"ray: reinstall requires the original user/repo (e.g. ray install user/{list(deps.keys())[0]})")
        return

    target = args[0]
    if '/' not in target:
        print(f"ray: specify package as 'user/repo'  (e.g. ray install Elabsurdo984/luz-http)")
        return

    user, repo = target.split('/', 1)
    install_package(user, repo)


def cmd_remove(args):
    if not args:
        print("ray: specify a package name  (e.g. ray remove http)")
        return
    name = args[0]
    dest = os.path.join(MODULES_DIR, name)
    if not os.path.exists(dest):
        print(f"ray: '{name}' is not installed")
        return
    shutil.rmtree(dest)
    manifest = load_manifest()
    manifest.get("dependencies", {}).pop(name, None)
    save_manifest(manifest)
    print(f"Removed {name}")


def cmd_list():
    if not os.path.exists(MODULES_DIR):
        print("No packages installed.")
        return
    pkgs = sorted(
        d for d in os.listdir(MODULES_DIR)
        if os.path.isdir(os.path.join(MODULES_DIR, d))
    )
    if not pkgs:
        print("No packages installed.")
        return
    print(f"Installed packages ({len(pkgs)}):")
    manifest = load_manifest()
    deps = manifest.get("dependencies", {})
    for pkg in pkgs:
        version = deps.get(pkg, "?")
        print(f"  {pkg}  {version}")


def cmd_init():
    if os.path.exists(MANIFEST):
        print("ray: luz.json already exists")
        return
    data = {
        "name": os.path.basename(os.getcwd()),
        "version": "1.0.0",
        "dependencies": {}
    }
    save_manifest(data)
    print("Created luz.json")


def usage():
    print(f"Ray v{VERSION} — Luz Package Manager")
    print()
    print("Commands:")
    print("  ray install <user/repo>   Install a package from GitHub")
    print("  ray remove <name>         Remove an installed package")
    print("  ray list                  List installed packages")
    print("  ray init                  Create a luz.json in the current directory")


def main():
    args = sys.argv[1:]
    if not args:
        usage()
        return

    cmd = args[0]
    rest = args[1:]

    if cmd == "install":
        cmd_install(rest)
    elif cmd == "remove":
        cmd_remove(rest)
    elif cmd == "list":
        cmd_list()
    elif cmd == "init":
        cmd_init()
    else:
        print(f"ray: unknown command '{cmd}'")
        print()
        usage()


if __name__ == "__main__":
    main()
