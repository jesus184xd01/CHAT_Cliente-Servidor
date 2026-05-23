import socket
import threading
import struct
import os
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

IMAGES_DIR = "imagenes_recibidas_cliente"


# ─── Binary Protocol ─────────────────────────────────────────────────────────

def enviar_paquete(conexion, tipo, nombre, datos):
    tipo_b = tipo.encode("utf-8")
    nombre_b = nombre.encode("utf-8")
    encabezado = struct.pack("!B", len(tipo_b)) + tipo_b
    encabezado += struct.pack("!H", len(nombre_b)) + nombre_b
    encabezado += struct.pack("!Q", len(datos))
    conexion.sendall(encabezado + datos)


def recibir_exactamente(conexion, n):
    datos = b""
    while len(datos) < n:
        parte = conexion.recv(n - len(datos))
        if not parte:
            return None
        datos += parte
    return datos


def recibir_paquete(conexion):
    tipo_len_b = recibir_exactamente(conexion, 1)
    if not tipo_len_b:
        return None, None, None
    tipo_len = struct.unpack("!B", tipo_len_b)[0]
    tipo = recibir_exactamente(conexion, tipo_len).decode("utf-8")
    nombre_len = struct.unpack("!H", recibir_exactamente(conexion, 2))[0]
    nombre = recibir_exactamente(conexion, nombre_len).decode("utf-8") \
             if nombre_len else ""
    tam = struct.unpack("!Q", recibir_exactamente(conexion, 8))[0]
    datos = recibir_exactamente(conexion, tam)
    return tipo, nombre, datos


# ─── Client class ─────────────────────────────────────────────────────────────

class ChatClient:
    BG       = "#1a1a2e"
    PANEL_BG = "#16213e"
    CHAT_BG  = "#0f0f23"
    ACCENT   = "#00d4ff"
    FG       = "#e0e0e0"

    def __init__(self, root):
        self.root = root
        self.root.configure(bg=self.BG)
        self.root.geometry("960x680")
        self.root.minsize(720, 520)

        self.sock = None
        self.alias = ""
        self.conectado = False
        self._photo_refs = []        # prevent GC of PhotoImage objects
        self.usuarios_en_linea = []

        os.makedirs(IMAGES_DIR, exist_ok=True)
        self._build_screen1()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Helper: replace all widgets ───────────────────────────────────────────

    def _clear_window(self):
        for w in self.root.winfo_children():
            w.destroy()

    # ─────────────────────────────────────────────────────────────────────────
    # SCREEN 1 — Connection dialog
    # ─────────────────────────────────────────────────────────────────────────

    def _build_screen1(self):
        self._clear_window()
        self.root.title("Chat — Conectar")

        outer = tk.Frame(self.root, bg=self.BG)
        outer.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        tk.Label(outer, text="Chat P2P", bg=self.BG, fg=self.ACCENT,
                 font=("Consolas", 24, "bold")).grid(
                 row=0, column=0, columnspan=2, pady=(0, 32))

        fields = [
            ("IP del Servidor", "127.0.0.1"),
            ("Puerto",          "5000"),
            ("Tu alias",        ""),
        ]
        self._entries = {}

        for i, (label, default) in enumerate(fields):
            tk.Label(outer, text=label, bg=self.BG, fg=self.FG,
                     font=("Consolas", 11),
                     anchor=tk.E).grid(row=i + 1, column=0,
                                       sticky=tk.E, padx=(0, 14), pady=9)
            e = tk.Entry(outer, bg="#0f3460", fg=self.FG,
                         insertbackground=self.ACCENT,
                         font=("Consolas", 11), relief=tk.FLAT,
                         bd=4, width=26)
            e.insert(0, default)
            e.grid(row=i + 1, column=1, pady=9, ipady=5)
            self._entries[label] = e

        self._entries["Tu alias"].bind("<Return>", lambda _e: self._conectar())

        tk.Button(
            outer, text="  Conectar  ",
            bg="#0d4f3c", fg=self.FG, font=("Consolas", 12, "bold"),
            bd=0, padx=16, pady=8,
            activebackground="#1a7a5e", activeforeground=self.FG,
            cursor="hand2", command=self._conectar
        ).grid(row=4, column=0, columnspan=2, pady=24)

    # ─────────────────────────────────────────────────────────────────────────
    # SCREEN 2 — Main chat
    # ─────────────────────────────────────────────────────────────────────────

    def _build_screen2(self):
        self._clear_window()
        self.root.title(f"Chat — {self.alias}")

        # TOP bar ─────────────────────────────────────────────────────────────
        top = tk.Frame(self.root, bg=self.PANEL_BG, height=44)
        top.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))
        top.pack_propagate(False)

        tk.Label(top, text="●", bg=self.PANEL_BG, fg="#00ff88",
                 font=("Consolas", 15)).pack(side=tk.LEFT, padx=(12, 4))
        tk.Label(top, text=f"Conectado como: {self.alias}",
                 bg=self.PANEL_BG, fg=self.FG,
                 font=("Consolas", 11)).pack(side=tk.LEFT)

        tk.Button(
            top, text="Desconectar",
            bg="#5c1010", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=12,
            activebackground="#8b0000", activeforeground=self.FG,
            cursor="hand2", command=self._desconectar
        ).pack(side=tk.RIGHT, padx=12, pady=8)

        # MAIN area ───────────────────────────────────────────────────────────
        main = tk.Frame(self.root, bg=self.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # LEFT panel — user list ──────────────────────────────────────────────
        left = tk.Frame(main, bg=self.PANEL_BG, width=180)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        left.pack_propagate(False)

        tk.Label(left, text="En línea", bg=self.PANEL_BG, fg=self.ACCENT,
                 font=("Consolas", 10, "bold"), pady=10).pack(fill=tk.X)
        tk.Frame(left, bg=self.ACCENT, height=1).pack(fill=tk.X, padx=4)

        self.lista_usuarios = tk.Listbox(
            left, bg="#0f3460", fg=self.FG,
            selectbackground=self.ACCENT, selectforeground="#000",
            font=("Consolas", 10), bd=0, highlightthickness=0, relief=tk.FLAT
        )
        self.lista_usuarios.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # CENTER — chat canvas ────────────────────────────────────────────────
        chat_outer = tk.Frame(main, bg=self.BG)
        chat_outer.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # BOTTOM input bar — packed BEFORE canvas so it isn't squeezed out
        bot = tk.Frame(chat_outer, bg=self.PANEL_BG, height=52)
        bot.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        bot.pack_propagate(False)

        self.btn_img = tk.Button(
            bot, text="Imagen",
            bg="#0d4f3c", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=10,
            activebackground="#1a7a5e", activeforeground=self.FG,
            cursor="hand2", command=self._enviar_imagen
        )
        self.btn_img.pack(side=tk.RIGHT, padx=4, pady=10)

        self.btn_send = tk.Button(
            bot, text="Enviar",
            bg="#0d3f8a", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=14,
            activebackground="#1a5fcc", activeforeground=self.FG,
            cursor="hand2", command=self._enviar_texto
        )
        self.btn_send.pack(side=tk.RIGHT, padx=4, pady=10)

        self.entry_msg = tk.Entry(
            bot, bg="#0f3460", fg=self.FG,
            insertbackground=self.ACCENT,
            font=("Consolas", 11), relief=tk.FLAT, bd=4
        )
        self.entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True,
                            padx=8, pady=10, ipady=5)
        self.entry_msg.bind("<Return>", lambda _e: self._enviar_texto())
        self.entry_msg.focus_set()

        # Canvas + scrollbar — packed after bottom bar so they fill remaining space
        canvas_frame = tk.Frame(chat_outer, bg=self.CHAT_BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg=self.CHAT_BG,
                                highlightthickness=0)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                           command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.bubble_frame = tk.Frame(self.canvas, bg=self.CHAT_BG)
        self._cw = self.canvas.create_window(
            (0, 0), window=self.bubble_frame, anchor=tk.NW
        )

        self.bubble_frame.bind("<Configure>", self._on_bubble_cfg)
        self.canvas.bind("<Configure>", self._on_canvas_cfg)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>",   self._on_wheel)
        self.canvas.bind_all("<Button-5>",   self._on_wheel)

    # ── Canvas resize helpers ─────────────────────────────────────────────────

    def _on_bubble_cfg(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_cfg(self, e):
        self.canvas.itemconfig(self._cw, width=e.width)

    def _on_wheel(self, e):
        if e.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif e.num == 5:
            self.canvas.yview_scroll(1, "units")
        else:
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _scroll_bottom(self):
        self.root.after(60, lambda: self.canvas.yview_moveto(1.0))

    # ── Message bubbles ───────────────────────────────────────────────────────

    def _add_bubble(self, text, side="left", alias="", sys=False):
        now = datetime.now().strftime("%H:%M")
        row = tk.Frame(self.bubble_frame, bg=self.CHAT_BG)
        row.pack(fill=tk.X, pady=2, padx=6)

        if sys:
            tk.Label(row, text=text, bg=self.CHAT_BG, fg="#888888",
                     font=("Consolas", 9, "italic"),
                     wraplength=520).pack(anchor=tk.CENTER, pady=2)
        elif side == "right":
            bubble = tk.Frame(row, bg="#0d47a1", padx=10, pady=6)
            bubble.pack(anchor=tk.E)
            tk.Label(bubble, text=f"[{now}]  {text}",
                     bg="#0d47a1", fg="white",
                     font=("Consolas", 10), wraplength=370,
                     justify=tk.RIGHT).pack()
        else:
            bubble = tk.Frame(row, bg="#2d2d44", padx=10, pady=6)
            bubble.pack(anchor=tk.W)
            header = f"[{now}] {alias}: " if alias else f"[{now}] "
            tk.Label(bubble, text=header + text,
                     bg="#2d2d44", fg="white",
                     font=("Consolas", 10), wraplength=370,
                     justify=tk.LEFT).pack()

        self._scroll_bottom()

    def _add_image_bubble(self, img_bytes, nombre, side="left", alias=""):
        now = datetime.now().strftime("%H:%M")
        row = tk.Frame(self.bubble_frame, bg=self.CHAT_BG)
        row.pack(fill=tk.X, pady=2, padx=6)

        color  = "#0d47a1" if side == "right" else "#2d2d44"
        anchor = tk.E      if side == "right" else tk.W

        bubble = tk.Frame(row, bg=color, padx=8, pady=6)
        bubble.pack(anchor=anchor)

        if side == "left" and alias:
            tk.Label(bubble, text=f"[{now}] {alias}",
                     bg=color, fg="#aaaaaa",
                     font=("Consolas", 9)).pack(anchor=tk.W)

        if PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(img_bytes))
                img.thumbnail((200, 200), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._photo_refs.append(photo)
                tk.Label(bubble, image=photo, bg=color).pack()
            except Exception:
                tk.Label(bubble, text="[imagen — error al decodificar]",
                         bg=color, fg="white",
                         font=("Consolas", 10)).pack()
        else:
            tk.Label(bubble, text="[imagen — instala Pillow para verla]",
                     bg=color, fg="white",
                     font=("Consolas", 10)).pack()

        tk.Label(bubble, text=nombre, bg=color, fg="#aaaaaa",
                 font=("Consolas", 8)).pack(anchor=tk.W)

        if side == "right":
            tk.Label(bubble, text=f"[{now}]", bg=color, fg="#aaaaaa",
                     font=("Consolas", 8)).pack(anchor=tk.E)

        self._scroll_bottom()

    # ── User list ─────────────────────────────────────────────────────────────

    def _actualizar_usuarios(self):
        self.lista_usuarios.delete(0, tk.END)
        for u in self.usuarios_en_linea:
            self.lista_usuarios.insert(tk.END, f"● {u}")

    def _parse_sys(self, msg):
        if msg.endswith(" se ha conectado"):
            alias = msg[: -len(" se ha conectado")]
            if alias not in self.usuarios_en_linea:
                self.usuarios_en_linea.append(alias)
        elif msg.endswith(" se ha desconectado"):
            alias = msg[: -len(" se ha desconectado")]
            if alias in self.usuarios_en_linea:
                self.usuarios_en_linea.remove(alias)
        self._actualizar_usuarios()

    # ── Network — connect / disconnect ────────────────────────────────────────

    def _conectar(self):
        ip       = self._entries["IP del Servidor"].get().strip()
        port_str = self._entries["Puerto"].get().strip()
        alias    = self._entries["Tu alias"].get().strip()

        if not ip or not port_str or not alias:
            messagebox.showerror("Error", "Completa todos los campos.")
            return
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "El puerto debe ser un número.")
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((ip, port))
            enviar_paquete(self.sock, "USR", "", alias.encode("utf-8"))
            self.alias = alias
            self.conectado = True
        except Exception as e:
            messagebox.showerror("Error de conexión", str(e))
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            return

        self._build_screen2()
        threading.Thread(target=self._receive_loop, daemon=True).start()

    def _desconectar(self):
        self.conectado = False
        if self.sock:
            try:
                enviar_paquete(self.sock, "EXT", "", b"")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.usuarios_en_linea.clear()
        self._build_screen1()

    # ── Receive loop (daemon thread) ──────────────────────────────────────────

    def _receive_loop(self):
        while self.conectado:
            try:
                tipo, nombre, datos = recibir_paquete(self.sock)
            except Exception:
                if self.conectado:
                    self.root.after(0, self._servidor_cerrado)
                return

            if tipo is None:
                if self.conectado:
                    self.root.after(0, self._servidor_cerrado)
                return

            if tipo == "TXT":
                sender = nombre
                msg = datos.decode("utf-8")
                self.root.after(
                    0, lambda s=sender, m=msg:
                    self._add_bubble(m, side="left", alias=s)
                )

            elif tipo == "IMG":
                img_bytes = datos
                fname     = nombre
                self.root.after(
                    0, lambda b=img_bytes, n=fname:
                    self._recv_imagen(b, n)
                )

            elif tipo == "SYS":
                msg = datos.decode("utf-8")
                self.root.after(0, lambda m=msg: self._handle_sys(m))

            elif tipo == "EXT":
                if self.conectado:
                    self.root.after(0, self._servidor_cerrado)
                return

    def _handle_sys(self, msg):
        self._parse_sys(msg)
        self._add_bubble(msg, sys=True)

    def _recv_imagen(self, img_bytes, nombre):
        saved = self._guardar_imagen(nombre, img_bytes)
        self._add_image_bubble(img_bytes, saved, side="left")

    def _servidor_cerrado(self):
        self.conectado = False
        messagebox.showinfo("Desconectado", "El servidor cerró la conexión.")
        self._desconectar()

    # ── Send — text ───────────────────────────────────────────────────────────

    def _enviar_texto(self):
        if not self.conectado:
            return
        text = self.entry_msg.get().strip()
        if not text:
            return
        self.entry_msg.delete(0, tk.END)
        try:
            enviar_paquete(self.sock, "TXT", "", text.encode("utf-8"))
        except Exception as e:
            messagebox.showerror("Error al enviar", str(e))
            return
        self._add_bubble(text, side="right")

    # ── Send — image (background thread to keep UI alive during large files) ──

    def _enviar_imagen(self):
        if not self.conectado:
            return
        path = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[("Imágenes",
                        "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
        )
        if not path:
            return

        try:
            with open(path, "rb") as f:
                img_bytes = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el archivo:\n{e}")
            return

        nombre = os.path.basename(path)

        # Progress popup
        pw = tk.Toplevel(self.root)
        pw.title("Enviando imagen…")
        pw.configure(bg=self.BG)
        pw.geometry("320x90")
        pw.resizable(False, False)
        pw.grab_set()
        tk.Label(pw, text=f"Enviando: {nombre}",
                 bg=self.BG, fg=self.FG,
                 font=("Consolas", 10)).pack(pady=(14, 4))
        pb = ttk.Progressbar(pw, mode="indeterminate", length=280)
        pb.pack(padx=20)
        pb.start(12)

        def _send():
            try:
                enviar_paquete(self.sock, "IMG", nombre, img_bytes)
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("Error al enviar", str(e))
                )
            finally:
                self.root.after(0, pw.destroy)
                self.root.after(
                    0, lambda: self._add_image_bubble(
                        img_bytes, nombre, side="right"
                    )
                )

        threading.Thread(target=_send, daemon=True).start()

    # ── Image saving ──────────────────────────────────────────────────────────

    def _guardar_imagen(self, nombre, datos):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        destino = Path(IMAGES_DIR) / nombre
        if destino.exists():
            stem, suffix = destino.stem, destino.suffix
            i = 1
            while destino.exists():
                destino = Path(IMAGES_DIR) / f"{stem}_{i}{suffix}"
                i += 1
        with open(destino, "wb") as f:
            f.write(datos)
        return destino.name

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self.conectado:
            self._desconectar()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatClient(root)
    root.mainloop()
