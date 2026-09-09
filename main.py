"""Orquestador principal de Smart Ads Retail Optimization."""

import logging

from src.core.brain import MotorDecisiones
from src.config.settings import configuracion
from src.services.context_api import GestorContexto
from src.services.meta_api import GestorMetaAds
from src.services.whatsapp_bot import NotificadorWhatsApp


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Ejecuta el flujo principal de la aplicación."""
    gestor_contexto = GestorContexto(configuracion)
    motor_decisiones = MotorDecisiones()
    gestor_meta_ads = GestorMetaAds(configuracion)
    notificador = NotificadorWhatsApp(configuracion)

    contexto = gestor_contexto.obtener_contexto()
    acciones = motor_decisiones.obtener_acciones(contexto)

    for accion in acciones:
        if accion.accion == "PAUSAR":
            gestor_meta_ads.pausar_campana(accion.nombre_campana)
        elif accion.accion == "ACTIVAR":
            gestor_meta_ads.activar_campana(accion.nombre_campana)
        elif accion.accion == "AUMENTAR_PRESUPUESTO":
            porcentaje = (accion.factor_presupuesto - 1) * 100
            gestor_meta_ads.modificar_presupuesto(accion.nombre_campana, porcentaje)

    notificador.enviar_reporte(contexto, acciones)
    logger.info("Flujo de optimización finalizado")


if __name__ == "__main__":
    main()
