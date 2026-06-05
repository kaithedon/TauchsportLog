import streamlit as st
import pandas as pd
import numpy as np
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import hashlib
import datetime
import uuid
import base64
import io
from PIL import Image

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Tauchsportclub - Deep Dive Counter",
    page_icon="🤿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- STYLING (Abgrund-Blau & Neon-Cyan) ---
st.markdown("""
    <style>
    :root {
        --bg-color: #0A192F;
        --neon-cyan: #00F5D4;
        --text-color: #E2E8F0;
        --panel-bg: rgba(255, 255, 255, 0.05);
    }
    
    .stApp {
        background-color: var(--bg-color);
        color: var(--text-color);
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: var(--neon-cyan) !important;
        font-family: 'Courier New', Courier, monospace;
    }
    
    /* Buttons */
    .stButton>button {
        background-color: transparent !important;
        color: var(--neon-cyan) !important;
        border: 2px solid var(--neon-cyan) !important;
        border-radius: 10px !important;
        transition: all 0.3s ease !important;
        font-weight: bold !important;
    }
    .stButton>button:hover {
        background-color: var(--neon-cyan) !important;
        color: var(--bg-color) !important;
        box-shadow: 0 0 15px var(--neon-cyan) !important;
    }
    
    /* Storno Button Special */
    .storno-btn>button {
        border-color: #ff4b4b !important;
        color: #ff4b4b !important;
    }
    .storno-btn>button:hover {
        background-color: #ff4b4b !important;
        color: white !important;
        box-shadow: 0 0 15px #ff4b4b !important;
    }
    
    /* Containers / Cards */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--neon-cyan) !important;
        background-color: var(--panel-bg);
        border-radius: 15px;
    }
    
    /* Dataframes and text */
    .stDataFrame, .stTable, p, div {
        color: var(--text-color) !important;
    }
    
    /* Link styling for PayPal */
    a.paypal-link {
        display: inline-block;
        padding: 10px 20px;
        background-color: #0070ba;
        color: white !important;
        text-decoration: none;
        border-radius: 5px;
        font-weight: bold;
        text-align: center;
        width: 100%;
        margin-top: 10px;
    }
    a.paypal-link:hover {
        background-color: #005ea6;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
SHEET_USER_DB = "User_DB"
SHEET_GETRAENKE_DB = "Getraenke_DB"
SHEET_KONSUM_LOG = "Konsum_Log"
SHEET_GLOBALE_STATS = "Globale_Stats"
SHEET_BACKUP_HISTORY = "Backup_History"

COLUMNS = {
    SHEET_USER_DB: ["Username", "Password_Hash", "Gewicht_kg", "Groesse_cm", "Geschlecht", "Rolle", "Profilbild_Url"],
    SHEET_GETRAENKE_DB: ["Marke", "Sorte", "Alkoholgehalt_Vol", "Standard_Menge_ml"],
    SHEET_KONSUM_LOG: ["Log_ID", "Zeitstempel", "Username", "Marke", "Sorte", "Menge_ml", "Alk_Vol"],
    SHEET_GLOBALE_STATS: ["Key", "Value"],
    SHEET_BACKUP_HISTORY: ["Backup_Zeitstempel", "Log_ID", "Zeitstempel", "Username", "Marke", "Sorte", "Menge_ml", "Alk_Vol"]
}

DEFAULT_DRINKS = [
    ["Licher", "Pils", 4.8, 330],
    ["Veltins", "Pils", 4.8, 330],
    ["Krombacher", "Pils", 4.8, 330],
    ["Bitburger", "Pils", 4.8, 330],
    ["Becks", "Pils", 4.9, 330],
    ["Augustiner", "Hell", 5.2, 500],
    ["Paulaner", "Weißbier", 5.5, 500],
    ["Erdinger", "Weißbier", 5.3, 500],
    ["Heineken", "Lager", 5.0, 330],
    ["Astra", "Urtyp", 4.9, 330],
    ["Jägermeister", "Shot", 35.0, 20],
    ["Softdrinks/Wasser", "Alkoholfrei", 0.0, 330]
]

# --- DATABASE HELPERS ---
@st.cache_resource
def get_gspread_client():
    try:
        # Streamlit secrets dict needs to be converted to a normal dict for gspread
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        
        # If public link without service account is used, this will fail. We need the service account.
        if "type" not in creds_dict:
            st.error("Bitte trage die Service Account Daten in die secrets.toml ein.")
            st.stop()
            
        client = gspread.service_account_from_dict(creds_dict)
        spreadsheet_url = creds_dict.get("spreadsheet")
        sheet = client.open_by_url(spreadsheet_url)
        return sheet
    except Exception as e:
        st.error(f"Datenbankverbindung fehlgeschlagen. Bitte .streamlit/secrets.toml prüfen. Fehler: {e}")
        st.stop()

def get_worksheet(sheet_name):
    sheet = get_gspread_client()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        st.info(f"Tabellenblatt '{sheet_name}' wird erstellt...")
        return sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")

def load_data(sheet_name):
    ws = get_worksheet(sheet_name)
    # Read everything into a dataframe
    # Drop rows where all elements are NaN
    df = get_as_dataframe(ws, evaluate_formulas=True)
    df = df.dropna(how='all')
    
    if df.empty or len(df.columns) == 0:
        return pd.DataFrame(columns=COLUMNS[sheet_name])
        
    return df

def save_data(sheet_name, df):
    ws = get_worksheet(sheet_name)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False)

def init_db():
    # Initialize all sheets
    for sheet in COLUMNS.keys():
        df = load_data(sheet)
        
        # specific init logic
        if sheet == SHEET_USER_DB and df.empty:
            pwd_hash = hashlib.sha256("tsc2026".encode()).hexdigest()
            new_user = pd.DataFrame([{"Username": "kai", "Password_Hash": pwd_hash, "Gewicht_kg": 85, "Groesse_cm": 185, "Geschlecht": "Männlich", "Rolle": "Admin", "Profilbild_Url": "🤿"}])
            df = pd.concat([df, new_user], ignore_index=True)
            save_data(SHEET_USER_DB, df)
            
        elif sheet == SHEET_GETRAENKE_DB and df.empty:
            drinks_df = pd.DataFrame(DEFAULT_DRINKS, columns=COLUMNS[SHEET_GETRAENKE_DB])
            save_data(SHEET_GETRAENKE_DB, drinks_df)

# Run init on app startup
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# --- AUTH HELPERS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_user(username, password):
    users_df = load_data(SHEET_USER_DB)
    pwd_hash = hash_password(password)
    user = users_df[(users_df['Username'] == username) & (users_df['Password_Hash'] == pwd_hash)]
    if not user.empty:
        st.session_state.logged_in = True
        st.session_state.username = username
        st.session_state.role = user.iloc[0]['Rolle']
        st.session_state.gewicht = float(user.iloc[0]['Gewicht_kg'])
        st.session_state.groesse = float(user.iloc[0]['Groesse_cm'])
        st.session_state.geschlecht = user.iloc[0]['Geschlecht']
        return True
    return False

def register_user(username, password, gewicht, groesse, geschlecht, profilbild):
    users_df = load_data(SHEET_USER_DB)
    if username in users_df['Username'].values:
        return False, "Username bereits vergeben."
    
    pwd_hash = hash_password(password)
    new_user = pd.DataFrame([{
        "Username": username,
        "Password_Hash": pwd_hash,
        "Gewicht_kg": gewicht,
        "Groesse_cm": groesse,
        "Geschlecht": geschlecht,
        "Rolle": "User",
        "Profilbild_Url": profilbild
    }])
    users_df = pd.concat([users_df, new_user], ignore_index=True)
    save_data(SHEET_USER_DB, users_df)
    return True, "Erfolgreich registriert!"

# --- PROMILLE RECHNER ---
def calc_promille(username):
    # Load user data
    users_df = load_data(SHEET_USER_DB)
    user_row = users_df[users_df['Username'] == username]
    if user_row.empty: return 0.0
    
    gewicht = float(user_row.iloc[0]['Gewicht_kg'])
    groesse = float(user_row.iloc[0]['Groesse_cm'])
    geschlecht = user_row.iloc[0]['Geschlecht']
    
    # Calculate Total Body Water (V) according to Watson
    if geschlecht == "Männlich":
        v = 2.447 - (0.09516 * 29) + (0.1074 * groesse) + (0.3362 * gewicht) # Assuming age 29 as standard if not provided
    else:
        v = -2.097 + (0.1069 * groesse) + (0.2466 * gewicht)
        
    if v <= 0: v = 1.0 # Fallback safety
    
    # Load logs for today
    logs_df = load_data(SHEET_KONSUM_LOG)
    logs_df['Zeitstempel'] = pd.to_datetime(logs_df['Zeitstempel'])
    
    # Consider only last 24h
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(hours=24)
    user_logs = logs_df[(logs_df['Username'] == username) & (logs_df['Zeitstempel'] >= cutoff)]
    
    if user_logs.empty: return 0.0
    
    user_logs = user_logs.sort_values('Zeitstempel')
    
    current_promille = 0.0
    last_time = None
    
    for _, row in user_logs.iterrows():
        drink_time = row['Zeitstempel']
        ml = float(row['Menge_ml'])
        vol = float(row['Alk_Vol'])
        
        # Abbau seit letztem Getränk
        if last_time is not None:
            hours_passed = (drink_time - last_time).total_seconds() / 3600.0
            current_promille = max(0.0, current_promille - (hours_passed * 0.15))
            
        # Promille des aktuellen Getränks hinzufügen
        a = ml * (vol / 100) * 0.8
        added_promille = a / (v * 1.055)
        current_promille += added_promille
        last_time = drink_time
        
    # Abbau seit letztem Getränk bis jetzt
    if last_time is not None:
        hours_passed = (now - last_time).total_seconds() / 3600.0
        current_promille = max(0.0, current_promille - (hours_passed * 0.15))
        
    return round(current_promille, 2)

def get_symptom_info(promille):
    if promille < 0.1:
        return "Nüchtern. Bereit für den Tauchgang! 🤿"
    elif promille <= 0.5:
        return "Bis 0.5‰: Leicht angetrunken / beginnender Tunnelblick."
    elif promille <= 1.0:
        return "0.5-1.0‰: Schwimmstadium. Enthemmung, leichte Koordinationsstörungen."
    elif promille <= 2.0:
        return "1.0-2.0‰: Tieftauchgang / Lallen. Deutliche Sprach- und Gleichgewichtsstörungen."
    else:
        return "Ab 2.0‰: Schwerer Rausch. *Hinweis: Bei einem nicht-alkoholkranken Menschen könnten bei dieser Promillezahl schwere Vergiftungssymptomatiken auftreten...*"

# --- VIEWS ---
def login_view():
    try:
        st.image("banner.png", use_container_width=True)
    except Exception:
        st.markdown("<h1 style='text-align: center;'>🤿 Tauchsportclub<br>Deep Dive Counter</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Registrierung"])
    
    with tab1:
        with st.container(border=True):
            st.subheader("Login")
            l_user = st.text_input("Username", key="l_user")
            l_pass = st.text_input("Passwort", type="password", key="l_pass")
            if st.button("Einloggen", use_container_width=True):
                if login_user(l_user, l_pass):
                    st.rerun()
                else:
                    st.error("Falscher Username oder Passwort.")
                    
    with tab2:
        with st.container(border=True):
            st.subheader("Neuer Taucher")
            r_user = st.text_input("Username", key="r_user")
            r_pass = st.text_input("Passwort", type="password", key="r_pass")
            r_gew = st.number_input("Gewicht (kg)", min_value=30.0, max_value=200.0, value=75.0)
            r_groesse = st.number_input("Größe (cm)", min_value=120, max_value=230, value=175)
            r_geschlecht = st.selectbox("Geschlecht", ["Männlich", "Weiblich"])
            
            st.write("Profilbild auswählen oder hochladen:")
            r_pic_emoji = st.selectbox("Emoji-Avatar", ["🤿", "🦈", "🐙", "🍺", "🍹", "🐋"])
            r_pic_file = st.file_uploader("Oder eigenes Bild hochladen (Optional)", type=["jpg", "jpeg", "png"])
            
            if st.button("Registrieren", use_container_width=True):
                if r_user and r_pass:
                    # Handle Image Upload (compress to Base64)
                    profilbild = r_pic_emoji
                    if r_pic_file is not None:
                        try:
                            img = Image.open(r_pic_file)
                            img.thumbnail((150, 150)) # Resize to small avatar
                            # Convert to RGB to ensure JPEG compatibility
                            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                            
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=70)
                            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                            profilbild = f"data:image/jpeg;base64,{encoded}"
                        except Exception as e:
                            st.warning("Bild konnte nicht verarbeitet werden. Nutze Emoji.")
                            
                    success, msg = register_user(r_user, r_pass, r_gew, r_groesse, r_geschlecht, profilbild)
                    if success:
                        st.success(msg + " Bitte logge dich nun ein.")
                    else:
                        st.error(msg)
                else:
                    st.error("Bitte alle Pflichtfelder ausfüllen.")

def buchung_view():
    st.title("🍺 Getränke buchen")
    
    getraenke_df = load_data(SHEET_GETRAENKE_DB)
    drink_options = getraenke_df.apply(lambda r: f"{r['Marke']} {r['Sorte']} ({r['Standard_Menge_ml']}ml)", axis=1).tolist()
    drink_options.append("Anderes Getränk (Manuell)")
    
    with st.container(border=True):
        selected_option = st.selectbox("Was trinkst du?", drink_options)
        
        # Manual entry logic
        if selected_option == "Anderes Getränk (Manuell)":
            col1, col2 = st.columns(2)
            with col1:
                marke = st.text_input("Marke/Name")
                menge = st.number_input("Menge (ml)", min_value=10, max_value=2000, step=10, value=330)
            with col2:
                sorte = "Manuell"
                alk_vol = st.number_input("Alkoholgehalt (Vol%)", min_value=0.0, max_value=100.0, step=0.1, value=5.0)
        else:
            idx = drink_options.index(selected_option)
            row = getraenke_df.iloc[idx]
            marke = row['Marke']
            sorte = row['Sorte']
            menge = row['Standard_Menge_ml']
            alk_vol = row['Alkoholgehalt_Vol']
            
        anzahl = st.number_input("Anzahl", min_value=1, max_value=10, value=1)
        
        mode = st.radio("Zeitpunkt", ["Jetzt live einbuchen", "Nachtragen"])
        buchungs_zeit = datetime.datetime.now()
        if mode == "Nachtragen":
            manual_time = st.time_input("Uhrzeit auswählen")
            buchungs_zeit = datetime.datetime.combine(datetime.date.today(), manual_time)
            if buchungs_zeit > datetime.datetime.now():
                buchungs_zeit -= datetime.timedelta(days=1) # Assume yesterday if time is in future
                
        if st.button("Einlochen 🎯", use_container_width=True):
            logs_df = load_data(SHEET_KONSUM_LOG)
            new_logs = []
            for _ in range(anzahl):
                new_logs.append({
                    "Log_ID": str(uuid.uuid4()),
                    "Zeitstempel": buchungs_zeit.strftime("%Y-%m-%d %H:%M:%S"),
                    "Username": st.session_state.username,
                    "Marke": marke,
                    "Sorte": sorte,
                    "Menge_ml": menge,
                    "Alk_Vol": alk_vol
                })
            
            new_logs_df = pd.DataFrame(new_logs)
            logs_df = pd.concat([logs_df, new_logs_df], ignore_index=True)
            save_data(SHEET_KONSUM_LOG, logs_df)
            st.toast(f"{anzahl}x {marke} erfolgreich verbucht!", icon="🍻")
            st.rerun()

    # Storno Bereich
    st.subheader("Letzte Buchungen (Storno)")
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username].copy()
    
    if not my_logs.empty:
        my_logs['Zeitstempel'] = pd.to_datetime(my_logs['Zeitstempel'])
        my_logs = my_logs.sort_values(by="Zeitstempel", ascending=False).head(5)
        
        for _, row in my_logs.iterrows():
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    time_str = row['Zeitstempel'].strftime("%H:%M")
                    st.write(f"**{time_str}** | {row['Marke']} {row['Sorte']}")
                with colB:
                    st.markdown("<div class='storno-btn'>", unsafe_allow_html=True)
                    if st.button("❌ Storno", key=f"storno_{row['Log_ID']}", use_container_width=True):
                        # Delete from dataframe
                        logs_df = logs_df[logs_df['Log_ID'] != row['Log_ID']]
                        save_data(SHEET_KONSUM_LOG, logs_df)
                        st.toast("Buchung storniert.", icon="🗑️")
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Noch keine Getränke heute gebucht.")

def mein_abend_view():
    st.title("🤿 Promille Status")
    
    promille = calc_promille(st.session_state.username)
    st.metric("Dein Live-Promillewert", f"{promille} ‰")
    st.info(get_symptom_info(promille))
    
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username]
    
    if my_logs.empty:
        st.write("Du hast heute noch nichts getrunken.")
        return
        
    st.subheader("Deine Deckel")
    st.dataframe(my_logs[['Zeitstempel', 'Marke', 'Sorte', 'Menge_ml']], use_container_width=True, hide_index=True)

def social_view():
    st.title("👑 Social & Stats")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    
    st.subheader("Mitglieder Live-Stats")
    
    col1, col2 = st.columns(2)
    for idx, user_row in users_df.iterrows():
        uname = user_row['Username']
        pic = user_row['Profilbild_Url']
        p_val = calc_promille(uname)
        
        # Lieblingsgetränk
        user_logs = logs_df[logs_df['Username'] == uname]
        fav_drink = "-"
        if not user_logs.empty:
            fav_drink = user_logs['Marke'].value_counts().idxmax()
            
        with (col1 if idx % 2 == 0 else col2):
            with st.container(border=True):
                if pic.startswith("data:image"):
                    st.markdown(f'<img src="{pic}" style="border-radius: 50%; width: 60px; height: 60px; object-fit: cover; margin-bottom: 10px;">', unsafe_allow_html=True)
                    st.markdown(f"### {uname}")
                else:
                    st.markdown(f"### {pic} {uname}")
                st.write(f"**Promille:** {p_val} ‰")
                st.write(f"**Fav. Drink:** {fav_drink}")

    st.divider()
    
    st.subheader("All-Time Rangliste")
    if not logs_df.empty:
        leaderboard = logs_df.groupby('Username').size().reset_index(name='Anzahl')
        leaderboard = leaderboard.sort_values(by='Anzahl', ascending=False).reset_index(drop=True)
        
        for i, row in leaderboard.iterrows():
            medal = "👑" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "🍻"))
            st.write(f"{medal} **{row['Username']}**: {row['Anzahl']} Drinks")
    else:
        st.write("Noch keine Daten für die Rangliste vorhanden.")

def admin_view():
    st.title("🛠️ Admin-Bereich")
    
    if st.session_state.role != "Admin":
        st.error("Zugriff verweigert.")
        return
        
    st.subheader("Globales Log (Heute)")
    logs_df = load_data(SHEET_KONSUM_LOG)
    st.dataframe(logs_df, use_container_width=True)
    
    with st.container(border=True):
        st.markdown("<h3 style='color: #ff4b4b;'>🚨 Abend beenden & Nullen</h3>", unsafe_allow_html=True)
        st.write("Dies verschiebt alle aktuellen Einträge in die Backup-Historie und leert das Live-Log.")
        if st.button("Jetzt durchführen", type="primary"):
            if not logs_df.empty:
                backup_df = load_data(SHEET_BACKUP_HISTORY)
                
                # Add backup timestamp
                logs_df['Backup_Zeitstempel'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Reorder to match backup columns
                logs_df = logs_df[COLUMNS[SHEET_BACKUP_HISTORY]]
                
                # Append to backup
                backup_df = pd.concat([backup_df, logs_df], ignore_index=True)
                save_data(SHEET_BACKUP_HISTORY, backup_df)
                
                # Clear active log
                empty_log = pd.DataFrame(columns=COLUMNS[SHEET_KONSUM_LOG])
                save_data(SHEET_KONSUM_LOG, empty_log)
                
                st.success("Erfolgreich gesichert und genullt!")
                st.rerun()
            else:
                st.info("Log ist bereits leer.")

# --- MAIN LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login_view()
else:
    try:
        st.image("banner.png", use_container_width=True)
    except Exception:
        pass
        
    # Top Navigation Bar
    st.write(f"Willkommen, **{st.session_state.username}** 🤿")
    menu = ["Getränke buchen", "Promille Status", "Social & Stats"]
    if st.session_state.role == "Admin":
        menu.append("Admin-Bereich")
        
    col_nav, col_logout = st.columns([0.85, 0.15])
    with col_nav:
        choice = st.radio("Navigation", menu, horizontal=True, label_visibility="collapsed")
    with col_logout:
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
            
    st.divider()
            
    # Route to views
    if choice == "Getränke buchen":
        buchung_view()
    elif choice == "Promille Status":
        mein_abend_view()
    elif choice == "Social & Stats":
        social_view()
    elif choice == "Admin-Bereich":
        admin_view()

