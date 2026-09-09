"""Motor de decisiones para la optimización de campañas."""

from dataclasses import dataclass
import logging

from src.services.context_api import DatosContexto


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccionPublicitaria:
	"""Acción normalizada que debe ejecutarse sobre una campaña."""

	nombre_campana: str
	accion: str
	factor_presupuesto: float = 1.0


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

	def decidir(self, contexto: DatosContexto) -> list[AccionPublicitaria]:
		"""Alias descriptivo para obtener las acciones del motor."""
		return self.obtener_acciones(contexto)
