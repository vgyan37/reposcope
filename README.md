# RepoScope — GitHub Repository Quality Analyzer

Uni-Projekt: Bewertung von Open-Source-Projekten anhand der GitHub REST API.
Valentina Gyan · 3-Säulen-Scoring · Mittelwert UND Median-Benchmark

## Projektstruktur

```
reposcope/
├── index_mittelwert.html  ← Analyzer (Mittelwert-Benchmark)
├── index_median.html      ← Analyzer (Median-Benchmark)
├── analysis.html          ← Top-100 Vergleichstabelle
├── collect_data.py        ← Datensammlung (Python)
├── requirements.txt       ← Python-Abhängigkeiten
└── data/
    ├── top100_repos.json  ← (generiert) Rohdaten + Scores
    └── benchmarks.json    ← (generiert) Mittelwert & Median
```

## Schnellstart

### 1. Daten sammeln
```bash
pip install requests
export GITHUB_TOKEN=ghp_xxx    # empfohlen
python collect_data.py --n 100
```

### 2. GitHub Pages aktivieren
Settings → Pages → Branch: `main` → Save

### 3. URLs
```
https://vgyan37.github.io/reposcope/index_mittelwert.html
https://vgyan37.github.io/reposcope/index_median.html
https://vgyan37.github.io/reposcope/analysis.html
```

## Scoring-Methodik (3 Säulen)

| Säule | Gewicht | Kennzahlen |
|-------|--------:|------------|
| ⚡ Aktivität & Community       | 40 % | Commits/30T (50%), Tage inaktiv (30%), Contributors (20%) |
| 🔧 Reaktionsfähigkeit & Wartung | 35 % | Close-Rate (25%), Release-Abstand (25%), Close-Zeit (25%), Engagement (15%), Fehlerbehebung (10%) |
| 📡 Reichweite & Dokumentation  | 25 % | Fork-Ratio (35%), Dokumentation (35%), Stars/Alter log (30%) |

### Scoring-Formel

```
Mehr ist besser:   Score = min(100,  Wert / Benchmark × 100)
Weniger ist besser: Score = min(100,  Benchmark / Wert × 100)
Dokumentation:     README vorhanden → 60 Pkt. + CONTRIBUTING → 40 Pkt.
Stars/Alter:       min(100, log10(Wert) / log10(Benchmark) × 100)
```

### Benchmark-Methoden
- **Mittelwert**: Arithmetisches Mittel der Top-N Repos — sensitiver für Ausreißer
- **Median**: Mittlerer Wert der Top-N Repos — robuster gegen Extremwerte

## Verwendete API-Endpunkte

| Endpunkt | KPIs |
|----------|------|
| `GET /repos/{owner}/{repo}` | Stars, Forks, Alter |
| `GET /repos/{owner}/{repo}/stats/commit_activity` | Commits/30T |
| `GET /repos/{owner}/{repo}/readme` | README |
| `GET /repos/{owner}/{repo}/contents/CONTRIBUTING.md` | CONTRIBUTING |
| `GET /repos/{owner}/{repo}/releases` | Release-Frequenz |
| `GET /repos/{owner}/{repo}/issues?state=all` | Close-Rate, Close-Zeit, Engagement |
| `GET /repos/{owner}/{repo}/contributors` | Contributor-Anzahl |
| `GET /search/repositories` | Top-N Suche |

## Rate-Limits

| Situation | Limit |
|-----------|-------|
| Ohne Token | 60 Req/h |
| Mit Token  | 5.000 Req/h |

Token erstellen: https://github.com/settings/tokens (Scope: `public_repo`)

---
*Valentina Gyan · Uni-Projekt Softwaretechnik · GitHub REST API v3*
