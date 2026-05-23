# Chat Cliente-Servidor

Aplicación de chat en red de área local con interfaz gráfica (Tkinter), soporte para mensajes de texto y transferencia de imágenes, usando un protocolo binario personalizado sobre TCP.

## Requisitos

- Python 3.8 o superior
- Pillow (para mostrar imágenes en el chat)

```bash
pip install Pillow
```

## Ejecutar

### Servidor

```bash
python servidor.py
# o en Linux:
python3 servidor.py
```

1. La ventana del servidor abrirá. Presiona **"Iniciar Servidor"**.
2. El servidor escucha en el puerto **5000** en todas las interfaces.

### Cliente

```bash
python cliente.py
# o en Linux:
python3 cliente.py
```

1. Ingresa la **IP del servidor**, el **puerto** (5000) y tu **alias**.
2. Presiona **Conectar**.
3. Envía mensajes con la tecla `Enter` o el botón **Enviar**.
4. Envía imágenes con el botón **Imagen** (PNG, JPG, JPEG, GIF, BMP, WEBP).

## Estructura de directorios generados automáticamente

```
imagenes_recibidas_servidor/   ← imágenes recibidas por el servidor
imagenes_recibidas_cliente/    ← imágenes recibidas por cada cliente
```

## Configuración de firewall

### Windows

Permite el tráfico TCP entrante al puerto 5000:

```
Panel de control → Firewall de Windows Defender
→ Configuración avanzada → Reglas de entrada → Nueva regla
→ Puerto → TCP → Puerto específico: 5000 → Permitir la conexión
```

O desde PowerShell (como administrador):

```powershell
New-NetFirewallRule -DisplayName "Chat Puerto 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

### Linux (UFW)

```bash
sudo ufw allow 5000/tcp
```

## Encontrar la IP del servidor

### Windows

```cmd
ipconfig
```

Busca la línea **"Dirección IPv4"** bajo tu adaptador de red activo.

### Linux

```bash
ip a
```

Busca la dirección `inet` bajo `eth0`, `wlan0` o el nombre de tu interfaz activa.

---

## Protocolo de red

El sistema usa un protocolo binario sobre TCP con los siguientes tipos de paquetes:

| Tipo  | Uso                              |
|-------|----------------------------------|
| `TXT` | Mensaje de texto                 |
| `IMG` | Transferencia de imagen          |
| `EXT` | Desconexión voluntaria           |
| `USR` | Registro de alias al conectar    |
| `SYS` | Notificaciones del sistema       |
