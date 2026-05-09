#!/usr/bin/env python3
"""
RepoScope — Datensammlung & Benchmark-Berechnung
Valentina Gyan · Uni-Projekt · GitHub REST API

Berechnet Mittelwert UND Median der Top-N Repos (nach Stars).
Schreibt:
  data/top100_repos.json   — Rohdaten + Scores für beide Methoden
  data/benchmarks.json     — Statistische Kennzahlen
  data/analysis_report.md  — Markdown-Report

Verwendung:
  pip install requests
  export GITHUB_TOKEN=ghp_xxx   # empfohlen, sonst sehr langsam
  python collect_data.py [--n 100] [--output data/]
"""

import json, os, sys, time, math, statistics, argparse
from datetime import datetime, timezone
import requests

# ── Auth ─────────────────────────────────────────────────────────
TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"
API = "https://api.github.com"


# ── API helpers ───────────────────────────────────────────────────
def get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=20)
        except requests.RequestException as e:
            print(f"  Netzwerkfehler: {e}"); time.sleep(2); continue
        if r.status_code == 200: return r.json()
        if r.status_code == 202:
            print(f"  202 — berechne noch, warte…"); time.sleep(3); continue
        if r.status_code in (403, 429):
            wait = min(int(r.headers.get("X-RateLimit-Reset", time.time()+10)) - int(time.time()) + 2, 60)
            print(f"  Rate Limit — warte {wait}s"); time.sleep(wait); continue
        if r.status_code == 404: return None
        print(f"  HTTP {r.status_code} für {url}")
        return None
    return None


# ── Top-N Repos holen ─────────────────────────────────────────────
def fetch_top_repos(n):
    repos, page = [], 1
    while len(repos) < n:
        per = min(50, n - len(repos))
        r = requests.get(f"{API}/search/repositories",
            headers=HEADERS, timeout=20,
            params={"q":"stars:>5000 is:public archived:false","sort":"stars","order":"desc","per_page":per,"page":page})
        if r.status_code != 200:
            print(f"  Search API Fehler {r.status_code}"); break
        data = r.json().get("items", [])
        repos.extend(data)
        page += 1
        if len(data) < per: break
        time.sleep(1.5)
    return repos[:n]


# ── KPI-Berechnung für ein Repo ───────────────────────────────────
def calc_metrics(base, owner, name):
    b = f"{API}/repos/{owner}/{name}"
    activity     = get(f"{b}/stats/commit_activity")
    readme       = get(f"{b}/readme")
    contributing = get(f"{b}/contents/CONTRIBUTING.md")
    releases_raw = get(f"{b}/releases", {"per_page": 20})
    issues_raw   = get(f"{b}/issues",   {"state": "all", "per_page": 100})
    contribs_raw = get(f"{b}/contributors", {"per_page": 100})

    # Commits (letzte 30 Tage)
    commits30 = None
    if isinstance(activity, list) and len(activity) >= 4:
        commits30 = sum(w.get("total", 0) for w in activity[-4:])

    # Inaktivität
    pushed = base.get("pushed_at", "")
    days_inactive = max(0, int((time.time() - datetime.fromisoformat(pushed.replace("Z","+00:00")).timestamp()) / 86400)) if pushed else None

    # Contributors
    contrib_count = len([c for c in (contribs_raw or []) if c.get("type") == "User"])

    # Issues
    close_rate = avg_close = avg_comments = fehler_prod = None
    if isinstance(issues_raw, list) and issues_raw:
        real = [i for i in issues_raw if "pull_request" not in i]
        if real:
            closed = [i for i in real if i["state"] == "closed"]
            close_rate = len(closed) / len(real)
            times = [(datetime.fromisoformat(i["closed_at"].replace("Z","+00:00")) -
                      datetime.fromisoformat(i["created_at"].replace("Z","+00:00"))).days
                     for i in closed if i.get("closed_at") and i.get("created_at")]
            times = [t for t in times if t >= 0]
            avg_close    = statistics.mean(times) if times else None
            avg_comments = statistics.mean([i.get("comments", 0) for i in real])
            if commits30 and commits30 > 0:
                fehler_prod = len(closed) / commits30

    # Release-Frequenz
    rel_freq = None
    if isinstance(releases_raw, list):
        stable = sorted([r for r in releases_raw if not r.get("draft") and not r.get("prerelease") and r.get("published_at")],
                        key=lambda r: r["published_at"])
        if len(stable) >= 2:
            diffs = [(datetime.fromisoformat(stable[i+1]["published_at"].replace("Z","+00:00")) -
                      datetime.fromisoformat(stable[i]["published_at"].replace("Z","+00:00"))).days
                     for i in range(len(stable)-1)]
            rel_freq = statistics.mean(diffs) if diffs else None

    # Säule 3
    stars = base.get("stargazers_count", 0)
    forks = base.get("forks_count", 0)
    age   = max(1, int((time.time() - datetime.fromisoformat(base["created_at"].replace("Z","+00:00")).timestamp()) / 86400))
    fork_ratio   = forks / stars if stars > 0 else 0
    stars_tage   = stars / age
    readme_ok    = bool(readme)
    contrib_ok   = bool(contributing)
    doku         = (60 if readme_ok else 0) + (40 if contrib_ok else 0)

    return {
        "commits30":    commits30,
        "daysInactive": days_inactive,
        "contributors": contrib_count if contrib_count else None,
        "closeRate":    round(close_rate, 4) if close_rate is not None else None,
        "relFreq":      round(rel_freq, 2)   if rel_freq   is not None else None,
        "avgClose":     round(avg_close, 2)  if avg_close  is not None else None,
        "avgComments":  round(avg_comments, 2) if avg_comments is not None else None,
        "fehlerProd":   round(fehler_prod, 4) if fehler_prod is not None else None,
        "forkRatio":    round(fork_ratio, 4),
        "doku":         doku,
        "starsTage":    round(stars_tage, 3),
        "readmePresent":   readme_ok,
        "contribPresent":  contrib_ok,
    }


# ── Statistiken berechnen ─────────────────────────────────────────
def safe_vals(data, key):
    return [d[key] for d in data if d.get(key) is not None and math.isfinite(d[key])]

def stats(vals):
    if not vals: return {"mean": None, "median": None, "stdev": None, "p25": None, "p75": None}
    s = sorted(vals)
    n = len(s)
    m = n // 2
    med = s[m] if n % 2 else (s[m-1] + s[m]) / 2
    p25 = s[int(n * 0.25)]
    p75 = s[int(n * 0.75)]
    return {
        "mean":   round(statistics.mean(vals), 4),
        "median": round(med, 4),
        "stdev":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
        "p25":    round(p25, 4),
        "p75":    round(p75, 4),
    }


# ── Scoring ───────────────────────────────────────────────────────
KPI_DIRS = {
    "commits30":    "more", "daysInactive": "less",  "contributors": "more",
    "closeRate":    "more", "relFreq":      "less",  "avgClose":     "less",
    "avgComments":  "more", "fehlerProd":   "more",
    "forkRatio":    "more", "doku":         "bool",  "starsTage":    "log",
}
KPI_WEIGHTS = {
    "p1": {"commits30": .50, "daysInactive": .30, "contributors": .20},
    "p2": {"closeRate": .25, "relFreq": .25, "avgClose": .25, "avgComments": .15, "fehlerProd": .10},
    "p3": {"forkRatio": .35, "doku": .35, "starsTage": .30},
}
PILLAR_W = {"p1": .40, "p2": .35, "p3": .25}

def score_kpi(key, val, ref):
    if val is None or ref is None: return None
    d = KPI_DIRS.get(key)
    if d == "more":  return min(100, round(val / ref * 100)) if ref > 0 else None
    if d == "less":  return 100 if val == 0 else (min(100, round(ref / val * 100)) if ref > 0 else None)
    if d == "bool":  return val  # already 0-100
    if d == "log":
        if val <= 0 or ref <= 0: return None
        lv, lr = math.log10(val), math.log10(ref)
        return min(100, round(lv / lr * 100)) if lr > 0 else None
    return None

def score_repo(kpis, refs):
    def pillar(pid):
        w = KPI_WEIGHTS[pid]
        pts, wt = 0, 0
        for key, weight in w.items():
            s = score_kpi(key, kpis.get(key), refs.get(key))
            if s is not None: pts += s * weight; wt += weight
        return round(pts / wt) if wt > 0 else None
    p1, p2, p3 = pillar("p1"), pillar("p2"), pillar("p3")
    parts = [(s, w) for s, w in [(p1, .4), (p2, .35), (p3, .25)] if s is not None]
    total = round(sum(s*w for s,w in parts) / sum(w for _,w in parts)) if parts else None
    return {"p1": p1, "p2": p2, "p3": p3, "overall": total}


# ── Main ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--output", default="data/")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    print(f"=== RepoScope · Datensammlung ===")
    print(f"Token: {'✓' if TOKEN else '✗ (langsamer ohne Token)'}")
    print(f"Ziel: Top-{args.n} Repos · Output: {args.output}\n")

    # 1. Repos holen
    print(f"[1/4] Top-{args.n} Repos nach Stars laden…")
    repos = fetch_top_repos(args.n)
    print(f"  → {len(repos)} Repos gefunden\n")

    # 2. Metriken sammeln
    print(f"[2/4] Metriken für {len(repos)} Repos berechnen…")
    all_data = []
    for i, repo in enumerate(repos):
        owner, name = repo["owner"]["login"], repo["name"]
        print(f"  [{i+1:3d}/{len(repos)}] {owner}/{name}")
        try:
            kpis = calc_metrics(repo, owner, name)
            stars = repo["stargazers_count"]
            forks = repo["forks_count"]
            age   = max(1, int((time.time() - datetime.fromisoformat(repo["created_at"].replace("Z","+00:00")).timestamp()) / 86400))
            all_data.append({
                "rank": i + 1,
                "full_name":   repo["full_name"],
                "html_url":    repo["html_url"],
                "description": repo.get("description", ""),
                "language":    repo.get("language"),
                "license":     (repo.get("license") or {}).get("spdx_id") or (repo.get("license") or {}).get("name"),
                "stars": stars, "forks": forks,
                "open_issues": repo.get("open_issues_count", 0),
                "age_days": age, "created_at": repo["created_at"],
                "kpis": kpis,
            })
        except Exception as e:
            print(f"    FEHLER: {e}")
        time.sleep(0.15)

    # 3. Statistiken berechnen
    print(f"\n[3/4] Benchmark berechnen (Mittelwert + Median)…")
    kpi_keys = ["commits30","daysInactive","contributors","closeRate","relFreq","avgClose","avgComments","fehlerProd","forkRatio","starsTage"]
    benchmarks = {}
    means, medians = {}, {}
    for key in kpi_keys:
        vals = safe_vals([d["kpis"] for d in all_data], key)
        s = stats(vals)
        benchmarks[key] = s
        means[key]   = s["mean"]
        medians[key] = max(s["median"], 1) if key == "daysInactive" else s["median"]
        print(f"  {key:<20}: mean={s['mean']:.3f}, median={s['median']:.3f}" if s['mean'] else f"  {key:<20}: N/A")

    # 4. Repos scoren + ranken
    print(f"\n[4/4] Repos scoren und Dateien schreiben…")
    for repo in all_data:
        repo["scores_mean"]   = score_repo(repo["kpis"], means)
        repo["scores_median"] = score_repo(repo["kpis"], medians)

    # Nach Mittelwert-Score ranken
    all_data.sort(key=lambda x: (x["scores_mean"].get("overall") or 0), reverse=True)
    for i, r in enumerate(all_data): r["rank"] = i + 1

    # top100_repos.json
    out_repos = f"{args.output}top100_repos.json"
    with open(out_repos, "w") as f: json.dump(all_data, f, indent=2, default=str)
    print(f"  ✓ {out_repos}")

    # benchmarks.json
    lang_freq = {}
    for d in all_data:
        l = d.get("language")
        if l: lang_freq[l] = lang_freq.get(l, 0) + 1
    top_langs = sorted(lang_freq.items(), key=lambda x: -x[1])[:10]

    bm_out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size":  len(all_data),
        "means":   means,
        "medians": medians,
        "kpi_stats": benchmarks,
        "top_languages": top_langs,
    }
    out_bm = f"{args.output}benchmarks.json"
    with open(out_bm, "w") as f: json.dump(bm_out, f, indent=2, default=str)
    print(f"  ✓ {out_bm}")

    # analysis_report.md
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    scores_mean = [d["scores_mean"].get("overall") for d in all_data if d["scores_mean"].get("overall")]
    avg_score = round(sum(scores_mean)/len(scores_mean)) if scores_mean else 0
    top10 = all_data[:10]
    langs_md = "\n".join(f"| {l} | {c} |" for l,c in top_langs)
    top10_md = "\n".join(f"| {r['rank']} | [{r['full_name']}]({r['html_url']}) | {r['scores_mean'].get('overall','—')} | {r['stars']:,} | {r.get('language','—')} |" for r in top10)

    report = f"""# RepoScope — Top-{len(all_data)} Analyse

*Generiert: {now_str} · {len(all_data)} Repositories analysiert*

## Benchmark-Übersicht (Mittelwert vs. Median)

| Kennzahl | Mittelwert | Median |
|----------|:----------:|:------:|
""" + "\n".join(f"| {k:<25} | {means.get(k,0):.3f} | {medians.get(k,0):.3f} |" for k in kpi_keys) + f"""

## Top 10 nach Gesamt-Score (Mittelwert-Benchmark)

| Rang | Repository | Score | Stars | Sprache |
|-----:|-----------|------:|------:|---------|
{top10_md}

## Häufigste Programmiersprachen

| Sprache | Anzahl |
|---------|:------:|
{langs_md}

## Scoring-Methodik

| Säule | Gewicht | Kennzahlen |
|-------|--------:|------------|
| Aktivität & Community       | 40 % | Commits/30T, Tage inaktiv, Contributors |
| Reaktionsfähigkeit & Wartung | 35 % | Close-Rate, Release-Freq, Close-Zeit, Engagement, Fehlerbehebung |
| Reichweite & Dokumentation  | 25 % | Fork-Ratio, Dokumentation, Stars/Alter |

---
*Daten via GitHub REST API v3 — Valentina Gyan · Uni-Projekt*
"""
    out_rep = f"{args.output}analysis_report.md"
    with open(out_rep, "w") as f: f.write(report)
    print(f"  ✓ {out_rep}")

    print(f"\n✅ Fertig! {len(all_data)} Repos · Ø Score: {avg_score}")
    print(f"\nNächste Schritte:")
    print(f"  git add {args.output}*.json")
    print(f"  git commit -m 'data: update top-100 benchmarks'")
    print(f"  git push")

if __name__ == "__main__":
    main()
