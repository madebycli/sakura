# sakura 🌸

A procedural Sakura tree with falling petals for Unix-like terminals. The runtime is implemented in one Python file, uses only the Python standard library, and ships as a reproducible Nix Flake and an Arch Linux package.

## Original project and maintainer

This Python rewrite is derived from the original [`csakura`](https://github.com/realstrawhat/csakura) project created and maintained by [`realstrawhat`](https://github.com/realstrawhat). The original project's authorship and MIT license are preserved and credited here.

## Features

- responsive, organic Sakura canopy
- falling two-cell petal sprites
- Unicode and ASCII rendering
- 15 color palettes
- configurable FPS, density, and wind
- deterministic seeds
- resize handling and terminal cleanup
- no network access, subprocesses, telemetry, or persistent application files
- Python 3.10 or newer

## Commands

The installed public command is:

```sh
sakura
```

The checkout remains directly runnable:

```sh
python3 ./sakura.py
```

Useful non-interactive checks:

```sh
sakura --help
sakura --version
sakura --self-test
```

## Usage

```text
sakura [-f FPS] [-p DENSITY] [-w WIND] [-c PALETTE] [-a]

-f, --fps       5-60, default 20
-p, --density   1-10, default 5
-w, --wind      0-10, default 1
-c, --palette   palette name, default sakura
-a, --ascii     ASCII-only glyphs
--seed          deterministic tree and animation seed
--self-test     non-interactive integrity test
-v, --version   print version
```

Palettes:

`sakura`, `rose`, `blush`, `magenta`, `peach`, `coral`, `sunset`, `gold`, `lavender`, `violet`, `sky`, `mint`, `matcha`, `white`, `ink`

Keys:

- `q`, `Q`, or `Esc`: quit
- `r` or `R`: regrow
- `c`: next palette
- `C`: previous palette

## Nix and NixOS

Nix is the primary packaged distribution target.

Run without installing:

```sh
nix run github:madebycli/sakura -- --help
nix run github:madebycli/sakura
```

Install into the current Nix profile:

```sh
nix profile add github:madebycli/sakura
sakura --self-test
sakura
```

Build and verify a checkout:

```sh
nix flake metadata --no-write-lock-file .
nix flake check --no-write-lock-file --print-build-logs
nix build .#default --no-write-lock-file
./result/bin/sakura --self-test
nix run .#default -- --help
```

### NixOS Flake integration

Add the input:

```nix
{
  inputs.sakura.url = "github:madebycli/sakura";
}
```

Then add the package in a NixOS module where `inputs` and `pkgs` are available:

```nix
{
  inputs,
  pkgs,
  ...
}:
{
  environment.systemPackages = [
    inputs.sakura.packages.${pkgs.system}.default
  ];
}
```

The Flake exports:

- `packages.x86_64-linux.sakura`
- `packages.aarch64-linux.sakura`
- `packages.<system>.default`
- `apps.<system>.sakura`
- `apps.<system>.default`
- `checks.<system>`
- `devShells.<system>.default`

## Development shell

Enter the pinned development environment:

```sh
nix develop
```

Inside the shell:

```sh
python3 ./sakura.py --help
python3 ./sakura.py --self-test
python3 -m unittest discover -s tests -v
python3 -m build --wheel --no-isolation
nixfmt --check flake.nix nix/package.nix
ruff check --select E9,F63,F7,F82 sakura.py tests
```

The packaged command is also available in the shell:

```sh
sakura --help
```

## Python wheel

The common Python package definition is `pyproject.toml`. It installs the single module `sakura.py` and creates the console entry point `sakura = sakura:main`.

Build locally:

```sh
python3 -m build --wheel --no-isolation
```

The application never invokes Pip or creates a virtual environment at runtime.

## Arch Linux

Arch packaging lives in `packaging/arch/` and builds the same wheel as Nix and local Python builds.

```sh
cd packaging/arch
makepkg --syncdeps --cleanbuild
sudo pacman -U ./sakura-*.pkg.tar.zst
```

Verify after installation:

```sh
sakura --version
sakura --self-test
sakura
```

The package is architecture-independent Python and therefore uses `arch=('any')`.

## Fedora status

Fedora packaging is intentionally deferred. Nix and Arch are the required targets and must remain green before an RPM specification is added. A future Fedora package should use the same `pyproject.toml` through the Fedora `%pyproject_*` macros.

## Filesystem behavior

The current application does not create configuration, cache, data, or runtime files. It mutates only in-memory animation state and writes to the active terminal.

No application files are written to:

- the Nix store
- `/usr`
- Python site-packages
- the Git checkout
- the current working directory
- the user home directory

If persistent features are introduced later, they must use XDG paths:

- config: `$XDG_CONFIG_HOME/sakura`
- cache: `$XDG_CACHE_HOME/sakura`
- data: `$XDG_DATA_HOME/sakura`
- runtime: `$XDG_RUNTIME_DIR/sakura`

## Versioning

`sakura.VERSION` in `sakura.py` is the canonical application version. `pyproject.toml` reads it dynamically. Nix, Arch, CI, and tests repeat the release version where their formats require it and verify that their value matches the application output.

## Branch migration and rollback

The Python rewrite was developed on `rewrite/python-single-file`. Before replacing the historical C-based `main`, the original commit was preserved as:

```text
backup/main-before-flake-migration-20260721
```

Original `main` SHA:

```text
9664fcbffac096acdb44cbc8c81527fb57d13639
```

Rollback without deleting history:

```sh
git fetch origin
git switch -c restore-old-main origin/backup/main-before-flake-migration-20260721
```

An administrator can restore the remote branch only after verifying the expected current SHA and using a protected pull request or `--force-with-lease`; uncontrolled force pushes must not be used.

## Testing

Mandatory source checks:

```sh
python3 -m compileall -q .
python3 -m unittest discover -s tests -v
python3 sakura.py --self-test
python3 -O sakura.py --self-test
python3 sakura.py --version
python3 sakura.py --help
```

The Nix derivation repeats syntax, unit, import, CLI, self-test, immutable-store, and version checks. GitHub Actions additionally builds the wheel, installs it in an isolated environment, builds the Arch package as an unprivileged user, inspects package contents, and tests Nix installation from the exact remote commit.

## Supported environments

The runtime targets Unix-like terminals with Python's standard `curses` module. Automated Linux PTY and model tests cover Unicode, ASCII, option extremes, resize behavior, low-color fallback, signal cleanup, terminal restoration, and multiple terminal proportions.

Native NixOS terminal/font combinations and macOS `curses` builds still require environment-specific visual validation. Unicode appearance depends on terminal, locale, and font support; use `--ascii` when needed.

## Architecture and maintenance context

The runtime intentionally remains a single physical file. Logical responsibilities are separated through `Opt`, state dataclasses, `Model`, `Renderer`, `App`, CLI, preflight, and self-test functions.

Future maintainers should read `ai-context/README.md` before changing runtime architecture.

## License

MIT. See `LICENSE`.
