import socket
import threading
import struct
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

HOST = "0.0.0.0"
PORT = 5000
IMAGES_DIR = "imagenes_recibidas_servidor"


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


# ─── Server class ─────────────────────────────────────────────────────────────

class ChatServer:
    # theme constants
    BG       = "#1a1a2e"
    PANEL_BG = "#16213e"
    ACCENT   = "#00d4ff"
    FG       = "#e0e0e0"

    def __init__(self, root):
        self.root = root
        self.root.title("Servidor de Chat — Puerto 5000")
        self.root.configure(bg=self.BG)
        self.root.geometry("950x620")
        self.root.minsize(700, 460)

        self.clientes = {}       # conn → {"alias": str, "addr": tuple}
        self.lock = threading.Lock()
        self.servidor_socket = None
        self.corriendo = False

        os.makedirs(IMAGES_DIR, exist_ok=True)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # BOTTOM bar — must be packed BEFORE expand=True widgets
        bottom = tk.Frame(self.root, bg=self.PANEL_BG, height=44)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        bottom.pack_propagate(False)

        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "127.0.0.1"

        tk.Label(bottom, text=f"IP: {local_ip}", bg=self.PANEL_BG, fg=self.FG,
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=10)
        tk.Label(bottom, text="Puerto: 5000", bg=self.PANEL_BG, fg=self.FG,
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=6)

        self.lbl_count = tk.Label(bottom, text="Clientes: 0",
                                  bg=self.PANEL_BG, fg=self.ACCENT,
                                  font=("Consolas", 9, "bold"))
        self.lbl_count.pack(side=tk.LEFT, padx=10)

        self.btn_stop = tk.Button(
            bottom, text="Detener Servidor",
            bg="#5c1010", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=10, pady=4,
            activebackground="#8b0000", activeforeground=self.FG,
            state=tk.DISABLED, cursor="hand2",
            command=self.detener_servidor
        )
        self.btn_stop.pack(side=tk.RIGHT, padx=8, pady=6)

        self.btn_start = tk.Button(
            bottom, text="Iniciar Servidor",
            bg="#0d4f3c", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=10, pady=4,
            activebackground="#1a7a5e", activeforeground=self.FG,
            cursor="hand2", command=self.iniciar_servidor
        )
        self.btn_start.pack(side=tk.RIGHT, padx=4, pady=6)

        # LEFT panel
        left = tk.Frame(self.root, bg=self.PANEL_BG, width=220)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0), pady=8)
        left.pack_propagate(False)

        tk.Label(left, text="Clientes Conectados", bg=self.PANEL_BG,
                 fg=self.ACCENT, font=("Consolas", 11, "bold"),
                 pady=10).pack(fill=tk.X)
        tk.Frame(left, bg=self.ACCENT, height=1).pack(fill=tk.X, padx=4)

        self.lista_clientes = tk.Listbox(
            left, bg="#0f3460", fg=self.FG,
            selectbackground=self.ACCENT, selectforeground="#000000",
            font=("Consolas", 10), bd=0, highlightthickness=0, relief=tk.FLAT
        )
        self.lista_clientes.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # CENTER panel
        center = tk.Frame(self.root, bg=self.BG)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        tk.Label(center, text="Log del Servidor", bg=self.BG,
                 fg=self.ACCENT, font=("Consolas", 11, "bold"),
                 pady=6).pack(fill=tk.X)
        tk.Frame(center, bg=self.ACCENT, height=1).pack(fill=tk.X)

        # Input bar — packed BEFORE log so it isn't squeezed out
        input_bar = tk.Frame(center, bg=self.PANEL_BG, height=48)
        input_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        input_bar.pack_propagate(False)

        self.btn_srv_img = tk.Button(
            input_bar, text="Imagen",
            bg="#0d4f3c", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=10,
            activebackground="#1a7a5e", activeforeground=self.FG,
            cursor="hand2", state=tk.DISABLED,
            command=self._enviar_imagen
        )
        self.btn_srv_img.pack(side=tk.RIGHT, padx=4, pady=10)

        self.btn_srv_send = tk.Button(
            input_bar, text="Enviar",
            bg="#0d3f8a", fg=self.FG, font=("Consolas", 9, "bold"),
            bd=0, padx=14,
            activebackground="#1a5fcc", activeforeground=self.FG,
            cursor="hand2", state=tk.DISABLED,
            command=self._enviar_texto
        )
        self.btn_srv_send.pack(side=tk.RIGHT, padx=4, pady=10)

        self.entry_srv = tk.Entry(
            input_bar, bg="#0f3460", fg=self.FG,
            insertbackground=self.ACCENT,
            font=("Consolas", 11), relief=tk.FLAT, bd=4,
            state=tk.DISABLED
        )
        self.entry_srv.pack(side=tk.LEFT, fill=tk.X, expand=True,
                            padx=8, pady=10, ipady=4)
        self.entry_srv.bind("<Return>", lambda _e: self._enviar_texto())

        self.log = scrolledtext.ScrolledText(
            center, bg="#0f0f23", fg=self.FG, insertbackground=self.ACCENT,
            font=("Consolas", 10), bd=0, relief=tk.FLAT,
            state=tk.DISABLED, wrap=tk.WORD
        )
        self.log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.log.tag_config("join",  foreground="#00ff88")
        self.log.tag_config("leave", foreground="#ff4444")
        self.log.tag_config("msg",   foreground="#ffffff")
        self.log.tag_config("img",   foreground="#00d4ff")
        self.log.tag_config("err",   foreground="#ffaa00")
        self.log.tag_config("sys",   foreground="#aaaaaa")
        self.log.tag_config("time",  foreground="#555577")
        self.log.tag_config("srv",   foreground="#ffd700")

    # ── Logging (thread-safe via root.after) ──────────────────────────────────

    def _log(self, mensaje, tag="sys"):
        now = datetime.now().strftime("%H:%M:%S")

        def _insert():
            self.log.config(state=tk.NORMAL)
            self.log.insert(tk.END, f"[{now}] ", "time")
            self.log.insert(tk.END, mensaje + "\n", tag)
            self.log.config(state=tk.DISABLED)
            self.log.see(tk.END)

        self.root.after(0, _insert)

    # ── Client list (thread-safe) ─────────────────────────────────────────────

    def _actualizar_lista(self):
        def _update():
            self.lista_clientes.delete(0, tk.END)
            with self.lock:
                snapshot = list(self.clientes.values())
            for info in snapshot:
                ip, port = info["addr"]
                self.lista_clientes.insert(
                    tk.END, f"● {info['alias']} ({ip}:{port})"
                )
            self.lbl_count.config(text=f"Clientes: {len(snapshot)}")

        self.root.after(0, _update)

    # ── Network ───────────────────────────────────────────────────────────────

    def broadcast(self, tipo, nombre, datos, exclude_conn=None):
        with self.lock:
            targets = list(self.clientes.keys())
        for conn in targets:
            if conn is exclude_conn:
                continue
            try:
                enviar_paquete(conn, tipo, nombre, datos)
            except Exception as e:
                self._log(f"Error broadcast → {e}", "err")

    def handle_client(self, conn, addr):
        alias = f"{addr[0]}:{addr[1]}"
        try:
            tipo, _, datos = recibir_paquete(conn)
            if tipo != "USR" or not datos:
                conn.close()
                return
            alias = datos.decode("utf-8").strip() or alias

            with self.lock:
                self.clientes[conn] = {"alias": alias, "addr": addr}

            self._log(f"{alias} ({addr[0]}:{addr[1]}) se ha conectado", "join")
            self._actualizar_lista()
            self.broadcast(
                "SYS", "",
                f"{alias} se ha conectado".encode("utf-8"),
                exclude_conn=conn
            )

            while True:
                tipo, nombre, datos = recibir_paquete(conn)
                if tipo is None or tipo == "EXT":
                    break

                if tipo == "TXT":
                    msg = datos.decode("utf-8")
                    self._log(f"{alias}: {msg}", "msg")
                    # relay with alias in nombre so receivers can display it
                    self.broadcast("TXT", alias, datos, exclude_conn=conn)

                elif tipo == "IMG":
                    self._log(f"{alias} envió imagen: {nombre}", "img")
                    self._guardar_imagen(nombre, datos)
                    self.broadcast("IMG", nombre, datos, exclude_conn=conn)

        except Exception as e:
            self._log(f"Error con {alias}: {e}", "err")
        finally:
            with self.lock:
                self.clientes.pop(conn, None)
            self._log(f"{alias} se ha desconectado", "leave")
            self._actualizar_lista()
            self.broadcast(
                "SYS", "",
                f"{alias} se ha desconectado".encode("utf-8")
            )
            try:
                conn.close()
            except Exception:
                pass

    def _guardar_imagen(self, nombre, datos):
        os.makedirs(IMAGES_DIR, exist_ok=True)
        destino = Path(IMAGES_DIR) / nombre
        if destino.exists():
            stem = destino.stem
            suffix = destino.suffix
            i = 1
            while destino.exists():
                destino = Path(IMAGES_DIR) / f"{stem}_{i}{suffix}"
                i += 1
        with open(destino, "wb") as f:
            f.write(datos)

    def _aceptar_clientes(self):
        while self.corriendo:
            try:
                conn, addr = self.servidor_socket.accept()
            except OSError:
                break
            t = threading.Thread(
                target=self.handle_client, args=(conn, addr), daemon=True
            )
            t.start()

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def iniciar_servidor(self):
        if self.corriendo:
            return
        try:
            self.servidor_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            self.servidor_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            if hasattr(socket, "SO_REUSEPORT"):
                self.servidor_socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEPORT, 1
                )
            self.servidor_socket.bind((HOST, PORT))
            self.servidor_socket.listen()
            self.corriendo = True
            self._log(f"Servidor escuchando en {HOST}:{PORT}", "sys")
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.entry_srv.config(state=tk.NORMAL)
            self.btn_srv_send.config(state=tk.NORMAL)
            self.btn_srv_img.config(state=tk.NORMAL)
            threading.Thread(target=self._aceptar_clientes, daemon=True).start()
        except Exception as e:
            self._log(f"Error al iniciar: {e}", "err")

    def detener_servidor(self):
        self.corriendo = False
        if self.servidor_socket:
            try:
                self.servidor_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.servidor_socket.close()
            except Exception:
                pass
            self.servidor_socket = None

        with self.lock:
            conns = list(self.clientes.keys())

        for conn in conns:
            try:
                enviar_paquete(conn, "EXT", "", b"")
                conn.close()
            except Exception:
                pass

        with self.lock:
            self.clientes.clear()

        self._actualizar_lista()
        self._log("Servidor detenido.", "sys")
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.entry_srv.config(state=tk.DISABLED)
        self.btn_srv_send.config(state=tk.DISABLED)
        self.btn_srv_img.config(state=tk.DISABLED)

    # ── Server → clients messaging ────────────────────────────────────────────

    def _enviar_texto(self):
        if not self.corriendo:
            return
        text = self.entry_srv.get().strip()
        if not text:
            return
        self.entry_srv.delete(0, tk.END)
        self.broadcast("TXT", "Servidor", text.encode("utf-8"))
        self._log(f"[Servidor]: {text}", "srv")

    def _enviar_imagen(self):
        if not self.corriendo:
            return
        path = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                img_bytes = f.read()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer la imagen:\n{e}")
            return

        nombre = os.path.basename(path)

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
                self.broadcast("IMG", nombre, img_bytes)
                self.root.after(0, lambda: self._log(
                    f"[Servidor] envió imagen: {nombre}", "img"
                ))
            except Exception as e:
                self.root.after(
                    0, lambda: messagebox.showerror("Error al enviar", str(e))
                )
            finally:
                self.root.after(0, pw.destroy)

        threading.Thread(target=_send, daemon=True).start()

    def _on_close(self):
        if self.corriendo:
            self.detener_servidor()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChatServer(root)
    root.mainloop()
