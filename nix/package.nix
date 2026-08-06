{
  lib,
  stdenvNoCC,
  python3,
}:

let
  versionLines = lib.splitString "\n" (builtins.readFile ../sakura.py);
  versionLine = lib.findFirst (
    line: builtins.match "VERSION = \"([^\"]+)\"" line != null
  ) null versionLines;
  versionMatch =
    if versionLine == null then
      throw "Unable to read Sakura VERSION from sakura.py"
    else
      builtins.match "VERSION = \"([^\"]+)\"" versionLine;
  packageVersion = builtins.elemAt versionMatch 0;
in
stdenvNoCC.mkDerivation {
  pname = "sakura";
  version = packageVersion;

  src = lib.cleanSource ../.;
  strictDeps = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall

    mkdir -p "$out/bin"
    install -m755 sakura.py "$out/bin/sakura"
    sed -i '1,2c#!${python3.interpreter}' "$out/bin/sakura"

    runHook postInstall
  '';

  doInstallCheck = true;
  installCheckPhase = ''
    runHook preInstallCheck

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

    test -x "$out/bin/sakura"
    test "$(head -n1 "$out/bin/sakura")" = '#!${python3.interpreter}'
    find "$out" -type f -exec sha256sum {} + | sort > "$TMPDIR/out-before"

    "$out/bin/sakura" --help >/dev/null
    test "$("$out/bin/sakura" --version)" = "sakura ${packageVersion}"
    "$out/bin/sakura" --self-test | grep -q '^sakura self-test: PASS$'
    ${python3.interpreter} -O "$out/bin/sakura" --self-test \
      | grep -q '^sakura self-test: PASS$'

    SCRIPT_PATH="$out/bin/sakura" ${python3.interpreter} -c \
      'import os, runpy; module = runpy.run_path(os.environ["SCRIPT_PATH"]); assert module["VERSION"] == "${packageVersion}"; assert callable(module["main"])'

    ! grep -R -E '/usr/bin/python3|/usr/bin/env|/home/[^/]+|~/|/nix/store/.*/source' \
      "$out/bin"

    find "$out" -type f -exec sha256sum {} + | sort > "$TMPDIR/out-after"
    cmp "$TMPDIR/out-before" "$TMPDIR/out-after"

    runHook postInstallCheck
  '';

  meta = {
    description = "Procedural Sakura tree animation for Unix-like terminals";
    homepage = "https://github.com/madebycli/sakura";
    license = lib.licenses.mit;
    mainProgram = "sakura";
    platforms = lib.platforms.unix;
  };
}
