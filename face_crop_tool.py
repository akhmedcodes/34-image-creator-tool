# -*- coding: utf-8 -*-
"""
Face Crop Tool  --  Passport Photo Sheet
Varaq: 1200x800 px @ 200 DPI
Grid va oraliq UI orqali sozlanadi
"""

import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

SHEET_W = 1200
SHEET_H = 800
OUT_DPI = 200

# Tez tanlov presetlari
PRESETS = [("4x2", 4, 2), ("3x2", 3, 2), ("5x3", 5, 3), ("6x4", 6, 4), ("2x2", 2, 2)]

DEFAULT_COLS   = 4
DEFAULT_ROWS   = 2
DEFAULT_GAP_MM = 1.5   # mm  (avval 3 mm edi, kichiklashtirildi)


def calc_layout(cols, rows, gap_mm):
    """Foto o'lchamlari va joyini hisoblash. Har doim SHEET ichiga sig'diradi."""
    gap = max(1, round(gap_mm * OUT_DPI / 25.4))

    # Avval kenglik bo'yicha urinib ko'r
    pw = (SHEET_W - (cols + 1) * gap) // cols
    ph = pw * 4 // 3

    # Balandlik yetmasa -- balandlik bo'yicha hisobla
    if rows * ph + (rows + 1) * gap > SHEET_H:
        ph = (SHEET_H - (rows + 1) * gap) // rows
        pw = ph * 3 // 4

    # Qolgan joyni markazga bo'l
    mh = (SHEET_W - cols * pw - (cols - 1) * gap) // 2
    mv = (SHEET_H - rows * ph - (rows - 1) * gap) // 2

    return pw, ph, gap, mh, mv


class FaceCropTool:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Face Crop Tool  --  Passport Sheet")
        self.root.configure(bg="#1e1e2e")
        self.root.geometry("1150x870")
        self.root.minsize(720, 580)

        self.original  = None
        self.tk_img    = None
        self.scale     = 1.0
        self.ox = self.oy = 0

        self.sel_start = None
        self.rect_id   = None
        self.guide_ids = []
        self.selection = None

        self.cols_var  = tk.IntVar(value=DEFAULT_COLS)
        self.rows_var  = tk.IntVar(value=DEFAULT_ROWS)
        self.gap_var   = tk.StringVar(value=str(DEFAULT_GAP_MM))

        self._build_ui()
        self._highlight_preset(DEFAULT_COLS, DEFAULT_ROWS)

    # ── UI qurilishi ──────────────────────────────────────────────────────────

    def _build_ui(self):
        # Yuqori panel
        topbar = tk.Frame(self.root, bg="#11111b", padx=14, pady=10)
        topbar.pack(fill=tk.X)

        tk.Label(topbar, text="Face Crop Tool",
                 font=("Segoe UI", 14, "bold"),
                 bg="#11111b", fg="#cdd6f4").pack(side=tk.LEFT)

        self.btn_save  = self._btn(topbar, "Saqlash  (JPG)", "#89b4fa",
                                   self.crop_and_save, side=tk.RIGHT, state=tk.DISABLED)
        self.btn_reset = self._btn(topbar, "Reset", "#f38ba8",
                                   self.reset_sel,    side=tk.RIGHT, state=tk.DISABLED)
        self._btn(topbar, "Rasm ochish", "#a6e3a1", self.open_image, side=tk.RIGHT)

        # Grid panel
        gridbar = tk.Frame(self.root, bg="#181825", padx=14, pady=9)
        gridbar.pack(fill=tk.X)

        # -- Presetlar
        tk.Label(gridbar, text="Tez tanlov:", bg="#181825", fg="#6c7086",
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 6))

        self.preset_btns = {}
        for label, c, r in PRESETS:
            b = tk.Button(gridbar, text=label,
                          command=lambda c=c, r=r: self._set_preset(c, r),
                          bg="#313244", fg="#cdd6f4", activebackground="#45475a",
                          font=("Segoe UI", 9, "bold"),
                          relief=tk.FLAT, bd=0, padx=12, pady=4, cursor="hand2")
            b.pack(side=tk.LEFT, padx=2)
            self.preset_btns[(c, r)] = b

        # -- Ajratgich
        tk.Frame(gridbar, bg="#45475a", width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=2)

        # -- Qo'l bilan kiritish: ustun x qator
        lbl = lambda t: tk.Label(gridbar, text=t, bg="#181825", fg="#6c7086",
                                  font=("Segoe UI", 9))
        spn = lambda var, lo, hi: tk.Spinbox(
            gridbar, from_=lo, to=hi, textvariable=var, width=3,
            font=("Segoe UI", 10, "bold"), bg="#313244", fg="#cdd6f4",
            buttonbackground="#45475a", relief=tk.FLAT,
            command=self._on_change)

        lbl("Ustun:").pack(side=tk.LEFT, padx=(0, 4))
        spn(self.cols_var, 1, 8).pack(side=tk.LEFT)
        lbl("  x  ").pack(side=tk.LEFT)
        lbl("Qator:").pack(side=tk.LEFT, padx=(4, 4))
        spn(self.rows_var, 1, 6).pack(side=tk.LEFT)

        # -- Ajratgich
        tk.Frame(gridbar, bg="#45475a", width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=12, pady=2)

        # -- Oraliq (mm)
        lbl("Oraliq mm:").pack(side=tk.LEFT, padx=(0, 4))
        gap_spn = tk.Spinbox(
            gridbar, from_=0.5, to=15.0, increment=0.5,
            textvariable=self.gap_var, width=5, format="%.1f",
            font=("Segoe UI", 10, "bold"), bg="#313244", fg="#cdd6f4",
            buttonbackground="#45475a", relief=tk.FLAT, command=self._on_change)
        gap_spn.pack(side=tk.LEFT)

        # -- O'ng: hisoblangan ma'lumot
        self.layout_lbl = tk.Label(gridbar, text="", bg="#181825",
                                    fg="#89b4fa", font=("Segoe UI", 9))
        self.layout_lbl.pack(side=tk.RIGHT, padx=8)

        # Trace: matn o'zgarganda ham yangilansin
        self.cols_var.trace_add("write", lambda *_: self._on_change())
        self.rows_var.trace_add("write", lambda *_: self._on_change())
        self.gap_var.trace_add("write",  lambda *_: self._on_change())

        # Holat satri
        self.status_var = tk.StringVar(value="Rasm oching.")
        tk.Label(self.root, textvariable=self.status_var, anchor=tk.W,
                 bg="#313244", fg="#a6adc8", font=("Segoe UI", 9),
                 padx=12, pady=6).pack(fill=tk.X)

        # Asosiy kanvas
        self.cv = tk.Canvas(self.root, bg="#181825",
                             highlightthickness=0, cursor="crosshair")
        self.cv.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.cv.bind("<ButtonPress-1>",  self._press)
        self.cv.bind("<B1-Motion>",       self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.root.bind("<Configure>",     lambda _: self._redraw())

        # Pastki info
        self.info_var = tk.StringVar()
        tk.Label(self.root, textvariable=self.info_var,
                 bg="#11111b", fg="#585b70",
                 font=("Segoe UI", 8), pady=4).pack(fill=tk.X)

        self._refresh_labels()

    @staticmethod
    def _btn(parent, text, color, cmd, side=tk.LEFT, state=tk.NORMAL):
        b = tk.Button(parent, text=text, command=cmd,
                      bg=color, fg="#1e1e2e", activebackground=color,
                      font=("Segoe UI", 10, "bold"),
                      relief=tk.FLAT, bd=0, padx=14, pady=7,
                      cursor="hand2", state=state)
        b.pack(side=side, padx=4)
        return b

    # ── Grid boshqaruvi ───────────────────────────────────────────────────────

    def _get_gap_mm(self):
        try:
            return max(0.5, float(self.gap_var.get()))
        except ValueError:
            return DEFAULT_GAP_MM

    def _layout(self):
        cols = max(1, self.cols_var.get())
        rows = max(1, self.rows_var.get())
        return cols, rows, *calc_layout(cols, rows, self._get_gap_mm())

    def _set_preset(self, cols, rows):
        self.cols_var.set(cols)
        self.rows_var.set(rows)
        self._highlight_preset(cols, rows)

    def _highlight_preset(self, ac, ar):
        for (c, r), btn in self.preset_btns.items():
            active = (c == ac and r == ar)
            btn.config(bg="#89b4fa" if active else "#313244",
                       fg="#1e1e2e" if active else "#cdd6f4")

    def _on_change(self):
        self._refresh_labels()
        try:
            c, r = self.cols_var.get(), self.rows_var.get()
            self._highlight_preset(c if (c, r) in self.preset_btns else -1,
                                   r if (c, r) in self.preset_btns else -1)
        except Exception:
            pass

    def _refresh_labels(self):
        try:
            cols, rows, pw, ph, gap, mh, mv = self._layout()
        except Exception:
            return
        gap_mm = round(gap / OUT_DPI * 25.4, 1)
        self.layout_lbl.config(
            text=f"{cols}x{rows} = {cols*rows} foto  |  har biri {pw}x{ph} px")
        self.info_var.set(
            f"Varaq: {SHEET_W}x{SHEET_H} px  |  "
            f"Har bir foto: {pw}x{ph} px (3:4)  |  "
            f"Oraliq: {gap} px ({gap_mm} mm)  |  "
            f"DPI: {OUT_DPI}")

    # ── Rasm yuklash ──────────────────────────────────────────────────────────

    def open_image(self):
        path = filedialog.askopenfilename(
            title="Rasm tanlang",
            filetypes=[("Rasmlar", "*.jpg *.jpeg *.png *.bmp *.tiff *.webp")]
        )
        if not path:
            return
        self.original  = Image.open(path).convert("RGB")
        self.selection = None
        self.sel_start = None
        self.btn_save.config(state=tk.DISABLED)
        self.btn_reset.config(state=tk.DISABLED)
        self._redraw()
        self.status("Yuz ustiga tortburchak chizing (3:4 nisbat avtomatik saqlanadi).")

    def _redraw(self):
        if not self.original:
            return
        cw = self.cv.winfo_width()  or 960
        ch = self.cv.winfo_height() or 640
        iw, ih = self.original.size
        self.scale = min(cw / iw, ch / ih, 1.0)
        dw, dh = round(iw * self.scale), round(ih * self.scale)
        self.ox = (cw - dw) // 2
        self.oy = (ch - dh) // 2
        disp = self.original.resize((dw, dh), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(disp)
        self.cv.delete("all")
        self.cv.create_image(self.ox, self.oy, anchor=tk.NW, image=self.tk_img)
        if self.selection:
            self._paint_rect(*self._i2s(*self.selection))

    # ── Koordinatlar ─────────────────────────────────────────────────────────

    def _s2i(self, sx, sy):
        return (sx - self.ox) / self.scale, (sy - self.oy) / self.scale

    def _i2s(self, ix1, iy1, ix2, iy2):
        s = self.scale
        return ix1*s+self.ox, iy1*s+self.oy, ix2*s+self.ox, iy2*s+self.oy

    # ── Sichqoncha ───────────────────────────────────────────────────────────

    def _press(self, e):
        if not self.original:
            return
        self.sel_start = (e.x, e.y)
        self._clear_overlay()

    def _drag(self, e):
        if not self.sel_start:
            return
        x1, y1 = self.sel_start
        dx = e.x - x1
        dy = math.copysign(abs(dx) * 4 / 3, e.y - y1) if dx != 0 else 0
        self._clear_overlay()
        self._paint_rect(x1, y1, x1 + dx, y1 + dy)

    def _release(self, e):
        if not self.sel_start:
            return
        x1, y1 = self.sel_start
        dx = e.x - x1
        dy = math.copysign(abs(dx) * 4 / 3, e.y - y1) if dx != 0 else 0
        sx1 = min(x1, x1+dx);  sy1 = min(y1, y1+dy)
        sx2 = max(x1, x1+dx);  sy2 = max(y1, y1+dy)
        ix1, iy1 = self._s2i(sx1, sy1)
        ix2, iy2 = self._s2i(sx2, sy2)
        iw, ih = self.original.size
        ix1 = max(0.0, min(ix1, float(iw)))
        iy1 = max(0.0, min(iy1, float(ih)))
        ix2 = max(0.0, min(ix2, float(iw)))
        iy2 = max(0.0, min(iy2, float(ih)))
        if (ix2 - ix1) < 20 or (iy2 - iy1) < 20:
            self.status("Tanlov juda kichik -- qaytadan chizing.")
            return
        self.selection = (ix1, iy1, ix2, iy2)
        try:
            cols, rows, pw, ph, gap, mh, mv = self._layout()
            extra = f"  -->  {cols}x{rows} = {cols*rows} foto, har biri {pw}x{ph}px"
        except Exception:
            extra = ""
        self.btn_save.config(state=tk.NORMAL)
        self.btn_reset.config(state=tk.NORMAL)
        self.status(f"Tanlandi: {round(ix2-ix1)}x{round(iy2-iy1)}px{extra}  |  'Saqlash' tugmasini bosing.")

    # ── To'rtburchak ─────────────────────────────────────────────────────────

    def _paint_rect(self, x1, y1, x2, y2):
        self._clear_overlay()
        self.rect_id = self.cv.create_rectangle(
            x1, y1, x2, y2, outline="#a6e3a1", width=2, dash=(6, 3))
        for t in (1/3, 2/3):
            gx, gy = x1+(x2-x1)*t, y1+(y2-y1)*t
            self.guide_ids += [
                self.cv.create_line(gx, y1, gx, y2, fill="#a6e3a170", dash=(2, 4)),
                self.cv.create_line(x1, gy, x2, gy, fill="#a6e3a170", dash=(2, 4)),
            ]
        c, arm = "#a6e3a1", 14
        for (cx, cy), (sx, sy) in zip(
                [(x1,y1),(x2,y1),(x1,y2),(x2,y2)],
                [(1,1),(-1,1),(1,-1),(-1,-1)]):
            self.guide_ids += [
                self.cv.create_line(cx, cy, cx+sx*arm, cy, fill=c, width=2),
                self.cv.create_line(cx, cy, cx, cy+sy*arm, fill=c, width=2),
            ]

    def _clear_overlay(self):
        if self.rect_id:
            self.cv.delete(self.rect_id)
            self.rect_id = None
        for g in self.guide_ids:
            self.cv.delete(g)
        self.guide_ids.clear()

    def reset_sel(self):
        self.selection = None
        self.sel_start = None
        self._clear_overlay()
        self.btn_save.config(state=tk.DISABLED)
        self.btn_reset.config(state=tk.DISABLED)
        self.status("Tanlov tozalandi -- qaytadan chizing.")

    # ── Eksport ───────────────────────────────────────────────────────────────

    def crop_and_save(self):
        if not self.selection or not self.original:
            return

        try:
            cols, rows, pw, ph, gap, mh, mv = self._layout()
        except Exception as e:
            messagebox.showerror("Xato", f"Layout hisoblashda xato: {e}")
            return

        if pw < 10 or ph < 10:
            messagebox.showerror(
                "Xato",
                "Foto o'lchami juda kichik.\n"
                "Ustun/qator sonini kamaytiring yoki oraliqni kichraytiring.")
            return

        ix1, iy1, ix2, iy2 = self.selection
        face_crop  = self.original.crop(
            (round(ix1), round(iy1), round(ix2), round(iy2)))
        face_photo = face_crop.resize((pw, ph), Image.LANCZOS)

        sheet = Image.new("RGB", (SHEET_W, SHEET_H), (255, 255, 255))
        for row in range(rows):
            for col in range(cols):
                x = mh + col * (pw + gap)
                y = mv + row * (ph + gap)
                sheet.paste(face_photo, (x, y))

        save_path = filedialog.asksaveasfilename(
            title="JPG sifatida saqlang",
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("Barcha fayllar", "*.*")]
        )
        if not save_path:
            return

        sheet.save(save_path, "JPEG", quality=95,
                   dpi=(OUT_DPI, OUT_DPI), optimize=True)

        gap_mm = round(gap / OUT_DPI * 25.4, 1)
        messagebox.showinfo(
            "Saqlandi!",
            f"Fayl:         {os.path.basename(save_path)}\n\n"
            f"Varaq:        {SHEET_W} x {SHEET_H} px\n"
            f"DPI:          {OUT_DPI}\n"
            f"Foto soni:    {cols}x{rows} = {cols*rows} ta\n"
            f"Har bir foto: {pw} x {ph} px  (3:4)\n"
            f"Oraliq:       {gap} px  ({gap_mm} mm)"
        )

    def status(self, msg: str):
        self.status_var.set(msg)


def main():
    root = tk.Tk()
    FaceCropTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
