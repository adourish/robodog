import os
import shutil
import subprocess
import sys

# Add robodogcli to the list
directories = [
    "robodoglib",
    "robodog",
    "robodogcli",
]

base_dir = os.getcwd()
print(f"Base directory: {base_dir}")

# If you want to gate the npm install step (and/or pip install) on a CLI flag,
# invoke this script with `python build.py install`
perform_install = len(sys.argv) > 1 and sys.argv[1] == "install"

for d in directories:
    dir_path = os.path.join(base_dir, d)
    print(f"\n=== Processing {d} ===")
    os.makedirs(dir_path, exist_ok=True)

    try:
        os.chdir(dir_path)
        print(f"  → cd {dir_path}")

        if d in ("robodoglib", "robodog"):
            if perform_install:
                print("  • npm install")
                subprocess.check_call("npm install", shell=True)
            print("  • npm run build")
            subprocess.check_call("npm run build", shell=True)

        elif d == "robodogcli":
            # Upgrade build tools and build the Python package
            print("  • Upgrading build and twine")
            subprocess.check_call(
                f"{sys.executable} -m pip install --upgrade build twine",
                shell=True,
            )
            print("  • python -m build")
            subprocess.check_call(
                f"{sys.executable} -m build",
                shell=True,
            )

        # Copy the top-level README.md into each package
        readme_src = os.path.join(base_dir, "README.md")
        readme_dest = os.path.join(dir_path, "README.md")
        if os.path.isfile(readme_src):
            print(f"  • Copy README.md → {readme_dest}")
            shutil.copy(readme_src, readme_dest)

    except subprocess.CalledProcessError as e:
        print(f"Command '{e.cmd}' failed with exit code {e.returncode}.")
    except Exception as e:
        print(f"Error in {d}: {e}")

    finally:
        # return to base dir for next iteration
        os.chdir(base_dir)

print("\nAll builds complete.")