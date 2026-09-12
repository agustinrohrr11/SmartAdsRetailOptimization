"""Motor de decisiones para la optimización de campañas."""

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from src.services.context_api import DatosContexto


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccionPublicitaria:
	"""Acción normalizada que debe ejecutarse sobre un anuncio."""

	nombre_anuncio: str
	accion: str
	factor_presupuesto: float = 1.0
	identificador: str = ""

	@property
	def nombre_campana(self) -> str:
		"""Alias temporal para consumidores antiguos del motor."""
		return self.nombre_anuncio


@dataclass(frozen=True)
class ConfiguracionAnuncio:
	"""Regla validada para evaluar un anuncio."""

	nombre: str
	hora_activacion: str
	hora_desactivacion: str
	temperatura_minima: float
	temperatura_maxima: float
	lluvia_minima: float
	lluvia_maxima: float
	dias: dict[str, bool]

	@classmethod
	def desde_json(cls, nombre: str, datos: dict[str, Any]) -> "ConfiguracionAnuncio | None":
		"""Convierte una regla JSON completa; reglas incompletas quedan sin configurar."""
		if datos.get("activo") is not True:
			return None
		try:
			return cls(
				nombre=nombre,
				hora_activacion=str(datos["hora_activacion"]),
				hora_desactivacion=str(datos["hora_desactivacion"]),
				temperatura_minima=float(datos["temperatura_minima"]),
				temperatura_maxima=float(datos["temperatura_maxima"]),
				lluvia_minima=float(datos["lluvia_minima"]),
				lluvia_maxima=float(datos["lluvia_maxima"]),
				dias={str(clave): bool(valor) for clave, valor in datos["dias"].items()},
			)
		except (KeyError, TypeError, ValueError, AttributeError):
			logger.warning("Configuración incompleta para '%s'", nombre)
			return None


class MotorDecisiones:
	"""Evalúa el contexto y genera acciones publicitarias."""

	def obtener_acciones(self, contexto: DatosContexto) -> list[AccionPublicitaria]:
		"""Devuelve las acciones aplicables al contexto recibido."""
		acciones: list[AccionPublicitaria] = []
		llueve = contexto.probabilidad_lluvia > 60

		if llueve:
			acciones.extend(
				[
					AccionPublicitaria("Asado", "PAUSAR"),
					AccionPublicitaria("Estofado", "ACTIVAR", 1.5),
				]
			)
		elif contexto.es_fin_de_semana:
			acciones.extend(
				[
					AccionPublicitaria("Asado", "ACTIVAR"),
					AccionPublicitaria("Asado", "AUMENTAR_PRESUPUESTO", 1.3),
				]
			)

		if contexto.es_quincena_o_fin_de_mes:
			acciones.append(
				AccionPublicitaria("Económicos/Picada", "ACTIVAR")
			)

		logger.info("Se generaron %d acciones publicitarias", len(acciones))
		return acciones

	def evaluar_anuncios(
		self,
		anuncios: list[dict[str, Any]],
		reglas: dict[str, dict[str, Any]],
		contexto: DatosContexto,
		momento: datetime | None = None,
	) -> list[AccionPublicitaria]:
		"""Decide ACTIVAR o PAUSAR sin acceder a red ni modificar persistencia."""
		ahora = momento or datetime.now()
		acciones: list[AccionPublicitaria] = []
		for anuncio in anuncios:
			nombre = str(anuncio.get("name", ""))
			identificador = str(anuncio.get("id", ""))
			regla = next(
				(
					valor
					for clave, valor in reglas.items()
					if " ".join(clave.casefold().split())
					== " ".join(nombre.casefold().split())
				),
				None,
			)
			configuracion = (
				ConfiguracionAnuncio.desde_json(nombre, regla)
				if isinstance(regla, dict)
				else None
			)
			if configuracion is None or contexto.temperatura is None:
				acciones.append(AccionPublicitaria(nombre, "PAUSAR", identificador=identificador))
				continue
			if self._coincide(configuracion, contexto, ahora):
				acciones.append(AccionPublicitaria(nombre, "ACTIVAR", identificador=identificador))
			else:
				acciones.append(AccionPublicitaria(nombre, "PAUSAR", identificador=identificador))
		return acciones

	@staticmethod
	def _coincide(
		configuracion: ConfiguracionAnuncio,
		contexto: DatosContexto,
		momento: datetime,
	) -> bool:
		"""Comprueba todos los umbrales dinámicos de una regla."""
		try:
			hora_inicio = datetime.strptime(configuracion.hora_activacion, "%H:%M").time()
			hora_fin = datetime.strptime(configuracion.hora_desactivacion, "%H:%M").time()
		except ValueError:
			return False
		en_horario = (
			hora_inicio <= momento.time() <= hora_fin
			if hora_inicio <= hora_fin
			else momento.time() >= hora_inicio or momento.time() <= hora_fin
		)
		dias = ("L", "MA", "MI", "J", "V", "S", "D")
		return (
			en_horario
			and configuracion.dias.get(dias[momento.weekday()], False)
			and configuracion.temperatura_minima <= contexto.temperatura <= configuracion.temperatura_maxima
			and configuracion.lluvia_minima <= contexto.probabilidad_lluvia <= configuracion.lluvia_maxima
		)

	def decidir(self, contexto: DatosContexto) -> list[AccionPublicitaria]:
		"""Alias descriptivo para obtener las acciones del motor."""
		return self.obtener_acciones(contexto)
