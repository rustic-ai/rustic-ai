#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib  # Requires Python 3.11+
from typing import Dict, List, Set


def get_project_root() -> Path:
    """Returns the project root directory."""
    return Path(__file__).resolve().parent.parent

def find_packages(root: Path) -> Dict[str, Path]:
    """
    Finds all packages in the monorepo by looking for pyproject.toml files.
    Returns a dict mapping package name to its directory path.
    """
    packages = {}
    for path in root.rglob("pyproject.toml"):
        # Skip the root pyproject.toml if it's just a container
        if path.parent == root:
             # In some setups root is also a package, let's include it if it has a name
             pass
        
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
                name = data.get("tool", {}).get("poetry", {}).get("name")
                if name:
                    packages[name] = path.parent
        except Exception as e:
            print(f"Warning: Could not parse {path}: {e}", file=sys.stderr)
    return packages

def get_dependencies(packages: Dict[str, Path]) -> Dict[str, Set[str]]:
    """
    Builds a dependency graph (mapping package -> set of direct dependencies).
    Only considers dependencies that are part of the monorepo (internal deps).
    """
    graph: Dict[str, Set[str]] = {name: set() for name in packages}
    
    for name, path in packages.items():
        pyproject_path = path / "pyproject.toml"
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                
            poetry = data.get("tool", {}).get("poetry", {})
            deps = poetry.get("dependencies", {})
            dev_deps = poetry.get("group", {}).get("dev", {}).get("dependencies", {})
            
            all_deps = list(deps.keys()) + list(dev_deps.keys())
            
            for dep in all_deps:
                if dep in packages and dep != name:
                    graph[name].add(dep)
                    
        except Exception:
            pass
            
    return graph

def get_dependents(graph: Dict[str, Set[str]]) -> Dict[str, Set[str]]:
    """
    Inverts the dependency graph to find dependents (mapping package -> set of packages that depend on it).
    """
    dependents: Dict[str, Set[str]] = {name: set() for name in graph}
    for pkg, deps in graph.items():
        for dep in deps:
            if dep in dependents:
                dependents[dep].add(pkg)
    return dependents

def get_changed_files(base_ref: str, head_ref: str, root: Path) -> Set[Path]:
    """
    Returns a set of changed files between base_ref and head_ref.
    """
    try:
        cmd = ["git", "diff", "--name-only", base_ref, head_ref]
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True)
        return {root / line.strip() for line in result.stdout.splitlines() if line.strip()}
    except subprocess.CalledProcessError as e:
        print(f"Error running git diff: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Determine which packages need testing based on changes.")
    parser.add_argument("--base", default="origin/main", help="Base ref for comparison")
    parser.add_argument("--head", default="HEAD", help="Head ref for comparison")
    args = parser.parse_args()

    root = get_project_root()
    packages = find_packages(root)
    # Filter out root if it's in packages but points to root directory, 
    # unless we specifically want to track it. For this logic, we usually want subdirs.
    # But if root has code, we should keep it.
    
    # Map paths to package names for easy lookup
    path_to_package = {p: n for n, p in packages.items()}
    
    # Build graph
    deps_graph = get_dependencies(packages)
    dependents_graph = get_dependents(deps_graph)
    
    # Get changes
    changed_files = get_changed_files(args.base, args.head, root)
    
    affected_packages = set()
    global_files_changed = False
    
    # Files that usually require full run
    global_triggers = {
        "poetry.lock",
        "pyproject.toml", # Root pyproject
        "tox.ini",
        ".github/workflows/validate-pr.yml",
        "scripts/run_all_tests.sh",
        "scripts/determine_test_targets.py"
    }

    for file_path in changed_files:
        rel_path = file_path.relative_to(root)
        
        # Check global triggers
        if str(rel_path) in global_triggers:
            global_files_changed = True
            break
            
        # Check if file belongs to any package
        found_pkg = False
        # Sort packages by path length descending to match most specific first
        sorted_packages = sorted(path_to_package.items(), key=lambda x: len(str(x[0])), reverse=True)
        
        for pkg_path, pkg_name in sorted_packages:
            # Check if file is inside package directory
            try:
                file_path.relative_to(pkg_path)
                affected_packages.add(pkg_name)
                found_pkg = True
                break
            except ValueError:
                continue
        
        if not found_pkg:
            # File outside any known package (e.g. shared scripts, root config not listed above)
            # Conservatively assume global change or ignore? 
            # If it's code/config, safer to run all.
            if file_path.suffix in ['.py', '.toml', '.ini', '.sh']:
                global_files_changed = True
                break

    if global_files_changed:
        print(".")
        return

    if not affected_packages:
        print("") # No packages affected
        return

    # Identify root package name
    root_pkg_name = None
    for name, p in packages.items():
        if p == root:
             root_pkg_name = name
             break

    # Resolve transitive dependents
    queue = list(affected_packages)
    final_set = set(affected_packages)
    
    while queue:
        current = queue.pop(0)
        for dependent in dependents_graph.get(current, []):
            # Skip root package as a dependent to avoid running all tests
            if dependent == root_pkg_name:
                continue
                
            if dependent not in final_set:
                final_set.add(dependent)
                queue.append(dependent)
    
    # Output paths relative to root
    # We want to print directories of the affected packages
    paths = [str(packages[pkg].relative_to(root)) for pkg in final_set]
    print(" ".join(sorted(paths)))

if __name__ == "__main__":
    main()
