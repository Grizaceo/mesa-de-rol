# Imágenes de escena

Ambientar es opcional. Hay tres modos, de más barato a más caro, y siempre se puede volver
al primero.

| Modo | Comando | Red | Costo | Cuándo |
|---|---|---|---|---|
| **Tarjeta local** | `bin/mesa imagen ninguna` | No | 0 | Por defecto. Una tarjeta tipográfica con el título, el lugar y el color de la historia |
| **Elegir una existente** | `bin/mesa imagen elegir <id \| ruta \| URL>` | Solo si es URL | 0 | Hay una imagen que encaja: de la biblioteca, del disco o de la web |
| **Generar** | `bin/mesa imagen generar` | Sí | Crédito de la clave | Una escena importante merece una imagen hecha a medida |

En los tres casos la imagen queda en `partidas/<slug>/imagenes/` y el visor la muestra con su origen.

## Elegir una existente

### La biblioteca compartida

`biblioteca/imagenes/` es una colección reutilizable entre historias, con un índice de etiquetas:

```bash
bin/mesa imagen biblioteca-agregar ~/Imágenes/muelle-niebla.jpg \
  --etiquetas "muelle,niebla,rio,amanecer,1917" \
  --descripcion "Muelle de madera en la niebla, barcas pequeñas" \
  --fuente "Wikimedia Commons, autor X" --licencia "CC BY-SA 4.0"

bin/mesa imagen buscar "muelle niebla"      # el director busca por etiquetas
bin/mesa imagen elegir muelle-niebla        # usa la imagen por su id
```

### Una ruta o una URL puntual

```bash
bin/mesa imagen elegir ~/Descargas/puente.jpg
bin/mesa imagen elegir https://upload.wikimedia.org/.../foto.jpg
```

Las URL se descargan una sola vez. Solo se aceptan si responden con un `Content-Type` de
imagen raster admitida y pesan hasta 15 MB.

### Qué se acepta (y qué no)

El **contenido manda sobre la extensión**: un archivo `foto.png` que por dentro es SVG se
rechaza, igual que un `.svg` importado. El visor solo sirve la tarjeta SVG que genera
`imagen ninguna` con valores controlados; los formatos admitidos son **PNG, JPEG, GIF y
WebP** de hasta **15 MB**. Desde el MCP solo se eligen imágenes ya curadas en
`biblioteca/imagenes/` (id o archivo): las rutas y URLs van por la CLI a mano
(ver [`seguridad.md`](seguridad.md)).

### Derechos

- **Anota fuente y licencia** de cada imagen en la biblioteca.
- **Fotos de época:** las de 1917 suelen ser de dominio público, pero conviene confirmarlo.
- **Imágenes con derechos:** no se suben a un repositorio público. Las raster de `partidas/*/imagenes/` están en `.gitignore` por peso.

## Generar (opcional)

```bash
bin/mesa imagen generar --simular            # muestra el prompt y no envía nada
bin/mesa imagen generar                      # gemini por defecto
bin/mesa imagen generar --proveedor openrouter --modelo google/gemini-2.5-flash-image
bin/mesa imagen generar --prompt "Una barca pequeña en la niebla del Neva, 1917, óleo"
```

- **Cómo se arma el prompt:** sale del `estilo_visual` de la partida más el título, lugar, hora, clima y descripción de la escena, y pide «sin texto».
- **Claves:**
  - `GOOGLE_API_KEY` o `GEMINI_API_KEY` para gemini; `OPENROUTER_API_KEY` para openrouter.
  - Se leen del entorno o de `MESA_ENV_FILE` (por ejemplo, `MESA_ENV_FILE=~/.hermes/.env`).
- **Privacidad:** el prompt sale a un servicio externo. Contiene solo la escena de ficción, pero aun así **nunca se genera sin que alguien lo pida**.
- **Coherencia:** reutiliza un mismo `estilo_visual` en toda la historia. Si un personaje aparece a menudo, describe su aspecto igual cada vez (está en la ficha).
