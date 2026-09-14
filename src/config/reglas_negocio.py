"""Persistencia de las reglas configurables de los anuncios."""

import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class GestorReglasNegocio:
    """Lee y actualiza las reglas de anuncios almacenadas en JSON."""

    def __init__(
        self, ruta: str | Path | None = None, clave_principal: str = "conjuntos"
    ) -> None:
        self.ruta = Path(ruta) if ruta is not None else Path(__file__).with_name(
            "reglas_conjuntos.json"
        )
        self.clave_principal = clave_principal

    def cargar(self) -> dict[str, Any]:
        """Devuelve el documento JSON y crea uno vacío si no existe."""
        if not self.ruta.exists():
            logger.warning("No existe el archivo de reglas; se crea '%s'", self.ruta)
            self._guardar_documento({self.clave_principal: {}})
        try:
            with self.ruta.open("r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            if not isinstance(datos, dict) or not isinstance(
                datos.get(self.clave_principal), dict
            ):
                raise ValueError(
                    f"El JSON debe contener un objeto '{self.clave_principal}'"
                )
            return datos
        except (OSError, json.JSONDecodeError, ValueError):
            logger.exception("No se pudo leer el archivo de reglas: %s", self.ruta)
            raise

    def obtener_todas(self) -> dict[str, dict[str, Any]]:
        """Devuelve las configuraciones indexadas por nombre normalizado."""
        return self.cargar()[self.clave_principal]

    def obtener(self, nombre_anuncio: str) -> dict[str, Any] | None:
        """Busca la configuración de un anuncio sin distinguir mayúsculas."""
        nombre = self.normalizar_nombre(nombre_anuncio)
        for clave, configuracion in self.obtener_todas().items():
            if self.normalizar_nombre(clave) == nombre:
                return configuracion
        return None

    def guardar(self, nombre_anuncio: str, configuracion: dict[str, Any]) -> None:
        """Reemplaza la configuración de un anuncio y persiste el documento."""
        datos = self.cargar()
        anuncios = datos[self.clave_principal]
        clave_existente = next(
            (
                clave
                for clave in anuncios
                if self.normalizar_nombre(clave)
                == self.normalizar_nombre(nombre_anuncio)
            ),
            nombre_anuncio.strip(),
        )
        anuncios[clave_existente] = configuracion
        self._guardar_documento(datos)

    def actualizar_estado(self, nombre_anuncio: str, activo: bool) -> None:
        """Cambia solo el estado lógico y conserva toda la configuración."""
        datos = self.cargar()
        nombre = self.normalizar_nombre(nombre_anuncio)
        for clave, configuracion in datos[self.clave_principal].items():
            if self.normalizar_nombre(clave) == nombre:
                configuracion["activo"] = activo
                self._guardar_documento(datos)
                return
        raise KeyError(f"No existe configuración para el anuncio '{nombre_anuncio}'")

    def vaciar(self, nombre_anuncio: str) -> None:
        """Elimina la configuración para que el anuncio quede sin configurar."""
        datos = self.cargar()
        nombre = self.normalizar_nombre(nombre_anuncio)
        datos[self.clave_principal] = {
            clave: valor
            for clave, valor in datos[self.clave_principal].items()
            if self.normalizar_nombre(clave) != nombre
        }
        self._guardar_documento(datos)

    def _guardar_documento(self, datos: dict[str, Any]) -> None:
        """Escribe el documento completo de forma legible."""
        try:
            with self.ruta.open("w", encoding="utf-8") as archivo:
                json.dump(datos, archivo, ensure_ascii=False, indent=2)
                archivo.write("\n")
        except OSError:
            logger.exception("No se pudo guardar el archivo de reglas: %s", self.ruta)
            raise

    @staticmethod
    def normalizar_nombre(nombre_anuncio: str) -> str:
        """Normaliza nombres para cruzar Telegram, JSON y Meta."""
        return " ".join(nombre_anuncio.strip().casefold().split())
