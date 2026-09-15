import asyncio
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.config.settings import Configuracion
from src.core.brain import AccionPublicitaria, ConfiguracionAnuncio, MotorDecisiones
from src.services.context_api import DatosContexto, GestorContexto
from src.services.meta_api import ErrorMetaAds, GestorMetaAds
from src.services.telegram_bot import BotTelegram
from src.config.reglas_negocio import GestorReglasNegocio


REGLAS_ASADO = {
    "activo": True,
    "hora_activacion": "08:00",
    "hora_desactivacion": "18:00",
    "temperatura_minima": 20,
    "temperatura_maxima": 30,
    "lluvia_minima": 0,
    "lluvia_maxima": 20,
    "dias": {"L": True},
}


class TestMotorDecisiones(unittest.TestCase):
    def test_anuncio_sin_regla_no_genera_accion(self) -> None:
        reglas = {"Asado": REGLAS_ASADO}
        contexto = DatosContexto(10, False, False, temperatura=25)
        acciones = MotorDecisiones().evaluar_anuncios(
            [
                {"name": "Asado", "id": "1", "status": "PAUSED"},
                {"name": "Estofado", "id": "2", "status": "ACTIVE"},
            ],
            reglas,
            contexto,
            datetime(2026, 9, 7, 12, 0),
        )
        self.assertEqual(
            [(accion.nombre_campana, accion.accion) for accion in acciones],
            [("Asado", "ACTIVAR")],
        )

    def test_clima_no_disponible_no_genera_acciones(self) -> None:
        contexto = DatosContexto(0, False, False)
        acciones = MotorDecisiones().evaluar_anuncios(
            [{"name": "Asado", "id": "1", "status": "PAUSED"}],
            {"Asado": REGLAS_ASADO},
            contexto,
            datetime(2026, 9, 7, 12, 0),
        )
        self.assertEqual(acciones, [])

    def test_no_genera_accion_si_estado_ya_coincide(self) -> None:
        reglas = {"Asado": REGLAS_ASADO}
        contexto = DatosContexto(10, False, False, temperatura=25)
        motor = MotorDecisiones()
        ahora = datetime(2026, 9, 7, 12, 0)
        acciones = motor.evaluar_anuncios(
            [{"name": "Asado", "id": "1", "status": "ACTIVE"}],
            reglas,
            contexto,
            ahora,
        )
        self.assertEqual(acciones, [])
        acciones = motor.evaluar_anuncios(
            [{"name": "Asado", "id": "1", "status": "PAUSED"}],
            reglas,
            contexto,
            ahora,
        )
        self.assertEqual(
            [(accion.nombre_campana, accion.accion, accion.identificador) for accion in acciones],
            [("Asado", "ACTIVAR", "1")],
        )


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
        gestor = GestorMetaAds(
            Configuracion(MODO_SIMULACION=True),
            nombres_adsets_simulados=lambda: ["Asado", "Estofado"],
        )
        gestor.activar_conjunto_por_nombre("asado")
        conjuntos = gestor.obtener_conjuntos()
        estados = {conjunto["name"]: conjunto["status"] for conjunto in conjuntos}
        self.assertEqual(estados["Asado"], "ACTIVE")
        self.assertEqual(estados["Estofado"], "PAUSED")

    def test_error_meta_no_se_confunde_con_lista_vacia(self) -> None:
        gestor = GestorMetaAds(Configuracion(MODO_SIMULACION=False), cliente_api=Mock())
        gestor._cuenta = None
        with self.assertRaises(ErrorMetaAds):
            gestor.obtener_conjuntos()


class TestReglasDinamicas(unittest.TestCase):
    def test_simulacion_conjuntos_pausa_y_refleja_estado(self) -> None:
        gestor = GestorMetaAds(
            Configuracion(MODO_SIMULACION=True),
            nombres_adsets_simulados=lambda: ["Asado"],
        )
        conjuntos = gestor.obtener_conjuntos()
        self.assertEqual(conjuntos[0]["status"], "PAUSED")
        self.assertTrue(conjuntos[0]["id"].startswith("simulado-"))
        gestor.activar_conjunto(conjuntos[0]["id"], conjuntos[0]["name"])
        self.assertEqual(gestor.obtener_conjuntos()[0]["status"], "ACTIVE")
        gestor.pausar_conjunto_por_nombre("Asado")
        self.assertEqual(gestor.obtener_conjuntos()[0]["status"], "PAUSED")

    def test_parser_con_punto_vacia_configuracion(self) -> None:
        texto = BotTelegram.PLANTILLA_CONFIGURACION.format(nombre="Asado").replace(
            "Desactivar anuncio: []", "Desactivar anuncio: [.]"
        )
        self.assertEqual(BotTelegram._parsear_plantilla(texto, "Asado"), {})

    def test_gestor_reglas_persiste_y_vacia(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            gestor = GestorReglasNegocio(f"{directorio}/reglas.json")
            with open(f"{directorio}/reglas.json", "w", encoding="utf-8") as archivo:
                archivo.write('{"conjuntos": {}}')
            gestor.guardar("Asado", {"activo": True})
            self.assertIsNotNone(gestor.obtener("ASADO"))
            gestor.vaciar("asado")
            self.assertIsNone(gestor.obtener("Asado"))

    def test_gestor_reglas_crea_archivo_si_falta(self) -> None:
        with tempfile.TemporaryDirectory() as directorio:
            ruta = f"{directorio}/reglas.json"
            gestor = GestorReglasNegocio(ruta)
            self.assertEqual(gestor.cargar(), {"conjuntos": {}})
            self.assertTrue(Path(ruta).exists())

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
                json.dump({"conjuntos": {"Asado": configuracion}}, archivo)
            gestor.actualizar_estado("Asado", False)
            resultado = gestor.obtener("Asado")
        self.assertEqual(resultado, {**configuracion, "activo": False})

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

    def test_error_real_meta_se_envuelve_en_error_meta_ads(self) -> None:
        class FalsoErrorMeta(Exception):
            def api_error_message(self) -> str:
                return "falta el permiso ads_management"

        ajustes = Configuracion(
            META_ACCESS_TOKEN="token-prueba",
            META_ACCOUNT_ID="cuenta-prueba",
            META_CAMPAIGN_ID="campana-prueba",
            MODO_SIMULACION=False,
        )
        gestor = GestorMetaAds(ajustes, cliente_api=Mock())
        conjunto = Mock()
        conjunto.api_update.side_effect = FalsoErrorMeta()
        with patch(
            "facebook_business.adobjects.adset.AdSet",
            return_value=conjunto,
        ):
            with self.assertRaises(ErrorMetaAds) as contexto_error:
                gestor.pausar_conjunto("conjunto-1", "Asado")
        self.assertIn(
            "falta el permiso ads_management", str(contexto_error.exception)
        )

    def test_desactivar_con_meta_fallido_responde_y_no_guarda(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = {"activo": True}
        bot.meta = Mock()
        bot.meta.pausar_conjunto_por_nombre.side_effect = ErrorMetaAds(
            "No se pudo actualizar el conjunto 'estofado' a PAUSED: falta permiso"
        )
        mensaje = Mock()
        mensaje.text = "Desactivar anuncio: [.]"
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(
            effective_chat=Mock(id=123), message=mensaje
        )
        contexto = Mock(user_data={"anuncio_configuracion": "estofado"})
        asyncio.run(bot.procesar_mensaje(actualizacion, contexto))
        bot.meta.pausar_conjunto_por_nombre.assert_called_once_with("estofado")
        bot.reglas.actualizar_estado.assert_not_called()
        bot.reglas.guardar.assert_not_called()
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("Meta rechazó la operación", respuesta)
        self.assertEqual(contexto.user_data["anuncio_configuracion"], "estofado")

    def test_desactivar_con_meta_ok_guarda_regla_y_responde(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = {"activo": True}
        bot.meta = Mock()
        mensaje = Mock()
        mensaje.text = "Desactivar anuncio: [.]"
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(
            effective_chat=Mock(id=123), message=mensaje
        )
        contexto = Mock(user_data={"anuncio_configuracion": "estofado"})
        asyncio.run(bot.procesar_mensaje(actualizacion, contexto))
        bot.meta.pausar_conjunto_por_nombre.assert_called_once_with("estofado")
        bot.reglas.actualizar_estado.assert_called_once_with("estofado", False)
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("se conservó", respuesta)
        self.assertNotIn("anuncio_configuracion", contexto.user_data)

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
        orquestador.meta.activar_conjunto.assert_not_called()
        orquestador.meta.pausar_conjunto.assert_not_called()
        orquestador.bot.enviar_alerta.assert_awaited_once_with("fallo")

    def test_cache_lleno_con_anuncios_real_aunque_una_accion_falle(self) -> None:
        from main import OrquestadorAsincrono

        orquestador = OrquestadorAsincrono()
        orquestador.contexto = Mock(
            obtener_contexto=Mock(
                return_value=DatosContexto(
                    30, False, False, descripcion_clima="Despejado", temperatura=25
                )
            )
        )
        anuncios = [{"id": "a1", "name": "Asado", "status": "PAUSED"}]
        orquestador.meta = Mock()
        orquestador.meta.obtener_conjuntos.return_value = anuncios
        orquestador.meta.activar_conjunto.side_effect = RuntimeError("fallo real")
        orquestador.bot.enviar_alerta = AsyncMock()
        orquestador.motor.evaluar_anuncios = Mock(
            return_value=[
                AccionPublicitaria("Asado", "ACTIVAR", identificador="a1")
            ]
        )
        asyncio.run(orquestador.evaluar_anuncios(None))
        self.assertEqual(
            orquestador.bot.ultimo_estado["clima"].descripcion_clima, "Despejado"
        )
        self.assertEqual(
            orquestador.bot.ultimo_estado["anuncios"][0]["name"], "Asado"
        )
        orquestador.bot.enviar_alerta.assert_awaited_once()
        contenido = orquestador.bot.enviar_alerta.call_args[0][0]
        self.assertIn("Asado", contenido)

    def test_cooldown_alertas_solo_alarma_una_vez_por_hora_por_adset(self) -> None:
        from main import OrquestadorAsincrono

        orquestador = OrquestadorAsincrono()
        orquestador.bot.enviar_alerta = AsyncMock()
        asyncio.run(
            orquestador._alertar_fallo_meta(
                AccionPublicitaria("Asado", "PAUSAR", identificador="a1"),
                RuntimeError("primer fallo"),
            )
        )
        asyncio.run(
            orquestador._alertar_fallo_meta(
                AccionPublicitaria("Asado", "PAUSAR", identificador="a1"),
                RuntimeError("segundo fallo"),
            )
        )
        self.assertEqual(orquestador.bot.enviar_alerta.await_count, 1)

    def test_alerta_sin_cooldown_para_otro_adset(self) -> None:
        from main import OrquestadorAsincrono

        orquestador = OrquestadorAsincrono()
        orquestador.bot.enviar_alerta = AsyncMock()
        asyncio.run(
            orquestador._alertar_fallo_meta(
                AccionPublicitaria("Asado", "PAUSAR", identificador="a1"),
                RuntimeError("primero"),
            )
        )
        asyncio.run(
            orquestador._alertar_fallo_meta(
                AccionPublicitaria("Estofado", "PAUSAR", identificador="a2"),
                RuntimeError("segundo"),
            )
        )
        self.assertEqual(orquestador.bot.enviar_alerta.await_count, 2)

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
        self.assertIn("L[.], MA[]", plantilla)

    def test_parser_dia_con_punto_queda_activo(self) -> None:
        configuracion = {
            "activo": True,
            "hora_activacion": "06:00",
            "hora_desactivacion": "19:00",
            "temperatura_minima": 0.0,
            "temperatura_maxima": 50.0,
            "lluvia_minima": 0.0,
            "lluvia_maxima": 60.0,
            "dias": {"L": False, "MA": False, "J": False, "S": False},
        }
        plantilla = BotTelegram._formatear_plantilla("Asado", configuracion)
        plantilla = plantilla.replace("+ Dias de la semana: L[]", "+ Dias de la semana: L[.]")
        plantilla = plantilla.replace("S[], D[]", "S[.], D[]")
        reparsed = BotTelegram._parsear_plantilla(plantilla, "Asado")
        self.assertIsNotNone(reparsed)
        self.assertTrue(reparsed["dias"]["L"])
        self.assertFalse(reparsed["dias"]["MA"])
        self.assertFalse(reparsed["dias"]["J"])
        self.assertTrue(reparsed["dias"]["S"])

    def test_formatear_y_parsear_dias_son_consistentes(self) -> None:
        configuracion = {
            "activo": True,
            "hora_activacion": "6:00",
            "hora_desactivacion": "19:00",
            "temperatura_minima": 0.0,
            "temperatura_maxima": 50.0,
            "lluvia_minima": 0.0,
            "lluvia_maxima": 60.0,
            "dias": {"L": True, "MA": False, "MI": True, "J": False, "V": True},
        }
        plantilla = BotTelegram._formatear_plantilla("estofado", configuracion)
        reparsed = BotTelegram._parsear_plantilla(plantilla, "estofado")
        self.assertEqual(
            {dia: reparsed["dias"][dia] for dia in configuracion["dias"]},
            configuracion["dias"],
        )

    def test_hora_sin_cero_inicial_hace_coincidir(self) -> None:
        motor = MotorDecisiones()
        configuracion = ConfiguracionAnuncio(
            nombre="asado",
            hora_activacion="6:00",
            hora_desactivacion="19:00",
            temperatura_minima=0.0,
            temperatura_maxima=50.0,
            lluvia_minima=0.0,
            lluvia_maxima=100.0,
            dias={"L": True, "MA": True, "MI": True, "J": True, "V": True, "S": True, "D": True},
        )
        contexto = DatosContexto(30, False, False, descripcion_clima="Despejado", temperatura=25)
        momento = datetime(2026, 9, 15, 12, 0)
        self.assertTrue(motor._coincide(configuracion, contexto, momento))

    def test_hora_invalida_queda_fuera_de_horario(self) -> None:
        motor = MotorDecisiones()
        configuracion = ConfiguracionAnuncio(
            nombre="asado",
            hora_activacion="--:--",
            hora_desactivacion="19:00",
            temperatura_minima=0.0,
            temperatura_maxima=50.0,
            lluvia_minima=0.0,
            lluvia_maxima=100.0,
            dias={"L": True},
        )
        contexto = DatosContexto(30, False, False, descripcion_clima="Despejado", temperatura=25)
        self.assertFalse(motor._coincide(configuracion, contexto, datetime(2026, 9, 15, 12, 0)))

    def test_chat_no_autorizado_recibe_denegacion(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=999), message=mensaje)
        autorizado = asyncio.run(bot._exigir_chat_autorizado(actualizacion))
        self.assertFalse(autorizado)
        mensaje.reply_text.assert_awaited_once_with("Acceso denegado.")

    def test_chats_autorizados_separados_por_coma(self) -> None:
        ajustes = Configuracion(TELEGRAM_CHAT_ID="123, 456,, 789 ")
        self.assertEqual(ajustes.chats_autorizados, ["123", "456", "789"])

    def test_segundo_chat_autorizado_tambien_accede(self) -> None:
        bot = BotTelegram(
            Configuracion(TELEGRAM_CHAT_ID="123, 456", ENVIAR_TELEGRAM=False)
        )
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=456), message=mensaje)
        autorizado = asyncio.run(bot._exigir_chat_autorizado(actualizacion))
        self.assertTrue(autorizado)

    def test_reporte_diario_envia_mensaje(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = None
        bot._enviar_mensaje = AsyncMock()
        contexto = DatosContexto(
            30,
            False,
            False,
            descripcion_clima="Despejado",
            temperatura=25,
        )
        anuncios = [
            {"name": "Asado", "status": "ACTIVE"},
            {"name": "Estofado", "status": "PAUSED"},
        ]
        asyncio.run(bot.enviar_reporte_diario(contexto, anuncios))
        mensaje = bot._enviar_mensaje.call_args[0][0]
        self.assertIn("Anuncios corriendo:", mensaje)
        self.assertIn("- Asado", mensaje)
        self.assertIn("Sin configurar:", mensaje)
        self.assertIn("- Estofado", mensaje)

    def test_construir_reporte_incluye_datos_clave(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = None
        contexto = DatosContexto(30, False, False, descripcion_clima="Despejado", temperatura=25)
        mensaje = bot._construir_reporte(contexto, [{"name": "Asado", "status": "ACTIVE"}])
        self.assertIn("Despejado", mensaje)
        self.assertIn("- Asado", mensaje)

    def test_adsinfo_responde_ultima_lectura_sin_consultar_meta(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.meta = Mock()
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = None
        bot.ultimo_estado["clima"] = DatosContexto(
            30, False, False, descripcion_clima="Despejado", temperatura=25
        )
        bot.ultimo_estado["anuncios"] = [{"name": "Asado", "status": "ACTIVE"}]
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        asyncio.run(bot.adsinfo(actualizacion, Mock()))
        bot.meta.obtener_conjuntos.assert_not_called()
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("Anuncios corriendo:", respuesta)
        self.assertIn("- Asado", respuesta)

    def test_adsinfo_sin_datos_avisa_proxima_lectura(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        job_queue = Mock()
        job = Mock()
        job.name = "evaluar_anuncios"
        job.next_t = datetime.now(timezone.utc) + timedelta(minutes=15, seconds=40)
        job_queue.jobs.return_value = [job]
        asyncio.run(bot.adsinfo(actualizacion, Mock(job_queue=job_queue)))
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("aproximadamente 16 minutos", respuesta)

    def test_calcular_proxima_lectura_redondea_menos_de_un_minuto(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        job_queue = Mock()
        job = Mock()
        job.name = "evaluar_anuncios"
        job.next_t = datetime.now(timezone.utc) + timedelta(seconds=40)
        job_queue.jobs.return_value = [job]
        minutos = bot._calcular_proxima_lectura(Mock(job_queue=job_queue))
        self.assertEqual(minutos, 1)

    def test_adsinfo_sin_datos_con_proxima_lectura_subminuto(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        job_queue = Mock()
        job = Mock()
        job.name = "evaluar_anuncios"
        job.next_t = datetime.now(timezone.utc) + timedelta(seconds=40)
        job_queue.jobs.return_value = [job]
        asyncio.run(bot.adsinfo(actualizacion, Mock(job_queue=job_queue)))
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("aproximadamente 1 minuto.", respuesta)

    def test_medir_ejecuta_medicion_y_responde_reporte(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        bot.reglas = Mock()
        bot.reglas.obtener.return_value = None

        async def medir(contexto) -> None:
            bot.ultimo_estado["clima"] = DatosContexto(
                30, False, False, descripcion_clima="Despejado", temperatura=25
            )
            bot.ultimo_estado["anuncios"] = [
                {"name": "Asado", "status": "ACTIVE"}
            ]

        bot.funcion_medicion = medir
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        asyncio.run(bot.medir(actualizacion, Mock()))
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("Despejado", respuesta)
        self.assertIn("- Asado", respuesta)

    def test_medir_sin_medicion_previa_responde_aviso(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))

        async def medir(contexto) -> None:
            pass

        bot.funcion_medicion = medir
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        asyncio.run(bot.medir(actualizacion, Mock()))
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("aún no hay datos disponibles", respuesta)

    def test_medir_chat_no_autorizado_no_ejecuta_medicion(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        funcion = AsyncMock()
        bot.funcion_medicion = funcion
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=999), message=mensaje)
        asyncio.run(bot.medir(actualizacion, Mock()))
        funcion.assert_not_called()
        mensaje.reply_text.assert_awaited_once_with("Acceso denegado.")

    def test_medir_sin_funcion_configurada_responde_aviso(self) -> None:
        bot = BotTelegram(Configuracion(TELEGRAM_CHAT_ID="123", ENVIAR_TELEGRAM=False))
        mensaje = Mock()
        mensaje.reply_text = AsyncMock()
        actualizacion = Mock(effective_chat=Mock(id=123), message=mensaje)
        asyncio.run(bot.medir(actualizacion, Mock()))
        respuesta = mensaje.reply_text.call_args[0][0]
        self.assertIn("no está configurada", respuesta)


if __name__ == "__main__":
    unittest.main()