#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplicación principal: sampler + ventana + bandeja + menú + ajustes + estadísticas."""
import os
import signal
import sys
import math
from datetime import datetime

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, GLib, Gdk

from .core import (VERSION, RateSampler, Tr, X11Shape,
                   load_settings, save_settings)
from .chart import ChartWindow
from .tray import TrayIcon
from .settings import SettingsWindow
from .stats import StatsWindow

AUTOSTART_FILE = os.path.expanduser("~/.config/autostart/nettraffic.desktop")


class App:
    def __init__(self):
        self.cfg = load_settings()
        self.tr = Tr(self.cfg)
        self.x11shape = X11Shape()
        from datetime import datetime
        self.started_at = datetime.now()
        self.win = None
        self.tray = None
        self.settings_win = None
        self.stats_win = None
        self.menu = self._build_menu()

        self.sampler = RateSampler(self.cfg)
        self.sampler.start()

        # La ventana decide si se muestra o arranca oculta (window_restore)
        self.win = ChartWindow(self)
        self.tray = TrayIcon(self)
        self.tray.set_menu(self.menu)
        self.apply_autostart()

        # 'Cursor' del original: distancia recorrida por el puntero (km/mm/s)
        self._cursor_pos = None
        self._last_cursor_poll = 0.0
        if not self.cfg["stats"].get("cursor_started"):
            self.cfg["stats"]["cursor_started"] = self.started_at.isoformat(timespec="seconds")
        GLib.timeout_add(500, self._tick_cursor)

        GLib.timeout_add(300000, self._autosave)      # respaldo cada 5 min
        GLib.timeout_add(1000, self._tick_tray)

    # ── Cursor: distancia del puntero como el 'Cursor' del original ──
    def _tick_cursor(self):
        """Cada 500 ms mide cuánto se movió el puntero y lo acumula en metros.
        El original lo reporta como distancia (km), velocidad (mm/s) y
        proyección — mismas cifras que aquí."""
        try:
            import time as _t
            now = _t.monotonic()
            if now - self._last_cursor_poll < 0.4:
                return True
            self._last_cursor_poll = now
            disp = Gdk.Display.get_default()
            seat = disp.get_default_seat()
            ptr = seat.get_pointer()
            if ptr is None:
                return True
            _, px, py = ptr.get_position()
            st = self.cfg["stats"]
            if self._cursor_pos is not None:
                dx = px - self._cursor_pos[0]
                dy = py - self._cursor_pos[1]
                dist = math.sqrt(dx * dx + dy * dy)
                # píxel ≈ 0.2646 mm en una pantalla típica de 96 dpi
                if dist > 0:
                    st["cursor_m"] = float(st.get("cursor_m", 0.0)) + dist * 0.0002646
            self._cursor_pos = (px, py)
        except Exception:
            pass
        return True

    def cursor_stats(self):
        """(distancia_km, velocidad_mm_s) del puntero, como el original."""
        st = self.cfg["stats"]
        dist_km = float(st.get("cursor_m", 0.0)) / 1000.0
        dur = max(1.0, (datetime.now() - self.started_at).total_seconds())
        speed_mm_s = (float(st.get("cursor_m", 0.0)) * 1000.0) / dur
        return dist_km, speed_mm_s

    # ── menú (como el menú contextual del original) ──
    def _build_menu(self):
        m = Gtk.Menu()
        self._ready = False       # los handlers se activan al terminar de armarlo
        made = []

        def item(label, cb, check=False, active=None):
            it = Gtk.CheckMenuItem(label=label) if check else Gtk.MenuItem(label=label)
            # OJO: en un CheckMenuItem, set_active() emite "activate"; por eso el
            # estado se fija ANTES de conectar el handler (si no, corre a medias
            # y revienta por atributos que aún no existen).
            if check and active is not None:
                it.set_active(bool(active))
            it.connect("activate", cb)
            m.append(it)
            made.append(it)
            return it

        g = self.cfg["general"]
        self.mi_show = item(self.tr("show"), self.on_toggle_show)
        self.mi_on_top = item(self.tr("on_top"), self.on_toggle_on_top, True, g["on_top"])
        self.mi_click_through = item(self.tr("click_through"), self.on_toggle_ct, True,
                                     g["click_through"])
        self.mi_hide_ptr = item(self.tr("hide_under_pointer"), self.on_toggle_hptr, True,
                                g["hide_under_pointer"])
        self.mi_window = item(self.tr("window_mode"), self.on_toggle_window, True,
                              self.cfg["plot"]["window_frame"])
        m.append(Gtk.SeparatorMenuItem())
        self.mi_settings = item(self.tr("settings"), self.on_settings)
        self.mi_stats = item(self.tr("statistic"), self.on_stats)
        self.mi_about = item(self.tr("about"), self.on_about)
        m.append(Gtk.SeparatorMenuItem())
        self.mi_exit = item(self.tr("exit"), self.on_exit)
        m.show_all()
        self._ready = True
        return m

    def refresh_menu_labels(self):
        if not getattr(self, "mi_click_through", None):
            return
        visible = bool(self.win and self.win.get_visible())
        self.mi_show.set_label(self.tr("hide") if visible else self.tr("show"))
        self.mi_on_top.set_label(self.tr("on_top"))
        self.mi_click_through.set_label(self.tr("click_through"))
        self.mi_hide_ptr.set_label(self.tr("hide_under_pointer"))
        self.mi_window.set_label(self.tr("window_mode"))
        self.mi_settings.set_label(self.tr("settings"))
        self.mi_stats.set_label(self.tr("statistic"))
        self.mi_about.set_label(self.tr("about"))
        self.mi_exit.set_label(self.tr("exit"))
        self.mi_window.set_active(bool(self.cfg["plot"]["window_frame"]))

    # ── acciones del menú ──
    def on_toggle_show(self, *_):
        if self.win.get_visible():
            self.win.hide()
        else:
            self.win.show()
        self.refresh_menu_labels()

    def on_toggle_on_top(self, item):
        if not self._ready:
            return
        self.cfg["general"]["on_top"] = item.get_active()
        self.apply_all()

    def on_toggle_ct(self, item):
        if not self._ready:
            return
        self.cfg["general"]["click_through"] = item.get_active()
        self.apply_all()

    def on_toggle_hptr(self, item):
        if not self._ready:
            return
        self.cfg["general"]["hide_under_pointer"] = item.get_active()
        if not item.get_active():
            self.win._set_pointer_hidden(False)

    def on_toggle_window(self, item):
        if not self._ready:
            return
        self.cfg["plot"]["window_frame"] = item.get_active()
        self.apply_all()

    def on_settings(self, *_):
        if self.settings_win:
            self.settings_win.present()
            return
        self.settings_win = SettingsWindow(self)
        self.settings_win.connect("destroy", self._settings_closed)
        self.settings_win.show_all()

    def _settings_closed(self, *_):
        self.settings_win = None

    def reopen_settings(self):
        GLib.idle_add(self.on_settings)

    def on_stats(self, *_):
        if self.stats_win:
            self.stats_win.present()
            return
        self.stats_win = StatsWindow(self)
        self.stats_win.connect("destroy", lambda *_: setattr(self, "stats_win", None))
        self.stats_win.show_all()

    def on_about(self, *_):
        dlg = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK)
        dlg.set_title(self.tr("about"))
        dlg.props.text = "NetTraffic Linux %s" % VERSION
        dlg.props.secondary_text = self.tr("about_text")
        dlg.run()
        dlg.destroy()

    def on_exit(self, *_):
        self.quit()

    # ── ciclo de vida ──
    def apply_all(self):
        """Propaga la config a ventana/bandeja y guarda."""
        self.apply_live()
        if hasattr(self, "refresh_menu_labels"):
            self.refresh_menu_labels()
        save_settings(self.cfg)

    def apply_live(self):
        """Aplica los cambios de Ajustes en vivo, SIN escribir en disco
        (se guarda al pulsar Aplicar/Aceptar)."""
        if self.win:
            self.win.apply_config()
        if self.tray:
            self.tray.update(force=True)

    def _autosave(self):
        save_settings(self.cfg)
        return True

    def _tick_tray(self):
        if self.tray:
            self.tray.update()
        return True

    def apply_autostart(self):
        if self.cfg["general"].get("start_with_system"):
            os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
            with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=NetTraffic\n"
                        "Exec=nettraffic\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
        else:
            try:
                os.remove(AUTOSTART_FILE)
            except FileNotFoundError:
                pass

    def quit(self):
        try:
            self.sampler.stop()
        except Exception:
            pass
        save_settings(self.cfg)
        Gtk.main_quit()

    def run(self):
        Gtk.main()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if os.environ.get("NETTRAFFIC_DEBUG"):
        import traceback
        sys.excepthook = lambda t, v, x: (traceback.print_exception(t, v, x), Gtk.main_quit())
    app = App()
    app.run()


if __name__ == "__main__":
    main()