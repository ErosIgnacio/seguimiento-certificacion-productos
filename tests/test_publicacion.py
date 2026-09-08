from __future__ import annotations

import json
import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]


class PruebasPublicacion(unittest.TestCase):
    def test_gitignore_excluye_archivos_sensibles(self):
        contenido = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        for patron in (
            "config.json",
            ".env",
            "config.dat",
            "installer/output/",
            "Certificacion.csv",
            "reportes/",
            "*.log",
        ):
            with self.subTest(patron=patron):
                self.assertIn(patron, contenido)

    def test_configuracion_ejemplo_es_valida_y_no_es_real(self):
        ejemplo = (RAIZ / "config.example.json").read_text(encoding="utf-8")
        configuracion = json.loads(ejemplo)
        self.assertEqual(
            set(("host", "user", "password", "database", "port"))
            - set(configuracion),
            set(),
        )
        self.assertNotIn(".rds.amazonaws.com", ejemplo.lower())
        self.assertIn("REEMPLAZAR", configuracion["password"])

    def test_publicacion_declara_dependencias_y_ci_sin_secretos(self):
        pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        workflow = (RAIZ / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("customtkinter", pyproject)
        self.assertIn("PyMySQL", pyproject)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("LOG_IMPORTADO_CONFIG", workflow)


if __name__ == "__main__":
    unittest.main()
