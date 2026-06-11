# chm_de_lidar

Gera o **Canopy Height Model (CHM)** a partir de uma nuvem de pontos LiDAR (`.las` ou `.laz`), usando apenas Python — sem CloudCompare, PDAL ou outras ferramentas externas.

```
CHM = DSM − DTM
```

| Raster | Descrição |
|--------|-----------|
| **DSM** | Digital Surface Model — retorno mais alto por pixel (dossel, telhados) |
| **DTM** | Digital Terrain Model — retorno mais baixo por pixel (aproximação do solo) |
| **CHM** | Canopy Height Model — altura da vegetação acima do solo |

---

## Saídas

```
saida_chm/
├── chm.tif               ← CHM principal (GeoTIFF, float32)
├── dsm.tif               ← DSM (opcional)
├── dtm.tif               ← DTM (opcional)
├── cobertura_dossel.tif  ← raster binário: 1 = vegetação acima do limiar
└── chm.png               ← visualização colorida (opcional)
```

Além dos rasters, o script imprime estatísticas de cobertura no terminal:

```
altura_max_m                        28.4
altura_media_m                       9.2
cobertura_arvore_pct                62.3
cobertura_arbusto_pct               12.1
```

## Instalação

```bash
pip install laspy lazrs-python rasterio numpy matplotlib
```

> `lazrs-python` é necessário para ler arquivos `.laz` comprimidos.

## Configuração

```python
CONFIG = {
    "arquivo_las":      "nuvem_pontos.las",   # ou .laz
    "dir_saida":        "saida_chm/",
    "resolucao_m":      1.0,      # 0.5m para nuvens densas, 2.0m para esparsas
    "epsg_saida":       31983,    # SIRGAS 2000 UTM 23S
    "limiar_arbusto_m": 0.5,
    "limiar_arvore_m":  3.0,
    "exportar_dsm_dtm": True,
    "gerar_png":        True,
    "paleta_png":       "YlGn",
}
```

## Uso

```bash
python chm_de_lidar.py
```

## Qual resolução usar?

| Densidade da nuvem | Resolução recomendada |
|--------------------|----------------------|
| > 25 pts/m² | 0.25–0.5m |
| 5–25 pts/m² | 0.5–1.0m |
| 1–5 pts/m²  | 1.0–2.0m |
| < 1 pt/m²   | 2.0–5.0m |

## Limitações e DTM preciso

O DTM gerado pelo script usa o **retorno mais baixo por pixel**, o que funciona bem em áreas abertas mas pode subestimar o solo em florestas densas. Para maior precisão:

1. Use nuvens com classificação de pontos (campo `classification == 2` = solo).
2. Filtre apenas pontos de solo antes de construir o DTM:

```python
import laspy
with laspy.open("nuvem.las") as f:
    las = f.read()
solo = las.classification == 2
xs_solo, ys_solo, zs_solo = las.x[solo], las.y[solo], las.z[solo]
```

3. Interpole o DTM de solo com `scipy.interpolate.griddata`.
