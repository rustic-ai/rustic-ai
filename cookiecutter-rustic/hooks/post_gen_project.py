import os
import sys
from pathlib import Path

import tomlkit

module_name = "rusticai-{{ cookiecutter.module_name }}"
module_path = "{{ cookiecutter.module_name }}"

project_directory = Path().resolve().parent
modules_sh_file = os.path.join(project_directory, "scripts/modules.sh")
modules_variable = "MODULES"


def update_pyproject_toml():
    pyproject_path = os.path.join(project_directory, "pyproject.toml")
    if not os.path.exists(pyproject_path):
        print(f"Error: pyproject.toml not found at {pyproject_path}")
        sys.exit(1)

    try:
        with open(pyproject_path, "r") as f:
            data = tomlkit.load(f)
    except Exception as e:
        print(f"Error parsing pyproject.toml: {e}")
        sys.exit(1)

    # Access the dependencies section
    dependencies = data["tool"]["poetry"]["dependencies"]
    # Add the new module
    dependencies[module_name] = tomlkit.inline_table()  # Use inline table for better formatting
    dependencies[module_name].update({"path": f"./{module_path}", "develop": True})

    try:
        with open(pyproject_path, "w") as f:
            tomlkit.dump(data, f)
        print(f"Updated {pyproject_path} with module {module_path}")
    except Exception as e:
        print(f"Error writing to pyproject.toml: {e}")
        sys.exit(1)


def update_modules_sh():
    # Append the module to the array
    try:
        # Read the existing file
        with open(modules_sh_file, "r") as f:
            content = f.read()

        for i, line in enumerate(content):
            if line.startswith(f"{modules_variable}="):
                # Find the ending quote position
                end_quote_pos = line.rfind('"')
                # Insert the new module before the closing quotes
                if end_quote_pos != -1:
                    new_content = content[:end_quote_pos] + f" {module_path}" + content[end_quote_pos:]

                    # Write the new content
                    with open(modules_sh_file, "w") as f:
                        f.write(new_content)
                        print(f"Updated {modules_sh_file} with module {module_path}")
                else:
                    print(f"Could not find closing quotes in {modules_sh_file}")

    except FileNotFoundError:
        print(f"Error: {modules_sh_file} not found.")


if __name__ == "__main__":
    update_pyproject_toml()
    update_modules_sh()
