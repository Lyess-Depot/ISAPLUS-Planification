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
# BARRE LATÉRALE
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
st.sidebar.subheader("📁 Ingestion Fichier Excel Unique")
uploaded_file = st.sidebar.file_uploader("Fichier Excel Global (.xlsx)", type=["xlsx"])

@st.cache_data
def get_demo_data():
    df_cmd = pd.DataFrame([
        {"ID_Commande": "CMD-101", "Client_Document": "Sevran Magazine N°213", "Secteur": "SEVRAN_SD", "Volume": 10600, "Date_Debut": "2026-10-05", "Date_Fin": "2026-10-07"},
        {"ID_Commande": "CMD-102", "Client_Document": "Aulnay Oxygène N°295", "Secteur": "AULNAY_B", "Volume": 18000, "Date_Debut": "2026-10-05", "Date_Fin": "2026-10-09"},
        {"ID_Commande": "CMD-103", "Client_Document": "Courbevoie Mag N°189", "Secteur": "COURBEVOIE_A", "Volume": 14000, "Date_Debut": "2026-10-07", "Date_Fin": "2026-10-09"},
        {"ID_Commande": "CMD-104", "Client_Document": "Livry Gargan Bulletin", "Secteur": "LIVRY_DE", "Volume": 8400, "Date_Debut": "2026-10-06", "Date_Fin": "2026-10-08"}
    ])
    df_eq = pd.DataFrame([
        {"ID_Equipe": "EQUIPE 01", "Responsable": "Mirtcha", "Nb_Agents": 2.0, "Capacite_Nominale": 9000, "Score_SEVRAN_SD": 85, "Score_AULNAY_B": 70, "Score_COURBEVOIE_A": 60, "Score_LIVRY_DE": 80, "Dispo": "OUI"},
        {"ID_Equipe": "EQUIPE 02", "Responsable": "Michel", "Nb_Agents": 1.0, "Capacite_Nominale": 4500, "Score_SEVRAN_SD": 60, "Score_AULNAY_B": 90, "Score_COURBEVOIE_A": 50, "Score_LIVRY_DE": 65, "Dispo": "OUI"},
        {"ID_Equipe": "EQUIPE 03", "Responsable": "Cristian", "Nb_Agents": 1.0, "Capacite_Nominale": 4500, "Score_SEVRAN_SD": 50, "Score_AULNAY_B": 75, "Score_COURBEVOIE_A": 95, "Score_LIVRY_DE": 70, "Dispo": "OUI"},
        {"ID_Equipe": "EQUIPE 04", "Responsable": "Gheorghe", "Nb_Agents": 3.0, "Capacite_Nominale": 13500, "Score_SEVRAN_SD": 40, "Score_AULNAY_B": 80, "Score_COURBEVOIE_A": 90, "Score_LIVRY_DE": 90, "Dispo": "OUI"}
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
    is_active = st.sidebar.checkbox(f"{eq_code} ({resp_name})", value=default_val, key=f"dispo_{eq_code}")
    equipes_dispos_status[eq_code] = is_active

df_equipes['Dispo'] = df_equipes['ID_Equipe'].map(equipes_dispos_status)

# -----------------------------------------------------------------------------
# MOTEUR MULTI-AGENTS
# -----------------------------------------------------------------------------
def resoudre_planning_multi_agents(df_cmd, df_eq):
    model = cp_model.CpModel()
    dates_horizon = [date(2026, 10, 1) + timedelta(days=i) for i in range(15)]
    commandes = df_cmd.to_dict('records')
    equipes = df_eq[df_eq['Dispo'] == True].to_dict('records')
    if not equipes: return pd.DataFrame()

    x_vol = {}
    for cmd in commandes:
        cmd_id = cmd['ID_Commande']
        d_debut = datetime.strptime(str(cmd['Date_Debut'])[:10], "%Y-%m-%d").date()
        d_fin = datetime.strptime(str(cmd['Date_Fin'])[:10], "%Y-%m-%d").date()
        for eq in equipes:
            eq_id = eq['ID_Equipe']
            for j in dates_horizon:
                if d_debut <= j <= d_fin:
                    cap_eff = int(float(eq['Capacite_Nominale']) * 1.10)
                    x_vol[(cmd_id, eq_id, j)] = model.NewIntVar(0, cap_eff, f"x_{cmd_id}_{eq_id}_{j}")

    for cmd in commandes:
        cmd_id = cmd['ID_Commande']
        vols = [x_vol[(cmd_id, eq['ID_Equipe'], j)] for eq in equipes for j in dates_horizon if (cmd_id, eq['ID_Equipe'], j) in x_vol]
        if vols: model.Add(sum(vols) == int(cmd['Volume']))

    for eq in equipes:
        eq_id = eq['ID_Equipe']
        for j in dates_horizon:
            cap_max = int(float(eq['Capacite_Nominale']) * 1.10)
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
        totaux_cumules = {}
        for (cmd_id, eq_id, j), var_vol in x_vol.items():
            if solver.Value(var_vol) > 0:
                totaux_cumules[(eq_id, j)] = totaux_cumules.get((eq_id, j), 0) + solver.Value(var_vol)

        for (cmd_id, eq_id, j), var_vol in x_vol.items():
            val = solver.Value(var_vol)
            if val > 0:
                cmd_info = next(c for c in commandes if c['ID_Commande'] == cmd_id)
                eq_info = next(e for e in equipes if e['ID_Equipe'] == eq_id)
                vol_cumule = totaux_cumules[(eq_id, j)]
                cap_nominale = int(eq_info['Capacite_Nominale'])
                taux_pct = round((vol_cumule / cap_nominale) * 100) if cap_nominale > 0 else 0

                # Code couleur selon les seuils demandés
                if taux_pct <= 50:
                    couleur = "Vert"
                    badge = f"🟢 {taux_pct}%"
                elif taux_pct <= 80:
                    couleur = "Orange"
                    badge = f"🟠 {taux_pct}%"
                elif taux_pct <= 95:
                    couleur = "Rouge"
                    badge = f"🔴 {taux_pct}%"
                else:
                    couleur = "Noir"
                    badge = f"⬛ {taux_pct}%"

                results.append({
                    "Date": j.strftime("%Y-%m-%d"), "Équipe": eq_id, "Responsable": eq_info['Responsable'],
                    "Ressources": eq_info['Nb_Agents'], "Client_Document": cmd_info['Client_Document'],
                    "Secteur": cmd_info['Secteur'], "Volume_Distribué": val, "Capacité_Nominale": cap_nominale,
                    "Taux_Charge_%": taux_pct, "Niveau_Couleur": couleur, "Indicateur_Charge": badge
                })
    return pd.DataFrame(results)

df_resultat = resoudre_planning_multi_agents(df_commandes, df_equipes)

# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
st.markdown('<div class="main-header">🚚 ISA Plus — Planning & Maquette Officielle Conforme</div>', unsafe_allow_html=True)

tab_planning, tab_export = st.tabs(["📅 Planning Généré", "📥 Export Maquette Excel Identique"])

with tab_planning:
    if not df_resultat.empty:
        st.dataframe(df_resultat, use_container_width=True)
    else:
        st.error("⚠️ Capacité insuffisante.")

with tab_export:
    st.markdown("### 📥 Télécharger le classeur au format exact de votre maquette")
    if not df_resultat.empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Formats de cellules et couleurs demandées
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9D9D9', 'border': 1, 'align': 'center'})
            fmt_vert = workbook.add_format({'bg_color': '#DCFCE7', 'font_color': '#166534', 'align': 'center'})
            fmt_orange = workbook.add_format({'bg_color': '#FFEDD5', 'font_color': '#9A3412', 'align': 'center'})
            fmt_rouge = workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B', 'align': 'center'})
            fmt_noir = workbook.add_format({'bg_color': '#18181B', 'font_color': '#FFFFFF', 'align': 'center'})

            # Génération des onglets journaliers (1 à 31) structurés comme la maquette
            all_equipes = df_equipes['ID_Equipe'].tolist()
            
            for day_num in range(1, 32):
                sheet_name = str(day_num)
                date_obj = date(2026, 10, day_num)
                date_str = date_obj.strftime("%Y-%m-%d")
                
                # Tableau récapitulatif des équipes pour ce jour
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
                        "CHARGEMENT Sous-Traitants": eq,
                        "RESS": ress,
                        "VOLUME": vol,
                        "PARTAGE": "",
                        "DOCUMENTS": doc,
                        "SECTEUR": secteur,
                        "STATUT_COULEUR": couleur
                    })
                
                df_sheet = pd.DataFrame(rows_day)
                
                # Écriture dans l'onglet avec la date en haut (exactement comme le modèle)
                worksheet = workbook.add_worksheet(sheet_name)
                writer.sheets[sheet_name] = worksheet
                
                # En-tête date
                worksheet.write(0, 5, datetime(2026, 10, day_num), workbook.add_format({'num_format': 'yyyy-mm-dd', 'bold': True}))
                
                # En-têtes de colonnes
                headers = ["", "EQUIPE", "RESS", "VOLUME", "PARTAGE", "DOCUMENTS", "SECTEUR"]
                for col_idx, h in enumerate(headers):
                    worksheet.write(1, col_idx, h, fmt_header)
                
                # Lignes de données
                for r_idx, row in df_sheet.iterrows():
                    row_num = r_idx + 2
                    worksheet.write(row_num, 1, row["CHARGEMENT Sous-Traitants"])
                    worksheet.write(row_num, 2, row["RESS"])
                    worksheet.write(row_num, 3, row["VOLUME"])
                    worksheet.write(row_num, 4, row["PARTAGE"])
                    worksheet.write(row_num, 5, row["DOCUMENTS"])
                    worksheet.write(row_num, 6, row["SECTEUR"])
                    
                    # Application du code couleur sur la ligne selon la charge
                    c = row["STATUT_COULEUR"]
                    cell_fmt = fmt_vert
                    if c == "Orange": cell_fmt = fmt_orange
                    elif c == "Rouge": cell_fmt = fmt_rouge
                    elif c == "Noir": cell_fmt = fmt_noir
                    worksheet.write(row_num, 0, c, cell_fmt)

        st.download_button(
            "📥 Télécharger la Maquette Excel Conforme (.xlsx)",
            data=buffer.getvalue(),
            file_name="CR_ISAPLUS_Maquette_Identique.xlsx",
            mime="application/vnd.ms-excel"
        )
    else:
        st.info("Générez d'abord un planning valide.")
