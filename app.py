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
from streamlit_option_menu import option_menu
from tenacity import retry, wait_exponential, stop_after_attempt

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Tauchsportclub - Deep Dive Counter",
    page_icon="🤿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- STYLING ---
st.markdown("""
    <style>
    /* Layout/Padding Fix für Mobilgeräte */
    .block-container {
        padding-left: 0.2rem !important;
        padding-right: 0.2rem !important;
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }
    
    /* Storno Button Special */
    .storno-btn>button {
        border-color: #ff4b4b !important;
        color: #ff4b4b !important;
    }
    .storno-btn>button:hover {
        background-color: #ff4b4b !important;
        color: white !important;
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

def generate_master_drinks():
    Brauereien = [
        "Licher", "Veltins", "Krombacher", "Bitburger", "Becks", "Warsteiner", "Radeberger", 
        "Jever", "Flensburger", "Rothaus", "Ur-Krostitzer", "König Pilsener", "Hasseröder",
        "Augustiner", "Bayreuther", "Chiemseer", "Tegernseer", "Paulaner", "Spaten", 
        "Oberdorfer", "Büble", "Hacker-Pschorr", "Löwenbräu", "Weihenstephan", "Ayinger",
        "Erdinger", "Franziskaner", "Maisel's", "Schöfferhofer", "Schneider Weisse", "Benediktiner",
        "Früh", "Reissdorf", "Gaffel", "Füchschen", "Uerige", "Diebels",
        "Astra", "Sternburg", "Oettinger", "5,0 Original", "Paderborner",
        "Heineken", "Corona", "Desperados", "Salitos", "Gösser", "San Miguel", "Peroni", 
        "Guinness", "Kilkenny", "Budweiser", "Estrella Damm", "Carlsberg", "Tuborg"
    ]

    Sorten_Konfiguration = [
        {"Sorte": "Pils (0.33l)", "Vol": 4.8, "Menge": 330},
        {"Sorte": "Pils (0.5l)", "Vol": 4.8, "Menge": 500},
        {"Sorte": "Helles (0.5l)", "Vol": 5.0, "Menge": 500},
        {"Sorte": "Export (0.5l)", "Vol": 5.2, "Menge": 500},
        {"Sorte": "Hefe-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Kristall-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Dunkelbier (0.5l)", "Vol": 5.1, "Menge": 500},
        {"Sorte": "Radler (0.33l)", "Vol": 2.5, "Menge": 330},
        {"Sorte": "Radler (0.5l)", "Vol": 2.5, "Menge": 500},
        {"Sorte": "Alkoholfrei (0.33l)", "Vol": 0.0, "Menge": 330},
        {"Sorte": "Alkoholfrei (0.5l)", "Vol": 0.0, "Menge": 500}
    ]

    Apfelwein_Marken = ["Possmann", "Bembel-with-Care", "Rapp's", "Höhl", "Heil"]
    Apfelwein_Sorten = [
        {"Sorte": "Pur (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Sauergespratzt (0.5l)", "Vol": 4.0, "Menge": 500},
        {"Sorte": "Süßgespratzt (0.5l)", "Vol": 3.5, "Menge": 500},
        {"Sorte": "Cola-Ascher (0.5l)", "Vol": 3.8, "Menge": 500},
        {"Sorte": "Kirsch-Weis (0.5l)", "Vol": 4.2, "Menge": 500}
    ]

    Spirituosen = [
        {"Name": "Bacardi Carta Blanca", "Vol": 37.5, "Menge": 40},
        {"Name": "Bacardi Oakheart", "Vol": 35.0, "Menge": 40},
        {"Name": "Havana Club 3 Jahre", "Vol": 40.0, "Menge": 40},
        {"Name": "Havana Club 7 Jahre", "Vol": 40.0, "Menge": 40},
        {"Name": "Captain Morgan Spiced Gold", "Vol": 35.0, "Menge": 40},
        {"Name": "Jack Daniel's Old No. 7", "Vol": 40.0, "Menge": 40},
        {"Name": "Jack Daniel's Honey", "Vol": 35.0, "Menge": 40},
        {"Name": "Jim Beam Bourbon", "Vol": 40.0, "Menge": 40},
        {"Name": "Johnny Walker Red Label", "Vol": 40.0, "Menge": 40},
        {"Name": "Jameson Irish Whiskey", "Vol": 40.0, "Menge": 40},
        {"Name": "Tullamore Dew", "Vol": 40.0, "Menge": 40},
        {"Name": "Absolut Wodka", "Vol": 40.0, "Menge": 40},
        {"Name": "Wodka Gorbatschow", "Vol": 37.5, "Menge": 40},
        {"Name": "Smirnoff Ice / Wodka", "Vol": 37.5, "Menge": 40},
        {"Name": "Three Sixty Wodka", "Vol": 37.5, "Menge": 40},
        {"Name": "Gordon's London Dry Gin", "Vol": 37.5, "Menge": 40},
        {"Name": "Bombay Sapphire Gin", "Vol": 40.0, "Menge": 40},
        {"Name": "Hendrick's Gin", "Vol": 44.0, "Menge": 40},
        {"Name": "Tanqueray Gin", "Vol": 47.3, "Menge": 40},
        {"Name": "Jägermeister", "Vol": 35.0, "Menge": 40},
        {"Name": "Asbach Uralt", "Vol": 38.0, "Menge": 40},
        {"Name": "Campari", "Vol": 25.0, "Menge": 40},
        {"Name": "Malibu Kokoslikör", "Vol": 21.0, "Menge": 40},
        {"Name": "Aperol", "Vol": 11.0, "Menge": 40},
        {"Name": "Lillet Blanc", "Vol": 17.0, "Menge": 40},
        {"Name": "Ramazzotti", "Vol": 30.0, "Menge": 40},
        {"Name": "Averna", "Vol": 29.0, "Menge": 40},
        {"Name": "Baileys Irish Cream", "Vol": 17.0, "Menge": 40},
        {"Name": "Licor 43", "Vol": 31.0, "Menge": 40},
        {"Name": "Batida de Côco", "Vol": 16.0, "Menge": 40}
    ]

    Filler = [
        {"Name": "mit Coca-Cola", "Menge": 260},
        {"Name": "mit Coca-Cola Zero", "Menge": 260},
        {"Name": "mit Fanta", "Menge": 260},
        {"Name": "mit Sprite", "Menge": 260},
        {"Name": "mit Mezzo Mix", "Menge": 260},
        {"Name": "mit Red Bull Energy", "Menge": 210},
        {"Name": "mit Red Bull Sugarfree", "Menge": 210},
        {"Name": "mit Schweppes Bitter Lemon", "Menge": 210},
        {"Name": "mit Schweppes Tonic Water", "Menge": 210},
        {"Name": "mit Schweppes Ginger Ale", "Menge": 210},
        {"Name": "mit Thomas Henry Tonic", "Menge": 210},
        {"Name": "mit Granini Orangensaft", "Menge": 260},
        {"Name": "mit Granini Maracujasaft", "Menge": 260},
        {"Name": "mit Granini Apfelsaft klar", "Menge": 260},
        {"Name": "mit Schweppes Wild Berry", "Menge": 210},
        {"Name": "mit Club Mate", "Menge": 260},
        {"Name": "mit Sprudelwasser (Skinny Bitch)", "Menge": 260}
    ]

    Shots = [
        {"Marke": "Berliner Luft", "Sorte": "Pfeffi Shot", "Vol": 18.0, "Menge": 20},
        {"Marke": "Berliner Luft", "Sorte": "Pfeffi Doppelshot", "Vol": 18.0, "Menge": 40},
        {"Marke": "Flimm", "Sorte": "Waldmeister Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Kleiner Feigling", "Sorte": "Original Klopfer", "Vol": 20.0, "Menge": 20},
        {"Marke": "Kleiner Feigling", "Sorte": "Erdbeer Erdbeere", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sourz", "Sorte": "Apple Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sourz", "Sorte": "Blackcurrant Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Ficken", "Sorte": "Johannisbeer-Partyschnaps", "Vol": 15.0, "Menge": 20},
        {"Marke": "Dos Mas", "Sorte": "Mex Shot (Zimt)", "Vol": 15.0, "Menge": 20},
        {"Marke": "Dos Mas", "Sorte": "Pink Shot (Beere)", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sierra Tequila", "Sorte": "Silber Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Sierra Tequila", "Sorte": "Gold Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Ouzo 12", "Sorte": "Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Sambuca Molinari", "Sorte": "Shot", "Vol": 40.0, "Menge": 40},
        {"Marke": "Mexikaner", "Sorte": "Scharfer Tomatenshot (Hausgemacht)", "Vol": 15.0, "Menge": 20},
        {"Marke": "B52", "Sorte": "Schichtshot", "Vol": 28.0, "Menge": 40}
    ]

    drinks = []
    
    for b in Brauereien:
        for s in Sorten_Konfiguration:
            drinks.append([b, s["Sorte"], s["Vol"], s["Menge"]])
            
    for m in Apfelwein_Marken:
        for s in Apfelwein_Sorten:
            drinks.append([m, s["Sorte"], s["Vol"], s["Menge"]])
            
    for sp in Spirituosen:
        for f in Filler:
            gesamtmenge = sp["Menge"] + f["Menge"]
            alk_vol = round((sp["Menge"] * sp["Vol"]) / gesamtmenge, 2)
            sorte_name = f'Longdrink {f["Name"]} ({gesamtmenge}ml)'
            drinks.append([sp["Name"], sorte_name, alk_vol, gesamtmenge])
            
    for s in Shots:
        drinks.append([s["Marke"], s["Sorte"], s["Vol"], s["Menge"]])
        
    return drinks

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

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def get_worksheet(sheet_name):
    sheet = get_gspread_client()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        st.info(f"Tabellenblatt '{sheet_name}' wird erstellt...")
        return sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def _fetch_from_google(sheet_name):
    ws = get_worksheet(sheet_name)
    # Read everything into a dataframe
    # Drop rows where all elements are NaN
    df = get_as_dataframe(ws, evaluate_formulas=True)
    df = df.dropna(how='all')
    
    if df.empty or len(df.columns) == 0:
        return pd.DataFrame(columns=COLUMNS[sheet_name])
        
    return df

@st.cache_data(ttl=15)
def _load_data_internal(sheet_name):
    return _fetch_from_google(sheet_name)

def load_data(sheet_name):
    return _load_data_internal(sheet_name).copy()

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def save_data(sheet_name, df):
    ws = get_worksheet(sheet_name)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False)
    _load_data_internal.clear()

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
            master_drinks = generate_master_drinks()
            drinks_df = pd.DataFrame(master_drinks, columns=COLUMNS[SHEET_GETRAENKE_DB])
            save_data(SHEET_GETRAENKE_DB, drinks_df)

# Run init on app startup
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# --- AUTH HELPERS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_user(username, password, is_hashed=False):
    users_df = load_data(SHEET_USER_DB)
    pwd_hash = password if is_hashed else hash_password(password)
    user = users_df[(users_df['Username'].str.lower() == username.lower()) & (users_df['Password_Hash'] == pwd_hash)]
    if not user.empty:
        st.session_state.logged_in = True
        st.session_state.username = user.iloc[0]['Username']
        st.session_state.role = user.iloc[0]['Rolle']
        st.session_state.gewicht = float(user.iloc[0]['Gewicht_kg'])
        st.session_state.groesse = float(user.iloc[0]['Groesse_cm'])
        st.session_state.geschlecht = user.iloc[0]['Geschlecht']
        return True
    return False

def register_user(username, password, gewicht, groesse, geschlecht, profilbild):
    users_df = load_data(SHEET_USER_DB)
    if not users_df.empty and username.lower() in users_df['Username'].str.lower().values:
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
        st.image("banner.png", use_column_width=True)
    except Exception as e:
        st.markdown("<h1 style='text-align: center;'>🤿 Tauchsportclub<br>Deep Dive Counter</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Registrierung"])
    
    with tab1:
        with st.container(border=True):
            st.subheader("Login")
            with st.form("login_form"):
                l_user = st.text_input("Username", key="l_user", autocomplete="username")
                l_pass = st.text_input("Passwort", type="password", key="l_pass", autocomplete="current-password")
                submitted = st.form_submit_button("Einloggen", use_container_width=True)
                if submitted:
                    if login_user(l_user, l_pass):
                        st.query_params["user"] = l_user
                        st.query_params["hash"] = hash_password(l_pass)
                        import time
                        time.sleep(0.5)
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

def generate_whatsapp_link(username, anzahl, marke, sorte):
    """Generiert einen wa.me-Link mit vorformulierter Nachricht."""
    import urllib.parse
    getraenk_str = f"{anzahl}x {marke} ({sorte})"
    msg = f"🍺 *{username}* hat gerade {getraenk_str} eingebucht! 🥂🎉"
    encoded = urllib.parse.quote(msg)
    return f"https://wa.me/?text={encoded}"

def book_drink_now(marke, sorte, menge, alk_vol, anzahl=1, buchungs_zeit=None):
    if buchungs_zeit is None:
        buchungs_zeit = datetime.datetime.now()
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
    logs_df = pd.concat([logs_df, pd.DataFrame(new_logs)], ignore_index=True)
    save_data(SHEET_KONSUM_LOG, logs_df)
    st.session_state['show_success_popup'] = True
    st.session_state['last_wa_link'] = generate_whatsapp_link(st.session_state.username, anzahl, marke, sorte)
    st.session_state['last_booked_label'] = f"{anzahl}x {marke}"
    st.rerun()

@st.dialog("🍻 Prost!")
def booking_success_popup(wa_link, label):
    st.markdown(f"""
    <div style='text-align:center; padding: 1rem 0;'>
        <div style='font-size: 3rem;'>🎉</div>
        <h2 style='margin: 0.5rem 0; color: #27ae60;'>Erfolgreich eingebucht!</h2>
        <p style='color: #aaa; font-size: 1.1rem;'><strong>{label}</strong> wurde verbucht.</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("❌ Schließen", use_container_width=True):
            st.rerun()
    with col2:
        st.link_button("📲 WhatsApp", wa_link, use_container_width=True, type="primary")

def buchung_view():
    st.title("🍺 Getränke buchen")
    
    # QUICK ACCESS
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username]
    if not my_logs.empty:
        # Get last 5 unique drinks
        recent = my_logs.drop_duplicates(subset=['Marke', 'Sorte'], keep='last').tail(5)
        if not recent.empty:
            st.write("**⚡ Quick-Booking (Nochmal das Gleiche):**")
            cols = st.columns(len(recent))
            for idx, (_, row) in enumerate(recent.iterrows()):
                with cols[idx]:
                    # Format text cleanly in one line to prevent UI breaking
                    btn_text = f"{row['Marke']} {row['Sorte'][:12]}" 
                    if len(btn_text) > 20: btn_text = btn_text[:17] + "..."
                    
                    if st.button(f"⚡ {btn_text}", key=f"qb_{row['Log_ID']}", use_container_width=True, help=f"{row['Marke']} {row['Sorte']}"):
                        book_drink_now(row['Marke'], row['Sorte'], float(row['Menge_ml']), float(row['Alk_Vol']))
            st.divider()
    
    getraenke_df = load_data(SHEET_GETRAENKE_DB)
    drink_options = getraenke_df.apply(lambda r: f"{r['Marke']} {r['Sorte']} ({r['Standard_Menge_ml']}ml)", axis=1).tolist()
    
    tab1, tab2 = st.tabs(["🍻 Aus Datenbank wählen", "➕ Eigenes Getränk anlegen"])
    
    with tab1:
        with st.container(border=True):
            st.write("**Schnellsuche:**")
            search_term = st.text_input("🔍 Suche nach Marke oder Sorte (z.B. Licher, Wodka...)", key="search_drink")
            
            filtered_options = drink_options
            if search_term:
                search_tokens = search_term.lower().split()
                search_nospace = search_term.lower().replace(" ", "")
                
                filtered_options = []
                for d in drink_options:
                    d_lower = d.lower()
                    d_nospace = d_lower.replace(" ", "")
                    # Match if ALL words are in the string (e.g. "paul weiz" -> "Paulaner Weizen")
                    # OR if the string without spaces matches (e.g. "brewdog" -> "Brew Dog")
                    if all(t in d_lower for t in search_tokens) or (search_nospace in d_nospace):
                        filtered_options.append(d)
                
            selected_option = st.selectbox("Was trinkst du?", filtered_options)
            
            anzahl = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_db")
            
            mode = st.radio("Zeitpunkt", ["Jetzt live einbuchen", "Nachtragen"], key="mode_db")
            buchungs_zeit = datetime.datetime.now()
            if mode == "Nachtragen":
                manual_time = st.time_input("Uhrzeit auswählen", key="time_db")
                buchungs_zeit = datetime.datetime.combine(datetime.date.today(), manual_time)
                if buchungs_zeit > datetime.datetime.now():
                    buchungs_zeit -= datetime.timedelta(days=1)
                    
            if st.button("Einlochen 🎯", use_container_width=True, key="btn_db"):
                if not selected_option:
                    st.error("Bitte wähle ein Getränk aus.")
                else:
                    idx = drink_options.index(selected_option)
                    row = getraenke_df.iloc[idx]
                    marke = row['Marke']
                    sorte = row['Sorte']
                    menge = row['Standard_Menge_ml']
                    alk_vol = row['Alkoholgehalt_Vol']
                    
                    book_drink_now(marke, sorte, menge, alk_vol, anzahl, buchungs_zeit)
            
            # Popup nach Buchung
            if st.session_state.pop('show_success_popup', False):
                booking_success_popup(
                    st.session_state.pop('last_wa_link', '#'),
                    st.session_state.pop('last_booked_label', 'Getränk')
                )

    with tab2:
        with st.container(border=True):
            st.write("Ist dein Getränk nicht in der Liste? Lege es hier einmalig an:")
            col1, col2 = st.columns(2)
            with col1:
                marke = st.text_input("Marke/Name", key="m_marke")
                menge = st.number_input("Menge (ml)", min_value=10, max_value=2000, step=10, value=330, key="m_menge")
            with col2:
                sorte = "Manuell"
                alk_vol = st.number_input("Alkoholgehalt (Vol%)", min_value=0.0, max_value=100.0, step=0.1, value=5.0, key="m_alk")
                
            anzahl2 = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_m")
            mode2 = st.radio("Zeitpunkt", ["Jetzt live einbuchen", "Nachtragen"], key="mode_m")
            buchungs_zeit2 = datetime.datetime.now()
            if mode2 == "Nachtragen":
                manual_time2 = st.time_input("Uhrzeit auswählen", key="time_m")
                buchungs_zeit2 = datetime.datetime.combine(datetime.date.today(), manual_time2)
                if buchungs_zeit2 > datetime.datetime.now():
                    buchungs_zeit2 -= datetime.timedelta(days=1)
                    
            if st.button("Trinken & für alle Speichern 🎯", use_container_width=True, key="btn_m"):
                if not marke:
                    st.error("Bitte eine Marke/einen Namen eintragen.")
                else:
                    new_drink = pd.DataFrame([{
                        "Marke": marke, "Sorte": sorte, "Alkoholgehalt_Vol": alk_vol, "Standard_Menge_ml": menge
                    }])
                    getraenke_df = pd.concat([getraenke_df, new_drink], ignore_index=True)
                    save_data(SHEET_GETRAENKE_DB, getraenke_df)
                    
                    book_drink_now(marke, sorte, menge, alk_vol, anzahl2, buchungs_zeit2)
            
            # Popup nach manueller Buchung
            if st.session_state.pop('show_success_popup', False):
                booking_success_popup(
                    st.session_state.pop('last_wa_link', '#'),
                    st.session_state.pop('last_booked_label', 'Getränk')
                )

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

def statistik_view():
    if st.session_state.get('view_profile_of'):
        public_profile_view(st.session_state.view_profile_of)
        return
        
    st.title("🏆 Statistiken")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    
    if logs_df.empty:
        st.info("Noch keine Daten vorhanden.")
        return
        
    stats_data = []
    for _, user_row in users_df.iterrows():
        uname = user_row['Username']
        user_logs = logs_df[logs_df['Username'] == uname]
        
        gesamt_getraenke = len(user_logs)
        if gesamt_getraenke == 0:
            continue
            
        total_ml = pd.to_numeric(user_logs['Menge_ml'], errors='coerce').sum()
        gesamt_liter = round(total_ml / 1000, 2)
        
        user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
        now = pd.Timestamp.now()
        first_drink_date = user_logs['Zeitstempel'].min()
        days_active = (now - first_drink_date).days + 1
        avg_per_day = round(gesamt_getraenke / max(1, days_active), 2)
        
        daily_counts_raw = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size()
        best_day_count = daily_counts_raw.max() if not daily_counts_raw.empty else 0
        
        promille = calc_promille(uname)
        fav_drink = user_logs['Marke'].value_counts().idxmax()
        
        stats_data.append({
            "Taucher": uname,
            "Getränke": gesamt_getraenke,
            "Ø pro Tag": avg_per_day,
            "Bester Tag": best_day_count,
            "Volumen (L)": gesamt_liter,
            "Fav. Drink": fav_drink,
            "Live Pegel (‰)": promille
        })
        
    if not stats_data:
        st.info("Noch keine Getränke verbucht.")
        return
        
    stats_df = pd.DataFrame(stats_data)
    stats_df = stats_df.sort_values(by="Getränke", ascending=False).reset_index(drop=True)
    
    if not stats_df.empty:
        winner = stats_df.iloc[0]
        winner_name = winner['Taucher']
        winner_row = users_df[users_df['Username'] == winner_name].iloc[0]
        pic = winner_row['Profilbild_Url']
        
        with st.container(border=True):
            col1, col2 = st.columns([0.15, 0.85])
            with col1:
                if pic.startswith("data:image"):
                    st.markdown(f'<img src="{pic}" style="border-radius: 50%; width: 50px; height: 50px; object-fit: cover;">', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span style="font-size: 40px;">{pic}</span>', unsafe_allow_html=True)
            with col2:
                st.success(f"👑 **All-Time King:** Wir verneigen uns vor **{winner_name}** mit unfassbaren **{winner['Getränke']} Drinks** ({winner['Volumen (L)']} Liter)! Prost! 🍻")
            
            if st.button(f"🔍 Öffne das Profil von {winner_name}", use_container_width=True):
                st.session_state.view_profile_of = winner_name
                st.rerun()
    
    stats_df.index = stats_df.index + 1
    stats_df.index.name = "Rang"
    stats_df = stats_df.reset_index()
    
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

def public_profile_view(uname):
    st.button("🔙 Zurück zur Übersicht", on_click=lambda: st.session_state.pop('view_profile_of', None))
    
    st.title(f"Profil von {uname}")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    
    user_row = users_df[users_df['Username'] == uname]
    if user_row.empty:
        st.error("Benutzer nicht gefunden.")
        return
        
    pic = user_row.iloc[0]['Profilbild_Url']
    p_val = calc_promille(uname)
    
    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        if pic.startswith("data:image"):
            st.markdown(f'<img src="{pic}" style="border-radius: 50%; width: 100px; height: 100px; object-fit: cover;">', unsafe_allow_html=True)
        else:
            st.markdown(f"<h1 style='margin:0;'>{pic}</h1>", unsafe_allow_html=True)
    with col2:
        st.write(f"**Aktueller Promillewert:** {p_val} ‰")
        user_logs = logs_df[logs_df['Username'] == uname].copy()
        if not user_logs.empty:
            fav_drink = user_logs['Marke'].value_counts().idxmax()
            st.write(f"**Lieblingsgetränk:** {fav_drink}")
    
    st.divider()
    
    if user_logs.empty:
        st.info("Noch keine Getränke verbucht.")
        return
        
    user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
    now = pd.Timestamp.now()
    
    all_time = len(user_logs)
    this_year = len(user_logs[user_logs['Zeitstempel'].dt.year == now.year])
    this_month = len(user_logs[(user_logs['Zeitstempel'].dt.year == now.year) & (user_logs['Zeitstempel'].dt.month == now.month)])
    
    start_of_week = now - pd.to_timedelta(now.dayofweek, unit='d')
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    this_week = len(user_logs[user_logs['Zeitstempel'] >= start_of_week])
    
    first_drink_date = user_logs['Zeitstempel'].min()
    days_active = (now - first_drink_date).days + 1
    avg_per_day = round(all_time / max(1, days_active), 2)
    avg_per_active_day = round(user_logs.groupby(user_logs['Zeitstempel'].dt.date).size().mean(), 2)
    daily_counts_raw = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size()
    best_day_count = daily_counts_raw.max() if not daily_counts_raw.empty else 0
    
    total_ml = pd.to_numeric(user_logs['Menge_ml'], errors='coerce').sum()
    total_liters = round(total_ml / 1000, 2)
    
    st.subheader("📊 Trink-Statistiken")
    c1, c2, c3, c_vol = st.columns(4)
    c1.metric("All-Time", f"{all_time}")
    c2.metric("Dieses Jahr", f"{this_year}")
    c3.metric("Dieser Monat", f"{this_month}")
    c_vol.metric("Volumen", f"{total_liters} L")
    
    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Diese Woche", f"{this_week}")
    c5.metric("Ø pro Tag (Gesamt)", f"{avg_per_day}")
    c6.metric("Ø pro Party-Tag", f"{avg_per_active_day}")
    c7.metric("Bester Tag", f"{best_day_count}")
    
    st.divider()
    st.subheader("📈 Getränke über die Zeit")
    
    daily_counts = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size().reset_index(name='Getränke')
    daily_counts = daily_counts.set_index('Zeitstempel')
    
    st.bar_chart(daily_counts)
    
    st.divider()
    st.subheader("📜 Buchungs-Historie")
    display_logs = user_logs[['Zeitstempel', 'Marke', 'Sorte', 'Menge_ml']].copy()
    display_logs = display_logs.sort_values(by='Zeitstempel', ascending=False)
    st.dataframe(display_logs, hide_index=True, use_container_width=True)

def social_view():
    if st.session_state.get('view_profile_of'):
        public_profile_view(st.session_state.view_profile_of)
        return
        
    st.title("Live")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    

    
    active_users = []
    sober_users = []
    
    for idx, user_row in users_df.iterrows():
        uname = user_row['Username']
        p_val = calc_promille(uname)
        user_logs = logs_df[logs_df['Username'] == uname]
        
        user_data = {
            "uname": uname,
            "pic": user_row['Profilbild_Url'],
            "p_val": p_val,
            "user_logs": user_logs
        }
        if p_val > 0.0:
            active_users.append(user_data)
        else:
            sober_users.append(user_data)
            
    def render_user_cards(users_list, is_knuelle=True):
        if not users_list:
            st.write("Niemand in dieser Kategorie.")
            return
            
        for i, u in enumerate(users_list):
            uname = u["uname"]
            pic = u["pic"]
            p_val = u["p_val"]
            user_logs = u["user_logs"]
            
            fav_drink = "-"
            if not user_logs.empty:
                fav_drink = user_logs['Marke'].value_counts().idxmax()
                
            if pic.startswith("data:image"):
                img_html = f'<img src="{pic}" style="border-radius: 50%; width: 40px; height: 40px; object-fit: cover; margin-right: 10px;">'
            else:
                img_html = f'<span style="font-size: 26px; margin-right: 8px;">{pic}</span>'
                
            is_active = False
            if not user_logs.empty:
                user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
                last_drink_time = user_logs['Zeitstempel'].max()
                now = pd.Timestamp.now()
                diff = now - last_drink_time
                if diff.total_seconds() <= 30 * 60:
                    is_active = True
                    
            status_badge = '<span style="color: #28a745; font-size: 0.7em; margin-left: auto; font-weight: bold;">🟢 Aktiv</span>' if is_active else '<span style="color: #6c757d; font-size: 0.7em; margin-left: auto;">⚪ Inaktiv</span>'
            
            border_color = "#ff4b4b" if is_knuelle else "#4b8bff"
            bg_color = "#1e1e1e"
            
            card_html = f"""
            <div style="background-color: {bg_color}; padding: 12px; border-radius: 8px; border-left: 5px solid {border_color}; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                <div style="display:flex; align-items:center; margin-bottom: 6px;">
                    {img_html}
                    <strong style="font-size:1.1em; color: #ffffff;">{uname}</strong>
                    {status_badge}
                </div>
                <div style="font-size: 0.85em; color: #aaaaaa; line-height: 1.4;">
                    <span style="background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; margin-right: 5px;"><b>P:</b> <span style="color:{border_color}; font-weight:bold;">{p_val}‰</span></span>
                    <span style="background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;"><b>Fav:</b> {fav_drink}</span>
                </div>
            </div>
            """
            
            st.markdown(card_html, unsafe_allow_html=True)
            
            if st.button("📊 Profil", key=f"btn_{uname}", use_container_width=True):
                st.session_state.view_profile_of = uname
                st.rerun()

    st.subheader("Knülle (> 0.0 ‰)")
    active_users = sorted(active_users, key=lambda x: x['p_val'], reverse=True)
    render_user_cards(active_users, is_knuelle=True)
    
    st.divider()
    
    # --- LIVE FEED & TAGES RANGLISTE ---
    recent_logs = logs_df.copy()
    if not recent_logs.empty:
        col_feed, col_today = st.columns(2)
        recent_logs['Zeitstempel'] = pd.to_datetime(recent_logs['Zeitstempel'])
        now = pd.Timestamp.now()
        
        with col_feed:
            st.write("**Letzte Buchungen**")
            feed_logs = recent_logs.sort_values(by='Zeitstempel', ascending=False).head(100)
            with st.container(height=150):
                for _, r in feed_logs.iterrows():
                    diff = now - r['Zeitstempel']
                    mins = int(diff.total_seconds() // 60)
                    st.markdown(f"**{r['Username']}** trank **{r['Marke']}** <small style='color:gray;'>(vor {mins}m)</small>", unsafe_allow_html=True)
                    
        with col_today:
            st.write("**Heute getrunken**")
            today_logs = recent_logs[recent_logs['Zeitstempel'].dt.date == now.date()]
            with st.container(height=150):
                if not today_logs.empty:
                    daily_board = today_logs.groupby('Username').size().reset_index(name='Anzahl')
                    daily_board = daily_board.sort_values(by='Anzahl', ascending=False).reset_index(drop=True)
                    for i, row in daily_board.iterrows():
                        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "🔹"))
                        st.markdown(f"{medal} **{row['Username']}**: {row['Anzahl']} Drinks")
                else:
                    st.write("Noch keine Getränke heute.")
                    
    st.divider()
    
    st.subheader("Nüchtern (0.0 ‰)")
    render_user_cards(sober_users, is_knuelle=False)



def admin_view():
    st.title("🛠️ Admin-Bereich")
    
    if st.session_state.role != "Admin":
        st.error("Zugriff verweigert.")
        return
        
    st.subheader("Globales Log (Heute)")
    logs_df = load_data(SHEET_KONSUM_LOG)
    st.dataframe(logs_df, use_container_width=True)
    
    with st.container(border=True):
        st.markdown("<h3>🍻 Erweiterte Getränke-Matrix Importieren</h3>", unsafe_allow_html=True)
        st.write("Fügt die große Liste an internationalen Bieren und Weinen zur Datenbank hinzu.")
        if st.button("Jetzt Getränke-Erweiterung importieren"):
            neue_brauereien_int = [
                "Pilsner Urquell", "Budweiser Budvar", "Staropramen", "Krušovice", "Gambrinus",
                "Stella Artois", "Leffe (Blond/Bruin)", "Chouffe", "Duvel", "Grimbergen", 
                "Hoegaarden", "Chimay", "Delirium Tremens", "Kastel Beer",
                "John Smith's", "Newcastle Brown Ale", "London Pride", "Sharp's Doom Bar", 
                "BrewDog (Punk IPA)", "Stiegl", "Zipfer", "Ottakringer", "Gösser", "Puntigamer", 
                "Wieselburger", "Feldschlösschen", "Calanda", "Quöllfrisch", "Amstel", "Grolsch", 
                "Bavaria", "Hertog Jan", "Diekirch", "Bofferding", "Kronenbourg 1664", "Pelforth", 
                "Fischer", "San Miguel", "Estrella Damm", "Cruzcampo", "Mahou", "Alhambra", 
                "Super Bock", "Sagres", "Peroni (Nastro Azzurro)", "Moretti", "Ichnusa", "Messina", 
                "Carlsberg", "Tuborg", "Mikkeller", "Lapin Kulta", "Norrlands Guld", "Saku", 
                "Švyturys", "Miller Genuine Draft", "Coors Light", "Samuel Adams", "Brooklyn Brewery", 
                "Asahi Super Dry", "Sapporo", "Tsingtao", "Tiger Beer", "Singha", "Chang", "Quilmes"
            ]

            neue_brauereien_int.extend([
                "Bernard", "Kozel", "Zubr", "Tyskie", "Żywiec", "Lech", "Warka", "Okocim", 
                "Jupiler", "Brugse Zot", "Duchesse de Bourgogne", "Westmalle", "Rochefort", "Orval",
                "La Trappe", "Hertog Jan Weizener", "Gulpener", "Bavaria 8.6",
                "Eggenberg", "Murauer", "Schremser", "Hirter", "Schützengarten", "Chopfab",
                "Carling", "Tennent's", "Hobgoblin", "Beavertown", "Fuller's", "Smithwick's",
                "Estrella Galicia", "Moritz", "Ambar", "Sagres Bohemia", "Baladin", "Birra Moretti La Rossa",
                "Lapin Kulta", "Norrlands Guld", "Pelforth", "Fischer", "3 Fonteinen", "Põhjala",
                "Svijany", "Regent", "Zlatý Bažant (Slowakei)", "Šariš", "Kaper", "Lwówek", "Namysłów",
                "La Chouffe Blonde", "Mc Chouffe", "Duvel Tripel Hop", "Karmeliet Tripel", "Kwak",
                "St. Bernardus", "Tongerlo", "Affligem", "Delirium Red", "Lindemans (Kriek/Lambic)",
                "Heineken Silver", "Brand Brauerei", "Texels Skuumkoppe", "Jopen",
                "Gösser Stiftsbräu", "Murauer Märzen", "Villacher", "Fohrenburger", "Eggenberg Urbock",
                "Eichhof", "Appenzeller Bier", "Chopfab Hell", "Boxer Bier",
                "Guinness Hop House 13", "Kilkenny Irish Red Ale", "Carling Black Label", "Belhaven",
                "Samuel Smith's Taddy Porter", "Fuller's London Pride", "Sharp's Atlantic Pale Ale",
                "Estrella Damm Inedit", "Alhambra Reserva 1925", "Super Bock Stout", "Sagres Preta",
                "Birra Moretti Autentica", "Peroni Gran Riserva", "Ichnusa Non Filtrata", "Mythos (Griechenland)", "Fix",
                "Tuborg Grøn", "Carlsberg Elephant", "Mikkeller Peter, Pale and Mary", "AASS (Norwegen)",
                "Mack", "Karhu (Finnland)", "Olvi", "Aldaris (Lettland)", "Kalnapilis (Litauen)", "Kronenbourg Blanc"
            ])

            brauereien_de_extra = [
                "Schlenkerla (Bamberg)", "Andechs", "Weltenburger Kloster", "Riegele", "FrauGruber",
                "Felsgold", "Wernesgrüner", "Brinkhoff's", "Dortmunder Kronen", "Stauder", 
                "König Ludwig", "Allgäuer Brauhaus", "Alpirsbacher", "Distelhäuser", "Hochstift", 
                "Gessner", "Köthener", "Freiberger", "Lausitzer Porter", "Würzburger Hofbräu",
                "Tucher", "Grüner", "Schanzenbräu", "Karg", "Unertl", "Kneitinger", "Spital",
                "Weltenburger", "Arcobräu", "Graf Arco", "Falter", "Eichbaum", "Welser",
                "Gaffel Wiess", "Peters Kölsch", "Sion Kölsch", "Mühlen Kölsch", "Dom Kölsch",
                "Bolten Alt", "Schlüssel Alt", "Schumacher Alt", "Kürzer Alt", "Hannen Alt"
            ]

            brauereien_de_extra.extend([
                "Guxhavener", "Störtebeker", "Dithmarscher", "Herforder", "Barre", "Veltins Grevensteiner",
                "Hasseröder", "Freiberger", "Radeberger Brauerei", "Feldschlößchen (Dresden)", "Wernesgrüner",
                "Augustiner Maximator", "Tegernseer Max I. Joseph", "König Ludwig Dunkel", "Hacker-Pschorr Kellerbier",
                "Kulmbacher Edelherb", "Kapuziner (Weizen)", "Mönchshof Kellerbier", "Schanzenbräu Kehlkopf",
                "Maisel & Friends", "Crew Republic", "Kambium", "Hanscraft", "Tilmans Biere",
                "Gutmann (Weizen)", "Kuchlbauer", "Schneider Weisse Aventinus", "Schlenkerla Rauchbier Fastenbier",
                "Ayinger Celebrator", "Felsenkeller", "Pyraser", "Kaufbeuren Buron", "Zirndorfer",
                "Glaabsbräu", "Schmucker", "Pfungstädter", "Michelstädter Brauhaus", "Brauhaus Faust", 
                "Krone (Darmstadt)", "Eichbaum Ureich", "Brauhaus Knallhütte", "Hochstift Pils",
                "Schöfferhofer Weizen", "Zunft Kölsch", "Sester Kölsch", "Küppers Kölsch",
                "Uerige Sticke", "Brauerei zum Schlüssel", "Diebels Alt", "Frankenheim Alt"
            ])
            
            sorten_de = [
                {"Sorte": "Pils (0.33l)", "Vol": 4.8, "Menge": 330},
                {"Sorte": "Pils (0.5l)", "Vol": 4.8, "Menge": 500},
                {"Sorte": "Helles (0.5l)", "Vol": 5.0, "Menge": 500},
                {"Sorte": "Export (0.5l)", "Vol": 5.2, "Menge": 500},
                {"Sorte": "Hefe-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
                {"Sorte": "Kristall-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
                {"Sorte": "Dunkelbier (0.5l)", "Vol": 5.1, "Menge": 500},
                {"Sorte": "Radler (0.33l)", "Vol": 2.5, "Menge": 330},
                {"Sorte": "Radler (0.5l)", "Vol": 2.5, "Menge": 500},
                {"Sorte": "Alkoholfrei (0.33l)", "Vol": 0.0, "Menge": 330},
                {"Sorte": "Alkoholfrei (0.5l)", "Vol": 0.0, "Menge": 500}
            ]

            neue_sorten_int = [
                {"Sorte": "Lager / Pils", "Vol": 5.0, "Menge": 330, "Preis": 3.00},
                {"Sorte": "Pale Ale / IPA", "Vol": 6.2, "Menge": 330, "Preis": 3.80},
                {"Sorte": "Belgian Blonde / Wit", "Vol": 6.6, "Menge": 330, "Preis": 4.00},
                {"Sorte": "Stout / Porter", "Vol": 4.5, "Menge": 440, "Preis": 3.50},
                {"Sorte": "Apple Cider", "Vol": 4.5, "Menge": 500, "Preis": 3.50},
                {"Sorte": "Strong Ale (Triple)", "Vol": 8.5, "Menge": 330, "Preis": 4.50}
            ]

            neue_wein_sorten = [
                {"Marke": "Hauswein Weiß", "Kategorie": "Weißwein (Standard)", "Vol": 12.0},
                {"Marke": "Hauswein Rot", "Kategorie": "Rotwein (Standard)", "Vol": 13.0},
                {"Marke": "Hauswein Rosé", "Kategorie": "Roséwein (Standard)", "Vol": 12.0},
                {"Marke": "Sekt (Hausmarke)", "Kategorie": "Schaumwein (Standard)", "Vol": 11.0},
                {"Marke": "Prosecco (Hausmarke)", "Kategorie": "Schaumwein (Standard)", "Vol": 10.5},
                {"Marke": "Glühwein", "Kategorie": "Heißgetränk", "Vol": 10.5},
                {"Marke": "Grauburgunder", "Kategorie": "Weißwein", "Vol": 12.5},
                {"Marke": "Riesling", "Kategorie": "Weißwein", "Vol": 12.0},
                {"Marke": "Chardonnay", "Kategorie": "Weißwein", "Vol": 13.0},
                {"Marke": "Sauvignon Blanc", "Kategorie": "Weißwein", "Vol": 12.5},
                {"Marke": "Primitivo", "Kategorie": "Rotwein", "Vol": 13.5},
                {"Marke": "Merlot", "Kategorie": "Rotwein", "Vol": 13.0},
                {"Marke": "Cabernet Sauvignon", "Kategorie": "Rotwein", "Vol": 14.0},
                {"Marke": "Provence Rosé", "Kategorie": "Roséwein", "Vol": 12.5},
                {"Marke": "Rotkäppchen Sekt", "Kategorie": "Sekt", "Vol": 11.0},
                {"Marke": "Moët & Chandon", "Kategorie": "Champagner", "Vol": 12.0}
            ]

            neue_wein_formen = [
                {"Typ": "Glas (klein/0.2l)", "Menge": 200, "Preis": 4.00, "Vol_Anpassung": 1.0},
                {"Typ": "Glas (groß/0.25l)", "Menge": 250, "Preis": 5.00, "Vol_Anpassung": 1.0},
                {"Typ": "Flasche (0.75l)", "Menge": 750, "Preis": 15.00, "Vol_Anpassung": 1.0},
                {"Typ": "Weinschorle Sauer (0.4l)", "Menge": 400, "Preis": 3.50, "Vol_Anpassung": 0.5},
                {"Typ": "Weinschorle Süß (0.4l)", "Menge": 400, "Preis": 3.50, "Vol_Anpassung": 0.5}
            ]

            new_drinks = []
            
            # Internationale Biere kombinieren
            for b in neue_brauereien_int:
                for s in neue_sorten_int:
                    new_drinks.append({
                        "Marke": b,
                        "Sorte": s["Sorte"],
                        "Alkoholgehalt_Vol": round(s["Vol"], 2),
                        "Standard_Menge_ml": s["Menge"]
                    })
                    
            # Deutsche Biere kombinieren
            for b in brauereien_de_extra:
                for s in sorten_de:
                    new_drinks.append({
                        "Marke": b,
                        "Sorte": s["Sorte"],
                        "Alkoholgehalt_Vol": round(s["Vol"], 2),
                        "Standard_Menge_ml": s["Menge"]
                    })
                    
            # Weine kombinieren
            for w in neue_wein_sorten:
                for d in neue_wein_formen:
                    calc_vol = w["Vol"] * d["Vol_Anpassung"]
                    new_drinks.append({
                        "Marke": w["Marke"],
                        "Sorte": f'{w["Kategorie"]} - {d["Typ"]}',
                        "Alkoholgehalt_Vol": round(calc_vol, 2),
                        "Standard_Menge_ml": d["Menge"]
                    })
            
            df = load_data(SHEET_GETRAENKE_DB)
            df_new = pd.DataFrame(new_drinks)
            df_combined = pd.concat([df, df_new], ignore_index=True)
            
            # Nur echte Duplikate löschen, alte Sachen unberührt lassen! keep='first' erhält die alten
            df_combined.drop_duplicates(subset=["Marke", "Sorte", "Standard_Menge_ml"], keep="first", inplace=True)
            
            # Alphabetisch sortieren nach Marke
            df_combined.sort_values(by=["Marke", "Sorte"], inplace=True)
            
            save_data(SHEET_GETRAENKE_DB, df_combined)
            st.success("Erweiterung erfolgreich importiert! Die alten Daten sind sicher und alles ist alphabetisch sortiert.")
            
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

def profil_view():
    st.title("👤 Mein Profil")
    users_df = load_data(SHEET_USER_DB)
    user_row = users_df[users_df['Username'] == st.session_state.username]
    if user_row.empty:
        st.error("Profil nicht gefunden.")
        return
        
    user_idx = user_row.index[0]
    curr_data = user_row.iloc[0]
    
    tab_data, tab_pw = st.tabs(["Profildaten ändern", "Passwort ändern"])
    
    with tab_data:
        with st.form("profil_form"):
            new_gew = st.number_input("Gewicht (kg)", min_value=30.0, max_value=200.0, value=float(curr_data['Gewicht_kg']))
            new_groesse = st.number_input("Größe (cm)", min_value=120, max_value=230, value=int(curr_data['Groesse_cm']))
            
            st.write("Aktuelles Profilbild:")
            if str(curr_data['Profilbild_Url']).startswith("data:image"):
                st.markdown(f'<img src="{curr_data["Profilbild_Url"]}" style="border-radius: 50%; width: 60px; height: 60px; object-fit: cover;">', unsafe_allow_html=True)
            else:
                st.write(curr_data['Profilbild_Url'])
                
            st.write("Neues Profilbild auswählen oder hochladen:")
            r_pic_emoji = st.selectbox("Emoji-Avatar", ["Beibehalten", "🤿", "🦈", "🐙", "🍺", "🍹", "🐋"])
            r_pic_file = st.file_uploader("Oder neues Bild hochladen", type=["jpg", "jpeg", "png"])
            
            if st.form_submit_button("Profil speichern"):
                profilbild = curr_data['Profilbild_Url']
                if r_pic_emoji != "Beibehalten":
                    profilbild = r_pic_emoji
                    
                if r_pic_file is not None:
                    try:
                        img = Image.open(r_pic_file)
                        img.thumbnail((150, 150))
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=70)
                        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                        profilbild = f"data:image/jpeg;base64,{encoded}"
                    except:
                        st.warning("Fehler beim Bild-Upload.")
                
                users_df.at[user_idx, 'Gewicht_kg'] = new_gew
                users_df.at[user_idx, 'Groesse_cm'] = new_groesse
                users_df.at[user_idx, 'Profilbild_Url'] = profilbild
                save_data(SHEET_USER_DB, users_df)
                st.success("Profil erfolgreich aktualisiert!")
                
    with tab_pw:
        with st.form("pw_form"):
            old_pw = st.text_input("Altes Passwort", type="password")
            new_pw = st.text_input("Neues Passwort", type="password")
            new_pw2 = st.text_input("Neues Passwort bestätigen", type="password")
            
            if st.form_submit_button("Passwort ändern"):
                if not old_pw or not new_pw:
                    st.error("Bitte alle Felder ausfüllen.")
                elif new_pw != new_pw2:
                    st.error("Die neuen Passwörter stimmen nicht überein.")
                elif hashlib.sha256(old_pw.encode()).hexdigest() != curr_data['Password_Hash']:
                    st.error("Altes Passwort ist falsch.")
                else:
                    users_df.at[user_idx, 'Password_Hash'] = hashlib.sha256(new_pw.encode()).hexdigest()
                    save_data(SHEET_USER_DB, users_df)
                    st.success("Passwort erfolgreich geändert!")

# --- MAIN LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    
    # Try autologin via secure URL parameters
    saved_user = st.query_params.get("user")
    saved_hash = st.query_params.get("hash")
    if saved_user and saved_hash:
        login_user(saved_user, saved_hash, is_hashed=True)

if not st.session_state.logged_in:
    login_view()
else:
    try:
        st.image("banner.png", use_column_width=True)
    except Exception as e:
        pass
        
    # Top Navigation Bar
    col_nav, col_logout = st.columns([0.85, 0.15])
    with col_nav:
        st.write(f"Willkommen, **{st.session_state.username}** 🤿")
    with col_logout:
        if st.button("Logout", use_container_width=True):
            if "user" in st.query_params:
                del st.query_params["user"]
            if "hash" in st.query_params:
                del st.query_params["hash"]
            st.session_state.logged_in = False
            st.rerun()
            
    menu = ["Live", "Getränke buchen", "Statistiken", "Mein Profil"]
    icons = ["people", "cup-hot", "bar-chart-line", "person"]
    if st.session_state.role == "Admin":
        menu.append("Admin-Bereich")
        icons.append("gear")
        
    choice = option_menu(
        menu_title=None,
        options=menu,
        icons=icons,
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "margin-bottom": "1rem"},
            "icon": {"font-size": "18px"},
            "nav-link": {"font-size": "15px", "text-align": "center", "margin": "0px", "--hover-color": "#4b4b4b"},
            "nav-link-selected": {"background-color": "#ff4b4b"},
        }
    )
            
    # Route to views
    if choice == "Getränke buchen":
        buchung_view()
    elif choice == "Statistiken":
        statistik_view()
    elif choice == "Live":
        social_view()
    elif choice == "Mein Profil":
        profil_view()
    elif choice == "Admin-Bereich":
        admin_view()

