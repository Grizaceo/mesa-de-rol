"""El paquete `mesa.cli` reemplaza el módulo monolito sin cambiar la fachada pública."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class TestCliPaquete(unittest.TestCase):
    def test_es_paquete_con_main(self):
        from mesa import cli
        self.assertEqual(Path(cli.__file__).name, "__init__.py")
        self.assertTrue(callable(cli.main))
        self.assertIn("turno", cli.ESCRIBEN)
        self.assertIn("vida", cli.CAMBIOS)

    def test_importar_no_carga_el_servidor(self):
        codigo = (
            "import sys\n"
            "from mesa import cli\n"
            "assert callable(cli.main)\n"
            "assert 'mesa.servidor' not in sys.modules\n"
            "assert 'mesa.cli.parser' not in sys.modules\n"
        )
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_el_parser_se_reusa(self):
        from mesa.cli.parser import construir
        self.assertIs(construir(), construir())

    def test_construir_parser_no_carga_submodulos_de_comandos(self):
        codigo = (
            "import sys\n"
            "from mesa.cli.parser import construir\n"
            "construir()\n"
            "for sub in ('admin', 'combate', 'escena', 'partida', 'registro'):\n"
            "    assert f'mesa.cli.{sub}' not in sys.modules, sub\n"
        )
        r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_modulos_js_del_visor_tienen_sintaxis_e_imports_validos(self):
        import re
        import shutil
        visor_dir = Path(__file__).resolve().parent.parent / "visor"
        archivos = sorted(visor_dir.glob("*.js"))
        self.assertGreaterEqual(len(archivos), 10)
        node = shutil.which("node")
        if node:
            for js in archivos:
                r = subprocess.run([node, "--input-type=module", "--check"], input=js.read_text(encoding="utf-8"), capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{js.name}: {r.stderr}")
        exportados = {}
        for js in archivos:
            src = js.read_text(encoding="utf-8")
            for m in re.finditer(r"export\s+(?:async\s+)?(?:function|const|let)\s+([A-Za-z0-9_$]+)", src):
                exportados[m.group(1)] = js.name
            for m in re.finditer(r"export\s*\{([^}]+)\}", src):
                for parte in m.group(1).split(","):
                    if parte.strip():
                        exportados[parte.strip()] = js.name
        for js in archivos:
            src = js.read_text(encoding="utf-8")
            importados = set()
            for m in re.finditer(r"import\s+\{([^}]+)\}\s+from", src):
                for tok in m.group(1).split(","):
                    if tok.strip():
                        importados.add(tok.strip().split()[-1])
            definidos = set(re.findall(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(", src))
            definidos |= set(re.findall(r"(?:export\s+)?(?:const|let)\s+([A-Za-z0-9_$]+)\s*=", src))
            for sym, dueno in exportados.items():
                if sym in definidos or sym in importados:
                    continue
                for linea in src.splitlines():
                    limpia = re.sub(r"//.*", "", linea)
                    if re.search(rf"(?<![.\w$/\"'\`-])\b{re.escape(sym)}\s*\([^)]*\)\s*\{{", limpia):
                        continue
                    if re.search(rf"(?<![.\w$/\"'\`-])\b{re.escape(sym)}\s*\(", limpia):
                        self.fail(f"{js.name} llama a `{sym}(...)` (de {dueno}) sin importarlo: {linea.strip()}")


if __name__ == "__main__":
    unittest.main()
