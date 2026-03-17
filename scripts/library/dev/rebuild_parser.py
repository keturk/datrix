#!/usr/bin/env python3
"""
Rebuild Tree-sitter Parser for Datrix DSL

This module rebuilds the tree-sitter parser by generating parser.c from grammar.js
and compiling it into a platform-specific shared library (.dll/.so/.dylib).

Steps:
1. Generates parser.c from grammar.js using 'tree-sitter generate'
2. Compiles the parser into a shared library using 'tree-sitter build'
3. Stores the grammar hash for change detection

The parser will automatically detect grammar changes on next use if the
Python auto-build functionality is enabled.
"""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Add datrix-common to path for logging
_script_dir = Path(__file__).resolve().parent
_datrix_root = _script_dir.parent.parent.parent
_core_src = _datrix_root / "datrix-common" / "src"
if _core_src.exists() and str(_core_src) not in sys.path:
    sys.path.insert(0, str(_core_src))
from datrix_common.logging import get_logger

logger = get_logger(__name__)


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_colored(message: str, color: str = '') -> None:
    """Print a message with optional color"""
    if color and sys.stdout.isatty():
        print(f"{color}{message}{Colors.RESET}")
    else:
        print(message)


def find_vcvarsall() -> Optional[Path]:
    """
    Find Visual Studio vcvarsall.bat on Windows

    Returns:
        Path to vcvarsall.bat if found, None otherwise
    """
    if platform.system() != 'Windows':
        return None

    # Possible Visual Studio installation paths
    program_files = os.environ.get('ProgramFiles', r'C:\Program Files')
    program_files_x86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')

    vcvars_paths = [
        # Visual Studio 18 (version number format)
        Path(program_files) / r'Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\18\Professional\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files_x86) / r'Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvarsall.bat',
        # Visual Studio 2022
        Path(program_files) / r'Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files_x86) / r'Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat',
        # Visual Studio 2019
        Path(program_files) / r'Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\2019\Professional\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files) / r'Microsoft Visual Studio\2019\Enterprise\VC\Auxiliary\Build\vcvarsall.bat',
        Path(program_files_x86) / r'Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvarsall.bat',
    ]

    for vcvars_path in vcvars_paths:
        if vcvars_path.exists():
            return vcvars_path

    return None


def setup_msvc_environment() -> bool:
    """
    Set up MSVC environment on Windows by sourcing vcvarsall.bat

    Returns:
        True if setup was successful, False otherwise
    """
    if platform.system() != 'Windows':
        return True

    # Check if cl.exe is already available AND include paths are set
    # Just having cl.exe in PATH isn't enough - we need the full MSVC environment
    # with INCLUDE paths for Windows SDK headers (stdbool.h, etc.)
    if shutil.which('cl.exe') and os.environ.get('INCLUDE'):
        cl_path = shutil.which('cl.exe')
        print_colored(f"Found C compiler: {cl_path}", Colors.GRAY)
        return True

    if shutil.which('cl.exe'):
        print_colored("MSVC compiler found but environment not fully configured", Colors.YELLOW)
    else:
        print_colored("MSVC compiler (cl.exe) not found in PATH", Colors.YELLOW)
    print_colored("Attempting to locate Visual Studio Build Tools...", Colors.GRAY)

    vcvarsall = find_vcvarsall()
    if not vcvarsall:
        print_colored("Visual Studio Build Tools not found.", Colors.YELLOW)
        print()
        print_colored("C compiler is not available.", Colors.RED)
        print()
        print_colored("Please either:", Colors.YELLOW)
        print_colored("  1. Run this script from a Developer Command Prompt for VS", Colors.CYAN)
        print_colored("  2. Install Visual Studio Build Tools and restart terminal:", Colors.CYAN)
        print_colored("     https://visualstudio.microsoft.com/downloads/", Colors.GRAY)
        print()
        return False

    print_colored(f"Found Visual Studio at: {vcvarsall}", Colors.GREEN)
    print_colored("Setting up MSVC environment...", Colors.GRAY)

    # Create a batch file that sets up MSVC and exports environment to a file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
        bat_path = bat_file.name
        bat_file.write('@echo off\n')
        bat_file.write(f'call "{vcvarsall}" x64 >nul 2>&1\n')
        bat_file.write('if %ERRORLEVEL% NEQ 0 (\n')
        bat_file.write(f'  call "{vcvarsall}" x86 >nul 2>&1\n')
        bat_file.write(')\n')
        bat_file.write('set\n')

    try:
        # Execute the batch file and capture environment variables
        result = subprocess.run(
            ['cmd.exe', '/c', bat_path],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # Parse environment variables from output
        for line in result.stdout.split('\n'):
            if '=' in line:
                key, _, value = line.partition('=')
                os.environ[key] = value

        # Verify cl.exe is now available
        if shutil.which('cl.exe'):
            cl_path = shutil.which('cl.exe')
            print_colored(f"[OK] MSVC environment configured: {cl_path}", Colors.GREEN)
            print()
            return True
        else:
            print_colored("Warning: MSVC environment setup may have failed", Colors.YELLOW)
            print_colored("You may need to run this from a Developer Command Prompt", Colors.YELLOW)
            print()
            return False

    except Exception as e:
        print_colored(f"Warning: Failed to set up MSVC environment: {e}", Colors.YELLOW)
        print_colored("You may need to run this from a Developer Command Prompt", Colors.YELLOW)
        print()
        return False

    finally:
        # Clean up temporary batch file
        try:
            os.unlink(bat_path)
        except:
            pass


def try_commands(commands: List[List[str]], success_check: callable) -> Tuple[bool, Optional[str]]:
    """
    Try a list of commands until one succeeds

    Args:
        commands: List of command arrays to try
        success_check: Function that returns True if command was successful

    Returns:
        Tuple of (success: bool, last_error: Optional[str])
    """
    last_error = None

    # Known non-critical error patterns to suppress
    suppress_patterns = [
        "Warning: You have not configured any parser directories",
        "Please run `tree-sitter init-config`",
        "configuration file to indicate where we should look for",
        "language grammars",
        "Error opening dynamic library",
        "LoadLibraryExW failed",
        "%1 is not a valid Win32 application",
        "thread 'main' panicked",
        "note: run with `RUST_BACKTRACE=1`",
        "Caused by:",
        "is not recognized as an internal or external command",
        "operable program or batch file",
        "Warning: unnecessary conflicts",
        " `"  # Suppress conflict detail lines that start with backtick
    ]

    for cmd in commands:
        try:
            # On Windows, use shell=True to properly find commands in PATH
            use_shell = platform.system() == 'Windows'

            result = subprocess.run(
                cmd if not use_shell else ' '.join(cmd),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                shell=use_shell
            )

            # Check if command succeeded by checking output file first
            # This is important because tree-sitter may crash during post-build
            # validation (LoadLibraryExW error) even when the build succeeded
            if success_check():
                # Only display relevant output from the successful command
                stdout_lines = [line for line in result.stdout.split('\n')
                                if line.strip() and not any(pattern in line for pattern in suppress_patterns)]
                stderr_lines = [line for line in result.stderr.split('\n')
                                if line.strip() and not any(pattern in line for pattern in suppress_patterns)]

                if stdout_lines:
                    print('\n'.join(stdout_lines))
                # Only show stderr if it contains meaningful errors
                if stderr_lines and result.returncode != 0:
                    print('\n'.join(stderr_lines))

                return True, None

            # Give file system a moment to sync, then check again
            time.sleep(0.5)
            if success_check():
                return True, None

            # File doesn't exist - record error and try next command
            if result.returncode != 0:
                last_error = result.stderr.strip() or f"Exit code: {result.returncode}"
            else:
                last_error = "Success check failed after command execution"
            continue

        except FileNotFoundError:
            last_error = f"Command not found: {cmd[0]}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    return False, last_error


def get_grammar_hash(grammar_file: Path) -> str:
    """Calculate SHA256 hash of grammar file"""
    content = grammar_file.read_bytes()
    return hashlib.sha256(content).hexdigest()


def rebuild_parser(force: bool = False) -> int:
    """
    Rebuild the tree-sitter parser

    Args:
        force: Force rebuild even if grammar hasn't changed

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Get script directory and project paths
    script_dir = Path(__file__).parent
    datrix_root = script_dir.parent.parent.parent.parent  # dev -> library -> scripts -> datrix -> repo root

    # Paths for structure
    grammar_dir = datrix_root / 'datrix-language' / 'src' / 'datrix_language' / 'parser' / 'tree_sitter_datrix'
    build_dir = grammar_dir / 'build'
    grammar_file = grammar_dir / 'grammar.js'

    # Determine library name based on OS
    system = platform.system()
    if system == 'Windows':
        lib_name = 'tree_sitter_datrix.dll'
    elif system == 'Darwin':
        lib_name = 'tree_sitter_datrix.dylib'
    else:
        lib_name = 'tree_sitter_datrix.so'

    lib_path = build_dir / lib_name
    hash_file = build_dir / 'tree_sitter_datrix.hash'

    # Check if grammar file exists
    if not grammar_file.exists():
        print_colored(f"Grammar file not found: {grammar_file}", Colors.RED)
        print()
        print_colored("Please ensure the grammar.js file exists in the tree-sitter grammar directory.", Colors.YELLOW)
        return 1

    # Check if grammar directory exists
    if not grammar_dir.exists():
        print_colored(f"Grammar directory not found: {grammar_dir}", Colors.RED)
        print()
        print_colored("Please ensure the datrix-language project is available.", Colors.YELLOW)
        return 1

    print()
    print_colored("========================================", Colors.CYAN)
    print_colored("Rebuilding Tree-sitter Parser (Datrix)", Colors.CYAN)
    print_colored("========================================", Colors.CYAN)
    print()
    print_colored(f"Grammar file: {grammar_file}", Colors.GRAY)
    print_colored(f"Output library: {lib_path}", Colors.GRAY)
    print()

    # Check if rebuild is needed
    current_hash = get_grammar_hash(grammar_file)
    if not force and lib_path.exists() and hash_file.exists():
        stored_hash = hash_file.read_text().strip()
        if stored_hash == current_hash:
            print_colored("Grammar unchanged - no rebuild needed.", Colors.GREEN)
            print_colored("Use --force to rebuild anyway.", Colors.GRAY)
            return 0

    # Check for C compiler on Windows and set up MSVC environment if needed
    if not setup_msvc_environment():
        return 1

    # Initialize tree-sitter config if it doesn't exist
    home_dir = Path.home()
    tree_sitter_config = home_dir / '.tree-sitter' / 'config.json'
    if not tree_sitter_config.exists():
        print_colored("Initializing tree-sitter configuration...", Colors.GRAY)
        try:
            use_shell = platform.system() == 'Windows'
            subprocess.run(
                'tree-sitter init-config' if use_shell else ['tree-sitter', 'init-config'],
                shell=use_shell,
                capture_output=True
            )
            print_colored("Tree-sitter config initialized", Colors.GRAY)
        except:
            # If this fails, it's not critical - tree-sitter will work without it
            pass

    try:
        # Step 1: Generate parser.c from grammar.js
        print_colored("Step 1: Generating parser.c from grammar.js...", Colors.YELLOW)
        print()

        os.chdir(grammar_dir)

        parser_c = grammar_dir / 'src' / 'parser.c'

        # Remove old parser.c to ensure fresh generation
        if parser_c.exists():
            parser_c.unlink()
            print_colored("Removed old parser.c", Colors.GRAY)

        # Try tree-sitter CLI first, then npx as fallback
        generate_commands = [
            ['tree-sitter', 'generate'],
            ['npx', 'tree-sitter-cli', 'generate'],
            ['npx', '--yes', 'tree-sitter-cli', 'generate']
        ]

        # Record time before generation
        generation_start_time = time.time()

        def check_parser_generated():
            # Check if file exists and was created after we started
            if parser_c.exists():
                return parser_c.stat().st_mtime >= generation_start_time
            return False

        generate_success, last_error = try_commands(generate_commands, check_parser_generated)

        if not generate_success:
            print_colored("Failed to generate parser.c", Colors.RED)
            print()
            print_colored("Tried commands:", Colors.YELLOW)
            for cmd in generate_commands:
                print_colored(f"  - {' '.join(cmd)}", Colors.GRAY)
            print()
            if last_error:
                print_colored(f"Last error: {last_error}", Colors.RED)
            print()
            print_colored("Please ensure tree-sitter CLI is installed:", Colors.YELLOW)
            print_colored("  npm install -g tree-sitter-cli", Colors.CYAN)
            print_colored("  or use npx (no installation needed)", Colors.CYAN)
            return 1

        # Verify parser.c exists and is not empty
        if not parser_c.exists():
            print_colored("Error: parser.c was not created", Colors.RED)
            return 1

        if parser_c.stat().st_size < 100:
            print_colored("Error: parser.c appears to be invalid (too small)", Colors.RED)
            return 1

        print_colored("[OK] Parser generation successful", Colors.GREEN)
        print()

        # Step 2: Build the library
        print_colored("Step 2: Building parser library...", Colors.YELLOW)
        print()

        # Ensure build directory exists
        build_dir.mkdir(parents=True, exist_ok=True)
        print_colored(f"Ensured build directory exists: {build_dir}", Colors.GRAY)

        # Handle old library if it exists
        old_lib_path = None
        if lib_path.exists():
            old_lib_path = lib_path.with_suffix(lib_path.suffix + '.old')
            try:
                if old_lib_path.exists():
                    old_lib_path.unlink()
                lib_path.rename(old_lib_path)
                print_colored(f"Renamed old library to: {old_lib_path.name}", Colors.GRAY)
            except OSError:
                try:
                    lib_path.unlink()
                    print_colored(f"Removed old library: {lib_name}", Colors.GRAY)
                except OSError as delete_error:
                    if platform.system() == 'Windows':
                        print_colored(f"Warning: Cannot remove old library (file may be in use): {lib_name}", Colors.YELLOW)
                    old_lib_path = None

        # Try tree-sitter CLI first, then npx as fallback
        build_commands = [
            ['tree-sitter', 'build', '--output', str(lib_path)],
            ['npx', 'tree-sitter-cli', 'build', '--output', str(lib_path)],
            ['npx', '--yes', 'tree-sitter-cli', 'build', '--output', str(lib_path)]
        ]

        def check_library_built():
            return lib_path.exists()

        build_success, last_error = try_commands(build_commands, check_library_built)

        if not build_success:
            print_colored("Failed to build parser library", Colors.RED)
            print()
            print_colored("Tried commands:", Colors.YELLOW)
            for cmd in build_commands:
                print_colored(f"  - {' '.join(cmd)}", Colors.GRAY)
            print()
            if last_error:
                print_colored(f"Last error: {last_error}", Colors.RED)
            print()
            print_colored("Please ensure:", Colors.YELLOW)
            print_colored("  1. tree-sitter CLI is installed: npm install -g tree-sitter-cli", Colors.CYAN)
            print_colored("  2. C compiler is available:", Colors.CYAN)
            print_colored("     - Windows: Install Visual Studio Build Tools", Colors.GRAY)
            print_colored("       https://visualstudio.microsoft.com/downloads/", Colors.GRAY)
            print_colored("       Or use: Developer Command Prompt for VS", Colors.GRAY)
            print_colored("     - Linux: GCC or Clang (usually pre-installed)", Colors.GRAY)
            print_colored("     - macOS: Xcode Command Line Tools (xcode-select --install)", Colors.GRAY)
            return 1

        print_colored("[OK] Library build successful", Colors.GREEN)
        print()

        # Clean up old library file if it was renamed
        if old_lib_path and old_lib_path.exists():
            try:
                old_lib_path.unlink()
                print_colored(f"Cleaned up old library: {old_lib_path.name}", Colors.GRAY)
            except OSError:
                print_colored(f"Note: Could not delete old library (still in use): {old_lib_path.name}", Colors.YELLOW)
        print()

        # Step 3: Update grammar hash
        print_colored("Step 3: Updating grammar hash...", Colors.YELLOW)
        print()

        hash_file.write_text(current_hash, encoding='utf-8')
        print_colored(f"Updated grammar hash: {current_hash[:16]}...", Colors.GRAY)
        print_colored(f"Hash file location: {hash_file}", Colors.GRAY)
        print_colored("[OK] Grammar hash updated", Colors.GREEN)
        print()

        print_colored("========================================", Colors.GREEN)
        print_colored("Parser rebuild complete!", Colors.GREEN)
        print_colored("========================================", Colors.GREEN)
        print()
        print_colored(f"Library location: {lib_path}", Colors.GRAY)
        print()
        print_colored("The parser will automatically detect grammar changes on next use.", Colors.CYAN)
        print()

        return 0

    except Exception as e:
        print()
        print_colored("Error occurred:", Colors.RED)
        print_colored(str(e), Colors.RED)
        print()
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Rebuild Tree-sitter Parser for Datrix DSL'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Force rebuild even if grammar hasn\'t changed'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    import logging
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

    exit_code = rebuild_parser(force=args.force)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
