#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Icono de bandeja (AyatanaAppIndicator3) dibujado dinámicamente a 32 px
(como los demás iconos del panel).

Diseño: monitor con pantalla oscura, barras verdes de descarga y línea roja de
subida (concepto del icono clásico de NetTraffic). Estados TX+RX / solo TX /
solo RX / inactivo; con cuota habilitada, barra superior = % del límite usado
y barra inferior = transcurso del periodo de facturación
(indicador 'quota_usage_period_lapse_indicator' del original)."""
import math
import os
import tempfile

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import AyatanaAppIndicator3 as AppIndicator
import cairo

from .core import theme_colors, hex_to_rgba, quota_period_progress, q_enabled

ICON_SIZE = 32          # como los demás iconos del panel del usuario
ACTIVITY_THRESHOLD = 1024.0   # 1 kiB/s


class TrayIcon:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg
        self._sig = None
        self.indicator = AppIndicator.Indicator.new(
            "nettraffic", "nettraffic",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.icon_dir = tempfile.mkdtemp(prefix="nettraffic-tray-")
        self.icon_path = os.path.join(self.icon_dir, "icon.png")
        self.update(force=True)
        self.indicator.set_menu(self.app.menu)
        self.indicator.set_title("NetTraffic")

    def update(self, force=False):
        dl, ul = self.app.sampler.get_rates()
        quota_on = q_enabled(self.cfg)
        if quota_on:
            quota_pct = self.app.sampler.get_quota_pct()
            period_pct = quota_period_progress(self.cfg)
        else:
            quota_pct, period_pct = None, None
        rx_active = dl > ACTIVITY_THRESHOLD
        tx_active = ul > ACTIVITY_THRESHOLD
        # con cuota activa se redibuja seguido: la barra crece byte a byte
        sig = (rx_active, tx_active,
               None if quota_pct is None else round(quota_pct, 4),
               None if period_pct is None else round(period_pct, 3),
               self.cfg["plot"].get("theme"))
        if sig == self._sig and not force:
            return
        self._sig = sig
        self._render(rx_active, tx_active, quota_pct, period_pct)
        try:
            self.indicator.set_icon_full(self.icon_path, "NetTraffic")
        except Exception:
            try:
                self.indicator.set_icon(self.icon_path)
            except Exception:
                pass

    # ── dibujo ──
    def _render(self, rx_active, tx_active, quota_pct, period_pct):
        s = ICON_SIZE
        theme = theme_colors(self.cfg)
        dl_col = theme["download"] if rx_active else self._dim(theme["download"])
        ul_col = theme["upload"] if tx_active else self._dim(theme["upload"])
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, s, s)
        cr = cairo.Context(surface)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.rectangle(0, 0, s, s)
        cr.fill()
        cr.set_operator(cairo.OPERATOR_OVER)

        # barras de cuota: franjas arriba y abajo (si hay cuota)
        if quota_pct is not None:
            col = (theme["download"] if quota_pct < 0.8 else
                   (theme["activity"] if quota_pct < 1.0 else theme["upload"]))
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.rectangle(1, 0, s - 2, 3.2)
            cr.fill()
            cr.set_source_rgba(*hex_to_rgba(col))
            cr.rectangle(1, 0, (s - 2) * quota_pct, 3.2)
            cr.fill()
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.rectangle(1, s - 3.2, s - 2, 3.2)
            cr.fill()
            cr.set_source_rgba(*hex_to_rgba(theme["total"]))
            cr.rectangle(1, s - 3.2, (s - 2) * (period_pct or 0.0), 3.2)
            cr.fill()

        # ── monitor: marco degradado, borde claro, pantalla oscura ──
        # margen ~2px alrededor (los iconos Papirus dejan aire interior)
        y_off = 6.0 if quota_pct is not None else 2.6
        x_off = 2.4
        body_h = s - y_off - 5.2
        body_w = s - x_off * 2
        mg = cairo.LinearGradient(0, y_off, 0, y_off + body_h)
        mg.add_color_stop_rgba(0, 0.30, 0.38, 0.48, 1.0)
        mg.add_color_stop_rgba(1, 0.11, 0.16, 0.24, 1.0)
        cr.set_source(mg)
        self._rrect(cr, x_off, y_off, body_w, body_h, 3.0)
        cr.fill()
        cr.set_source_rgba(0.62, 0.68, 0.76, 0.95)
        cr.set_line_width(1.1)
        self._rrect(cr, x_off, y_off, body_w, body_h, 3.0)
        cr.stroke()
        scr = cairo.LinearGradient(0, y_off + 2, 0, y_off + body_h - 2)
        scr.add_color_stop_rgba(0, 0.05, 0.08, 0.14, 1.0)
        scr.add_color_stop_rgba(1, 0.09, 0.13, 0.22, 1.0)
        cr.set_source(scr)
        self._rrect(cr, x_off + 2.1, y_off + 2.2, body_w - 4.2, body_h - 5.2, 1.8)
        cr.fill()

        # ── dentro de la pantalla: barras verdes (descarga) ──
        gx0, gy0 = x_off + 4.2, y_off + 4.0
        gw = body_w - 8.4
        gh = body_h - 8.4
        profile = (0.34, 0.62, 0.44, 0.86, 0.58)
        slot = gw / 5.0
        bw = slot * 0.64
        if rx_active:
            r_, g_, b_, _a = hex_to_rgba(dl_col)
            g1 = cairo.LinearGradient(0, gy0 + gh, 0, gy0)
            g1.add_color_stop_rgba(0, r_ * 0.72, g_ * 0.72, b_ * 0.72, 0.95)
            g1.add_color_stop_rgba(1, r_, g_, b_, 1.0)
            cr.set_source(g1)
        else:
            cr.set_source_rgba(*hex_to_rgba(dl_col, 0.35))
        for i, hgt in enumerate(profile):
            bh = gh * hgt
            x = gx0 + slot * i + (slot - bw) / 2.0
            self._rrect(cr, x, gy0 + gh - bh, bw, bh, min(1.2, bw / 3.0))
            cr.fill()

        # ── línea roja de subida con puntos ──
        pts = [(gx0 + slot * i + slot / 2.0,
                gy0 + gh * (0.28 if i % 2 == 0 else 0.72)) for i in range(5)]
        cr.set_source_rgba(*hex_to_rgba(ul_col, 0.95 if tx_active else 0.35))
        cr.set_line_width(1.7 if tx_active else 1.2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(*pts[0])
        for pt in pts[1:]:
            cr.line_to(*pt)
        cr.stroke()
        for (px, py) in pts:
            cr.arc(px, py, 0.95, 0, 2 * math.pi)
            cr.fill()

        # peana
        cr.set_source_rgba(0.55, 0.61, 0.69, 1.0)
        cr.rectangle(s / 2 - 3.0, y_off + body_h - 0.2, 6.0, 2.4)
        cr.fill()

        surface.write_to_png(self.icon_path)

    @staticmethod
    def _rrect(cr, x, y, w, h, r):
        r = max(0.0, min(r, w / 2.0, h / 2.0))
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    @staticmethod
    def _dim(hexc, factor=0.42):
        r, g, b, _a = hex_to_rgba(hexc)
        return "#%02x%02x%02x" % (round(r * 255 * factor + 34),
                                  round(g * 255 * factor + 34),
                                  round(b * 255 * factor + 34))

    def set_menu(self, menu):
        self.indicator.set_menu(menu)

    def hide(self):
        self.indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)