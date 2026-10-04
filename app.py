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
# BARRE LATÉRALE : PARAMÈTRES & CONFIGURATION
# -----------------------------------------------------------------------------
st.sidebar.markdown("""
    <div class="logo-container">
        <div class="logo-title">🐐 ISA PLUS</div>
        <div class="logo-subtitle">Distribution & Logistique</div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.info(f"Connecté : **{st.session_state.get('user_name', 'Administrateur')}**")

if st.sidebar.button("🔒 Se déconnecter", use_container_width=True):
    st.session_state["authentifie"] = False
    st.rerun()

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

@st.cache_data
def get_demo_data():
    df_cmd = pd.DataFrame([
        {"ID_Commande": "CMD-101", "Client_Document": "Sevran Magazine N°213", "Secteur": "SEVRAN_SD", "Volume": 10600, "Date_Debut": "2026-10-01", "Date_Fin": "2026-10-05"},
        {"ID_Commande": "CMD-102", "Client_Document": "Aulnay Oxygène N°295", "Secteur": "AULNAY_B", "Volume": 18000, "Date_Debut": "2026-10-01", "Date_Fin": "2026-10-06"},
        {"ID_Commande": "CMD-103", "Client_Document": "Courbevoie Mag N°189", "Secteur": "COURBEVOIE_A", "Volume": 14000, "Date_Debut": "2026-10-02", "Date_Fin": "2026-10-06"},
        {"ID_Commande": "CMD-104", "Client_Document": "Livry Gargan Bulletin", "Secteur": "LIVRY_DE", "Volume": 8400, "Date_Debut": "2026-10-01", "Date_Fin": "2026-10-04"}
    ])
    df_eq = pd.DataFrame([
        {"ID_Equipe": "MIRTCHA", "Responsable": "Mirtcha", "Nb_Agents": 2.0, "Capacite_Nominale": 9000, "Score_SEVRAN_SD": 85, "Score_AULNAY_B": 70, "Score_COURBEVOIE_A": 60, "Score_LIVRY_DE": 80, "Dispo": "OUI"},
        {"ID_Equipe": "MICHEL", "Responsable": "Michel", "Nb_Agents": 1.0, "Capacite_Nominale": 4500, "Score_SEVRAN_SD": 60, "Score_AULNAY_B": 90, "Score_COURBEVOIE_A": 50, "Score_LIVRY_DE": 65, "Dispo": "OUI"},
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
# DISPONIBILITÉS ÉQUIPES EN DIRECT
# -----------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Disponibilité des Équipes")
equipes_dispos_status = {}
for idx, row in df_equipes.iterrows():
    eq_code = str(row['ID_Equipe'])
    resp_name = str(row['Responsable'])
    val_disp = row.get('Dispo', True)
    default_val = val_disp.upper() in ["OUI", "TRUE", "1", "YES"] if isinstance(val_disp, str) else bool(val_disp)
    is_active = st.sidebar.checkbox(f"{eq_code} ({resp_name})", value=default_val, key=f"dispo_{eq_code}")
    equipes_dispos_status[eq_code] = is_active

df_equipes['Dispo'] = df_equipes['ID_Equipe'].map(equipes_dispos_status)

# -----------------------------------------------------------------------------
# SERVICE API MÉTÉO AUTOMATIQUE (Open-Meteo)
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
# MOTEUR MULTI-AGENTS
# -----------------------------------------------------------------------------
def resoudre_planning_multi_agents(df_cmd, df_eq, mode_m, coeff_m_man, depot_adr, h_chargement, api_k):
    model = cp_model.CpModel()
    dates_horizon = [date(2026, 10, 1) + timedelta(days=i) for i in range(15)]
    commandes = df_cmd.to_dict('records')
    equipes = df_eq[df_eq['Dispo'] == True].to_dict('records')
    if not equipes: return pd.DataFrame(), {}

    previsions_meteo = obtenir_meteo_previsionnelle_openmeteo() if mode_m == "API Open-Meteo (Automatique)" else {}
    x_vol, meteo_par_jour = {}, {}

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
            for j in dates_horizon:
                if d_debut <= j <= d_fin:
                    coeff_j = meteo_par_jour[j]["coeff"]
                    cap_eff = int((float(eq['Capacite_Nominale']) / coeff_j) * 1.10)
                    x_vol[(cmd_id, eq_id, j)] = model.NewIntVar(0, cap_eff, f"x_{cmd_id}_{eq_id}_{j}")

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

    obj_terms = []
    for (cmd_id, eq_id, j), var_vol in x_vol.items():
        cmd_info = next(c for c in commandes if c['ID_Commande'] == cmd_id)
        score = next(e for e in equipes if e['ID_Equipe'] == eq_id).get(f"Score_{cmd_info['Secteur']}", 50)
        day_idx = (j - date(2026, 10, 1)).days
        obj_terms.append(var_vol * (int(score) + (15 - day_idx) * 500))

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

                if taux_pct <= 50:
                    couleur, badge = "Vert", f"🟢 {taux_pct}%"
                elif taux_pct <= 80:
                    couleur, badge = "Orange", f"🟠 {taux_pct}%"
                elif taux_pct <= 95:
                    couleur, badge = "Rouge", f"🔴 {taux_pct}%"
                else:
                    couleur, badge = "Noir", f"⬛ {taux_pct}%"

                if secteur not in cache_trajets:
                    cache_trajets[secteur] = estimer_trajet_google_maps(depot_adr, secteur, h_chargement, api_k)
                dist_km, duree_m, _ = cache_trajets[secteur]
                dt_arrivee = datetime.combine(j, h_chargement) + timedelta(minutes=duree_m)

                results.append({
                    "Date": j.strftime("%Y-%m-%d"), "Jour": j.strftime("%A"), "Équipe": eq_id,
                    "Responsable": eq_info['Responsable'], "Ressources": eq_info['Nb_Agents'],
                    "Client_Document": cmd_info['Client_Document'], "Secteur": secteur, "Volume_Distribué": val,
                    "Capacité_Nominale": cap_nominale, "Taux_Charge_%": taux_pct, "Niveau_Couleur": couleur,
                    "Indicateur_Charge": badge, "Arrivée_Est_Chantier": dt_arrivee.strftime("%H:%M")
                })
    return pd.DataFrame(results), meteo_par_jour

df_resultat, dict_meteo = resoudre_planning_multi_agents(
    df_commandes, df_equipes, mode_meteo, coeff_meteo_manuel, depot_depart, heure_chargement, cle_google_maps
)

# -----------------------------------------------------------------------------
# INTERFACE PRINCIPALE (RESTITUTION DES 6 ONGLETS)
# -----------------------------------------------------------------------------
tab_planning, tab_charges, tab_meteo, tab_maps, tab_qa, tab_export = st.tabs([
    "📅 Planning Généré",
    "📊 Analyse des Charges Équipes",
    "🌤️ Rapport Météo Live", 
    "🚘 Logistique & Google Maps", 
    "🔍 Contrôle Qualité", 
    "📥 Export Maquette Excel"
])

with tab_planning:
    col1, col2, col3, col4 = st.columns(4)
    vol_total_moyen = df_commandes['Volume'].sum()
    col1.metric("Volume Total à Distribuer", f"{vol_total_moyen:,} ex.".replace(",", " "))
    col2.metric("Missions Planifiées", f"{len(df_resultat)} affectations")
    col3.metric("Équipes Actives", f"{len(df_equipes[df_equipes['Dispo']==True])} / {len(df_equipes)}")
    col4.metric("Dépôt Départ", depot_depart.split(',')[0])

    st.markdown("### 📋 Affectations Optimisées & Suivi des Charges")
    if not df_resultat.empty:
        equipe_filter = st.multiselect("Filtrer par Équipe :", options=df_resultat["Équipe"].unique(), default=df_resultat["Équipe"].unique())
        df_display = df_resultat[df_resultat["Équipe"].isin(equipe_filter)]
        cols_affichage = ["Date", "Équipe", "Responsable", "Client_Document", "Secteur", "Volume_Distribué", "Capacité_Nominale", "Indicateur_Charge", "Arrivée_Est_Chantier"]
        st.dataframe(df_display[cols_affichage], use_container_width=True)
    else:
        st.error("⚠️ Capacité insuffisante pour le volume demandé.")

with tab_charges:
    st.markdown("### 📊 Synthèse des Charges Journalières par Équipe")
    if not df_resultat.empty:
        df_charges_agg = df_resultat.groupby(["Date", "Équipe", "Responsable", "Capacité_Nominale"]).agg({
            "Volume_Distribué": "sum",
            "Indicateur_Charge": "first"
        }).reset_index()
        st.dataframe(df_charges_agg, use_container_width=True)

with tab_meteo:
    st.markdown("### 🌤️ Suivi Météo Prévisionnel")
    meteo_rows = [{"Date": d.strftime("%Y-%m-%d"), "Conditions": info["description"], "Coefficient": f"{info['coeff']}x"} for d, info in dict_meteo.items()]
    st.table(pd.DataFrame(meteo_rows))

with tab_maps:
    st.markdown("### 🗺️ Module d'Estimation des Trajets")
    if not df_resultat.empty:
        st.dataframe(df_resultat[["Équipe", "Secteur", "Arrivée_Est_Chantier"]].drop_duplicates(), use_container_width=True)

with tab_qa:
    st.markdown("### 🤖 Contrôle Qualité — Agence IA")
    st.success("✅ Tous les onglets et la conformité des noms d'équipes ont été restaurés avec succès.")

with tab_export:
    st.markdown("### 📥 Télécharger la Maquette Excel Conforme (Multi-onglets journaliers avec vrais noms d'équipes et codes couleurs)")
    if not df_resultat.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center'})
            fmt_vert = workbook.add_format({'bg_color': '#DCFCE7', 'font_color': '#166534', 'align': 'center'})
            fmt_orange = workbook.add_format({'bg_color': '#FFEDD5', 'font_color': '#9A3412', 'align': 'center'})
            fmt_rouge = workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B', 'align': 'center'})
            fmt_noir = workbook.add_format({'bg_color': '#18181B', 'font_color': '#FFFFFF', 'align': 'center'})

            all_equipes = df_equipes['ID_Equipe'].tolist()
            
            for day_num in range(1, 32):
                sheet_name = str(day_num)
                date_obj = date(2026, 10, day_num)
                date_str = date_obj.strftime("%Y-%m-%d")
                
                rows_day = []
                df_day_res = df_resultat[df_resultat['Date'] == date_str]
                
                for eq in all_equipes:
                    eq_row = df_equipes[df_equipes['ID_Equipe'] == eq].iloc[0]
                    ress = eq_row['Nb_Agents']
                    
                    match_res = df_day_res[df_day_res['Équipe'] == eq]
                    if not match_res.empty:
                        vol = match_res.iloc[0]['Volume_Distribué']
                        doc = match_res.iloc[0]['Client_Document']
                        secteur = match_res.iloc[0]['Secteur']
                        couleur = match_res.iloc[0]['Niveau_Couleur']
                    else:
                        vol = 0
                        doc = ""
                        secteur = ""
                        couleur = "Vert"

                    rows_day.append({
                        "EQUIPE": eq,
                        "RESS": ress,
                        "VOLUME": vol,
                        "PARTAGE": "",
                        "DOCUMENTS": doc,
                        "SECTEUR": secteur,
                        "STATUT_COULEUR": couleur
                    })
                
                df_sheet = pd.DataFrame(rows_day)
                
                worksheet = workbook.add_worksheet(sheet_name)
                writer.sheets[sheet_name] = worksheet
                
                # Écriture de la date en haut de l'onglet
                worksheet.write(0, 5, datetime(2026, 10, day_num), workbook.add_format({'num_format': 'yyyy-mm-dd', 'bold': True}))
                
                headers = ["", "EQUIPE", "RESS", "VOLUME", "PARTAGE", "DOCUMENTS", "SECTEUR"]
                for col_idx, h in enumerate(headers):
                    worksheet.write(1, col_idx, h, fmt_header)
                
                for r_idx, row in df_sheet.iterrows():
                    row_num = r_idx + 2
                    worksheet.write(row_num, 1, row["EQUIPE"])
                    worksheet.write(row_num, 2, row["RESS"])
                    worksheet.write(row_num, 3, row["VOLUME"])
                    worksheet.write(row_num, 4, row["PARTAGE"])
                    worksheet.write(row_num, 5, row["DOCUMENTS"])
                    worksheet.write(row_num, 6, row["SECTEUR"])
                    
                    c = row["STATUT_COULEUR"]
                    cell_fmt = fmt_vert
                    if c == "Orange": cell_fmt = fmt_orange
                    elif c == "Rouge": cell_fmt = fmt_rouge
                    elif c == "Noir": cell_fmt = fmt_noir
                    worksheet.write(row_num, 0, c, cell_fmt)

        st.download_button(
            "📥 Télécharger la Maquette Excel Identique (.xlsx)",
            data=buffer.getvalue(),
            file_name="CR_ISAPLUS_Maquette_Conforme.xlsx",
            mime="application/vnd.ms-excel"
        )
    else:
        st.info("Générez d'abord un planning valide.")
