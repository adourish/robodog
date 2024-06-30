
import os
import shutil
import subprocess

# defining the directories
directories = [r".\robodog\robodoglib", r".\robodog\robodogcli", r".\robodog\robodog"]

# get the base directory
base_dir = os.getcwd()

# loop through each directory
for dir in directories:
    print(f"Working on directory: {dir}")
    # make sure the directory exists
    os.makedirs(dir, exist_ok=True)
    
    try:
        # navigate to the directory
        dir_path = os.path.join(base_dir, dir)
        os.chdir(dir_path)
        print(f"Navigated to directory: {dir_path}")

        # run the npm install and build commands
        print("Running 'npm install'...")
        subprocess.check_call('npm install', shell=True)
        print("'npm install' completed.")

        print("Running 'npm run build'...")
        subprocess.check_call('npm run build', shell=True)
        print("'npm run build' completed.")

        # copy the root readme.md into the current directory
        readme_src = os.path.join(base_dir, 'README.md')
        readme_dest = os.path.join(dir_path, 'README.md') # Corrected line
        print(f"Copying README.md from {readme_src} to {readme_dest}")
        shutil.copy(readme_src, readme_dest) # Corrected line
        print("README.md copied.")

        # navigate back to the base directory
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