# Fit Money Rule Check

**1 dépense → 1 règle. En une phrase.**

*by Fit Money Circle — AI Builders Hackathon 2026*

---

## Le problème

Les apps de finances personnelles pilotées par IA ratent l'essentiel : elles génèrent des dashboards que personne ne relit, et laissent le LLM décider si une dépense est "raisonnable" — un LLM ne calcule pas de façon fiable et invente des seuils.

## La solution

Tu tapes une dépense (item, montant, catégorie, planifiée ou impulsive). Un moteur Python **déterministe** calcule ta position réelle par rapport à tes seuils déclarés. L'IA n'intervient **jamais** dans la décision — elle formule uniquement la phrase finale, à partir d'un payload JSON strict produit par le gate.

```
Input utilisateur → Contexte récupéré (dépenses du mois, seuils) → Gate Python (décision) → LLM (formulation) → 1 phrase
```

Pas de dashboard. Pas de rapport mensuel. La discipline se joue dans l'instant de la tentation.

## Pourquoi ce n'est pas un wrapper IA

- La décision (**GARDE / REMPLACE / COUPE**) est calculée par des règles Python explicites (seuils par catégorie, plafond global), jamais par un prompt.
- Si la dépense est autorisée (`ALLOW`), l'app répond **instantanément, sans appel API** — zéro latence, zéro token dépensé.
- Le LLM ne reçoit qu'un JSON strict (`status`, `pct_categorie`, `reste_dispo`) et n'a pas le droit d'inventer de chiffres.

## Logique de décision

| Règle | Condition | Résultat |
|---|---|---|
| R1 | Dépense > 15 % du budget total mensuel | `BLOCK_CRITICAL` (COUPE) |
| R2 | Dépenses catégorie + montant > seuil catégorie | `BLOCK_CRITICAL` (COUPE) |
| R3 | > 80 % du seuil catégorie **et** dépense impulsive | `WARNING_IMPULSIVE` (REMPLACE) |
| R4 | Sinon | `ALLOW` (GARDE) |

## Installation

```bash
git clone https://github.com/Mister-Phil/fit-money-rule-check.git
cd fit-money-rule-check
pip install -r requirements.txt
export ANTHROPIC_API_KEY=ta_clé   # optionnel — l'app fonctionne sans (fallback déterministe)
python app.py
```

→ ouvre `http://127.0.0.1:5000`

## Stack

Flask (Python) · JS/HTML vanilla · Anthropic API (Claude) en renfort de formulation

## Avertissement

Ceci n'est pas un conseil financier réglementé. C'est une méthodologie de discipline personnelle.

## Roadmap

- Saisie par photo du reçu (OCR/Vision)
- Persistance multi-session
- API publique (B2A-ready) pour intégration tierce
