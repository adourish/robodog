import os
import shutil
import subprocess
import sys

directories = [r"robodoglib", r"robodogcli", r"robodog"]
base_dir = os.getcwd()
print(f"Base directory: {base_dir}")

# Check if the 'install' command line argument is passed
if len(sys.argv) > 1 and sys.argv[1] == 'install':
    perform_install = True
else:
    perform_install = False

for dir in directories:
    print(f"Working on directory: {dir}")
    os.makedirs(dir, exist_ok=True)
    
    try:
        dir_path = os.path.join(base_dir, dir)
        os.chdir(dir_path)
        print(f"Navigated to directory: {dir_path}")

        if perform_install:
            print("Running 'npm install'...")
            subprocess.check_call('npm install', shell=True)
            print("'npm install' completed.")

        print("Running 'npm run build'...")
        subprocess.check_call('npm run build', shell=True)
        print("'npm run build' completed.")
        readme_src = os.path.join(base_dir, 'README.md')
        readme_dest = os.path.join(dir_path, 'README.md') 
        print(f"Copying README.md from {readme_src} to {readme_dest}")
        shutil.copy(readme_src, readme_dest)
        print("README.md copied.")

        # Navigate back to the base directory
        os.chdir(base_dir)
        print("Navigated back to base directory.")
        
    except subprocess.CalledProcessError as e:
        print(f"Command '{e.cmd}' returned non-zero exit status {e.returncode}.")
        continue
    except FileNotFoundError as e:
        print(f"Error: {e}")
        continue
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        continue

print("Operation completed successfully!")