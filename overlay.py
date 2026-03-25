"""
Overlay da Stormy — janela flutuante sem bordas.
Abre com Ctrl+↑, fecha com Escape ou Enter.
"""

import threading
import tkinter as tk
from tkinter import font as tkfont

# Cores
BG          = "#0d0d0d"
BG_INPUT    = "#1a1a1a"
BG_RESPONSE = "#111111"
FG_INPUT    = "#e0e0e0"
FG_RESPONSE = "#a0d4ff"
FG_LABEL    = "#444444"
ACCENT      = "#00bfff"
BORDER      = "#222222"

WIDTH  = 600
MARGIN = 20  # distância do canto superior direito


class StormyOverlay:
    def __init__(self, on_send_callback):
        """
        on_send_callback(message: str) -> str
        Chamado quando usuário envia mensagem. Deve retornar a resposta.
        """
        self._callback = on_send_callback
        self._root = None
        self._visible = False
        self._last_response = ""
        self._lock = threading.Lock()

    def _build(self):
        root = tk.Tk()
        root.withdraw()

        root.overrideredirect(True)       # sem bordas
        root.attributes("-topmost", True)  # sempre no topo
        root.attributes("-alpha", 0.95)
        root.configure(bg=BORDER)

        # Posição: canto superior direito
        sw = root.winfo_screenwidth()
        x = sw - WIDTH - MARGIN
        y = MARGIN
        root.geometry(f"{WIDTH}x130+{x}+{y}")

        # Frame principal
        frame = tk.Frame(root, bg=BG, padx=12, pady=10)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Label "Stormy"
        lbl_font = tkfont.Font(family="Segoe UI", size=8)
        tk.Label(frame, text="STORMY", fg=ACCENT, bg=BG,
                 font=lbl_font).pack(anchor="w")

        # Campo de input
        input_font = tkfont.Font(family="Segoe UI", size=11)
        self._input = tk.Entry(
            frame,
            bg=BG_INPUT, fg=FG_INPUT,
            insertbackground=ACCENT,
            relief="flat",
            font=input_font,
            bd=4,
        )
        self._input.pack(fill="x", pady=(4, 8))
        self._input.focus_set()

        # Label de resposta
        resp_font = tkfont.Font(family="Segoe UI", size=10)
        self._response_var = tk.StringVar(value="")
        self._response_lbl = tk.Label(
            frame,
            textvariable=self._response_var,
            fg=FG_RESPONSE, bg=BG,
            font=resp_font,
            wraplength=WIDTH - 40,
            justify="left",
            anchor="w",
        )
        self._response_lbl.pack(fill="x", anchor="w")

        # Bindings
        self._input.bind("<Return>", self._on_enter)
        self._input.bind("<Escape>", lambda e: self.hide())
        root.bind("<FocusOut>", self._on_focus_out)

        self._root = root

    def _on_enter(self, event=None):
        msg = self._input.get().strip()
        if not msg:
            return
        self._input.delete(0, tk.END)
        self._response_var.set("...")
        threading.Thread(target=self._process, args=(msg,), daemon=True).start()

    def _process(self, msg: str):
        try:
            resp = self._callback(msg)
        except Exception as e:
            resp = f"erro: {e}"
        self._last_response = resp
        if self._root:
            self._root.after(0, lambda: self._response_var.set(resp[:120]))

    def _on_focus_out(self, event=None):
        # Fecha se perder foco (clicou fora)
        if self._root and self._visible:
            self._root.after(200, self._check_focus)

    def _check_focus(self):
        if self._root and self._visible:
            try:
                if self._root.focus_get() is None:
                    self.hide()
            except Exception:
                pass

    def show(self):
        with self._lock:
            if not self._root:
                self._build()
            if not self._visible:
                self._visible = True
                self._root.deiconify()
                self._root.lift()
                self._input.focus_set()
                self._input.delete(0, tk.END)

    def hide(self):
        with self._lock:
            if self._root and self._visible:
                self._visible = False
                self._root.withdraw()

    def toggle(self):
        if self._visible:
            self.hide()
        else:
            self.show()

    def run(self):
        """Deve ser chamado na thread principal (Tkinter exige)."""
        if not self._root:
            self._build()
        self._root.mainloop()

    def destroy(self):
        if self._root:
            self._root.destroy()
            self._root = None
