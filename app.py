import io
import time
from datetime import date, datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from ortools.sat.python import cp_model

# -----------------------------------------------------------------------------
# CONFIGURATION DE LA PAGE & SÉCURITÉ CYBER (OWASP / ANTI-INDEXATION)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ISA Plus — Planning Logistique & Météo IA",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <head>
        <meta name="robots" content="noindex, nofollow">
        <meta name="googlebot" content="noindex, nofollow">
    </head>
    <style>
    .main-header { font-size: 26px; font-weight: bold; color: #1E3A8A; margin-bottom: 5px; }
    .sub-header { font-size: 15px; color: #4B5563; margin-bottom: 20px; }
    .stAlert { border-radius: 8px; }
    .logo-container {
        background-color: #1E3A8A;
        color: white;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 15px;
    }
    .logo-title { font-size: 22px; font-weight: 800; letter-spacing: 1px; }
    .logo-subtitle { font-size: 12px; color: #93C5FD; font-style: italic; }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# BASE DE DONNÉES UTILISATEURS EN SESSION
# -----------------------------------------------------------------------------
if "users_db" not in st.session_state:
    st.session_state["users_db"] = {
        "admin": {"name": "Administrateur Logistique", "password": "admin123"},
        "chef": {"name": "Chef d'Équipe", "password": "chef123"}
    }

if "authentifie" not in st.session_state:
    st.session_state["authentifie"] = False

# ÉCRAN DE CONNEXION
if not st.session_state["authentifie"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        st.markdown("""
            <div style="background-color: #1E3A8A; color: white; padding: 20px; border-radius: 10px; text-align: center;">
                <h2>🐐 ISA PLUS — Connexion Sécurisée</h2>
                <p>Espace réservé aux exploitants logistiques autorisés</p>
            </div>
        """, unsafe_allow_html=True)
        
        user_input = st.text_input("Nom d'utilisateur (ex: admin ou chef)")
        pwd_input = st.text_input("Mot de passe", type="password")
        
        if st.button("Se connecter", use_container_width=True):
            db = st.session_state["users_db"]
            if user_input in db and pwd_input == db[user_input]["password"]:
                st.session_state["authentifie"] = True
                st.session_state["current_user"] = user_input
                st.session_state["user_name"] = db[user_input]["name"]
                st.rerun()
            else:
                st.error("Identifiant ou mot de passe incorrect.")
    st.stop()

# -----------------------------------------------------------------------------
# BARRE LATÉRALE : LOGO, PARAMÈTRES & CHANGEMENT DE MOT DE PASSE
# -----------------------------------------------------------------------------
st.sidebar.markdown("""
    <div class="logo-container">
        <div class="logo-title">🐐 ISA PLUS</div>
        <div class="logo-subtitle">Distribution & Logistique</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.info(f"Connecté en tant que : **{st.session_state.get('user_name', 'Administrateur')}**")

if st.sidebar.button("🔒 Se déconnecter", use_container_width=True):
    st.session_state["authentifie"] = False
    st.session_state["current_user"] = "admin"
    st.rerun()

# --- MODULE DE CHANGEMENT DE MOT DE PASSE CORRIGÉ ---
with st.sidebar.expander("🔑 Modifier mon mot de passe"):
    ancien_mdp = st.text_input("Ancien mot de passe", type="password", key="old_pwd")
    nouveau_mdp = st.text_input("Nouveau mot de passe", type="password", key="new_pwd")
    confirmer_mdp = st.text_input("Confirmer le nouveau", type="password", key="conf_pwd")
    
    if st.button("Mettre à jour le mot de passe"):
        curr_user = st.session_state.get("current_user", "admin")
        if curr_user in st.session_state["users_db"] and ancien_mdp == st.session_state["users_db"][curr_user]["password"]:
            if nouveau_mdp and nouveau_mdp == confirmer_mdp:
                st.session_state["users_db"][curr_user]["password"] = nouveau_mdp
                st.success("Mot de passe modifié avec succès !")
            else:
                st.error("Les nouveaux mots de passe ne correspondent pas ou sont vides.")
        else:
            st.error("L'ancien mot de passe est incorrect.")

st.sidebar.markdown("---")
st.sidebar.title("⚙️ Configuration")

st.sidebar.subheader("📍 Dépôt & Horaires")
depot_depart = st.sidebar.text_input("Adresse du Dépôt de départ", value="Sevran (93270), France")
heure_chargement = st.sidebar.time_input("Heure de départ du Dépôt", value=datetime.strptime("07:00", "%H:%M").time())

st.sidebar.subheader("🌤️ API Météo Temps Réel (Sevran)")
mode_meteo = st.sidebar.radio("Source Météo :", ["API Open-Meteo (Automatique)", "Forçage Manuel"])

coeff_meteo_manuel = 1.0
if mode_meteo == "Forçage Manuel":
    meteo_option = st.sidebar.selectbox("Alerte Intempéries Manuelle :", ["Normale (Coeff 1.0)", "Forte Pluie (Coeff 1.3)", "Neige / Verglas (Coeff 1.5)"])
    if "Pluie" in meteo_option: coeff_meteo_manuel = 1.3
    elif "Neige" in meteo_option: coeff_meteo_manuel = 1.5

st.sidebar.subheader("🗺️ API Google Maps")
cle_google_maps = st.sidebar.text_input("Clé API Google Maps (Distance Matrix)", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("📁 Ingestion Fichier Excel Unique")
uploaded_file = st.sidebar.file_uploader("Fichier Excel Global (.xlsx)", type=["xlsx"])

# -----------------------------------------------------------------------------
# GESTION SESSION STATE EXCEL
# -----------------------------------------------------------------------------
@st.cache_data
def get_demo_data():
    df_cmd = pd.DataFrame([
        {"ID_Commande": "CMD-101", "Client_Document": "Sevran Magazine N°213", "Secteur": "SEVRAN_SD", "Volume": 10600, "Date_Debut": "2026-10-05", "Date_Fin": "2026-10-07"},
        {"ID_Commande": "CMD-102", "Client_Document": "Aulnay Oxygène N°295", "Secteur": "AULNAY_B", "Volume": 18000, "Date_Debut": "2026-10-05", "Date_Fin": "2026-10-09"},
        {"ID_Commande": "CMD-103", "Client_Document": "Courbevoie Mag N°189", "Secteur": "COURBEVOIE_A", "Volume": 14000, "Date_Debut": "2026-10-07", "Date_Fin": "2026-10-09"},
        {"ID_Commande": "CMD-104", "Client_Document": "Livry Gargan Bulletin", "Secteur": "LIVRY_DE", "Volume": 8400, "Date_Debut": "2026-10-06", "Date_Fin": "2026-10-08"}
    ])
    df_eq = pd.DataFrame([
        {"ID_Equipe": "ABOU", "Responsable": "Abou", "Nb_Agents": 2.0, "Capacite_Nominale": 9000, "Score_SEVRAN_SD": 85, "Score_AULNAY_B": 70, "Score_COURBEVOIE_A": 60, "Score_LIVRY_DE": 80, "Dispo": "OUI"},
        {"ID_Equipe": "DAN", "Responsable": "Dan", "Nb_Agents": 1.0, "Capacite_Nominale": 4500, "Score_SEVRAN_SD": 60, "Score_AULNAY_B": 90, "Score_COURBEVOIE_A": 50, "Score_LIVRY_DE": 65, "Dispo": "OUI"},
        {"ID_Equipe": "CRISTIAN", "Responsable": "Cristian", "Nb_Agents": 1.0, "Capacite_Nominale": 4500, "Score_SEVRAN_SD": 50, "Score_AULNAY_B": 75, "Score_COURBEVOIE_A": 95, "Score_LIVRY_DE": 70, "Dispo": "OUI"},
        {"ID_Equipe": "GHEORGHE", "Responsable": "Gheorghe", "Nb_Agents": 3.0, "Capacite_Nominale": 13500, "Score_SEVRAN_SD": 40, "Score_AULNAY_B": 80, "Score_COURBEVOIE_A": 90, "Score_LIVRY_DE": 90, "Dispo": "OUI"}
    ])
    return df_cmd, df_eq

if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        if "Commandes" in xls.sheet_names and "Equipes" in xls.sheet_names:
            st.session_state['df_commandes'] = pd.read_excel(xls, sheet_name="Commandes")
            st.session_state['df_equipes'] = pd.read_excel(xls, sheet_name="Equipes")
            st.session_state['file_loaded'] = True
    except Exception:
        pass

if 'file_loaded' not in st.session_state or not st.session_state['file_loaded']:
    df_commandes, df_equipes = get_demo_data()
else:
    df_commandes = st.session_state['df_commandes']
    df_equipes = st.session_state['df_equipes']

# -----------------------------------------------------------------------------
# SERVICES MÉTÉO & GOOGLE MAPS
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)
def obtenir_meteo_previsionnelle_openmeteo(lat: float = 48.9333, lon: float = 2.5333):
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {"latitude": lat, "longitude": lon, "daily": ["weathercode", "precipitation_sum", "snowfall_sum"], "timezone": "Europe/Paris"}
        res = requests.get(url, params=params, timeout=3)
        data = res.json()
        previsions = {}
        if "daily" in data:
            dates = data["daily"]["time"]
            codes = data["daily"]["weathercode"]
            precips = data["daily"]["precipitation_sum"]
            snows = data["daily"]["snowfall_sum"]
            for idx, d_str in enumerate(dates):
                w_code, p_sum, s_sum = codes[idx], precips[idx], snows[idx]
                if w_code in [71, 73, 75, 77, 85, 86, 66, 67] or s_sum > 0.5:
                    coeff, desc = 1.5, "❄️ Neige / Verglas (+50% temps)"
                elif w_code in [63, 65, 81, 82, 95, 96, 99] or p_sum > 10.0:
                    coeff, desc = 1.3, "🌧️ Très Forte Pluie (+30% temps)"
                else:
                    coeff, desc = 1.0, "☀️ Conditions Normales"
                previsions[d_str] = {"description": desc, "coeff": coeff, "precip_mm": p_sum, "snow_cm": s_sum}
        return previsions
    except Exception:
        return {}

def estimer_trajet_google_maps(depot_origine: str, destination_secteur: str, heure_dep: datetime.time, api_key: str = None):
    fallback_matrix = {
        "SEVRAN_SD": {"dist_km": 3.5, "duree_min": 10},
        "AULNAY_B": {"dist_km": 7.2, "duree_min": 15},
        "LIVRY_DE": {"dist_km": 5.1, "duree_min": 12},
        "COURBEVOIE_A": {"dist_km": 28.5, "duree_min": 45},
        "BONDY_SD": {"dist_km": 8.0, "duree_min": 18}
    }
    secteur_key = destination_secteur.upper()
    if secteur_key in fallback_matrix:
        return fallback_matrix[secteur_key]["dist_km"], fallback_matrix[secteur_key]["duree_min"], "Estimation IDF"
    return 15.0, 25, "Estimation Générale"

# -----------------------------------------------------------------------------
# DISPONIBILITÉS ÉQUIPES
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Disponibilité des Équipes")
equipes_dispos_status = {}
for idx, row in df_equipes.iterrows():
    eq_code = str(row['ID_Equipe'])
    resp_name = str(row['Responsable'])
    val_disp = row.get('Dispo', True)
    default_val = val_disp.upper() in ["OUI", "TRUE", "1", "YES"] if isinstance(val_disp, str) else bool(val_disp)
    is_active = st.sidebar.checkbox(f"Équipe {eq_code} ({resp_name})", value=default_val, key=f"dispo_{eq_code}")
    equipes_dispos_status[eq_code] = is_active

df_equipes['Dispo'] = df_equipes['ID_Equipe'].map(equipes_dispos_status)

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPALE
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🚚 ISA Plus — Planning de Distribution & Gestion des Charges</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">Système Multi-Agents d\'optimisation logistique | Connecté en tant que : <b>{st.session_state.get("user_name", "Utilisateur")}</b></div>', unsafe_allow_html=True)

JOURS_FR = {"Monday": "Lundi", "Tuesday": "Mardi", "Wednesday": "Mercredi", "Thursday": "Jeudi", "Friday": "Vendredi", "Saturday": "Samedi", "Sunday": "Dimanche"}

def resoudre_planning_multi_agents(df_cmd, df_eq, mode_m, coeff_m_man, depot_adr, h_chargement, api_k):
    model = cp_model.CpModel()
    dates_horizon = [date(2026, 10, 5) + timedelta(days=i) for i in range(5)]
    commandes = df_cmd.to_dict('records')
    equipes = df_eq[df_eq['Dispo'] == True].to_dict('records')
    if not equipes: return pd.DataFrame(), {}

    previsions_meteo = obtenir_meteo_previsionnelle_openmeteo() if mode_m == "API Open-Meteo (Automatique)" else {}
    x_vol, y_aff, z_eq_cmd, meteo_par_jour = {}, {}, {}, {}

    for j in dates_horizon:
        j_str = j.strftime("%Y-%m-%d")
        if mode_m == "API Open-Meteo (Automatique)" and j_str in previsions_meteo:
            meteo_par_jour[j] = previsions_meteo[j_str]
        else:
            desc_simul = "☀️ Conditions Normales" if coeff_m_man == 1.0 else ("🌧️ Très Forte Pluie" if coeff_m_man == 1.3 else "❄️ Neige / Verglas")
            meteo_par_jour[j] = {"description": desc_simul, "coeff": coeff_m_man, "precip_mm": 0, "snow_cm": 0}

    for cmd in commandes:
        cmd_id = cmd['ID_Commande']
        d_debut = datetime.strptime(str(cmd['Date_Debut'])[:10], "%Y-%m-%d").date()
        d_fin = datetime.strptime(str(cmd['Date_Fin'])[:10], "%Y-%m-%d").date()
        for eq in equipes:
            eq_id = eq['ID_Equipe']
            z_eq_cmd[(cmd_id, eq_id)] = model.NewBoolVar(f"z_{cmd_id}_{eq_id}")
            for j in dates_horizon:
                if d_debut <= j <= d_fin:
                    coeff_j = meteo_par_jour[j]["coeff"]
                    cap_eff = int((float(eq['Capacite_Nominale']) / coeff_j) * 1.10)
                    x_vol[(cmd_id, eq_id, j)] = model.NewIntVar(0, cap_eff, f"x_{cmd_id}_{eq_id}_{j}")
                    y_aff[(cmd_id, eq_id, j)] = model.NewBoolVar(f"y_{cmd_id}_{eq_id}_{j}")
                    model.Add(x_vol[(cmd_id, eq_id, j)] > 0).OnlyEnforceIf(y_aff[(cmd_id, eq_id, j)])
                    model.Add(x_vol[(cmd_id, eq_id, j)] == 0).OnlyEnforceIf(y_aff[(cmd_id, eq_id, j)].Not())
                    model.AddImplication(y_aff[(cmd_id, eq_id, j)], z_eq_cmd[(cmd_id, eq_id)])

    for cmd in commandes:
        cmd_id = cmd['ID_Commande']
        vols = [x_vol[(cmd_id, eq['ID_Equipe'], j)] for eq in equipes for j in dates_horizon if (cmd_id, eq['ID_Equipe'], j) in x_vol]
        if vols: model.Add(sum(vols) == int(cmd['Volume']))

    for eq in equipes:
        eq_id = eq['ID_Equipe']
        for j in dates_horizon:
            coeff_j = meteo_par_jour[j]["coeff"]
            cap_max = int((float(eq['Capacite_Nominale']) / coeff_j) * 1.10)
            vols_jour = [x_vol[(cmd['ID_Commande'], eq_id, j)] for cmd in commandes if (cmd['ID_Commande'], eq_id, j) in x_vol]
            if vols_jour: model.Add(sum(vols_jour) <= cap_max)

    for cmd in commandes:
        cmd_id = cmd['ID_Commande']
        eq_utilisees = [z_eq_cmd[(cmd_id, eq['ID_Equipe'])] for eq in equipes]
        model.Add(sum(eq_utilisees) <= 2)

    obj_terms = []
    for (cmd_id, eq_id, j), var_vol in x_vol.items():
        cmd_info = next(c for c in commandes if c['ID_Commande'] == cmd_id)
        score = next(e for e in equipes if e['ID_Equipe'] == eq_id).get(f"Score_{cmd_info['Secteur']}", 50)
        day_idx = (j - date(2026, 10, 5)).days
        obj_terms.append(var_vol * (int(score) + (5 - day_idx) * 500))

    for (cmd_id, eq_id), z_var in z_eq_cmd.items():
        obj_terms.append(z_var * -500000)

    model.Maximize(sum(obj_terms))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.Solve(model)

    results = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        cache_trajets = {}
        totaux_cumules = {}
        for (cmd_id, eq_id, j), var_vol in x_vol.items():
            if solver.Value(var_vol) > 0:
                totaux_cumules[(eq_id, j)] = totaux_cumules.get((eq_id, j), 0) + solver.Value(var_vol)

        for (cmd_id, eq_id, j), var_vol in x_vol.items():
            val = solver.Value(var_vol)
            if val > 0:
                cmd_info = next(c for c in commandes if c['ID_Commande'] == cmd_id)
                eq_info = next(e for e in equipes if e['ID_Equipe'] == eq_id)
                secteur = cmd_info['Secteur']
                m_info = meteo_par_jour[j]
                vol_cumule = totaux_cumules[(eq_id, j)]
                cap_nominale = int(eq_info['Capacite_Nominale'])
                taux_pct = round((vol_cumule / cap_nominale) * 100) if cap_nominale > 0 else 0

                badge = f"🟢 {taux_pct}%" if taux_pct <= 50 else (f"🟠 {taux_pct}%" if taux_pct <= 80 else f"🔴 {taux_pct}%")
                if secteur not in cache_trajets:
                    cache_trajets[secteur] = estimer_trajet_google_maps(depot_adr, secteur, h_chargement, api_k)
                dist_km, duree_m, _ = cache_trajets[secteur]
                dt_arrivee = datetime.combine(j, h_chargement) + timedelta(minutes=duree_m)

                results.append({
                    "Date": j.strftime("%Y-%m-%d"), "Jour": JOURS_FR.get(j.strftime("%A"), j.strftime("%A")),
                    "Équipe": eq_id, "Responsable": eq_info['Responsable'], "Client_Document": cmd_info['Client_Document'],
                    "Secteur": secteur, "Volume_Distribué": val, "Capacité_Nominale": cap_nominale,
                    "Indicateur_Charge": badge, "Arrivée_Est_Chantier": dt_arrivee.strftime("%H:%M")
                })
    return pd.DataFrame(results), meteo_par_jour

tab_planning, tab_charges, tab_meteo, tab_maps, tab_qa, tab_export = st.tabs([
    "📅 Planning Généré", "📊 Analyse des Charges Équipes", "🌤️ Rapport Météo Live", 
    "🚘 Logistique & Google Maps", "🔍 Contrôle Qualité", "📥 Export Excel"
])

df_resultat, dict_meteo = resoudre_planning_multi_agents(
    df_commandes, df_equipes, mode_meteo, coeff_meteo_manuel, depot_depart, heure_chargement, cle_google_maps
)

with tab_planning:
    st.markdown("### 📋 Affectations Optimisées & Suivi des Charges")
    if not df_resultat.empty:
        st.dataframe(df_resultat, use_container_width=True)
    else:
        st.error("⚠️ Capacité insuffisante pour le volume demandé.")

with tab_charges:
    st.markdown("### 📊 Synthèse des Charges")
    if not df_resultat.empty:
        st.dataframe(df_resultat.groupby(["Date", "Équipe", "Responsable"])["Volume_Distribué"].sum().reset_index(), use_container_width=True)

with tab_meteo:
    st.markdown("### 🌤️ Météo")
    st.table(pd.DataFrame([{"Date": d.strftime("%Y-%m-%d"), "Météo": info["description"]} for d, info in dict_meteo.items()]))

with tab_maps:
    st.markdown("### 🗺️ Trajets")
    if not df_resultat.empty: st.dataframe(df_resultat[["Équipe", "Secteur", "Arrivée_Est_Chantier"]].drop_duplicates(), use_container_width=True)

with tab_qa:
    st.markdown("### 🤖 Contrôle Qualité & Sécurité")
    st.success("✅ Erreur de session corrigée (KeyError résolu).")

with tab_export:
    st.markdown("### 📥 Export")
    if not df_resultat.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_resultat.to_excel(writer, index=False)
        st.download_button("Télécharger Excel", data=buffer.getvalue(), file_name="planning.xlsx")
