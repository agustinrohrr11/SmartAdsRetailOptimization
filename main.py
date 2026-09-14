"""Orquestador asíncrono de Smart Ads Retail Optimization."""

import asyncio
import logging
from datetime import time
from pathlib import Path
from typing import Any

from src.config.reglas_negocio import GestorReglasNegocio
from src.config.settings import configuracion
from src.core.brain import MotorDecisiones
from src.services.context_api import GestorContexto
from src.services.meta_api import ErrorMetaAds, GestorMetaAds
from src.services.telegram_bot import BotTelegram


logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class OrquestadorAsincrono:
    """Coordina clima, reglas, Meta Ads y Telegram dentro de JobQueue."""

    def __init__(self) -> None:
        self.contexto = GestorContexto(configuracion)
        self.motor = MotorDecisiones()
        self.reglas = GestorReglasNegocio(
            Path(__file__).parent / "src" / "config" / "reglas_conjuntos.json",
            clave_principal="conjuntos",
        )
        self.meta = GestorMetaAds(
            configuracion,
            nombres_adsets_simulados=lambda: list(
                self.reglas.obtener_todas().keys()
            ),
        )
        self.bot = BotTelegram(configuracion, self.reglas, self.meta)

    async def evaluar_anuncios(self, contexto_job: Any) -> None:
        """Evalúa y aplica el estado de todos los anuncios."""
        datos_clima = self.contexto.obtener_contexto()
        try:
            anuncios = self.meta.obtener_conjuntos()
        except ErrorMetaAds as error:
            logger.exception("Se omite la evaluación por un error de Meta Ads")
            await self.bot.enviar_alerta(str(error))
            return
        acciones = self.motor.evaluar_anuncios(anuncios, self.reglas.obtener_todas(), datos_clima)
        for accion in acciones:
            try:
                if accion.accion == "ACTIVAR":
                    self.meta.activar_conjunto(accion.identificador, accion.nombre_anuncio)
                else:
                    self.meta.pausar_conjunto(accion.identificador, accion.nombre_anuncio)
                self._reflejar_estado_en_cache(anuncios, accion)
            except (RuntimeError, ValueError):
                logger.exception("No se pudo aplicar %s a '%s'", accion.accion, accion.nombre_anuncio)
        self.bot.ultimo_estado["clima"] = datos_clima
        self.bot.ultimo_estado["anuncios"] = anuncios

    async def enviar_reporte(self, contexto_job: Any) -> None:
        """Envía el reporte con una lectura fresca de clima y Meta."""
        datos_clima = self.contexto.obtener_contexto()
        try:
            anuncios = self.meta.obtener_conjuntos()
        except ErrorMetaAds as error:
            logger.exception("Se omite el reporte por un error de Meta Ads")
            await self.bot.enviar_alerta(str(error))
            return
        self.bot.ultimo_estado["clima"] = datos_clima
        self.bot.ultimo_estado["anuncios"] = anuncios
        await self.bot.enviar_reporte_diario(datos_clima, anuncios)

    @staticmethod
    def _reflejar_estado_en_cache(
        anuncios: list[dict[str, str]], accion: Any
    ) -> None:
        """Actualiza el estado en la lista cacheada sin reconsultar Meta."""
        estado = "ACTIVE" if accion.accion == "ACTIVAR" else "PAUSED"
        for anuncio in anuncios:
            if str(anuncio.get("id", "")) == accion.identificador:
                anuncio["status"] = estado
                return

    def construir_aplicacion(self) -> Any:
        """Construye el bot y registra los tres jobs programados."""
        aplicacion = self.bot.construir_aplicacion()
        if aplicacion.job_queue is None:
            raise RuntimeError("JobQueue no está disponible; instala el extra job-queue")
        aplicacion.job_queue.run_repeating(
            self.evaluar_anuncios, interval=1800, first=0, name="evaluar_anuncios"
        )
        aplicacion.job_queue.run_daily(
            self.enviar_reporte, time=time(hour=6, minute=0), name="reporte_6"
        )
        aplicacion.job_queue.run_daily(
            self.enviar_reporte, time=time(hour=15, minute=0), name="reporte_15"
        )
        return aplicacion


def main() -> None:
    """Inicia el polling del bot y sus tareas programadas."""
    orquestador = OrquestadorAsincrono()
    asyncio.set_event_loop(asyncio.new_event_loop())
    orquestador.construir_aplicacion().run_polling()


if __name__ == "__main__":
    main()
