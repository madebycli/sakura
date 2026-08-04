#!/usr/bin/env nix-shell
#! nix-shell -i python3 -p python3
"""Single-file, standard-library terminal sakura animation."""
from __future__ import annotations

import argparse
import curses
import locale
import math
import os
import random
import signal
import sys
import time
from dataclasses import dataclass

VERSION = "3.0.4"
MAX_PETALS = 768
MAX_SOURCES = 4096
MAX_BLOBS = 28
MIN_W = 20
MIN_H = 8
REF_FPS = 20.0

PALETTES = {
    "sakura": (225, 224, 218, 212, 211, 175, 168, 132),
    "rose": (224, 218, 211, 204, 203, 161, 125, 88),
    "blush": (225, 218, 217, 211, 210, 168, 131, 95),
    "magenta": (219, 213, 207, 200, 163, 127, 90, 53),
    "peach": (223, 216, 215, 209, 173, 130, 94, 58),
    "coral": (217, 210, 209, 203, 167, 131, 88, 52),
    "sunset": (223, 216, 209, 203, 167, 131, 88, 52),
    "gold": (229, 222, 221, 179, 136, 94, 58, 52),
    "lavender": (189, 183, 147, 141, 140, 98, 61, 54),
    "violet": (183, 177, 141, 135, 98, 91, 54, 53),
    "sky": (153, 117, 111, 75, 68, 31, 25, 24),
    "mint": (158, 122, 115, 79, 72, 35, 29, 22),
    "matcha": (193, 150, 149, 107, 70, 64, 28, 22),
    "white": (255, 225, 224, 218, 211, 175, 168, 132),
    "ink": (255, 252, 251, 248, 245, 242, 239, 236),
}
NAMES = tuple(PALETTES)
BLOOMS = ("❀", "✿", "❁", "✽")
PETALS = ("❀.", ".✿", "❁*", "*✽")
ABLOOMS = ("&", "%", "@", "*")
APETALS = ("*.", ".*", "o*", "*o")

P0 = 1
TD = 9
TM = 10
TL = 11
GRASS = 12
FADED = 13


@dataclass(slots=True)
class Opt:
    fps: int = 20
    density: int = 5
    wind: float = 1.0
    ascii: bool = False
    palette: str = "sakura"
    seed: int | None = None

    def __post_init__(self) -> None:
        if type(self.fps) is not int or not 5 <= self.fps <= 60:
            raise ValueError("fps must be an integer between 5 and 60")
        if type(self.density) is not int or not 1 <= self.density <= 10:
            raise ValueError("density must be an integer between 1 and 10")
        if isinstance(self.wind, bool) or not isinstance(self.wind, (int, float)):
            raise ValueError("wind must be a number between 0 and 10")
        self.wind = float(self.wind)
        if not math.isfinite(self.wind) or not 0.0 <= self.wind <= 10.0:
            raise ValueError("wind must be a finite number between 0 and 10")
        if type(self.ascii) is not bool:
            raise ValueError("ascii must be a boolean")
        if self.palette not in PALETTES:
            raise ValueError(f"unknown palette: {self.palette}")
        if self.seed is not None and (type(self.seed) is not int):
            raise ValueError("seed must be an integer or None")


@dataclass(slots=True)
class Cell:
    glyph: str
    pair: int
    bold: bool = False


@dataclass(slots=True)
class Blob:
    x: float
    y: float
    rx: float
    ry: float


@dataclass(slots=True)
class Petal:
    x: float = 0.0
    y: float = 0.0
    vy: float = 0.0
    phase: float = 0.0
    omega: float = 0.0
    sway: float = 0.0
    glyph: str = "*"
    pair: int = P0
    rest: float = -1.0
    active: bool = False


class Model:
    def __init__(self, w: int, h: int, opt: Opt):
        self.o = opt
        self.r = random.Random(opt.seed)
        self.petals = [Petal() for _ in range(MAX_PETALS)]
        self.wind = 0.0
        self.wind_target = 0.0
        self.resize(w, h, True)

    def u(self, a: float, b: float) -> float:
        return self.r.uniform(a, b)

    @staticmethod
    def clamp(v: float, a: float, b: float) -> float:
        return a if v < a else b if v > b else v

    @property
    def drawable(self) -> bool:
        return self.w >= MIN_W and self.h >= MIN_H

    def glyphs(self):
        if self.o.ascii:
            return "@", "%", ":", ".", ABLOOMS, APETALS
        return "█", "▓", "▒", "·", BLOOMS, PETALS

    def resize(self, w: int, h: int, scatter: bool) -> None:
        self.w = max(1, int(w))
        self.h = max(1, int(h))
        self.grid = [None] * (self.w * self.h)
        self.sources = []
        self.blobs = []
        self.tips = []
        self.npetals = 0
        if self.drawable:
            self.tree()
            self.reset_petals(scatter)
        else:
            for petal in self.petals:
                petal.active = False

    def put(self, x: int, y: int, glyph: str, pair: int, bold: bool = False) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.grid[y * self.w + x] = Cell(glyph, pair, bold)

    def field(self, x: float, y: float) -> float:
        return sum(
            math.exp(-(((x - blob.x) / blob.rx) ** 2 + ((y - blob.y) / blob.ry) ** 2) * 2.2)
            for blob in self.blobs
        )

    def canopy(self) -> None:
        full, dark, med, dot, blooms, _ = self.glyphs()
        x0 = min(blob.x - blob.rx for blob in self.blobs)
        x1 = max(blob.x + blob.rx for blob in self.blobs)
        y0 = min(blob.y - blob.ry for blob in self.blobs)
        y1 = max(blob.y + blob.ry for blob in self.blobs)
        cy = (y0 + y1) / 2.0
        ry = max((y1 - y0) / 2.0, 2.0)

        for y in range(int(y0 - 2), int(y1 + 3) + 1):
            if not 0 <= y < self.h:
                continue
            for x in range(int(x0 - 3), int(x1 + 3) + 1):
                if not 0 <= x < self.w:
                    continue
                field = self.field(x, y)
                if field < 0.30 or (field < 0.42 and self.r.random() < 0.35):
                    continue
                vertical = self.clamp((y - (cy - ry)) / (2.0 * ry), 0.0, 1.0)
                if vertical > 0.62 and field < 0.85 and self.r.random() < (vertical - 0.62) * 1.3:
                    continue
                shade = vertical * 6.0 + self.u(-0.9, 0.9)
                above = self.field(x, y - 1.6)
                shade += 1.7 if above > field * 1.12 else -1.5 if above < field * 0.88 else 0.0
                bold = False
                if field > 0.92:
                    glyph = full if self.r.random() < 0.80 else dark
                elif field > 0.55:
                    glyph = dark if self.r.random() < 0.60 else med
                else:
                    choice = self.r.random()
                    glyph = med if choice < 0.45 else self.r.choice(blooms) if choice < 0.85 else dot
                    bold = self.r.random() < 0.30
                if field > 0.55 and self.r.random() < 0.07:
                    glyph = self.r.choice(blooms)
                    bold = True
                    shade -= 2.0
                self.put(x, y, glyph, P0 + int(self.clamp(shade, 0.0, 7.0)), bold)
                if (
                    len(self.sources) < MAX_SOURCES
                    and (field < 0.60 or above > field * 1.12)
                    and self.r.random() < 0.50
                ):
                    self.sources.append((x, y))

    def trunk(self, bx: float, tx: float, ty: float) -> None:
        full, *_ = self.glyphs()
        base_y = self.h - 2.0
        height = max(base_y - ty, 2.0)
        max_width = self.clamp(self.w * 0.028, 2.0, 5.0)
        bend = self.u(-1.0, 1.0) * self.clamp(self.w * 0.02, 1.0, 4.0)
        steps = int(height * 2.0) + 2
        for index in range(steps + 1):
            t = index / steps
            y = base_y - t * height
            x = bx + (tx - bx) * t + math.sin(t * math.pi) * bend
            half = max_width * (1.0 - t) ** 1.1 * (1.0 + 1.1 * math.exp(-t * 10.0)) + 0.6
            for dx in range(int(-half), int(half) + 1):
                pair = TD if dx < -half * 0.35 else TL if dx > half * 0.45 else TM
                self.put(int(x + dx), int(y), full, pair)

    def branch(self, x: float, y: float, angle: float, length: float, depth: int) -> None:
        full, *_ = self.glyphs()
        travelled = 0.0
        while travelled < length:
            next_x = x + math.cos(angle) * 1.7
            next_y = y - math.sin(angle) * 0.85
            travelled += 1.0
            angle = self.clamp(angle + self.u(-0.10, 0.10), 0.15, math.pi - 0.15)

            # Do not reflect at the crown limits. Reflection made shallow
            # branches scrape along one row and appear as solid brown bars.
            if next_x < self.bxmin or next_x > self.bxmax or next_y < self.bymin:
                if len(self.tips) < 64:
                    self.tips.append((int(x), int(y)))
                return

            x, y = next_x, next_y
            self.put(int(x), int(y), full, TM if depth == 0 else TL)
            if depth == 0:
                self.put(int(x) + 1, int(y), full, TD)
            elif self.r.random() < 0.35:
                self.put(int(x) + (-1 if self.r.random() < 0.5 else 1), int(y), full, TM)

        if depth >= 2 or length < 3.0:
            if len(self.tips) < 64:
                self.tips.append((int(x), int(y)))
            return

        for index in range(3 if self.r.random() < 0.5 else 2):
            spread = self.u(0.40, 0.80)
            new_angle = (
                angle + spread
                if index == 0
                else angle - spread
                if index == 1
                else angle + self.u(-0.25, 0.25)
            )
            self.branch(x, y, new_angle, length * self.u(0.55, 0.75), depth + 1)

    def ground(self, cx: float, rx: float) -> None:
        *_, dot, blooms, _ = self.glyphs()
        y = self.h - 1
        for x in range(self.w):
            probability = math.exp(-(((x - cx) / (rx * 1.25)) ** 2) * 2.2)
            choice = self.r.random()
            if choice < probability * 0.50:
                glyph_choice = self.r.random()
                glyph = self.r.choice(blooms) if glyph_choice < 0.25 else dot if glyph_choice < 0.60 else ","
                self.put(x, y, glyph, P0 + 3 + self.r.randrange(4))
            elif choice < probability * 0.50 + 0.10:
                self.put(x, y, '"', GRASS)
            elif choice < probability * 0.50 + 0.16:
                self.put(x, y, ",", GRASS)
            else:
                self.put(x, y, "_", GRASS)
            if self.h > 3 and self.r.random() < probability * 0.12:
                self.put(x, y - 1, dot, FADED)

    def tree(self) -> None:
        self.grid = [None] * (self.w * self.h)
        self.sources = []
        self.blobs = []
        self.tips = []

        # Keep the organic version-2/original generator. Only the former fixed
        # rx <= 36 cap is replaced with responsive horizontal scaling.
        usable_width = max(1.0, self.w - 4.0)
        rx = self.clamp(min(usable_width * 0.36, self.h * 1.55), 6.0, usable_width * 0.48)
        ry = self.clamp(min(self.h * 0.225, rx * 0.25), 3.0, max(3.0, rx * 0.30))
        self.crown_rx = rx
        self.crown_ry = ry

        cx = self.w * 0.5 + self.u(-1.5, 1.5)
        cy = min(max(ry + 2.5, self.h * 0.25), self.h - ry - 5.0)
        cy = max(ry + 1.0, cy)
        self.crown_cx = cx
        self.crown_cy = cy

        bx = cx + self.u(-2.0, 2.0)
        tx = cx + self.u(-2.0, 2.0)
        ty = min(max(cy + ry * 1.15, self.h * 0.52), self.h - 4.0)
        self.bxmin = cx - rx * 0.72
        self.bxmax = cx + rx * 0.72
        self.bymin = max(1.0, cy - ry * 0.55)

        self.ground(cx, rx)
        self.trunk(bx, tx, ty)

        limbs = 3 + self.r.randrange(2)
        reach = (ty - self.bymin) * 0.60 + 2.0
        for index in range(limbs):
            angle = (
                math.pi / 2.0
                + (index - (limbs - 1) / 2.0) * self.u(0.55, 0.75)
                + self.u(-0.15, 0.15)
            )
            self.branch(
                tx + self.u(-1.0, 1.0),
                ty + self.u(0.0, 1.5),
                angle,
                reach * self.u(0.75, 1.0),
                0,
            )

        self.blobs = [Blob(cx, cy - ry * 0.10, rx * 0.50, ry * 0.50)]
        for x, y in self.tips:
            if len(self.blobs) >= MAX_BLOBS - 4:
                break
            self.blobs.append(
                Blob(
                    self.clamp(x + self.u(-1.5, 1.5), cx - rx * 0.72, cx + rx * 0.72),
                    self.clamp(y - self.u(0.0, 1.5), cy - ry * 0.45, cy + ry * 0.45),
                    rx * self.u(0.18, 0.30),
                    ry * self.u(0.24, 0.38),
                )
            )
        for _ in range(5):
            if len(self.blobs) >= MAX_BLOBS:
                break
            self.blobs.append(
                Blob(
                    cx + self.u(-0.70, 0.70) * rx,
                    cy + self.u(0.25, 0.60) * ry,
                    rx * self.u(0.18, 0.28),
                    ry * self.u(0.24, 0.34),
                )
            )
        self.canopy()

    def spawn(self, petal: Petal, scatter: bool = False) -> None:
        *_, petal_glyphs = self.glyphs()
        petal.active = True
        petal.rest = -1.0
        if self.sources and self.r.random() < 0.85:
            x, y = self.r.choice(self.sources)
            petal.x = x + self.u(-1.0, 1.0)
            petal.y = y + self.u(0.0, 1.0)
        else:
            petal.x = self.r.random() * self.w
            petal.y = -self.u(0.0, 3.0)
        if scatter:
            petal.y = self.u(0.0, max(0.0, self.h - 2.0))
        petal.vy = self.u(0.10, 0.28) * REF_FPS
        petal.sway = self.u(0.10, 0.45) * REF_FPS
        petal.omega = self.u(0.05, 0.18) * REF_FPS
        petal.phase = self.r.random() * 2.0 * math.pi
        petal.glyph = self.r.choice(petal_glyphs)
        petal.pair = P0 + 1 + self.r.randrange(5)

    def reset_petals(self, scatter: bool = False) -> None:
        for petal in self.petals:
            petal.active = False
        if not self.drawable:
            self.npetals = 0
            return
        self.npetals = max(16, min(MAX_PETALS, self.w * self.o.density // 4))
        for petal in self.petals[: self.npetals]:
            if self.r.random() < 0.60:
                self.spawn(petal, scatter)

    def update(self, dt: float) -> None:
        if not isinstance(dt, (int, float)) or isinstance(dt, bool) or not math.isfinite(dt) or dt <= 0.0:
            return
        dt = min(float(dt), 0.25)
        frame_scale = dt * REF_FPS
        if self.r.random() < 1.0 - (1.0 - 0.008) ** frame_scale:
            self.wind_target = self.u(-0.12, 0.45) * self.o.wind * REF_FPS
        self.wind += (self.wind_target - self.wind) * (1.0 - (1.0 - 0.02) ** frame_scale)
        respawn_probability = 1.0 - (1.0 - 0.03) ** frame_scale

        for petal in self.petals[: self.npetals]:
            if not petal.active:
                if self.r.random() < respawn_probability:
                    self.spawn(petal)
                continue
            if petal.rest >= 0.0:
                petal.rest -= dt
                if petal.rest < 0.0:
                    petal.active = False
                continue
            petal.phase += petal.omega * dt
            petal.x += (self.wind + petal.sway * math.sin(petal.phase)) * dt
            petal.y += petal.vy * dt
            if petal.x < -2.0:
                petal.x = self.w + 1.0
            elif petal.x > self.w + 2.0:
                petal.x = -1.0
            if petal.y >= self.h - 1.0:
                petal.y = self.h - 1.0
                petal.rest = self.u(2.0, 7.0)
                petal.pair = FADED
                petal.glyph = "." if self.o.ascii else "·"

    def cycle(self, step: int) -> None:
        self.o.palette = NAMES[(NAMES.index(self.o.palette) + step) % len(NAMES)]


class Renderer:
    def __init__(self, screen, model: Model):
        self.s = screen
        self.m = model
        self.colors = False
        self.background = curses.COLOR_BLACK
        self.setup()
        self.palette()

    def setup(self) -> None:
        curses.noecho()
        curses.cbreak()
        self.s.keypad(True)
        self.s.nodelay(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        if not curses.has_colors():
            return
        try:
            curses.start_color()
        except curses.error:
            return
        if getattr(curses, "COLOR_PAIRS", 0) <= FADED:
            return
        try:
            curses.use_default_colors()
            self.background = -1
        except curses.error:
            self.background = curses.COLOR_BLACK
        self.colors = True

    def palette(self) -> None:
        if not self.colors:
            return
        try:
            name = self.m.o.palette
            ramp = PALETTES[name]
            if getattr(curses, "COLORS", 0) >= 256:
                for index, color in enumerate(ramp):
                    curses.init_pair(P0 + index, color, self.background)
                for pair, color in ((TD, 52), (TM, 94), (TL, 137), (GRASS, 108), (FADED, ramp[5])):
                    curses.init_pair(pair, color, self.background)
            else:
                base = (
                    curses.COLOR_YELLOW
                    if name == "gold"
                    else curses.COLOR_CYAN
                    if name == "sky"
                    else curses.COLOR_GREEN
                    if name in {"mint", "matcha"}
                    else curses.COLOR_WHITE
                    if name == "ink"
                    else curses.COLOR_MAGENTA
                )
                curses.init_pair(P0, curses.COLOR_WHITE, self.background)
                curses.init_pair(P0 + 1, curses.COLOR_WHITE, self.background)
                for pair in range(P0 + 2, P0 + 6):
                    curses.init_pair(pair, base, self.background)
                curses.init_pair(P0 + 6, curses.COLOR_RED, self.background)
                curses.init_pair(P0 + 7, curses.COLOR_RED, self.background)
                for pair in (TD, TM, TL):
                    curses.init_pair(pair, curses.COLOR_YELLOW, self.background)
                curses.init_pair(GRASS, curses.COLOR_GREEN, self.background)
                curses.init_pair(FADED, base, self.background)
        except curses.error:
            self.colors = False

    def add(self, y: int, x: int, glyph: str, attributes: int = 0) -> None:
        try:
            self.s.addstr(y, x, glyph, attributes)
        except (curses.error, UnicodeError):
            try:
                self.s.addstr(y, x, glyph if glyph.isascii() else "?", attributes)
            except (curses.error, UnicodeError):
                pass

    def draw(self) -> None:
        self.s.erase()
        model = self.m
        if not model.drawable:
            messages = (
                "sakura: terminal too small",
                f"need {MIN_W}x{MIN_H}; current {model.w}x{model.h}",
                "resize or press q",
            )
            for y, text in enumerate(messages):
                if y < model.h:
                    self.add(y, 0, text[: max(0, model.w - 1)])
        else:
            for y in range(model.h):
                for x in range(model.w):
                    cell = model.grid[y * model.w + x]
                    if cell:
                        attributes = (curses.color_pair(cell.pair) if self.colors else 0) | (
                            curses.A_BOLD if cell.bold else 0
                        )
                        self.add(y, x, cell.glyph, attributes)
            for petal in model.petals[: model.npetals]:
                x, y = int(petal.x), int(petal.y)
                if not petal.active or not 0 <= y < model.h:
                    continue
                attributes = (curses.color_pair(petal.pair) if self.colors else 0) | curses.A_BOLD
                for offset, glyph in enumerate(petal.glyph):
                    draw_x = x + offset
                    if 0 <= draw_x < model.w:
                        self.add(y, draw_x, glyph, attributes)
        try:
            self.s.refresh()
        except curses.error:
            pass


class App:
    def __init__(self, screen, opt: Opt):
        self.s = screen
        height, width = screen.getmaxyx()
        self.m = Model(width, height, opt)
        self.r = Renderer(screen, self.m)
        self.running = True

    def stop(self, *_args) -> None:
        self.running = False

    def resize(self, force: bool = False) -> None:
        update_lines = getattr(curses, "update_lines_cols", None)
        if update_lines is not None:
            update_lines()
        height, width = self.s.getmaxyx()
        if force or (width, height) != (self.m.w, self.m.h):
            self.m.resize(width, height, True)

    def key(self, key: int) -> None:
        if key in (ord("q"), ord("Q"), 27):
            self.running = False
        elif key in (ord("r"), ord("R")) and self.m.drawable:
            self.m.tree()
            self.m.reset_petals()
        elif key in (ord("c"), ord("C")):
            self.m.cycle(1 if key == ord("c") else -1)
            self.r.palette()
            if self.m.drawable:
                self.m.tree()
                self.m.reset_petals()
        elif key == curses.KEY_RESIZE:
            self.resize(True)

    def run(self) -> None:
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        for sig in previous:
            signal.signal(sig, self.stop)
        frame = 1.0 / self.m.o.fps
        last = next_frame = time.monotonic()
        try:
            while self.running:
                self.resize()
                while True:
                    key = self.s.getch()
                    if key == -1:
                        break
                    self.key(key)
                now = time.monotonic()
                dt = min(max(now - last, 0.0), 0.25)
                last = now
                if self.m.drawable:
                    self.m.update(dt)
                self.r.draw()
                next_frame += frame
                delay = next_frame - time.monotonic()
                if delay > 0.0:
                    time.sleep(delay)
                else:
                    next_frame = time.monotonic()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def ranged(kind, low, high):
    def parse(value):
        try:
            number = kind(value)
        except (TypeError, ValueError) as error:
            raise argparse.ArgumentTypeError("invalid number") from error
        if isinstance(number, float) and not math.isfinite(number):
            raise argparse.ArgumentTypeError("must be a finite number")
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse

def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="sakura",
        description="Procedural sakura tree with falling petals.",
        epilog="keys: q/Esc quit, r regrow, c/C palettes\npalettes: " + ", ".join(NAMES),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    result.add_argument("-f", "--fps", type=ranged(int, 5, 60), default=20)
    result.add_argument("-p", "--density", type=ranged(int, 1, 10), default=5)
    result.add_argument("-w", "--wind", type=ranged(float, 0.0, 10.0), default=1.0)
    result.add_argument("-c", "--palette", choices=NAMES, default="sakura")
    result.add_argument("-a", "--ascii", action="store_true")
    result.add_argument("--seed", type=int)
    result.add_argument("--self-test", action="store_true")
    result.add_argument("-v", "--version", action="version", version=f"sakura {VERSION}")
    return result


def preflight(stdin=None, stdout=None, term: str | None = None) -> str | None:
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    term = os.environ.get("TERM", "") if term is None else term
    if not stdin.isatty() or not stdout.isatty():
        return "interactive stdin and stdout TTYs are required"
    if term.strip().lower() in {"", "dumb", "unknown"}:
        return "a usable TERM value is required"
    return None


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def self_test() -> int:
    valid = parser().parse_args(["-f", "60", "-p", "10", "-w", "10", "-c", "mint", "-a", "--seed", "42"])
    _check((valid.fps, valid.density, valid.wind, valid.palette, valid.ascii, valid.seed) == (60, 10, 10.0, "mint", True, 42), "CLI parsing failed")
    _check(all(len(sprite) == 2 for sprite in PETALS), "Unicode falling-petal sprites must span two cells")
    _check(all(len(sprite) == 2 and sprite.isascii() for sprite in APETALS), "ASCII falling-petal sprites must span two ASCII cells")

    for parse, value in (
        (ranged(int, 5, 60), "4"),
        (ranged(int, 5, 60), "bad"),
        (ranged(float, 0.0, 10.0), "nan"),
        (ranged(float, 0.0, 10.0), "inf"),
    ):
        try:
            parse(value)
        except argparse.ArgumentTypeError:
            pass
        else:
            raise RuntimeError(f"invalid CLI value accepted: {value}")

    for kwargs in (
        {"fps": 4},
        {"density": 0},
        {"wind": float("nan")},
        {"palette": "missing"},
        {"ascii": 1},
        {"seed": True},
    ):
        try:
            Opt(**kwargs)
        except ValueError:
            pass
        else:
            raise RuntimeError(f"invalid Opt accepted: {kwargs}")

    first = Model(80, 24, Opt(seed=123456))
    second = Model(80, 24, Opt(seed=123456))
    _check(first.grid == second.grid, "deterministic grid generation failed")
    _check(first.sources == second.sources and first.blobs == second.blobs, "deterministic model generation failed")

    responsive_small = Model(80, 24, Opt(seed=2026))
    responsive_large = Model(160, 48, Opt(seed=2026))
    responsive_tall = Model(120, 80, Opt(seed=2026))
    _check(responsive_large.crown_rx > 36.0, "large-terminal crown still has the old fixed cap")
    _check(responsive_large.crown_rx > responsive_small.crown_rx * 1.9, "crown does not scale with terminal growth")
    _check(responsive_large.crown_rx / responsive_large.crown_ry >= 4.0, "wide crown is too tall")
    _check(responsive_tall.crown_rx / responsive_tall.crown_ry >= 3.8, "tall-terminal crown became a vertical ball")

    for model in (responsive_small, responsive_large, responsive_tall):
        upper_limit = min(model.h, int(model.crown_cy + model.crown_ry * 1.65) + 1)
        side_limit = model.crown_rx * 0.76
        side_trunk = [
            (x, y)
            for y in range(upper_limit)
            for x in range(model.w)
            if (cell := model.grid[y * model.w + x]) is not None
            and cell.pair in (TD, TM, TL)
            and abs(x - model.crown_cx) > side_limit
        ]
        _check(not side_trunk, "branch escaped the crown and formed a brown side bar")

    for ascii_mode in (False, True):
        for name in NAMES:
            for width, height in ((20, 8), (40, 12), (80, 24), (160, 48)):
                model = Model(
                    width,
                    height,
                    Opt(density=10, wind=10, ascii=ascii_mode, palette=name, seed=123456),
                )
                _check(len(model.grid) == width * height, "grid size mismatch")
                _check(0 < len(model.blobs) <= MAX_BLOBS, "blob count out of bounds")
                _check(len(model.sources) <= MAX_SOURCES, "source count out of bounds")
                _check(16 <= model.npetals <= MAX_PETALS, "petal count out of bounds")
                _check(all(0 <= x < width and 0 <= y < height for x, y in model.sources), "source coordinate out of bounds")
                _check(any(model.grid), "generated grid is empty")
                _check(all(cell is None or P0 <= cell.pair <= FADED for cell in model.grid), "cell color pair out of bounds")
                if ascii_mode:
                    _check(all(cell is None or cell.glyph.isascii() for cell in model.grid), "non-ASCII tree glyph in ASCII mode")

                for _ in range(300):
                    model.update(0.05)
                for petal in model.petals[: model.npetals]:
                    _check(type(petal.active) is bool, "invalid petal activity state")
                    _check(math.isfinite(petal.x) and math.isfinite(petal.y), "non-finite petal coordinate")
                    _check(-2.0 <= petal.x <= width + 2.0, "petal x coordinate out of simulation bounds")
                    _check(-3.0 <= petal.y <= height - 1.0, "petal y coordinate out of simulation bounds")
                    if ascii_mode:
                        _check(petal.glyph.isascii(), "non-ASCII petal glyph in ASCII mode")
                    if petal.active and petal.rest < 0.0:
                        _check(len(petal.glyph) == 2, "falling petal does not use the two-cell sprite")

    cycle_model = Model(40, 12, Opt(seed=7))
    original_palette = cycle_model.o.palette
    cycle_model.cycle(1)
    _check(cycle_model.o.palette == NAMES[1], "forward palette cycle failed")
    cycle_model.cycle(-1)
    _check(cycle_model.o.palette == original_palette, "reverse palette cycle failed")

    cycle_model.resize(1, 1, True)
    _check(cycle_model.npetals == 0 and not any(p.active for p in cycle_model.petals), "tiny-terminal state is active")
    cycle_model.cycle(1)
    cycle_model.reset_petals()
    _check(cycle_model.npetals == 0, "tiny-terminal reset reactivated petals")
    cycle_model.resize(40, 12, True)
    _check(cycle_model.drawable and cycle_model.npetals >= 16 and any(cycle_model.grid), "resize recovery failed")

    landing_model = Model(40, 12, Opt(seed=11))
    landing = landing_model.petals[0]
    landing.active = True
    landing.rest = -1.0
    landing.x = 10.0
    landing.y = landing_model.h - 1.1
    landing.vy = 10.0
    landing.sway = 0.0
    landing.omega = 0.0
    landing_model.update(0.05)
    _check(landing.y == landing_model.h - 1 and landing.rest >= 0.0, "petal landing failed")
    _check(landing.pair == FADED, "landed petal did not fade")

    before = (landing_model.wind, landing_model.wind_target, landing.x, landing.y)
    for invalid_dt in (0.0, -1.0, float("nan"), float("inf")):
        landing_model.update(invalid_dt)
    after = (landing_model.wind, landing_model.wind_target, landing.x, landing.y)
    _check(before == after, "invalid elapsed time changed model state")

    class TTY:
        def __init__(self, value: bool):
            self.value = value

        def isatty(self) -> bool:
            return self.value

    _check(preflight(TTY(True), TTY(True), "xterm-256color") is None, "valid terminal preflight failed")
    _check(preflight(TTY(False), TTY(True), "xterm") is not None, "non-TTY stdin accepted")
    _check(preflight(TTY(True), TTY(True), "dumb") is not None, "dumb TERM accepted")

    print("sakura self-test: PASS")
    return 0


def main(argv=None) -> int:
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass
    args = parser().parse_args(argv)
    if args.self_test:
        try:
            return self_test()
        except RuntimeError as error:
            print(f"sakura self-test: FAIL: {error}", file=sys.stderr)
            return 1

    terminal_problem = preflight()
    if terminal_problem is not None:
        print(f"sakura: {terminal_problem}", file=sys.stderr)
        return 2

    options = Opt(args.fps, args.density, args.wind, args.ascii, args.palette, args.seed)
    try:
        curses.wrapper(lambda screen: App(screen, options).run())
    except KeyboardInterrupt:
        return 130
    except curses.error as error:
        print(f"sakura: terminal error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
