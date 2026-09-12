import asyncio
from datetime import date, datetime
import json
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.config.settings import Configuracion
from src.core.brain import MotorDecisiones
from src.services.context_api import DatosContexto, GestorContexto
from src.services.meta_api import ErrorMetaAds, GestorMetaAds
from src.services.telegram_bot import NotificadorTelegram
from src.services.telegram_bot import BotTelegram
from src.config.reglas_negocio import GestorReglasNegocio


class TestMotorDecisiones(unittest.TestCase):
    def test_lluvia_activa_estofado_y_pausa_asado(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(61, False, False)
        )
        self.assertEqual(
            [(accion.nombre_campana, accion.accion) for accion in acciones],
            [("Asado", "PAUSAR"), ("Estofado", "ACTIVAR")],
        )

    def test_fin_de_semana_aumenta_asado(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(0, True, False)
        )
        self.assertEqual(acciones[1].factor_presupuesto, 1.3)

    def test_quincena_activa_economicos(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(0, False, True)
        )
        self.assertEqual(acciones[0].nombre_campana, "Económicos/Picada")


class TestGestorContexto(unittest.TestCase):
    def test_parsea_open_meteo_y_ultimo_dia_del_mes(self) -> None:
        respuesta = Mock()
        respuesta.json.return_value = {
            "daily": {
                "precipitation_probability_max": [70],
                "weather_code": [61],
                "temperature_2m_max": [20],
            }
        }
        cliente = Mock()
        cliente.get.return_value = respuesta
        contexto = GestorContexto(
            cliente_http=cliente,
            fecha_actual=date(2026, 2, 28),
        ).obtener_contexto()
        self.assertEqual(contexto.probabilidad_lluvia, 70)
        self.assertTrue(contexto.es_quincena_o_fin_de_mes)
        cliente.get.assert_called_once()


class TestIntegracionesSeguras(unittest.TestCase):
    def test_meta_simulada_no_requiere_credenciales(self) -> None:
        gestor = GestorMetaAds(Configuracion(MODO_SIMULACION=True))
        gestor.activar_campana("Asado")
        gestor.modificar_presupuesto("Asado", 30)

    def test_telegram_desactivado_no_envia(self) -> None:
        cliente = Mock()
        notificador = NotificadorTelegram(
            Configuracion(ENVIAR_TELEGRAM=False), cliente_http=cliente
        )
        self.assertIsNone(
            notificador.enviar_reporte(DatosContexto(0, False, False), [])
        )


class TestReglasDinamicas(unittest.TestCase):
    def test_anuncio_sin_regla_se_pausa_y_regla_coincidente_se_activa(self) -> None:
        reglas = {
            "Asado": {
                "activo": True,
                "hora_activacion": "08:00",
                "hora_desactivacion": "18:00",
                "temperatura_minima": 20,
                "temperatura_maxima": 30,
                "lluvia_minima": 0,
                "lluvia_maxima": 20,
                "dias": {"L": True},
            }
        }
        contexto = DatosContexto(10, False, False, temperatura=25)
        acciones = MotorDecisiones().evaluar_anuncios(
            [{"name": "Asado"}, {"name": "Estofado"}],
            reglas,
            contexto,
            datetime(2026, 9, 7, 12, 0),
        )
        self.assertEqual(
            [(accion.nombre_campana, accion.accion) for accion in acciones],
            [("Asado", "ACTIVAR"), ("Estofado", "PAUSAR")],
        )

    def test_parser_con_punto_vacia_configuracion(self) -> None:
        texto = BotTelegram.PLANTILLA_CONFIGURACION.format(nombre="Asado").replace(
            "Desactivar anuncio: []", "Desactivar anuncio: [.]"
        )
        self.assertEqual(BotTelegram._parsear_plantilla(texto, "Asado"), {})

    def test_gestor_reglas_persiste_y_vacia(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            gestor = GestorReglasNegocio(f"{directorio}/reglas.json")
            with open(f"{directorio}/reglas.json", "w", encoding="utf-8") as archivo:
                archivo.write('{"anuncios": {}}')
            gestor.guardar("Asado", {"activo": True})
            self.assertIsNotNone(gestor.obtener("ASADO"))
            gestor.vaciar("asado")
            self.assertIsNone(gestor.obtener("Asado"))

    def test_desactivar_conserva_configuracion_y_cambia_solo_estado(self) -> None:
        configuracion = {
            "activo": True,
            "hora_activacion": "08:00",
            "hora_desactivacion": "18:00",
            "temperatura_minima": 20,
            "temperatura_maxima": 30,
            "lluvia_minima": 0,
            "lluvia_maxima": 40,
            "dias": {"L": True, "MA": False},
        }
        with tempfile.TemporaryDirectory() as directorio:
            gestor = GestorReglasNegocio(f"{directorio}/reglas.json")
            with open(f"{directorio}/reglas.json", "w", encoding="utf-8") as archivo:
                json.dump({"anuncios": {"Asado": configuracion}}, archivo)
            gestor.actualizar_estado("Asado", False)
            resultado = gestor.obtener("Asado")
        self.assertEqual(resultado, {**configuracion, "activo": False})

    def test_meta_simulada_pausa_ad_y_no_campana(self) -> None:
        gestor = GestorMetaAds(Configuracion(MODO_SIMULACION=True))
        anuncio = gestor.obtener_anuncios()[0]
        gestor.pausar_anuncio(anuncio["id"], anuncio["name"])
        resultado = gestor.obtener_anuncios()[0]
        self.assertEqual(resultado["status"], "PAUSED")
        self.assertTrue(resultado["id"].startswith("simulado-"))

    def test_error_meta_no_se_confunde_con_lista_vacia(self) -> None:
        gestor = GestorMetaAds(Configuracion(MODO_SIMULACION=False), cliente_api=Mock())
        gestor._cuenta = None
        with self.assertRaises(ErrorMetaAds):
            gestor.obtener_anuncios()

    def test_descubre_conjuntos_de_la_campana_principal(self) -> None:
        ajustes = Configuracion(
            META_ACCESS_TOKEN="token-prueba",
            META_ACCOUNT_ID="cuenta-prueba",
            META_CAMPAIGN_ID="campana-prueba",
            MODO_SIMULACION=False,
        )
        gestor = GestorMetaAds(ajustes, cliente_api=Mock())
        campana = Mock()
        campana.get_ad_sets.return_value = [
            {"id": "conjunto-1", "name": "Asado", "status": "ACTIVE"},
            {"id": "conjunto-2", "name": "Estofado", "status": "PAUSED"},
        ]
        with patch(
            "facebook_business.adobjects.campaign.Campaign",
            return_value=campana,
        ) as constructor:
            conjuntos = gestor.obtener_conjuntos()
        constructor.assert_called_once_with("campana-prueba")
        campana.get_ad_sets.assert_called_once_with(
            fields=["id", "name", "status", "campaign_id"]
        )
        self.assertEqual([conjunto["name"] for conjunto in conjuntos], ["Asado", "Estofado"])

    def test_actualiza_adset_y_no_campaign(self) -> None:
        ajustes = Configuracion(
            META_ACCESS_TOKEN="token-prueba",
            META_ACCOUNT_ID="cuenta-prueba",
            META_CAMPAIGN_ID="campana-prueba",
            MODO_SIMULACION=False,
        )
        gestor = GestorMetaAds(ajustes, cliente_api=Mock())
        conjunto = Mock()
        with patch(
            "facebook_business.adobjects.adset.AdSet",
            return_value=conjunto,
        ):
            gestor.pausar_conjunto("conjunto-1", "Asado")
        conjunto.api_update.assert_called_once_with(params={"status": "PAUSED"})

    def test_evaluador_no_modifica_anuncios_si_meta_falla(self) -> None:
        from main import OrquestadorAsincrono

        orquestador = OrquestadorAsincrono()
        orquestador.contexto = Mock(
            obtener_contexto=Mock(
                return_value=DatosContexto(0, False, False, temperatura=25)
            )
        )
        orquestador.meta = Mock()
        orquestador.meta.obtener_conjuntos.side_effect = ErrorMetaAds("fallo")
        orquestador.bot.enviar_alerta = AsyncMock()
        asyncio.run(orquestador.evaluar_anuncios(None))
        orquestador.meta.activar_anuncio.assert_not_called()
        orquestador.meta.pausar_anuncio.assert_not_called()
        orquestador.bot.enviar_alerta.assert_awaited_once_with("fallo")

    def test_estados_configuracion_distinguen_desactivado(self) -> None:
        self.assertEqual(
            BotTelegram._estado_configuracion({"activo": False}),
            "Configurado - Desactivado",
        )
        self.assertEqual(
            BotTelegram._estado_configuracion({"activo": True}),
            "Configurado - Activo",
        )
        self.assertEqual(BotTelegram._estado_configuracion(None), "Sin configurar")

    def test_plantilla_prellenada_conserva_valores_guardados(self) -> None:
        configuracion = {
            "activo": False,
            "hora_activacion": "6:00",
            "hora_desactivacion": "19:00",
            "temperatura_minima": 0.0,
            "temperatura_maxima": 50.0,
            "lluvia_minima": 0.0,
            "lluvia_maxima": 60.0,
            "dias": {"L": True, "MA": False, "MI": True},
        }
        plantilla = BotTelegram._formatear_plantilla("asado", configuracion)
        self.assertIn("Activación: [6:00]", plantilla)
        self.assertIn("Desactivación: [19:00]", plantilla)
        self.assertIn("Desactivar anuncio: [.]", plantilla)
        self.assertIn("L[], MA[.]", plantilla)

    def test_chat_no_autorizado_recibe_denegacion(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123"))
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=999), message=mensaje)
        autorizado = asyncio.run(bot._exigir_chat_autorizado(actualizacion))
        self.assertFalse(autorizado)
        mensaje.reply_text.assert_awaited_once_with("Acceso denegado.")

    def test_telegram_envia_reporte_con_cliente_simulado(self) -> None:
        respuesta = Mock()
        respuesta.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }
        cliente = Mock()
        cliente.post.return_value = respuesta
        notificador = NotificadorTelegram(
            Configuracion(
                ENVIAR_TELEGRAM=True,
                TELEGRAM_BOT_TOKEN="token-prueba",
                TELEGRAM_CHAT_ID="chat-prueba",
            ),
            cliente_http=cliente,
        )
        resultado = notificador.enviar_reporte(
            DatosContexto(0, False, False), []
        )
        self.assertEqual(resultado, 42)
        cliente.post.assert_called_once()

    def test_telegram_maneja_error_de_red(self) -> None:
        import requests

        cliente = Mock()
        cliente.post.side_effect = requests.RequestException("fallo")
        notificador = NotificadorTelegram(
            Configuracion(
                ENVIAR_TELEGRAM=True,
                TELEGRAM_BOT_TOKEN="token-prueba",
                TELEGRAM_CHAT_ID="chat-prueba",
            ),
            cliente_http=cliente,
        )
        self.assertIsNone(
            notificador.enviar_reporte(DatosContexto(0, False, False), [])
        )


if __name__ == "__main__":
    unittest.main()
