"""Persistencia de los horarios para los reportes diarios por Telegram."""

import json
import logging
import re
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class GestorReportes:
	"""Lee y actualiza la lista de horarios (HH:MM) de los reportes diarios."""

	HORARIOS_PREDETERMINADOS: list[str] = ["06:00", "15:00"]

	def __init__(
		self,
		ruta: str | Path | None = None,
		clave_principal: str = "horarios",
	) -> None:
		self.ruta = Path(ruta) if ruta is not None else Path(__file__).parents[1] / "config" / "horarios_reportes.json"
		self.clave_principal = clave_principal

	def listar(self) -> list[str]:
		"""Devuelve los horarios guardados, ordenados."""
		return sorted(self.cargar())

	def agregar(self, texto: str) -> tuple[bool, str]:
		"""Agrega un horario. Devuelve (éxito, mensaje para el usuario)."""
		hora = self._normalizar(texto)
		if hora is None:
			return False, "Horario inválido. Usá el formato HH:MM, ej: /setreporte 6:00"
		horarios = self.listar()
		if hora in horarios:
			return False, f"Ya existe un reporte a las {hora}."
		horarios.append(hora)
		self._guardar(sorted(horarios))
		return True, f"Reporte diario configurado para las {hora}."

	def eliminar(self, texto: str) -> tuple[bool, str]:
		"""Elimina un horario. Devuelve (éxito, mensaje para el usuario)."""
		hora = self._normalizar(texto)
		if hora is None:
			return False, "Horario inválido. Usá el formato HH:MM, ej: /delreporte 6:00"
		horarios = self.listar()
		if hora not in horarios:
			return False, f"No existe un reporte a las {hora}."
		horarios.remove(hora)
		self._guardar(horarios)
		return True, f"Reporte de las {hora} eliminado."

	def cargar(self) -> list[str]:
		"""Lee el documento y lo crea con los valores por defecto si no existe."""
		if not self.ruta.exists():
			logger.warning("No existe el archivo de horarios; se crea '%s'", self.ruta)
			self._guardar(self.HORARIOS_PREDETERMINADOS)
			return list(self.HORARIOS_PREDETERMINADOS)
		try:
			with self.ruta.open("r", encoding="utf-8") as archivo:
				datos = json.load(archivo)
			valor = datos.get(self.clave_principal, []) if isinstance(datos, dict) else []
			if not isinstance(valor, list):
				raise ValueError(
					f"El JSON debe contener una lista '{self.clave_principal}'"
				)
			return [str(hora) for hora in valor]
		except (OSError, ValueError, json.JSONDecodeError):
			logger.exception("No se pudo leer el archivo de horarios: %s", self.ruta)
			raise

	def _guardar(self, horarios: list[str]) -> None:
		"""Escribe el documento JSON de forma legible."""
		try:
			with self.ruta.open("w", encoding="utf-8") as archivo:
				json.dump(
					{self.clave_principal: sorted(horarios)},
					archivo,
					ensure_ascii=False,
					indent=2,
				)
				archivo.write("\n")
		except OSError:
			logger.exception("No se pudo guardar el archivo de horarios: %s", self.ruta)
			raise

	@staticmethod
	def _normalizar(texto: str) -> str | None:
		"""Acepta '6', '6:00' y '06:00' y devuelve 'HH:MM' canónico."""
		coincidencia = re.fullmatch(r"([01]?\d|2[0-3])(?::([0-5]\d))?", texto.strip())
		if not coincidencia:
			return None
		hora = int(coincidencia.group(1))
		minuto = int(coincidencia.group(2) or 0)
		return f"{hora:02d}:{minuto:02d}"
