{
  description = "Procedural Sakura tree animation for Unix-like terminals";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          package = pkgs.callPackage ./nix/package.nix { };
        in
        {
          sakura = package;
          default = package;
        }
      );

      apps = forAllSystems (system: rec {
        sakura = {
          type = "app";
          program = "${self.packages.${system}.sakura}/bin/sakura";
        };
        default = sakura;
      });

      checks = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          package = self.packages.${system}.sakura;
          source = nixpkgs.lib.cleanSource ./.;
          closure = pkgs.closureInfo { rootPaths = [ package ]; };
          developmentPython = pkgs.python3.withPackages (
            pythonPackages: with pythonPackages; [
              build
              installer
              setuptools
              wheel
            ]
          );
        in
        {
          inherit package;

          source-tests =
            pkgs.runCommand "sakura-source-tests"
              {
                nativeBuildInputs = [ developmentPython ];
              }
              ''
                cp -r ${source} source
                chmod -R u+w source
                cd source
                python -m compileall -q .
                python -m unittest discover -s tests -v
                python sakura.py --self-test | grep -q '^sakura self-test: PASS$'
                python -O sakura.py --self-test | grep -q '^sakura self-test: PASS$'
                touch "$out"
              '';

          cli-smoke =
            pkgs.runCommand "sakura-cli-smoke"
              {
                nativeBuildInputs = [ package ];
              }
              ''
                export HOME="$TMPDIR/home"
                export XDG_RUNTIME_DIR="$TMPDIR/runtime"
                export XDG_CONFIG_HOME="$TMPDIR/config"
                export XDG_CACHE_HOME="$TMPDIR/cache"
                export XDG_DATA_HOME="$TMPDIR/data"
                mkdir -p \
                  "$HOME" \
                  "$XDG_RUNTIME_DIR" \
                  "$XDG_CONFIG_HOME" \
                  "$XDG_CACHE_HOME" \
                  "$XDG_DATA_HOME"
                chmod 700 "$XDG_RUNTIME_DIR"

                sakura --help >/dev/null
                test "$(sakura --version)" = "sakura 3.0.4"
                sakura --self-test | grep -q '^sakura self-test: PASS$'
                touch "$out"
              '';

          runtime-closure-policy = pkgs.runCommand "sakura-runtime-closure-policy" { } ''
            if grep -E '/[^/]*(setuptools|wheel|pytest|gcc-wrapper|binutils-wrapper)-' \
              ${closure}/store-paths; then
              echo "forbidden build or test dependency in sakura runtime closure" >&2
              exit 1
            fi
            touch "$out"
          '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          package = self.packages.${system}.sakura;
          python = pkgs.python3.withPackages (
            pythonPackages: with pythonPackages; [
              build
              installer
              setuptools
              wheel
            ]
          );
        in
        {
          default = pkgs.mkShell {
            packages = [
              package
              python
              pkgs.ruff
              pkgs.nixfmt-rfc-style
            ];
            shellHook = ''
              export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
              echo "sakura dev shell: python, build, installer, setuptools, wheel, ruff, nixfmt"
              echo "Checkout run: python3 ./sakura.py --help"
              echo "Packaged run: sakura --help"
            '';
          };
        }
      );
    };
}
