from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import sakura


class FakeTTY:
    def __init__(self, value: bool) -> None:
        self.value = value

    def isatty(self) -> bool:
        return self.value


class SakuraTests(unittest.TestCase):
    def test_version_is_public(self) -> None:
        self.assertRegex(sakura.VERSION, r"^\d+\.\d+\.\d+$")

    def test_packaging_uses_expected_entrypoint_and_version(self) -> None:
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        nix_package = Path("nix/package.nix").read_text(encoding="utf-8")
        arch_package = Path("packaging/arch/PKGBUILD").read_text(encoding="utf-8")
        srcinfo = Path("packaging/arch/.SRCINFO").read_text(encoding="utf-8")

        self.assertIn('sakura = "sakura:main"', pyproject)
        self.assertIn('version = { attr = "sakura.VERSION" }', pyproject)
        self.assertIn(f'version = "{sakura.VERSION}";', nix_package)
        self.assertIn(f"pkgver={sakura.VERSION}", arch_package)
        self.assertIn(f"pkgver = {sakura.VERSION}", srcinfo)

    def test_parser_defaults(self) -> None:
        args = sakura.parser().parse_args([])
        self.assertEqual(args.fps, 20)
        self.assertEqual(args.density, 5)
        self.assertEqual(args.wind, 1.0)
        self.assertEqual(args.palette, "sakura")
        self.assertFalse(args.ascii)

    def test_parser_rejects_invalid_values(self) -> None:
        for argv in (["--fps", "4"], ["--density", "11"], ["--wind", "nan"]):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    sakura.parser().parse_args(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_deterministic_generation(self) -> None:
        first = sakura.Model(80, 24, sakura.Opt(seed=12345))
        second = sakura.Model(80, 24, sakura.Opt(seed=12345))
        self.assertEqual(first.grid, second.grid)
        self.assertEqual(first.sources, second.sources)
        self.assertEqual(first.blobs, second.blobs)

    def test_resize_deactivates_and_recovers(self) -> None:
        model = sakura.Model(80, 24, sakura.Opt(seed=7))
        model.resize(1, 1, True)
        self.assertFalse(model.drawable)
        self.assertEqual(model.npetals, 0)
        self.assertFalse(any(petal.active for petal in model.petals))

        model.resize(80, 24, True)
        self.assertTrue(model.drawable)
        self.assertGreaterEqual(model.npetals, 16)
        self.assertTrue(any(model.grid))

    def test_active_petal_sprites_are_two_cells(self) -> None:
        self.assertTrue(all(len(sprite) == 2 for sprite in sakura.PETALS))
        self.assertTrue(all(len(sprite) == 2 and sprite.isascii() for sprite in sakura.APETALS))

    def test_terminal_preflight(self) -> None:
        self.assertIsNone(sakura.preflight(FakeTTY(True), FakeTTY(True), "xterm-256color"))
        self.assertIsNotNone(sakura.preflight(FakeTTY(False), FakeTTY(True), "xterm"))
        self.assertIsNotNone(sakura.preflight(FakeTTY(True), FakeTTY(True), "dumb"))

    def test_main_self_test(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = sakura.main(["--self-test"])
        self.assertEqual(result, 0)
        self.assertIn("sakura self-test: PASS", output.getvalue())


if __name__ == "__main__":
    unittest.main()
