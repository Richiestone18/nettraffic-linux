#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ventana de gráfica flotante: GTK3 + cairo. Área/columnas/líneas, rect o velocímetro.

Notas del entorno (MATE + Compiz, verificadas):
  - Compiz pisa posición y opacidad al mapear: se re-aplican tras show().
  - La opacidad se fija por XChangeProperty(_NET_WM_WINDOW_OPACITY); el
    set_opacity de GTK no llega al WM aquí.
  - begin_resize_drag no funciona en ventanas sin marco: la redimensión es manual.
  - Con marco activado el WM añade decoración; si la ventana está pegada al borde
    inferior, la barra de título queda fuera de pantalla → se empuja hacia arriba.
"""
import math

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

from .core import (fmt_amount, parse_amount, hex_to_rgba, nice_ceil, theme_colors,
                   other_window_fullscreen, q_enabled)

UP_ARROW = "↑"
DOWN_ARROW = "↓"
FRAME_MIN_Y = 40          # margen mínimo para que la barra del WM se vea

_ZONE_CURSORS = None


def _zone_cursor_types():
    """Mapa ventana-borde → cursor de redimensión (lazy: requiere Gdk inicializado)."""
    global _ZONE_CURSORS
    if _ZONE_CURSORS is None:
        _ZONE_CURSORS = {
            Gdk.WindowEdge.NORTH_WEST: Gdk.CursorType.TOP_LEFT_CORNER,
            Gdk.WindowEdge.NORTH_EAST: Gdk.CursorType.TOP_RIGHT_CORNER,
            Gdk.WindowEdge.SOUTH_WEST: Gdk.CursorType.BOTTOM_LEFT_CORNER,
            Gdk.WindowEdge.SOUTH_EAST: Gdk.CursorType.BOTTOM_RIGHT_CORNER,
            Gdk.WindowEdge.NORTH: Gdk.CursorType.TOP_SIDE,
            Gdk.WindowEdge.SOUTH: Gdk.CursorType.BOTTOM_SIDE,
            Gdk.WindowEdge.WEST: Gdk.CursorType.LEFT_SIDE,
            Gdk.WindowEdge.EAST: Gdk.CursorType.RIGHT_SIDE,
        }
    return _ZONE_CURSORS


class ChartWindow(Gtk.Window):
    MIN_W, MIN_H = 90, 70
    EDGE_PX = 14

    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.cfg = app.cfg
        self.shape = app.x11shape
        self._pointer_inside = False
        self._hidden_by_fullscreen = False
        self._hidden_by_pointer = False
        self._mapped = False
        self._last_transparent = None
        self._resize_zone = None
        self._resize_drag = None   # (zone, x0, y0, w0, h0, px0, py0)
        self._move_drag = None     # (x0, y0, px0, py0, w0, h0)
        self._font_px = 9.0        # último tamaño de fuente calculado

        self.set_title("NetTraffic")
        self.set_app_paintable(True)
        self.set_border_width(0)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        self.da = Gtk.DrawingArea()
        self.add(self.da)
        self.da.connect("draw", self.on_draw)
        # los eventos los recibe el DrawingArea (cubre toda la ventana);
        # conectar a la toplevel no sirve: su GDK window queda debajo
        self.da.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                           | Gdk.EventMask.BUTTON_RELEASE_MASK
                           | Gdk.EventMask.POINTER_MOTION_MASK
                           | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.da.connect("button-press-event", self.on_button)
        self.da.connect("button-release-event", self.on_release)
        self.da.connect("motion-notify-event", self.on_motion)
        self.da.connect("leave-notify-event", self.on_leave)
        self.connect("configure-event", self.on_configure)
        self.connect("delete-event", self.on_delete)
        self.connect("map-event", self._on_map)

        self.apply_config(first=True)
        if self.cfg["general"].get("window_restore", 1) == 1:
            self.show()
        else:
            self._mapped = False

        GLib.timeout_add(self._redraw_interval_ms(), self._tick_redraw)
        GLib.timeout_add(250, self._tick_pointer)
        GLib.timeout_add(3000, self._tick_fullscreen)

    # ── mostrar/ocultar (con re-mapeo y re-aplicación por Compiz) ──
    def show(self):
        self.show_all()
        self._mapped = True

    def hide(self):
        Gtk.Window.hide(self)
        self._mapped = False
        self._hidden_by_pointer = False

    def _on_map(self, *_):
        """Al mapear, Compiz reescribe posición/opacidad: se re-aplican aquí."""
        GLib.idle_add(self._reapply_state)
        return False

    def _reapply_state(self):
        if not self._mapped:
            return False
        g = self.cfg["general"]
        p = self.cfg["plot"]
        loc = g["location"]
        self.set_keep_above(bool(g["on_top"]))
        if p.get("window_frame"):
            self.set_decorated(True)
            self._ensure_on_screen()
        self.move(int(loc.get("x", 60)), int(loc.get("y", 40)))
        self.resize(max(self.MIN_W, int(loc.get("width", 320))),
                    max(self.MIN_H, int(loc.get("height", 120))))
        self._set_wm_opacity(self._target_opacity())
        win = self.get_window()
        if win is not None:
            self.shape.apply_to_widget(self, bool(g["click_through"]))
        self.da.queue_draw()
        return False

    def _ensure_on_screen(self):
        """Con marco activado deja sitio para la barra del WM: nunca por encima
        del borde superior (donde vive la barra) ni saliéndose por abajo."""
        # jamás interferir con un arrastre en curso (devolvería la ventana)
        if self._move_drag is not None or self._resize_drag is not None:
            return
        loc = self.cfg["general"]["location"]
        ox, oy, sw, sh = 0, 0, 1920, 1200
        try:
            win = self.get_window()
            disp = self.get_display()
            # OJO: get_monitor_at_window del Display devuelve un Gdk.Monitor, pero
            # get_monitor_workarea quiere el ÍNDICE → se saca del Screen.
            idx = self.get_screen().get_monitor_at_window(win) if win else 0
            wa = self.get_screen().get_monitor_workarea(idx)
            ox, oy, sw, sh = wa.x, wa.y, wa.width, wa.height
        except Exception:
            pass
        w, h = int(loc.get("width", 320)), int(loc.get("height", 120))
        ext = self._frame_extents() or (1, 1, 0, 1)
        top, bottom = ext[2], ext[3]
        x, y = int(loc.get("x", 60)), int(loc.get("y", 40))
        # la barra de título ocupa 'top' píxeles ARRIBA del cliente
        if y < oy + top + 4:
            y = oy + top + 4
        if y + h + bottom > oy + sh:
            y = max(oy + top + 4, oy + sh - h - bottom)
            if y + h + bottom > oy + sh:
                loc["height"] = max(self.MIN_H, oy + sh - y - bottom)
                h = loc["height"]
        loc["x"], loc["y"] = x, y
        self.move(x, y)
        self.resize(max(self.MIN_W, w), max(self.MIN_H, h))

    def _frame_extents(self):
        """_NET_FRAME_EXTENTS (izq, der, arriba, abajo) o None si no las hay."""
        win = self.get_window()
        if win is None:
            return None
        try:
            import ctypes
            lib = ctypes.CDLL("libX11.so.6")
            lib.XOpenDisplay.restype = ctypes.c_void_p
            lib.XInternAtom.restype = ctypes.c_ulong
            lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            lib.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                               ctypes.c_long, ctypes.c_long, ctypes.c_int,
                                               ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                               ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
                                               ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p)]
            disp = lib.XOpenDisplay(None)
            if not disp:
                return None
            atom = lib.XInternAtom(disp, b"_NET_FRAME_EXTENTS", False)
            actual_type = ctypes.c_ulong()
            actual_fmt = ctypes.c_int()
            nitems = ctypes.c_ulong()
            after = ctypes.c_ulong()
            data = ctypes.c_void_p()
            lib.XGetWindowProperty(disp, ctypes.c_ulong(win.get_xid()), atom,
                                   0, 4, False, 0x0, ctypes.byref(actual_type),
                                   ctypes.byref(actual_fmt), ctypes.byref(nitems),
                                   ctypes.byref(after), ctypes.byref(data))
            if not data.value or nitems.value < 4 or actual_fmt.value != 32:
                return None
            vals = ctypes.cast(data, ctypes.POINTER(ctypes.c_ulong))
            ext = tuple(int(vals[i]) for i in range(4))
            # al quitar la decoración el WM deja la propiedad en ceros
            return None if not any(ext) else ext
        except Exception:
            return None

    # ── configuración ──
    def _redraw_interval_ms(self):
        return max(100, min(int(self.cfg["general"]["frequency_ms"]), 1000))

    def _target_opacity(self):
        tr = max(0, min(90, int(self.cfg["plot"]["transparency"])))
        return 1.0 - tr / 100.0

    def _set_wm_opacity(self, opacity):
        """Fija _NET_WM_WINDOW_OPACITY vía Xlib: GDK no sirve para props del WM
        y Compiz ignora set_opacity cerca del map."""
        try:
            win = self.get_window()
            if win is None:
                return
            import ctypes
            lib = ctypes.CDLL("libX11.so.6")
            lib.XOpenDisplay.restype = ctypes.c_void_p
            lib.XInternAtom.restype = ctypes.c_ulong
            lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            lib.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                                            ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_void_p, ctypes.c_int]
            disp = lib.XOpenDisplay(None)
            if not disp:
                return
            atom = lib.XInternAtom(disp, b"_NET_WM_WINDOW_OPACITY", False)
            CARDINAL, PROP_MODE_REPLACE = 6, 0
            val = ctypes.c_uint32(int(max(0.0, min(1.0, opacity)) * 0xFFFFFFFF))
            lib.XChangeProperty(disp, ctypes.c_ulong(win.get_xid()), atom,
                                CARDINAL, 32, PROP_MODE_REPLACE, ctypes.byref(val), 1)
            lib.XFlush(disp)
        except Exception:
            pass

    def apply_config(self, first=False):
        p = self.cfg["plot"]
        g = self.cfg["general"]
        loc = g["location"]
        framed = bool(p.get("window_frame"))
        self.set_decorated(framed)
        self.set_keep_above(bool(g["on_top"]))
        # Como el NetTraffic de Windows: la gráfica NUNCA va a la barra de tareas,
        # tenga marco o no (en Windows solo se ve la ventana, no el botón).
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        w = max(self.MIN_W, int(loc.get("width", 320)))
        h = max(self.MIN_H, int(loc.get("height", 120)))
        self.resize(w, h)
        self.move(int(loc.get("x", 60)), int(loc.get("y", 40)))
        if framed:
            # al recién activar el marco el WM aún no publica _NET_FRAME_EXTENTS:
            # se corrige ahora y se reintenta hasta que el marco exista
            self._ensure_on_screen()
            self._schedule_frame_fixup()
        self._set_wm_opacity(self._target_opacity())
        win = self.get_window()
        if win is not None:
            self.shape.apply_to_widget(self, bool(g["click_through"]))
        self.da.queue_draw()

    def _schedule_frame_fixup(self, tries=6):
        """Reintenta el ajuste on-screen mientras el marco termina de aparecer.
        Al activar el marco sobre una ventana ya mapeada, el WM publica
        _NET_FRAME_EXTENTS un momento después: sin este reintento la corrección
        se calcula con un marco de 0 px y no hace nada.

        DOS límites importantes (bug real arrastrando con marco):
        - en cuanto el marco existe, se ajusta una vez y se TERMINA (antes
          seguía disparando y devolvía la ventana a su lugar, peleándose con
          el usuario);
        - nunca actúa con un arrastre en curso (con la ventana pegada al borde
          inferior, cada intento la regresaba y era imposible moverla)."""
        def step(left):
            if not self._mapped or not self.cfg["plot"].get("window_frame"):
                return False
            if self._move_drag is not None or self._resize_drag is not None:
                return left > 1     # arrastre en curso: reintentar más tarde
            ext = self._frame_extents()
            self._ensure_on_screen()
            if ext is not None:
                return False        # el marco ya existe: ajuste final, terminar
            return left > 1
        GLib.timeout_add(160, step, tries)
        GLib.timeout_add(420, step, tries)

    # ── eventos ──
    def on_configure(self, widget, event):
        x, y = self.get_position()
        w, h = self.get_size()
        loc = self.cfg["general"]["location"]
        loc.update({"x": x, "y": y, "width": w, "height": h})
        return False

    def on_delete(self, widget, event):
        if self.cfg["general"].get("close_to_tray", True):
            self.hide()
            return True
        self.app.quit()
        return False

    def on_button(self, widget, event):
        if event.button == 3 and not self.cfg["general"]["click_through"]:
            self.app.menu.popup_at_pointer(event)
            return True
        if event.button == 1:
            # Con o SIN marco: bordes/esquinas redimensionan y el centro mueve.
            # (Antes, con marco el clic izquierdo no hacía nada: la ventana solo
            # se podía mover desde la barra del WM.)
            zone = self._zone_at(event.x, event.y,
                                 widget.get_allocated_width(), widget.get_allocated_height())
            if zone is not None:
                w, h = self.get_size()
                px, py = self.get_position()
                self._resize_drag = (zone, int(event.x_root), int(event.y_root),
                                     w, h, px, py)
                return True
            w, h = self.get_size()
            px, py = self.get_position()
            self._move_drag = (int(event.x_root), int(event.y_root), px, py, w, h)
            return True
        return False

    def on_release(self, widget, event):
        if event.button != 1:
            return False
        if self._resize_drag is not None or self._move_drag is not None:
            self._resize_drag = None
            self._move_drag = None
            x, y = self.get_position()
            w, h = self.get_size()
            self.cfg["general"]["location"].update(
                {"x": x, "y": y, "width": w, "height": h})
        return False

    def _apply_resize(self, zone, dx, dy, w0, h0, px0, py0):
        """Redimensión manual: ajusta tamaño (y posición en bordes N/O)."""
        x, y = px0, py0
        w, h = w0, h0
        if zone in (Gdk.WindowEdge.EAST, Gdk.WindowEdge.SOUTH_EAST, Gdk.WindowEdge.NORTH_EAST):
            w = max(self.MIN_W, w0 + dx)
        if zone in (Gdk.WindowEdge.WEST, Gdk.WindowEdge.SOUTH_WEST, Gdk.WindowEdge.NORTH_WEST):
            w = max(self.MIN_W, w0 - dx)
            x = px0 + (w0 - w)
        if zone in (Gdk.WindowEdge.SOUTH, Gdk.WindowEdge.SOUTH_EAST, Gdk.WindowEdge.SOUTH_WEST):
            h = max(self.MIN_H, h0 + dy)
        if zone in (Gdk.WindowEdge.NORTH, Gdk.WindowEdge.NORTH_EAST, Gdk.WindowEdge.NORTH_WEST):
            h = max(self.MIN_H, h0 - dy)
            y = py0 + (h0 - h)
        self.resize(w, h)
        self.move(x, y)

    # ── redimensión por bordes/esquinas (ventana sin marco) ──
    def on_motion(self, widget, event):
        # 1) mover arrastrando el centro (con y sin marco)
        if self._move_drag is not None:
            x0, y0, px0, py0, w0, h0 = self._move_drag
            self.move(px0 + (int(event.x_root) - x0), py0 + (int(event.y_root) - y0))
            return False
        # 2) redimensionar arrastrando un borde o esquina
        if self._resize_drag is not None:
            zone, x0, y0, w0, h0, px0, py0 = self._resize_drag
            self._apply_resize(zone, int(event.x_root) - x0, int(event.y_root) - y0,
                               w0, h0, px0, py0)
            return False
        # 3) cursor según la zona (con marco el WM ya pone el de su barra)
        zone = self._zone_at(event.x, event.y,
                             widget.get_allocated_width(), widget.get_allocated_height())
        if zone != self._resize_zone:
            self._resize_zone = zone
            win = self.get_window()
            if win is not None:
                if zone is None:
                    win.set_cursor(None)
                else:
                    try:
                        cur = Gdk.Cursor.new_for_display(Gdk.Display.get_default(),
                                                         _zone_cursor_types()[zone])
                        win.set_cursor(cur)
                    except Exception:
                        pass
        return False

    def on_leave(self, widget, event):
        if self._resize_zone is not None:
            self._resize_zone = None
            win = self.get_window()
            if win is not None:
                win.set_cursor(None)
        return False

    def _zone_at(self, x, y, w, h):
        if self.cfg["plot"]["window_frame"]:
            return None
        e = self.EDGE_PX
        west, east = x < e, x > w - e
        north, south = y < e, y > h - e
        if north and west:
            return Gdk.WindowEdge.NORTH_WEST
        if north and east:
            return Gdk.WindowEdge.NORTH_EAST
        if south and west:
            return Gdk.WindowEdge.SOUTH_WEST
        if south and east:
            return Gdk.WindowEdge.SOUTH_EAST
        if north:
            return Gdk.WindowEdge.NORTH
        if south:
            return Gdk.WindowEdge.SOUTH
        if west:
            return Gdk.WindowEdge.WEST
        if east:
            return Gdk.WindowEdge.EAST
        return None

    # ── ticks ──
    def _tick_redraw(self):
        self.da.queue_draw()
        # XFixes trae los eventos de re-mapeo/redibujado: GTK los usa para reponer
        # su propia forma de entrada, así que el clic a través se re-aplica aquí
        self._reapply_click_through()
        return True

    def _reapply_click_through(self):
        if not self._mapped:
            return
        g = self.cfg["general"]
        want = bool(g["click_through"]) or self._hidden_by_pointer
        if g.get("hide_under_pointer") and not want:
            return
        if want == getattr(self, "_ct_applied", None):
            return
        self._ct_applied = want
        self.shape.apply_to_widget(self, want)

    def _tick_pointer(self):
        """Ocultar bajo el puntero: opacidad 0 y clic a través mientras el mouse
        encima, para no bloquear los clics sobre lo que hay debajo."""
        try:
            g = self.cfg["general"]
            if not g.get("hide_under_pointer") or not self._mapped:
                if self._hidden_by_pointer:
                    self._set_pointer_hidden(False)
                return True
            disp = Gdk.Display.get_default()
            ptr = disp.get_default_seat().get_pointer()
            if ptr is None:
                return True
            _, px, py = ptr.get_position()
            wx, wy = self.get_position()
            w, h = self.get_size()
            inside = wx <= px < wx + w and wy <= py < wy + h
            if inside != self._pointer_inside:
                self._pointer_inside = inside
                self._set_pointer_hidden(inside)
        except Exception:
            pass
        return True

    def _set_pointer_hidden(self, hidden):
        """Aplica/quita el estado 'oculto bajo el puntero'."""
        if hidden == self._hidden_by_pointer:
            return
        self._hidden_by_pointer = hidden
        self._set_wm_opacity(0.0 if hidden else self._target_opacity())
        win = self.get_window()
        if win is not None and not self.cfg["general"]["click_through"]:
            # mientras está invisible no debe tragarse los clics: se vacía la
            # forma de entrada de la ventana Y de las hijas de GDK
            self.shape.apply_to_widget(self, hidden)
        self.da.queue_draw()

    def _tick_fullscreen(self):
        g = self.cfg["general"]
        if not g.get("hide_when_fullscreen"):
            if self._hidden_by_fullscreen:
                self._hidden_by_fullscreen = False
                self.show()
            return True
        fs = other_window_fullscreen()
        if fs and not self._hidden_by_fullscreen:
            self._hidden_by_fullscreen = True
            self.hide()
        elif not fs and self._hidden_by_fullscreen:
            self._hidden_by_fullscreen = False
            self.show()
        return True

    # ── dibujo ──
    def _theme(self):
        return theme_colors(self.cfg)

    def _fmt_rate(self, n):
        return fmt_amount(n, self.cfg["general"].get("unit_speed", "iB"), per_second=True)

    def on_draw(self, da, cr):
        p = self.cfg["plot"]
        theme = self._theme()
        w = da.get_allocated_width()
        h = da.get_allocated_height()
        if w < 20 or h < 20:
            return False

        # fondo
        cr.set_source_rgba(*hex_to_rgba(theme["back"]))
        if p.get("window_frame"):
            cr.rectangle(0, 0, w, h)
        else:
            self._round_rect(cr, 0, 0, w, h, 6)
        cr.fill()

        title_h = self._title_height(w, theme)
        if title_h:
            self._draw_title_bar(cr, w, title_h, theme)

        dl, ul = self.app.sampler.get_rates()
        points = self.app.sampler.get_points(max(2, int(p.get("points_count", 60))))

        top = title_h + (2 if title_h else 2)
        if p.get("chart_shape") == "pie":
            self._draw_pie(cr, 2, top - 2, w - 4, h - top - 2, dl, ul, points, theme)
        else:
            self._draw_rectangle_chart(cr, top, w, h - top, dl, ul, points, theme)
        return False

    def _round_rect(self, cr, x, y, w, h, r):
        r = max(0.0, min(r, w / 2.0, h / 2.0))
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    # ── fuente auto-ajustable ──
    def _auto_font(self, w, h):
        """Tamaño de fuente de las etiquetas según el tamaño de la ventana.
        Con 'Auto-escala de fuente' apagado se usa el tamaño histórico (9)."""
        if not self.cfg["plot"].get("font_autosize", True):
            return 9.0
        base = min(w / 320.0, h / 140.0)
        return max(5.5, min(13.0, 9.0 * (base ** 0.45)))

    def _title_height(self, w, theme):
        p = self.cfg["plot"]
        if not p.get("title_bar", True) or p.get("window_frame"):
            return 0
        fs = self._auto_font(w, 140.0)
        return max(13, int(fs + 6))

    def _title_items(self, theme):
        p = self.cfg["plot"]
        dl, ul = self.app.sampler.get_rates()
        elems = []
        if p.get("show_dl", True):
            elems.append((DOWN_ARROW, self._fmt_rate(dl), theme["download"]))
        if p.get("show_ul", True):
            elems.append((UP_ARROW, self._fmt_rate(ul), theme["upload"]))
        if p.get("show_total", False):
            elems.append(("Σ", self._fmt_rate(dl + ul), theme["total"]))
        if q_enabled(self.cfg) and p.get("show_quota", True):
            q = self.cfg["quota"]
            pct = self.app.sampler.get_quota_pct() or 0.0
            col = (theme["download"] if pct < 0.8 else
                   (theme["activity"] if pct < 1.0 else theme["upload"]))
            elems.append(("", "%.0f%%" % (pct * 100.0), col))
        return elems

    def _draw_title_bar(self, cr, w, hgt, theme):
        cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.07))
        self._round_rect(cr, 0, 0, w, hgt, 6)
        cr.fill()
        cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.5))
        cr.set_line_width(0.7)
        cr.move_to(2, hgt)
        cr.line_to(w - 2, hgt)
        cr.stroke()

        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        fs = self._auto_font(w, hgt * 8.0)
        cr.set_font_size(fs)
        elems = self._title_items(theme)
        gap = max(8.0, fs * 1.5)
        widths = [cr.text_extents((a + " " + t).strip()).width for a, t, _ in elems]
        total = sum(widths) + gap * max(0, len(elems) - 1)
        x = max(4.0, (w - total) / 2.0)
        baseline = hgt / 2.0 + fs * 0.38
        for i, (arrow, txt, color) in enumerate(elems):
            label = (arrow + " " + txt).strip()
            cr.set_source_rgba(*hex_to_rgba(color))
            cr.move_to(x, baseline)
            cr.show_text(label)
            x += widths[i] + gap

    def _scale_max(self, dl, ul, points):
        p = self.cfg["plot"]
        if p.get("scale_y") == "manual":
            m = parse_amount(p["scale_max"]["value"], p["scale_max"]["prefix"],
                             p["scale_max"]["kind"])
            return max(1.0, m)
        show_total = p.get("show_total", False)
        mx = (dl + ul) if show_total else max(dl, ul)
        n = int(p.get("points_count", 60))
        for _, d, u in points[-n:]:
            mx = max(mx, (d + u) if show_total else max(d, u))
        return nice_ceil(mx * 1.05 + 1e-9)

    def _draw_rectangle_chart(self, cr, top, w, h, dl, ul, points, theme):
        """Gráfica rectangular. El margen izquierdo se calcula según el ancho real
        de las etiquetas del eje Y (antes fijo en 40 px y se encimaban o se salían)."""
        p = self.cfg["plot"]
        kind = self.cfg["general"].get("unit_speed", "iB")
        smax = self._scale_max(dl, ul, points)
        fs = self._auto_font(w, h)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(fs)

        hide_y = p.get("hide_y_labels", False)
        labels = [fmt_amount(smax * i / 4.0, kind, per_second=True) for i in range(5)]
        pad_l = 4.0 if hide_y else max(26.0, max(cr.text_extents(l).width for l in labels) + 8.0)
        pad_r, pad_b, pad_t = 4.0, max(10.0, fs + 4.0), 3.0
        x0, y0 = pad_l, top + pad_t
        pw = max(10.0, w - pad_l - pad_r)
        ph = max(10.0, h - pad_t - pad_b)

        # rejilla + etiquetas Y
        for i in range(5):
            frac = i / 4.0
            y = y0 + ph - ph * frac
            cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.4))
            cr.set_line_width(0.5)
            cr.move_to(x0, y)
            cr.line_to(x0 + pw, y)
            cr.stroke()
            if not hide_y:
                lbl = labels[i]
                cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.75))
                cr.move_to(max(1, x0 - cr.text_extents(lbl).width - 4), y + fs * 0.35)
                cr.show_text(lbl)
        # línea base
        cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.8))
        cr.set_line_width(0.8)
        cr.move_to(x0, y0 + ph)
        cr.line_to(x0 + pw, y0 + ph)
        cr.stroke()

        nmax = max(2, int(p.get("points_count", 60)))
        data = points[-nmax:]
        if len(data) < 2:
            return
        slot = pw / float(nmax)
        bw = max(1.0, min(slot * 0.8, max(1.5, float(p.get("point_width", 3)))))

        def yval(v):
            return y0 + ph - min(1.0, v / smax) * ph

        def stroke_series(vals, color, filled):
            ctype = p.get("chart_type", "area")
            if ctype == "column":
                cr.set_source_rgba(*hex_to_rgba(color, 0.9))
                for i, v in enumerate(vals):
                    cx = x0 + slot * i + (slot - bw) / 2.0
                    cr.rectangle(cx, yval(v), bw, y0 + ph - yval(v))
                cr.fill()
            elif ctype == "area":
                cr.set_source_rgba(*hex_to_rgba(color, 0.55))
                cr.move_to(x0 + bw / 2.0, y0 + ph)
                for i, v in enumerate(vals):
                    cr.line_to(x0 + slot * i + bw / 2.0, yval(v))
                cr.line_to(x0 + slot * (len(vals) - 1) + bw / 2.0, y0 + ph)
                cr.close_path()
                cr.fill()
                cr.set_source_rgba(*hex_to_rgba(color, 1.0))
                cr.set_line_width(1.0)
                for i, v in enumerate(vals):
                    pt = (x0 + slot * i + bw / 2.0, yval(v))
                    cr.line_to(*pt) if i else cr.move_to(*pt)
                cr.stroke()
            else:  # line
                cr.set_source_rgba(*hex_to_rgba(color, 1.0))
                cr.set_line_width(1.2)
                for i, v in enumerate(vals):
                    pt = (x0 + slot * i + bw / 2.0, yval(v))
                    cr.line_to(*pt) if i else cr.move_to(*pt)
                cr.stroke()

        if p.get("show_total", False):
            stroke_series([d + u for (_, d, u) in data], theme["total"], True)
        if p.get("show_dl", True):
            stroke_series([d for (_, d, _) in data], theme["download"], True)
        if p.get("show_ul", True):
            stroke_series([u for (_, _, u) in data], theme["upload"], True)

    def _draw_pie(self, cr, x0, y0, pw, ph, dl, ul, points, theme):
        """Velocímetro: arco de 270°; cada serie traza su recorrido del arco."""
        p = self.cfg["plot"]
        kind = self.cfg["general"].get("unit_speed", "iB")
        smax = self._scale_max(dl, ul, points)
        fs = max(5.0, min(9.0, self._auto_font(pw, ph) * 0.8))
        cx = x0 + pw / 2.0
        # el arco necesita espacio abajo para las etiquetas: centro un poco arriba
        r = max(8.0, min((pw - 24) / 2.0, (ph - fs * 2.6) / 1.62))
        cy = y0 + ph - fs * 1.9 - r * 0.62
        a0 = 0.75 * math.pi   # 135°
        a1 = 2.25 * math.pi   # 405° (=45°)

        # pista
        cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.35))
        cr.set_line_width(max(2.0, r * 0.09))
        cr.new_sub_path()
        cr.arc(cx, cy, r, a0, a1)
        cr.stroke()

        # marcas y etiquetas de escala
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(fs)
        for i in range(5):
            ang = a0 + (a1 - a0) * (i / 4.0)
            cr.set_source_rgba(*hex_to_rgba(theme["axis"], 0.7))
            cr.set_line_width(0.6)
            cr.move_to(cx + math.cos(ang) * (r - 3), cy + math.sin(ang) * (r - 3))
            cr.line_to(cx + math.cos(ang) * (r + 2), cy + math.sin(ang) * (r + 2))
            cr.stroke()
            lbl = fmt_amount(smax * i / 4.0, kind, per_second=True)
            mx = cx + math.cos(ang) * (r + 6)
            my = cy + math.sin(ang) * (r + 8)
            cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.7))
            cr.move_to(mx - cr.text_extents(lbl).width / 2.0, my)
            cr.show_text(lbl)

        data = points[-max(2, int(p.get("points_count", 60))):]
        if len(data) >= 2:
            def draw_gauge(vals, color, width):
                cr.set_source_rgba(*hex_to_rgba(color, 0.95))
                cr.set_line_width(width)
                first = True
                for v in vals:
                    frac = min(1.0, v / smax)
                    ang = a0 + (a1 - a0) * frac
                    pt = (cx + math.cos(ang) * r, cy + math.sin(ang) * r)
                    cr.line_to(*pt) if not first else cr.move_to(*pt)
                    first = False
                cr.stroke()

            lw = max(1.4, r * 0.08)
            if p.get("show_total", False):
                draw_gauge([d + u for (_, d, u) in data], theme["total"], lw * 0.7)
            if p.get("show_dl", True):
                draw_gauge([d for (_, d, _) in data], theme["download"], lw)
            if p.get("show_ul", True):
                draw_gauge([u for (_, _, u) in data], theme["upload"], lw)

        # lectura actual bajo el arco
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        txt = self._fmt_rate(dl + ul)
        size = max(7.0, min(13.0, r * 0.30))
        cr.set_font_size(size)
        cr.set_source_rgba(*hex_to_rgba(theme["font"], 0.92))
        cr.move_to(cx - cr.text_extents(txt).width / 2.0, cy + r * 0.42 + size)
        cr.show_text(txt)