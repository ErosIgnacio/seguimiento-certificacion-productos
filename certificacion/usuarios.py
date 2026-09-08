"""Contrato común para identificar al usuario en interfaz y auditoría."""

from __future__ import annotations

import getpass
import os


def normalizar_usuario(usuario: str) -> str:
    """Valida un nombre no vacío y conserva la convención TRIM/mayúsculas."""
    if not isinstance(usuario, str) or not usuario.strip():
        raise ValueError("El usuario conectado es obligatorio")
    normalizado = usuario.strip().upper()
    if len(normalizado) > 100:
        raise ValueError("El usuario conectado no puede exceder 100 caracteres")
    return normalizado


def obtener_usuario_equipo() -> str:
    """Obtiene la cuenta de la sesión de Windows usada para la auditoría."""
    try:
        return normalizar_usuario(os.environ.get("USERNAME"))
    except ValueError:
        pass

    for proveedor in (getpass.getuser, os.getlogin):
        try:
            return normalizar_usuario(proveedor())
        except (OSError, KeyError):
            continue
        except ValueError:
            continue
    raise RuntimeError(
        "No se pudo determinar el usuario de Windows del equipo"
    )


def resolver_usuario(usuario: str | None = None) -> str:
    """Conserva overrides explícitos y usa Windows cuando no se informan."""
    if usuario is None:
        return obtener_usuario_equipo()
    return normalizar_usuario(usuario)
