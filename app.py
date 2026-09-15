"""
Fit Money Rule Check — Moteur de décision
Principe non-négociable : le gate Python décide (garde/coupe/remplace).
Le LLM ne décide jamais — il formule la phrase finale à partir d'un
payload JSON strict produit par le gate.
"""

import os
import json
from flask import Flask, request, jsonify, render_template
import requests

app = Flask(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ---------------------------------------------------------------------------
# ÉTAT EN MÉMOIRE — pas de DB, MVP hackathon
# ---------------------------------------------------------------------------

USER_STATE = {
    "budget_mensuel_total": 2000.0,
    "seuils_categorie": {
        "bouffe": 500.0,
        "sorties": 200.0,
        "shopping": 250.0,
        "abonnements": 100.0,
        "transport": 150.0,
        "autre": 150.0,
    },
    "depenses": [],  # liste de {item, montant, categorie, type}
}


# ---------------------------------------------------------------------------
# ÉTAPE A — GATE DÉTERMINISTE (jamais de LLM ici)
# ---------------------------------------------------------------------------

def evaluer_depense(item: str, montant: float, categorie: str, type_depense: str) -> dict:
    budget_total = USER_STATE["budget_mensuel_total"]
    seuil = USER_STATE["seuils_categorie"].get(categorie, 150.0)

    total_categorie = sum(
        d["montant"] for d in USER_STATE["depenses"] if d["categorie"] == categorie
    )

    # R1 — garde-fou dérapage majeur, peu importe catégorie/type
    if montant > 0.15 * budget_total:
        return {
            "status": "BLOCK_CRITICAL",
            "raison": "montant_disproportionne",
            "item": item,
            "montant": montant,
            "categorie": categorie,
            "pct_categorie": round((total_categorie + montant) / seuil, 2),
            "reste_dispo": round(seuil - total_categorie, 2),
        }

    pct_apres = (total_categorie + montant) / seuil

    # R2 — plafond catégorie dépassé
    if pct_apres > 1.0:
        status = "BLOCK_CRITICAL"
    # R3 — impulsive + zone à risque (>80% du seuil)
    elif pct_apres > 0.8 and type_depense == "impulsive":
        status = "WARNING_IMPULSIVE"
    # R4/R5 — planifiée ou marge confortable
    else:
        status = "ALLOW"

    return {
        "status": status,
        "raison": f"pct_categorie_{round(pct_apres * 100)}",
        "item": item,
        "montant": montant,
        "categorie": categorie,
        "pct_categorie": round(pct_apres, 2),
        "reste_dispo": round(seuil - total_categorie, 2),
    }


# ---------------------------------------------------------------------------
# ÉTAPE B — LLM EN RENFORT (formulation uniquement, JAMAIS la décision)
# ---------------------------------------------------------------------------

DECISION_TO_LABEL = {
    "ALLOW": "GARDE",
    "WARNING_IMPULSIVE": "REMPLACE",
    "BLOCK_CRITICAL": "COUPE",
}

SYSTEM_PROMPT = (
    "Tu formules UNE phrase courte de discipline personnelle en français, "
    "basée STRICTEMENT sur le JSON fourni. Interdiction d'inventer des chiffres "
    "ou de changer la décision. Ne jamais utiliser les mots 'conseil financier' "
    "ou 'recommandation financière' — utilise 'règle personnelle' ou 'discipline'. "
    "Si status=WARNING_IMPULSIVE, propose une alternative concrète moins chère. "
    "Réponds uniquement avec la phrase, rien d'autre."
)


def formuler_phrase(gate_result: dict) -> str:
    label = DECISION_TO_LABEL[gate_result["status"]]

    # ALLOW = zéro appel LLM (économie tokens + latence + preuve du gate)
    if gate_result["status"] == "ALLOW":
        return f"Garde. {gate_result['item']} reste sous ta règle pour {gate_result['categorie']} (reste {gate_result['reste_dispo']}$)."

    if not ANTHROPIC_API_KEY:
        return _fallback_branded(gate_result, label)

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 100,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": json.dumps(gate_result, ensure_ascii=False)}
        ],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=8)
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip()
        return text
    except Exception:
        return _fallback_branded(gate_result, label)


def _fallback_branded(gate_result: dict, label: str) -> str:
    """
    Templates déterministes, pré-écrits, 100% fiables (pas de dépendance réseau).
    C'est le chemin PRINCIPAL de démo — pas un plan B honteux.
    """
    item = gate_result["item"]
    montant = gate_result["montant"]
    pct = int(gate_result["pct_categorie"] * 100)
    reste = gate_result["reste_dispo"]

    if gate_result["status"] == "WARNING_IMPULSIVE":
        return (
            f"REMPLACE. {item} à {montant}$ te met à {pct}% de ta règle "
            f"(il reste {reste}$ de marge). Attends 48h. Si tu la veux encore, "
            f"trouve une version d'occasion en dessous de {round(montant * 0.6)}$."
        )

    if gate_result["status"] == "BLOCK_CRITICAL":
        return (
            f"COUPE. {item} à {montant}$ dépasse ta règle de {pct}%. "
            f"Zéro exception. Annule, ou réalloue depuis une autre catégorie avant de valider."
        )

    return f"{label}. {item} ({montant}$) reste dans ta règle."


# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json()
    item = data.get("item", "").strip() or "dépense"
    montant = float(data.get("montant", 0))
    categorie = data.get("categorie", "autre")
    type_depense = data.get("type", "planifiee")

    gate_result = evaluer_depense(item, montant, categorie, type_depense)
    phrase = formuler_phrase(gate_result)

    # On enregistre seulement si la décision finale n'est pas un blocage critique
    if gate_result["status"] != "BLOCK_CRITICAL":
        USER_STATE["depenses"].append(
            {"item": item, "montant": montant, "categorie": categorie, "type": type_depense}
        )

    return jsonify(
        {
            "decision": DECISION_TO_LABEL[gate_result["status"]],
            "phrase": phrase,
            "gate": gate_result,  # transparence totale pour la démo/juges
        }
    )


@app.route("/reset", methods=["POST"])
def reset():
    USER_STATE["depenses"] = []
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
